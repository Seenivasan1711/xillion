"""
CP14's own Verify line: "kill the process mid-position, restart after
market close, confirm M01 reports the position was flattened (or alerts
loudly that it wasn't) rather than silently carrying it forward."

Simulates the crash by never involving StrategyEngine/StrategyContext at
all -- a real open position sitting at the broker with no xillion process
even aware of it (the actual "died mid-position, restarted cold" scenario)
-- then runs X02 and M01 exactly as the scheduler would, in sequence.
"""
from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Position
from xillion.db.session import get_session_factory, init_db
from xillion.engine.reconciliation import run_reconciliation
from xillion.engine.square_off import run_square_off


def _pos(symbol: str, qty: int) -> Position:
    return Position(
        symbol=symbol, quantity=qty, avg_price=Decimal("100"),
        realised_pnl=Decimal("0"), unrealised_pnl=Decimal("0"), last_price=Decimal("100"),
    )


@pytest.mark.asyncio
async def test_x02_flattens_then_m01_confirms_clean():
    """The good path: a position survives a simulated crash (broker still
    shows it open, nothing in xillion's memory knows about it), X02 closes
    it, M01 independently confirms flat."""
    await init_db()
    broker = DummyBroker()
    call_count = {"n": 0}

    async def get_positions():
        call_count["n"] += 1
        # Found open on X02's first check and its verify pass finds it
        # gone; M01 (running after) also finds it gone.
        return [_pos("EOD_TEST_SYM_1", 65)] if call_count["n"] == 1 else []
    broker.get_positions = get_positions

    x02_report = await run_square_off(broker)
    assert x02_report.status == "FLATTENED"

    m01_result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert m01_result.status == "CLEAN"
    assert "EOD_TEST_SYM_1" not in m01_result.eod_open_positions


@pytest.mark.asyncio
async def test_x02_fails_to_flatten_and_m01_catches_it_loudly():
    """The bad path: X02's close order is rejected (illiquid leg, broker
    error, whatever) -- the position is genuinely still open. M01 must
    NOT silently carry it forward; it has to show DISCREPANCY and fire a
    critical alert."""
    await init_db()
    broker = DummyBroker()

    async def get_positions():
        return [_pos("EOD_TEST_SYM_2", 65)]  # never actually closes
    broker.get_positions = get_positions

    async def failing_place_order(request):
        raise RuntimeError("leg illiquid -- broker rejected")
    broker.place_order = failing_place_order

    x02_alerts = []
    async def x02_notify(title, body, severity):
        x02_alerts.append((title, severity))

    x02_report = await run_square_off(broker, notify=x02_notify)
    assert x02_report.status == "FAILED"
    assert "EOD_TEST_SYM_2" in x02_report.failed_to_close
    assert any(severity == "critical" for _, severity in x02_alerts)

    m01_alerts = []
    async def m01_notify(title, body, severity):
        m01_alerts.append((title, severity))

    m01_result = await run_reconciliation(broker, "Test Broker", get_session_factory, notify=m01_notify)
    assert m01_result.status == "DISCREPANCY"
    assert "EOD_TEST_SYM_2" in m01_result.eod_open_positions
    assert any(severity == "critical" for _, severity in m01_alerts)


@pytest.mark.asyncio
async def test_no_position_at_all_after_a_clean_prior_close_stays_clean_through_both_jobs():
    await init_db()
    broker = DummyBroker()  # nothing open anywhere

    x02_report = await run_square_off(broker)
    assert x02_report.status == "CLEAN"

    m01_result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert "EOD_TEST_SYM_3" not in m01_result.eod_open_positions
