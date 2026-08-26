"""
X02 square-off enforcer (CP14). Driven ONLY by a Broker -- per the spec,
this job "must work when everything else is broken," so these tests never
touch StrategyEngine/StrategyContext at all.
"""

from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Position
from xillion.engine.square_off import SQUARE_OFF_TAG, run_square_off


async def _async_list(items):
    return items


def _pos(symbol: str, qty: int) -> Position:
    return Position(
        symbol=symbol,
        quantity=qty,
        avg_price=Decimal("100"),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("0"),
        last_price=Decimal("100"),
    )


@pytest.mark.asyncio
async def test_no_open_positions_is_clean():
    broker = DummyBroker()
    report = await run_square_off(broker)
    assert report.status == "CLEAN"
    assert report.flattened == []


@pytest.mark.asyncio
async def test_zero_quantity_positions_are_not_flattened():
    broker = DummyBroker()

    async def get_positions():
        return [_pos("NIFTY", 0)]

    broker.get_positions = get_positions

    report = await run_square_off(broker)
    assert report.status == "CLEAN"


@pytest.mark.asyncio
async def test_long_position_flattened_with_a_sell_market_order():
    broker = DummyBroker()
    call_count = {"n": 0}

    async def get_positions():
        call_count["n"] += 1
        # First call finds the open long; verification call (2nd) finds flat.
        return [_pos("NIFTY", 65)] if call_count["n"] == 1 else []

    broker.get_positions = get_positions

    report = await run_square_off(broker)

    assert report.status == "FLATTENED"
    assert report.flattened == ["NIFTY"]
    assert len(broker.placed_orders) == 1
    order = broker.calls[0][1]["request"]
    assert order.side.value == "SELL"  # closing a long
    assert order.quantity == 65
    assert order.tag == SQUARE_OFF_TAG


@pytest.mark.asyncio
async def test_short_position_flattened_with_a_buy_market_order():
    broker = DummyBroker()
    call_count = {"n": 0}

    async def get_positions():
        call_count["n"] += 1
        return [_pos("NIFTY", -65)] if call_count["n"] == 1 else []

    broker.get_positions = get_positions

    report = await run_square_off(broker)

    assert report.status == "FLATTENED"
    order = broker.calls[0][1]["request"]
    assert order.side.value == "BUY"  # closing a short


@pytest.mark.asyncio
async def test_broker_fetch_failure_is_reported_not_raised():
    broker = DummyBroker()

    async def failing_get_positions():
        raise RuntimeError("broker unreachable")

    broker.get_positions = failing_get_positions

    report = await run_square_off(broker)  # must not raise
    assert report.status == "FAILED"
    assert "unreachable" in report.error


@pytest.mark.asyncio
async def test_order_placement_failure_is_reported_and_alerted():
    broker = DummyBroker()
    call_count = {"n": 0}

    async def get_positions():
        call_count["n"] += 1
        return [_pos("NIFTY", 65)] if call_count["n"] == 1 else [_pos("NIFTY", 65)]  # still open

    broker.get_positions = get_positions

    async def failing_place_order(request):
        raise RuntimeError("order rejected")

    broker.place_order = failing_place_order

    alerts = []

    async def notify(title, body, severity):
        alerts.append((title, severity))

    report = await run_square_off(broker, notify=notify)

    assert report.status == "FAILED"
    assert "NIFTY" in report.failed_to_close
    assert any("INCOMPLETE" in title or "FAILED" in title for title, _ in alerts)


@pytest.mark.asyncio
async def test_still_open_after_verify_is_reported_and_alerted():
    """Order placed successfully, but the post-close verification query
    still shows the position open -- must not be silently reported as clean."""
    broker = DummyBroker()

    async def get_positions():
        return [_pos("NIFTY", 65)]  # ALWAYS open, even on the verify pass

    broker.get_positions = get_positions

    alerts = []

    async def notify(title, body, severity):
        alerts.append((title, severity))

    report = await run_square_off(broker, notify=notify)

    assert report.status == "FAILED"
    assert "NIFTY" in report.still_open_after_verify
    assert any(severity == "critical" for _, severity in alerts)


@pytest.mark.asyncio
async def test_verification_fetch_failure_is_reported_and_alerted():
    broker = DummyBroker()
    call_count = {"n": 0}

    async def get_positions():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [_pos("NIFTY", 65)]
        raise RuntimeError("broker dropped mid-flatten")

    broker.get_positions = get_positions

    alerts = []

    async def notify(title, body, severity):
        alerts.append((title, severity))

    report = await run_square_off(broker, notify=notify)

    assert report.status == "FAILED"
    assert "verify fetch failed" in report.error
    assert any(severity == "critical" for _, severity in alerts)
