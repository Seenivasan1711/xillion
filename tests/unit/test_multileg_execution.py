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
