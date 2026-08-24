"""
Signals API (CP4): the join query GET /signals runs, and the response shape
_row_dict produces -- both exercised directly against the DB rather than
through FastAPI's dependency injection (no HTTP TestClient pattern exists
elsewhere in this codebase; API tests here go through the DB layer).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from xillion.api.signals import _row_dict
from xillion.db.models import SignalLog, StrategyInstance
from xillion.db.session import get_session_factory, init_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed_instance(instance_id: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(StrategyInstance(
            id=instance_id, strategy_class_id=1, strategy_class_version="1.0.0",
            name="Test Instance For Signals API", mode="alert", status="running",
            broker_connection_id=1, instruments_json="[]", timeframe="1m",
            params_json="{}", capital_allocation=100000, risk_limits_json="{}",
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_row_dict_shapes_a_signal_log_row_correctly():
    await init_db()
    instance_id = "test-signals-api-instance"
    await _seed_instance(instance_id)

    factory = get_session_factory()
    async with factory() as session:
        session.add(SignalLog(
            strategy_instance_id=instance_id, ts=_now(), underlying_symbol="NIFTY 50",
            signal_type="ENTER", tag="setup_1", target_price=25100.0, stop_loss_price=24950.0,
            side="BUY", price=25000.0, message="BUY ENTER: NIFTY 50", mode="alert",
            notified=True, notified_at=_now(),
        ))
        await session.commit()

    async with factory() as session:
        row = (await session.execute(
            select(SignalLog).where(SignalLog.strategy_instance_id == instance_id)
        )).scalar_one()

    d = _row_dict(row, "Test Instance For Signals API")
    assert d["strategy_instance_name"] == "Test Instance For Signals API"
    assert d["signal_type"] == "ENTER"
    assert d["tag"] == "setup_1"
    assert d["target_price"] == 25100.0
    assert d["stop_loss_price"] == 24950.0
    assert d["notified"] is True


@pytest.mark.asyncio
async def test_join_query_resolves_instance_name_and_filters_by_instance(monkeypatch):
    await init_db()
    instance_a = "test-signals-api-instance-a"
    instance_b = "test-signals-api-instance-b"
    await _seed_instance(instance_a)

    factory = get_session_factory()
    async with factory() as session:
        session.add(SignalLog(
            strategy_instance_id=instance_a, ts=_now(), underlying_symbol="NIFTY 50",
            signal_type="SIGNAL", side="BUY", message="m", mode="alert", notified=False,
        ))
        session.add(SignalLog(
            strategy_instance_id=instance_b, ts=_now(), underlying_symbol="NIFTY 50",
            signal_type="SIGNAL", side="BUY", message="m", mode="alert", notified=False,
        ))
        await session.commit()

    # Same select/join/where shape as GET /signals?instance_id=...
    async with factory() as session:
        stmt = (
            select(SignalLog, StrategyInstance.name)
            .join(StrategyInstance, SignalLog.strategy_instance_id == StrategyInstance.id, isouter=True)
            .where(SignalLog.strategy_instance_id == instance_a)
        )
        rows = (await session.execute(stmt)).all()

    assert len(rows) == 1
    signal, name = rows[0]
    assert signal.strategy_instance_id == instance_a
    assert name == "Test Instance For Signals API"
