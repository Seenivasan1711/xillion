"""
Leg-failure protocol (CP11 / automation-platform-spec E05). Indian brokers
don't support atomic multi-leg execution -- a spread is N independent orders
that can partially fill. Flagged in the spec as "the single most dangerous
part of the system": getting this wrong is how a strategy ends up naked
short by accident. This module is what stands between a rejected leg and an
unbounded position.

Deliberately broker-agnostic: it drives `place_order_fn`/`cancel_order_fn`/
`get_order_fn`, which the caller binds to StrategyContext.place_order/
cancel_order/get_order -- so every leg still passes through the normal risk
gate, position tracking, and DB persistence, one leg at a time.

**2026-08-29, building the iron condor (the first 4-leg consumer) surfaced
two real bugs that the credit spread's 2-leg shape could never expose:**

1. The original `_execute` stopped attempting legs after the FIRST failure,
   even on entry, where an unrelated pair further down the sequence (e.g.
   the put side of a condor when the call side's long leg failed) should
   still be attempted independently. For exactly 2 legs this was invisible
   (there was nothing left to attempt after leg 2 anyway) but for 3+ legs
   it silently reported SUCCESS with legs that were never even placed, or
   UNWOUND without ever having tried the independent pair. Fixed: `_execute`
   now walks the full ordered sequence, skipping (not attempting) only a
   leg whose own dependency already failed -- see `_blocked_by_dependency`.
2. The naked-short "force unwind" reversal only makes sense on ENTRY
   (undo a newly-created naked position by closing it). Applied to an EXIT
   failure -- short's close succeeds, long's close then fails -- the old
   code would REVERSE the short's already-successful close, i.e. re-sell
   it, recreating the exact naked short the whole protocol exists to
   prevent. This was a latent bug in the 2-leg case too (nothing ever
   tested a leg failing partway through an EXIT). Fixed: `_rollback` now
   handles `is_exit` as its own case -- nothing is ever reversed on a
   failed exit, since whatever's in `filled` is legitimately closed
   already; the only problem is what's still open, which halts for human
   review rather than getting "reversed" into a new position.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

import structlog

from xillion.core.events import Order, OrderRequest, OrderStatus, OrderType, Side
from xillion.core.multileg import (
    Leg,
    LegRole,
    MultiLegSpec,
    order_entry_sequence,
    order_exit_sequence,
)

logger = structlog.get_logger(__name__)

PlaceOrderFn = Callable[[OrderRequest], Awaitable[Order]]
CancelOrderFn = Callable[[str], Awaitable[bool]]
GetOrderFn = Callable[[str], Awaitable[Order | None]]

_TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
_OPEN = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.ACCEPTED}


class ExecutionOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FORCE_UNWOUND = "FORCE_UNWOUND"  # naked short detected -> unwound at market immediately
    UNWOUND = "UNWOUND"  # defined-risk partial, retry failed -> unwound cleanly
    HALTED_FOR_HUMAN = "HALTED_FOR_HUMAN"  # unclassifiable partial -- do not touch it automatically


@dataclass
class LegFill:
    leg: Leg
    order: Order


@dataclass
class ExecutionResult:
    outcome: ExecutionOutcome
    fills: list[LegFill] = field(default_factory=list)
    failed_legs: list[Leg] = field(default_factory=list)
    message: str = ""

    @property
    def success(self) -> bool:
        return self.outcome == ExecutionOutcome.SUCCESS


def _reverse_side(side: Side) -> Side:
    return Side.SELL if side == Side.BUY else Side.BUY


class MultiLegExecutor:
    """One instance per strategy context (cheap, stateless between calls)."""

    def __init__(
        self,
        place_order_fn: PlaceOrderFn,
        cancel_order_fn: CancelOrderFn,
        get_order_fn: GetOrderFn | None = None,
        *,
        fill_timeout_sec: float = 5.0,
        poll_interval_sec: float = 0.2,
        min_partial_ratio: Decimal = Decimal("0.5"),
        alert_fn: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._place_order = place_order_fn
        self._cancel_order = cancel_order_fn
        self._get_order = get_order_fn
        self._fill_timeout_sec = fill_timeout_sec
        self._poll_interval_sec = poll_interval_sec
        self._min_partial_ratio = min_partial_ratio
        self._alert = alert_fn

    async def _alert_p0(self, title: str, body: str) -> None:
        logger.critical(title, detail=body)
        if self._alert is not None:
            try:
                await self._alert(title, body)
            except Exception as exc:  # alerting must never break the protocol itself
                logger.error("multileg executor: alert_fn raised", error=str(exc))

    async def _wait_for_fill(self, order: Order) -> Order:
        """Order comes back already terminal from paper/backtest brokers
        (synchronous fills); a real broker connection may still be
        SUBMITTED/ACCEPTED, so poll get_order_fn until terminal or timeout."""
        if order.status in _TERMINAL or self._get_order is None:
            return order
        elapsed = 0.0
        current = order
        while elapsed < self._fill_timeout_sec:
            await asyncio.sleep(self._poll_interval_sec)
            elapsed += self._poll_interval_sec
            latest = await self._get_order(order.client_order_id)
            if latest is not None:
                current = latest
                if current.status in _TERMINAL:
                    return current
        return current  # timed out, still open -- caller treats as a failure

    async def _attempt_leg(self, leg: Leg, tag: str | None) -> LegFill | None:
        """Places one leg's order and waits for it to resolve. Returns a
        LegFill if it counts as filled (fully, or partially at/above
        min_partial_ratio -- cancelling any leftover open remainder either
        way), or None on REJECTED / a weak partial / stuck-open-past-
        timeout (having already cancelled whatever's left of it)."""
        request = OrderRequest(
            symbol=leg.symbol,
            side=leg.side,
            quantity=leg.quantity,
            order_type=leg.order_type,
            price=leg.price,
            tag=tag,
        )
        order = await self._place_order(request)
        order = await self._wait_for_fill(order)

        if order.status == OrderStatus.FILLED:
            return LegFill(leg=leg, order=order)

        if order.status == OrderStatus.PARTIAL:
            ratio = Decimal(order.filled_quantity) / Decimal(leg.quantity)
            if order.broker_order_id:
                await self._cancel_order(order.client_order_id)
            if ratio >= self._min_partial_ratio:
                return LegFill(leg=leg, order=order)
            return None

        # REJECTED, or still open (PENDING/SUBMITTED/ACCEPTED) after timeout
        if order.status in _OPEN and order.broker_order_id:
            await self._cancel_order(order.client_order_id)
        return None

    async def execute_entry(self, spec: MultiLegSpec, tag: str | None = None) -> ExecutionResult:
        return await self._execute(spec, order_entry_sequence(spec), tag, is_exit=False)

    async def execute_exit(self, spec: MultiLegSpec, tag: str | None = None) -> ExecutionResult:
        """Same protocol, reversed sides (BUY<->SELL) and shorts-first
        ordering -- closing the short first removes the unbounded-risk side
        before touching the long leg that was protecting it."""
        exit_legs = []
        for leg in order_exit_sequence(spec):
            exit_legs.append(
                Leg(
                    symbol=leg.symbol,
                    exchange=leg.exchange,
                    role=leg.role,
                    side=_reverse_side(leg.side),
                    quantity=leg.quantity,
                    order_type=leg.order_type,
                    price=leg.price,
                    index=leg.index,
                    protects_leg_index=leg.protects_leg_index,
                )
            )
        return await self._execute(spec, exit_legs, tag, is_exit=True)

    def _blocked_by_dependency(
        self,
        spec: MultiLegSpec,
        leg: Leg,
        failed_indices: set[int],
        is_exit: bool,
    ) -> bool:
        """True if `leg` must never be attempted given what's already
        failed earlier in this same ordered sequence -- beyond 2 legs, a
        leg can depend on one resolved earlier, and attempting it anyway
        would be actively dangerous, not just wasteful:

        ENTRY (longs attempted before shorts): a SHORT leg whose
        protecting LONG already failed must never be placed -- doing so
        would manufacture exactly the naked-short scenario this whole
        protocol exists to prevent, rather than merely detect it after
        the fact.

        EXIT (shorts attempted before longs): a LONG leg must not be
        closed while any SHORT it protects has failed to close -- closing
        the long would strip that still-open short of its protection.
        Because order_exit_sequence() puts every short before the longs
        it protects, every relevant short has already been attempted by
        the time a long is reached here.
        """
        if not is_exit:
            return (
                leg.role == LegRole.SHORT
                and leg.protects_leg_index is not None
                and leg.protects_leg_index in failed_indices
            )
        if leg.role != LegRole.LONG:
            return False
        protecting_shorts = (
            other.index
            for other in spec.legs
            if other.role == LegRole.SHORT and other.protects_leg_index == leg.index
        )
        return any(idx in failed_indices for idx in protecting_shorts)

    async def _execute(
        self,
        spec: MultiLegSpec,
        ordered_legs: list[Leg],
        tag: str | None,
        is_exit: bool = False,
    ) -> ExecutionResult:
        filled: list[LegFill] = []
        failed: list[Leg] = []  # genuinely attempted (and retried) legs that failed
        blocked: list[Leg] = []  # never attempted -- a dependency already failed
        already_retried = False

        for leg in ordered_legs:
            failed_indices = {f.index for f in failed}
            if self._blocked_by_dependency(spec, leg, failed_indices, is_exit):
                blocked.append(leg)
                continue

            lf = await self._attempt_leg(leg, tag)
            if lf is None and not already_retried:
                already_retried = True
                lf = await self._attempt_leg(leg, "RETRY")
            if lf is not None:
                filled.append(lf)
            else:
                failed.append(leg)

        if not failed and not blocked:
            return ExecutionResult(outcome=ExecutionOutcome.SUCCESS, fills=filled)

        result = await self._rollback(spec, filled, failed, is_exit)
        if blocked:
            result.failed_legs = result.failed_legs + blocked
        return result

    # ── Rollback (E05) ──────────────────────────────────────────────────────

    def _has_naked_short(self, spec: MultiLegSpec, filled: list[LegFill]) -> bool:
        """A SHORT leg is naked iff we hold its fill but not the fill of the
        LONG leg indexed by its protects_leg_index. A SHORT leg with no
        protects_leg_index set is treated as always-naked (undefined-risk
        structures have no protecting leg by definition). Entry-only --
        see `_rollback`'s is_exit branch for why this check doesn't apply
        to a failed exit."""
        filled_indices = {lf.leg.index for lf in filled}
        for lf in filled:
            if lf.leg.role != LegRole.SHORT:
                continue
            if lf.leg.protects_leg_index is None or lf.leg.protects_leg_index not in filled_indices:
                return True
        return False

    async def _rollback(
        self,
        spec: MultiLegSpec,
        filled: list[LegFill],
        failed: list[Leg],
        is_exit: bool,
    ) -> ExecutionResult:
        if is_exit:
            # Nothing here is ever reversed. Everything in `filled` during
            # an exit is legitimately CLOSED -- that's the goal -- so there
            # is nothing to unwind. The only problem is the leg(s) that
            # failed to close, which remain open (as does anything
            # deliberately left alone by `_blocked_by_dependency` to avoid
            # stripping a still-open short of its protection). Reversing
            # what DID close, the way the entry-side branch below does,
            # would recreate the exact exposure the exit was trying to
            # remove -- see this module's own docstring.
            await self._alert_p0(
                "EXIT INCOMPLETE -- LEG(S) STILL OPEN",
                f"{spec.underlying} {spec.structure_type.value} exit: could not close "
                f"{[leg.symbol for leg in failed]}. {len(filled)} other leg(s) closed "
                "successfully; the rest remain open -- manual intervention required.",
            )
            return ExecutionResult(
                outcome=ExecutionOutcome.HALTED_FOR_HUMAN,
                fills=filled,
                failed_legs=failed,
                message=f"exit incomplete -- still open: {[leg.symbol for leg in failed]}",
            )

        if self._has_naked_short(spec, filled):
            await self._alert_p0(
                "NAKED SHORT FROM PARTIAL FILL",
                f"{spec.underlying} {spec.structure_type.value} entry: forcing unwind of "
                f"{len(filled)} filled leg(s) at market -- failed leg(s): "
                f"{[leg.symbol for leg in failed]}",
            )
            for lf in filled:
                reverse_request = OrderRequest(
                    symbol=lf.leg.symbol,
                    side=_reverse_side(lf.order.side),
                    quantity=lf.order.filled_quantity,
                    order_type=OrderType.MARKET,
                    tag=f"{lf.order.tag}|FORCE_UNWIND" if lf.order.tag else "FORCE_UNWIND",
                )
                await self._place_order(reverse_request)
            return ExecutionResult(
                outcome=ExecutionOutcome.FORCE_UNWOUND,
                fills=filled,
                failed_legs=failed,
                message="naked short from partial fill -- force-unwound at market",
            )

        if len(failed) > 1:
            await self._alert_p0(
                "UNCLASSIFIED PARTIAL STRUCTURE -- MANUAL INTERVENTION REQUIRED",
                f"{spec.underlying} {spec.structure_type.value} entry: {len(filled)} filled, "
                f"{len(failed)} failed -- halting, no automatic action taken",
            )
            return ExecutionResult(
                outcome=ExecutionOutcome.HALTED_FOR_HUMAN,
                fills=filled,
                failed_legs=failed,
                message="multiple simultaneous leg failures -- halted for manual review",
            )

        if not filled:
            # Nothing filled at all -- flat, nothing to unwind or classify.
            return ExecutionResult(
                outcome=ExecutionOutcome.UNWOUND,
                fills=[],
                failed_legs=failed,
                message="no legs filled -- position never opened",
            )

        # Exactly one failed leg (already retried once by _execute before
        # calling here), something filled, not naked -- defined risk
        # either way. Unwind everything filled cleanly.
        await self._alert_p0(
            "PARTIAL STRUCTURE UNWINDING",
            f"{spec.underlying} {spec.structure_type.value} entry: leg(s) "
            f"{[leg.symbol for leg in failed]} unavailable -- unwinding {len(filled)} filled leg(s)",
        )
        for lf in filled:
            reverse_request = OrderRequest(
                symbol=lf.leg.symbol,
                side=_reverse_side(lf.order.side),
                quantity=lf.order.filled_quantity,
                order_type=lf.leg.order_type,
                price=lf.leg.price,
                tag=f"{lf.order.tag}|UNWIND" if lf.order.tag else "UNWIND",
            )
            await self._place_order(reverse_request)
        return ExecutionResult(
            outcome=ExecutionOutcome.UNWOUND,
            fills=filled,
            failed_legs=failed,
            message=f"leg(s) {[leg.symbol for leg in failed]} unavailable -- unwound cleanly",
        )
