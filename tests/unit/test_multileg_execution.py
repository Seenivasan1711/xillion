"""
CP11 leg-failure protocol (E05) -- the acceptance tests are lifted directly
from docs/architecture/automation-platform-spec/06-JOBS-ENTRY.md E05's own
"Acceptance tests (all mandatory before live multi-leg)" list.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from xillion.core.events import Order, OrderRequest, OrderStatus, OrderType, Side
from xillion.core.multileg import Leg, LegRole, MultiLegSpec, StructureType
from xillion.core.multileg_execution import ExecutionOutcome, MultiLegExecutor


def _now():
    return datetime.now(UTC)


def _order(request: OrderRequest, status: OrderStatus, filled_qty: int = 0, price=None) -> Order:
    return Order(
        client_order_id=request.client_order_id,
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        order_type=request.order_type,
        status=status,
        submitted_at=_now(),
        updated_at=_now(),
        broker_order_id=f"B-{uuid4().hex[:6]}",
        filled_quantity=filled_qty,
        avg_fill_price=price if filled_qty else None,
    )


class FakeBroker:
    """Scripted place_order/cancel_order/get_order for one symbol -> one
    outcome. `fills` maps symbol -> "FILLED" | "REJECTED" | "PARTIAL" |
    "TIMEOUT". Records every order placed, in order, for assertions."""

    def __init__(self, outcomes: dict[str, str], partial_ratio: Decimal = Decimal("0.6")) -> None:
        self.outcomes = outcomes
        self.partial_ratio = partial_ratio
        self.placed: list[OrderRequest] = []
        self.cancelled: list[str] = []
        self._pending: dict[str, Order] = {}

    async def place_order(self, request: OrderRequest) -> Order:
        self.placed.append(request)
        outcome = self.outcomes.get(request.symbol, "FILLED")
        if outcome == "REJECTED":
            order = _order(request, OrderStatus.REJECTED)
        elif outcome == "PARTIAL":
            filled_qty = int(request.quantity * self.partial_ratio)
            order = _order(request, OrderStatus.PARTIAL, filled_qty, price=Decimal("10"))
        elif outcome == "TIMEOUT":
            order = _order(request, OrderStatus.ACCEPTED)
            self._pending[request.client_order_id] = order
        else:
            order = _order(request, OrderStatus.FILLED, request.quantity, price=Decimal("10"))
        return order

    async def cancel_order(self, client_order_id: str) -> bool:
        self.cancelled.append(client_order_id)
        return True

    async def get_order(self, client_order_id: str):
        # Always-open broker: simulates a leg that never resolves within timeout.
        return self._pending.get(client_order_id)


def _two_leg_spec(short_symbol="SHORT", long_symbol="LONG") -> MultiLegSpec:
    long_leg = Leg(
        symbol=long_symbol,
        exchange="NFO",
        role=LegRole.LONG,
        side=Side.BUY,
        quantity=65,
        order_type=OrderType.MARKET,
    )
    short_leg = Leg(
        symbol=short_symbol,
        exchange="NFO",
        role=LegRole.SHORT,
        side=Side.SELL,
        quantity=65,
        order_type=OrderType.MARKET,
        protects_leg_index=0,
    )
    return MultiLegSpec(
        structure_type=StructureType.CREDIT_SPREAD,
        underlying="NIFTY",
        legs=[long_leg, short_leg],
        lot_size=65,
        width=Decimal("50"),
        credit=Decimal("10"),
    )


def _condor_spec() -> MultiLegSpec:
    """A1 (Iron Condor, KB 03): two independent credit-spread pairs sharing
    one underlying/expiry. Call side: long_call protects short_call. Put
    side: long_put protects short_put -- structurally identical to two
    2-leg credit spreads combined, which is exactly why this is the right
    shape to prove _execute() generalises past 2 legs, not just claim it."""
    long_call = Leg(
        symbol="LONG_CALL",
        exchange="NFO",
        role=LegRole.LONG,
        side=Side.BUY,
        quantity=65,
        order_type=OrderType.MARKET,
    )
    long_put = Leg(
        symbol="LONG_PUT",
        exchange="NFO",
        role=LegRole.LONG,
        side=Side.BUY,
        quantity=65,
        order_type=OrderType.MARKET,
    )
    short_call = Leg(
        symbol="SHORT_CALL",
        exchange="NFO",
        role=LegRole.SHORT,
        side=Side.SELL,
        quantity=65,
        order_type=OrderType.MARKET,
        protects_leg_index=0,
    )
    short_put = Leg(
        symbol="SHORT_PUT",
        exchange="NFO",
        role=LegRole.SHORT,
        side=Side.SELL,
        quantity=65,
        order_type=OrderType.MARKET,
        protects_leg_index=1,
    )
    return MultiLegSpec(
        structure_type=StructureType.IRON_CONDOR,
        underlying="NIFTY",
        legs=[long_call, long_put, short_call, short_put],
        lot_size=65,
        width=Decimal("200"),
        credit=Decimal("55"),
    )


def _executor(broker: FakeBroker, **kwargs) -> MultiLegExecutor:
    return MultiLegExecutor(
        place_order_fn=broker.place_order,
        cancel_order_fn=broker.cancel_order,
        get_order_fn=broker.get_order,
        fill_timeout_sec=0.3,
        poll_interval_sec=0.05,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_both_legs_fill_success_and_long_placed_first():
    broker = FakeBroker({})
    spec = _two_leg_spec()
    result = await _executor(broker).execute_entry(spec)
    assert result.outcome == ExecutionOutcome.SUCCESS
    assert len(result.fills) == 2
    assert broker.placed[0].symbol == "LONG"  # long-first entry ordering
    assert broker.placed[1].symbol == "SHORT"


@pytest.mark.asyncio
async def test_leg1_long_fills_leg2_short_rejected_retries_then_unwinds_if_retry_fails():
    """E05 acceptance test 1: long fills, short rejected. Not naked (we hold
    only the protective long) -> retry once. If the retry also fails, unwind
    the long cleanly -- no naked short at any point."""
    broker = FakeBroker({"SHORT": "REJECTED"})
    spec = _two_leg_spec()
    result = await _executor(broker).execute_entry(spec)
    assert result.outcome == ExecutionOutcome.UNWOUND
    # placed: LONG (fills), SHORT (rejected), SHORT (retry, also rejected per
    # outcomes map), then a reversing SELL of LONG to flatten.
    symbols_and_sides = [(r.symbol, r.side) for r in broker.placed]
    assert symbols_and_sides[0] == ("LONG", Side.BUY)
    assert symbols_and_sides[-1] == ("LONG", Side.SELL)  # unwound the long


@pytest.mark.asyncio
async def test_short_fills_without_its_protecting_long_forces_unwind():
    """E05 acceptance test 2: a short is held without its protecting long
    filled -- must be classified naked and force-unwound at market
    immediately, regardless of how that state was reached."""
    broker = FakeBroker({})
    spec = _two_leg_spec()
    executor = _executor(broker)
    # Directly exercise the rollback classifier with a filled set containing
    # only the SHORT leg -- this is what "naked short" means structurally,
    # independent of which code path produced it.
    from xillion.core.multileg_execution import LegFill

    short_leg = spec.legs[1]
    fake_fill_order = _order(
        OrderRequest(
            symbol=short_leg.symbol,
            side=short_leg.side,
            quantity=short_leg.quantity,
            order_type=short_leg.order_type,
        ),
        OrderStatus.FILLED,
        short_leg.quantity,
        price=Decimal("10"),
    )
    result = await executor._rollback(
        spec, [LegFill(leg=short_leg, order=fake_fill_order)], [spec.legs[0]], False
    )
    assert result.outcome == ExecutionOutcome.FORCE_UNWOUND
    # A reversing BUY (close the short) must have been placed at market.
    reversing = [r for r in broker.placed if r.symbol == short_leg.symbol]
    assert len(reversing) == 1
    assert reversing[0].side == Side.BUY
    assert reversing[0].order_type == OrderType.MARKET


@pytest.mark.asyncio
async def test_partial_fill_above_min_ratio_is_accepted_and_remainder_cancelled():
    broker = FakeBroker({"SHORT": "PARTIAL"}, partial_ratio=Decimal("0.6"))
    spec = _two_leg_spec()
    result = await _executor(broker, min_partial_ratio=Decimal("0.5")).execute_entry(spec)
    assert result.outcome == ExecutionOutcome.SUCCESS
    assert len(result.fills) == 2
    assert len(broker.cancelled) == 1  # remainder of the partial fill cancelled


@pytest.mark.asyncio
async def test_partial_fill_below_min_ratio_is_treated_as_failed_leg():
    broker = FakeBroker({"SHORT": "PARTIAL"}, partial_ratio=Decimal("0.3"))
    spec = _two_leg_spec()
    result = await _executor(broker, min_partial_ratio=Decimal("0.5")).execute_entry(spec)
    # Long filled fully, short's weak partial rejected -> not naked (long-only) -> retry/unwind path.
    assert result.outcome in (ExecutionOutcome.SUCCESS, ExecutionOutcome.UNWOUND)


@pytest.mark.asyncio
async def test_leg_stuck_open_past_timeout_is_cancelled_and_treated_as_failed():
    broker = FakeBroker({"SHORT": "TIMEOUT"})
    spec = _two_leg_spec()
    result = await _executor(broker).execute_entry(spec)
    assert result.outcome == ExecutionOutcome.UNWOUND
    assert any(cid for cid in broker.cancelled)  # the stuck order was cancelled


@pytest.mark.asyncio
async def test_multiple_failures_halt_for_human_not_auto_unwound():
    broker = FakeBroker({})
    spec = _two_leg_spec()
    executor = _executor(broker)
    long_leg, short_leg = spec.legs
    # Simulate: nothing filled, but two legs both in the failed list at once
    # (e.g. a wider structure) -- unclassifiable by the single-retry path.
    result = await executor._rollback(spec, [], [long_leg, short_leg], False)
    assert result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN
    assert broker.placed == []  # no automatic order placed while halted


@pytest.mark.asyncio
async def test_exit_places_short_before_long_and_reverses_sides():
    broker = FakeBroker({})
    spec = _two_leg_spec()
    result = await _executor(broker).execute_exit(spec)
    assert result.outcome == ExecutionOutcome.SUCCESS
    assert (
        broker.placed[0].symbol == "SHORT" and broker.placed[0].side == Side.BUY
    )  # buy-to-close short first
    assert (
        broker.placed[1].symbol == "LONG" and broker.placed[1].side == Side.SELL
    )  # sell-to-close long second


# ── 2026-08-29: N-leg entry (iron condor, 4 legs) ────────────────────────────
# Building the condor -- the first 3+ leg consumer -- surfaced a real bug:
# _execute() used to stop attempting legs after the FIRST failure, invisible
# with exactly 2 legs (nothing left to attempt) but silently wrong for 4:
# an unrelated pair further down the sequence never even got tried.


@pytest.mark.asyncio
async def test_condor_all_four_legs_fill_success_longs_then_shorts():
    broker = FakeBroker({})
    spec = _condor_spec()
    result = await _executor(broker).execute_entry(spec)
    assert result.outcome == ExecutionOutcome.SUCCESS
    assert len(result.fills) == 4
    # Both longs before both shorts (order_entry_sequence), original
    # relative order preserved within each role.
    assert [r.symbol for r in broker.placed] == [
        "LONG_CALL",
        "LONG_PUT",
        "SHORT_CALL",
        "SHORT_PUT",
    ]


@pytest.mark.asyncio
async def test_condor_independent_pair_still_entered_when_the_other_pairs_long_fails():
    """LONG_PUT is rejected (both the original attempt and its one retry).
    The call side has nothing to do with the put side's failure and must
    still be entered -- the bug this regresses against silently never
    attempted SHORT_CALL/SHORT_PUT at all once LONG_PUT failed."""
    broker = FakeBroker({"LONG_PUT": "REJECTED"})
    spec = _condor_spec()
    result = await _executor(broker).execute_entry(spec)

    assert result.outcome == ExecutionOutcome.UNWOUND
    # The call side (long_call, short_call) genuinely filled -- both must
    # appear among the fills, and both must then be unwound cleanly since
    # the whole 4-leg structure couldn't complete.
    filled_symbols = {lf.leg.symbol for lf in result.fills}
    assert filled_symbols == {"LONG_CALL", "SHORT_CALL"}
    # SHORT_PUT must NEVER have been placed at all -- its protecting long
    # (LONG_PUT) already failed, so placing it would manufacture a naked
    # short outright rather than merely risk one.
    assert all(r.symbol != "SHORT_PUT" for r in broker.placed)
    assert "SHORT_PUT" in [leg.symbol for leg in result.failed_legs]


@pytest.mark.asyncio
async def test_condor_naked_short_not_falsely_flagged_on_the_successful_pair():
    """The put side fails entirely (long rejected) while the call side
    fully fills -- short_call's own protecting long (long_call) DID fill,
    so it must never be misclassified as naked just because a different,
    independent pair didn't complete."""
    broker = FakeBroker({"LONG_PUT": "REJECTED"})
    spec = _condor_spec()
    result = await _executor(broker).execute_entry(spec)
    # FORCE_UNWOUND would mean a false naked-short positive; the correct
    # outcome is a clean UNWOUND of the call side (see test above).
    assert result.outcome != ExecutionOutcome.FORCE_UNWOUND
    assert result.outcome == ExecutionOutcome.UNWOUND


@pytest.mark.asyncio
async def test_condor_two_independent_leg_failures_halts_for_human():
    """Both shorts fail after both longs succeed -- two genuinely
    independent failures in one entry attempt is exactly the ambiguous
    case E05 reserves for a human, not an automatic call."""
    broker = FakeBroker({"SHORT_CALL": "REJECTED", "SHORT_PUT": "REJECTED"})
    spec = _condor_spec()
    result = await _executor(broker).execute_entry(spec)
    assert result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN
    filled_symbols = {lf.leg.symbol for lf in result.fills}
    assert filled_symbols == {"LONG_CALL", "LONG_PUT"}  # left open, untouched, pending review


# ── 2026-08-29: exit-failure reversal bug ────────────────────────────────────
# The naked-short "force unwind" reversal only makes sense on ENTRY. Applied
# to a failed EXIT it would re-open a leg that had just been closed
# successfully -- a latent bug in the 2-leg case too, never caught because
# no test exercised a leg failing partway through an exit until now.


@pytest.mark.asyncio
async def test_exit_failure_never_reverses_a_leg_that_already_closed():
    """SHORT's close succeeds; LONG's close is then rejected (and its
    retry also rejected). The bug: the old code saw "a filled SHORT
    without its LONG" and force-unwound by RE-SELLING the just-closed
    short, recreating the naked position the exit was trying to remove.
    Correct behaviour: leave the closed short closed, halt for human
    review on the long that's still open, and place no new orders for
    either leg beyond what already happened."""
    broker = FakeBroker({"LONG": "REJECTED"})
    spec = _two_leg_spec()
    result = await _executor(broker).execute_exit(spec)

    assert result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN
    # SHORT's close (BUY, since it was originally SELL) must appear exactly
    # once -- never reversed back into a fresh SELL.
    short_orders = [r for r in broker.placed if r.symbol == "SHORT"]
    assert len(short_orders) == 1
    assert short_orders[0].side == Side.BUY
    assert all(r.side != Side.SELL for r in short_orders)
    # LONG's close was attempted (plus one retry) but never "reversed" into
    # a fresh BUY -- only SELL attempts for LONG should exist.
    long_orders = [r for r in broker.placed if r.symbol == "LONG"]
    assert all(r.side == Side.SELL for r in long_orders)


@pytest.mark.asyncio
async def test_condor_exit_long_left_open_when_its_short_fails_to_close():
    """4-leg exit: SHORT_CALL's close fails -- LONG_CALL must be left
    open (not closed) since closing it would strip SHORT_CALL's
    protection while it's still held. The put side, unaffected, closes
    normally."""
    broker = FakeBroker({"SHORT_CALL": "REJECTED"})
    spec = _condor_spec()
    result = await _executor(broker).execute_exit(spec)

    assert result.outcome == ExecutionOutcome.HALTED_FOR_HUMAN
    closed_symbols = {lf.leg.symbol for lf in result.fills}
    assert closed_symbols == {"SHORT_PUT", "LONG_PUT"}  # put side fully closed
    # LONG_CALL must never even have been attempted.
    assert all(r.symbol != "LONG_CALL" for r in broker.placed)
    still_open = {leg.symbol for leg in result.failed_legs}
    assert "SHORT_CALL" in still_open  # failed to close
    assert "LONG_CALL" in still_open  # deliberately left open to protect it
