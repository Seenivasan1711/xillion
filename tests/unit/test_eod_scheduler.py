"""CP14 scheduler timing + connected-broker discovery, plus (2026-08-28) the
run_reconciliation_tick() trading gate -- the M01 wiring CP14 shipped with a
documented, honest gap ("blocking behaviour itself isn't wired to
anything"). The reconciliation math itself is covered by
tests/unit/test_reconciliation.py; this covers only the scheduling/gating
wiring around it.
"""

from datetime import datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from brokers._dummy import DummyBroker
from xillion.core.events import Position
from xillion.core.risk import RiskManager
from xillion.db.models import PositionRecord
from xillion.db.session import get_session_factory, init_db
from xillion.engine.eod_scheduler import (
    IST,
    _connected_brokers,
    _next_occurrence,
    run_reconciliation_tick,
)


def test_next_occurrence_same_day_when_target_is_later():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=IST)
    target = time(15, 15)
    result = _next_occurrence(now, target)
    assert result == datetime(2026, 8, 25, 15, 15, tzinfo=IST)


def test_next_occurrence_rolls_to_next_day_when_target_already_passed():
    now = datetime(2026, 8, 25, 16, 0, tzinfo=IST)
    target = time(15, 15)
    result = _next_occurrence(now, target)
    assert result == datetime(2026, 8, 26, 15, 15, tzinfo=IST)


def test_next_occurrence_rolls_over_when_exactly_at_target():
    now = datetime(2026, 8, 25, 15, 15, tzinfo=IST)
    target = time(15, 15)
    result = _next_occurrence(now, target)
    assert result == datetime(2026, 8, 26, 15, 15, tzinfo=IST)


class _FakeApp:
    class State:
        pass

    def __init__(self, broker_instances):
        self.state = self.State()
        self.state.broker_instances = broker_instances


async def test_connected_brokers_skips_entries_with_no_instance():
    app = _FakeApp(
        {
            "Zerodha Primary": {"instance": "fake-broker-1", "status": "connected"},
            "Dhan Primary": {"instance": None, "status": "failed"},
        }
    )
    result = await _connected_brokers(app)
    assert result == [("Zerodha Primary", "fake-broker-1")]


async def test_connected_brokers_empty_when_none_connected():
    app = _FakeApp({})
    result = await _connected_brokers(app)
    assert result == []


# ── run_reconciliation_tick() trading gate (2026-08-28) ─────────────────────


def _pos(symbol: str, qty: int) -> Position:
    return Position(
        symbol=symbol,
        quantity=qty,
        avg_price=Decimal("100"),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("0"),
        last_price=Decimal("100"),
    )


def _fake_tick_app(broker, risk: RiskManager, broker_name: str = "Gate Tick Broker"):
    return SimpleNamespace(
        state=SimpleNamespace(
            broker_instances={broker_name: {"instance": broker}},
            risk=risk,
            telegram=None,
        )
    )


@pytest.mark.asyncio
async def test_clean_tick_leaves_trading_enabled():
    await init_db()
    # run_reconciliation() checks EVERY nonzero PositionRecord row in the
    # table, not just ones this test created -- other test files
    # deliberately leave open positions behind to test the DISCREPANCY path
    # (see test_reconciliation.py), so this test can't assume the table is
    # already flat regardless of run order. Clearing it here is a test-
    # isolation fix scoped to this test only, not a production behaviour
    # change.
    async with get_session_factory()() as session:
        await session.execute(delete(PositionRecord))
        await session.commit()

    risk = RiskManager()
    app = _fake_tick_app(DummyBroker(), risk)  # DummyBroker.get_positions() -> []

    await run_reconciliation_tick(app)

    assert risk.status()["trading_enabled"] is True


@pytest.mark.asyncio
async def test_discrepancy_tick_pauses_trading():
    await init_db()
    risk = RiskManager()
    broker = DummyBroker()

    async def get_positions():
        return [_pos("GATE_TICK_SYM_1", 65)]  # open at EOD -> DISCREPANCY

    broker.get_positions = get_positions
    app = _fake_tick_app(broker, risk)

    await run_reconciliation_tick(app)

    assert risk.status()["trading_enabled"] is False


@pytest.mark.asyncio
async def test_failed_fetch_tick_also_pauses_trading():
    await init_db()
    risk = RiskManager()
    broker = DummyBroker()

    async def failing_get_positions():
        raise RuntimeError("broker down")

    broker.get_positions = failing_get_positions
    app = _fake_tick_app(broker, risk)

    await run_reconciliation_tick(app)

    assert risk.status()["trading_enabled"] is False


@pytest.mark.asyncio
async def test_paused_trading_actually_blocks_new_orders_via_risk_check():
    """Not just a status flag -- prove RiskManager.check() itself rejects
    once M01 has paused trading, the same gate every order routes through."""
    from xillion.core.events import OrderRequest, OrderType, Side
    from xillion.core.risk import RiskRejected

    await init_db()
    risk = RiskManager()
    broker = DummyBroker()

    async def get_positions():
        return [_pos("GATE_TICK_SYM_2", 10)]

    broker.get_positions = get_positions
    app = _fake_tick_app(broker, risk)
    await run_reconciliation_tick(app)

    decision = risk.check(
        OrderRequest(symbol="NIFTY", side=Side.BUY, quantity=50, order_type=OrderType.MARKET)
    )
    assert isinstance(decision, RiskRejected)
    assert "trading_enabled" in decision.failed_checks
