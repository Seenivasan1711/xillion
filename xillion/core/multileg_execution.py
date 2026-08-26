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

    async def execute_entry(self, spec: MultiLegSpec, tag: str | None = None) -> ExecutionResult:
        return await self._execute(spec, order_entry_sequence(spec), tag)

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

    async def _execute(
        self,
        spec: MultiLegSpec,
        ordered_legs: list[Leg],
        tag: str | None,
        is_exit: bool = False,
    ) -> ExecutionResult:
        filled: list[LegFill] = []
        failed: list[Leg] = []

        for leg in ordered_legs:
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
                filled.append(LegFill(leg=leg, order=order))
                continue

            if order.status == OrderStatus.PARTIAL:
                ratio = Decimal(order.filled_quantity) / Decimal(leg.quantity)
                if ratio >= self._min_partial_ratio:
                    filled.append(LegFill(leg=leg, order=order))
                    if order.broker_order_id:
                        await self._cancel_order(order.client_order_id)
                    continue
                if order.broker_order_id:
                    await self._cancel_order(order.client_order_id)
                failed.append(leg)
                break

            # REJECTED, or still open after timeout / CANCELLED
            if order.status in _OPEN and order.broker_order_id:
                await self._cancel_order(order.client_order_id)
            failed.append(leg)
            break

        if not failed:
            return ExecutionResult(outcome=ExecutionOutcome.SUCCESS, fills=filled)

        return await self._rollback(spec, filled, failed, is_exit)

    # ── Rollback (E05) ──────────────────────────────────────────────────────

    def _has_naked_short(self, spec: MultiLegSpec, filled: list[LegFill]) -> bool:
        """A SHORT leg is naked iff we hold its fill but not the fill of the
        LONG leg indexed by its protects_leg_index. A SHORT leg with no
        protects_leg_index set is treated as always-naked (undefined-risk
        structures have no protecting leg by definition)."""
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
        action = "exit" if is_exit else "entry"

        if self._has_naked_short(spec, filled):
            await self._alert_p0(
                "NAKED SHORT FROM PARTIAL FILL",
                f"{spec.underlying} {spec.structure_type.value} {action}: forcing unwind of "
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
            # `_execute` never produces more than one failed leg in a single
            # call (it breaks on the first failure) -- this guards a direct/
            # future multi-simultaneous-failure caller where it's genuinely
            # ambiguous which leg to retry.
            await self._alert_p0(
                "UNCLASSIFIED PARTIAL STRUCTURE -- MANUAL INTERVENTION REQUIRED",
                f"{spec.underlying} {spec.structure_type.value} {action}: {len(filled)} filled, "
                f"{len(failed)} failed simultaneously -- halting, no automatic action taken",
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

        # Not naked, exactly one failed leg, and we hold something -- defined
        # risk either way. Retry the failed leg once.
        if len(failed) == 1 and filled:
            retry_leg = failed[0]
            retry_request = OrderRequest(
                symbol=retry_leg.symbol,
                side=retry_leg.side,
                quantity=retry_leg.quantity,
                order_type=retry_leg.order_type,
                price=retry_leg.price,
                tag="RETRY",
            )
            retry_order = await self._place_order(retry_request)
            retry_order = await self._wait_for_fill(retry_order)
            if retry_order.status == OrderStatus.FILLED:
                filled.append(LegFill(leg=retry_leg, order=retry_order))
                return ExecutionResult(outcome=ExecutionOutcome.SUCCESS, fills=filled)

            await self._alert_p0(
                "PARTIAL STRUCTURE UNWINDING",
                f"{spec.underlying} {spec.structure_type.value} {action}: leg "
                f"{retry_leg.symbol} unavailable after retry -- unwinding "
                f"{len(filled)} filled leg(s)",
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
                message=f"leg {retry_leg.symbol} unavailable after retry -- unwound cleanly",
            )

        # Unreachable from _execute() (which always yields exactly one failed
        # leg), kept as a defensive floor for any future/direct caller.
        await self._alert_p0(
            "UNCLASSIFIED PARTIAL STRUCTURE -- MANUAL INTERVENTION REQUIRED",
            f"{spec.underlying} {spec.structure_type.value} {action}: {len(filled)} filled, "
            f"{len(failed)} failed -- halting, no automatic action taken",
        )
        return ExecutionResult(
            outcome=ExecutionOutcome.HALTED_FOR_HUMAN,
            fills=filled,
            failed_legs=failed,
            message="unclassified partial structure -- halted for manual review",
        )
