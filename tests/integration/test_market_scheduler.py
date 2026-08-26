"""
Auto start/stop instances at market open/close (CP9): an instance is only
ever touched by the scheduler if it opted in via auto_start=True. This
drives _start_auto_instances/_stop_auto_instances directly (DB layer, same
pattern as the rest of this codebase's API tests -- see
tests/unit/test_signals_api.py) plus the open/close transition-detection
loop in run_market_hours_scheduler itself.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.db.models import BrokerClass, BrokerConnection, StrategyClass, StrategyInstance
from xillion.db.session import get_session_factory, init_db
from xillion.engine.market_scheduler import (
    _start_auto_instances,
    _stop_auto_instances,
    run_market_hours_scheduler,
)
from xillion.engine.strategy_engine import StrategyEngine


class _NoopStrategy(Strategy):
    timeframe = "5m"
    instruments = ["NIFTY"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _make_app() -> FastAPI:
    app = FastAPI()
    registry = PluginRegistry()

    class _FakeLoader:
        def __init__(self, reg):
            self.registry = reg

    app.state.plugin_loader = _FakeLoader(registry)
    bus = MarketDataBus()
    app.state.bus = bus
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    app.state.strategy_engine = engine
    app.state.broker_instances = {}
    app.state.telegram = None
    return app


async def _seed_instance(
    app: FastAPI, instance_id: str, auto_start: bool, status: str = "idle"
) -> None:
    await init_db()
    strategy_name = f"Market Scheduler Test Strategy {instance_id}"
    app.state.plugin_loader.registry.strategies[strategy_name] = _NoopStrategy
    factory = get_session_factory()
    async with factory() as db:
        bc = BrokerClass(
            name=f"Dummy Broker {instance_id}",
            module_path="x",
            class_name="X",
            version="1.0.0",
            capabilities_json="{}",
            discovered_at=_now(),
            last_seen_at=_now(),
        )
        db.add(bc)
        await db.flush()
        conn = BrokerConnection(
            broker_class_id=bc.id,
            name=f"conn-{instance_id}",
            credentials_ref="PAPER",
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(conn)
        sc = StrategyClass(
            name=strategy_name,
            module_path="x",
            class_name="X",
            version="1.0.0",
            params_schema_json="{}",
            code_hash="abc",
            discovered_at=_now(),
            last_seen_at=_now(),
        )
        db.add(sc)
        await db.flush()
        db.add(
            StrategyInstance(
                id=instance_id,
                strategy_class_id=sc.id,
                strategy_class_version="1.0.0",
                name=f"Instance {instance_id}",
                mode="paper",
                status=status,
                broker_connection_id=conn.id,
                instruments_json='["NIFTY"]',
                timeframe="5m",
                params_json="{}",
                capital_allocation=100000,
                risk_limits_json="{}",
                auto_start=auto_start,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await db.commit()


async def _get_status(instance_id: str) -> str:
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(StrategyInstance).where(StrategyInstance.id == instance_id)
        )
        return result.scalar_one().status


@pytest.mark.asyncio
async def test_market_open_starts_only_opted_in_idle_instances():
    app = await _make_app()
    await _seed_instance(app, "sched-autostart-1", auto_start=True, status="idle")
    await _seed_instance(app, "sched-autostart-2", auto_start=False, status="idle")

    await _start_auto_instances(app)

    assert await _get_status("sched-autostart-1") == "running"
    assert await _get_status("sched-autostart-2") == "idle"  # not opted in -- untouched
    assert app.state.strategy_engine.get_runner("sched-autostart-1") is not None
    assert app.state.strategy_engine.get_runner("sched-autostart-2") is None


@pytest.mark.asyncio
async def test_market_close_stops_only_opted_in_running_instances():
    app = await _make_app()
    await _seed_instance(app, "sched-autostop-1", auto_start=True, status="idle")
    await _seed_instance(app, "sched-autostop-2", auto_start=True, status="idle")
    await _start_auto_instances(app)
    assert await _get_status("sched-autostop-1") == "running"
    assert await _get_status("sched-autostop-2") == "running"

    # Simulate a manual stop of instance 2 before market close -- the
    # scheduler must only touch what's actually still running.
    await app.state.strategy_engine.stop_instance("sched-autostop-2", reason="user_stopped")
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(StrategyInstance).where(StrategyInstance.id == "sched-autostop-2")
        )
        inst = result.scalar_one()
        inst.status = "idle"
        await db.commit()

    await _stop_auto_instances(app)

    assert await _get_status("sched-autostop-1") == "idle"
    assert app.state.strategy_engine.get_runner("sched-autostop-1") is None


@pytest.mark.asyncio
async def test_an_instance_already_running_is_skipped_not_errored():
    """A race where the scheduler's own query is stale by the time it acts
    (e.g. a manual start happened in between) must not blow up the loop for
    every other instance behind it."""
    app = await _make_app()
    await _seed_instance(app, "sched-race-1", auto_start=True, status="idle")
    # Start it manually first, exactly like a race would.
    factory = get_session_factory()
    async with factory() as db:
        from xillion.api.instances import start_instance_core

        await start_instance_core(app, db, "sched-race-1")

    await _start_auto_instances(app)  # must not raise

    assert await _get_status("sched-race-1") == "running"


@pytest.mark.asyncio
async def test_scheduler_reacts_only_to_open_close_transitions(monkeypatch):
    """The very first tick must never fire a start/stop based on an assumed
    prior state -- only a genuine transition after the baseline is set."""
    calls: list[str] = []

    async def _fake_start(app):
        calls.append("start")

    async def _fake_stop(app):
        calls.append("stop")

    monkeypatch.setattr("xillion.engine.market_scheduler._start_auto_instances", _fake_start)
    monkeypatch.setattr("xillion.engine.market_scheduler._stop_auto_instances", _fake_stop)

    # market state sequence observed across successive polls
    states = iter([True, True, False, False, True])
    sleep_count = 0

    async def _fake_sleep(_secs):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 5:
            raise asyncio.CancelledError()

    monkeypatch.setattr("xillion.engine.market_scheduler.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr(
        "xillion.engine.market_scheduler.is_market_open",
        lambda *a, **k: next(states),
    )

    app = FastAPI()

    with pytest.raises(asyncio.CancelledError):
        await run_market_hours_scheduler(app, poll_interval_seconds=0)

    # open(baseline) -> open(no-op) -> closed(STOP) -> closed(no-op) -> open(START)
    assert calls == ["stop", "start"]
