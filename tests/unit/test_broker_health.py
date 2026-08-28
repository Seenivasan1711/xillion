"""
Broker health monitoring + auto-failover trigger (2026-08-29):
xillion/engine/broker_health.py. Exercises _health_tick directly (bypassing
the asyncio.sleep loop wrapper), same precedent as
test_eod_scheduler.py's run_reconciliation_tick tests.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brokers._dummy import DummyBroker
from xillion.db.models import BrokerClass, BrokerConnection
from xillion.db.session import get_session_factory, init_db
from xillion.engine import broker_health as broker_health_module
from xillion.engine.broker_health import CONSECUTIVE_FAILURE_THRESHOLD, _health_tick


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _seed_connection(name: str, failover_target_name: str | None = None) -> int:
    unique = uuid4().hex
    factory = get_session_factory()
    async with factory() as session:
        bc = BrokerClass(
            name=f"Health Test Class {unique}",
            module_path="x",
            class_name="X",
            version="1.0.0",
            capabilities_json="{}",
            discovered_at=_now_iso(),
            last_seen_at=_now_iso(),
        )
        session.add(bc)
        await session.flush()
        conn = BrokerConnection(
            broker_class_id=bc.id,
            name=name,
            credentials_ref="PAPER",
            is_active=True,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        session.add(conn)
        await session.flush()

        if failover_target_name is not None:
            target_result = await session.execute(select_connection_by_name(failover_target_name))
            target = target_result.scalars().first()
            if target is not None:
                conn.failover_connection_id = target.id

        await session.commit()
        return conn.id


def select_connection_by_name(name: str):
    from sqlalchemy import select

    return select(BrokerConnection).where(BrokerConnection.name == name)


def _fake_app(broker_instances: dict) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(broker_instances=broker_instances, broker_health={}, telegram=None)
    )


@pytest.mark.asyncio
async def test_healthy_broker_never_accumulates_failures():
    await init_db()
    name = f"Health Healthy Broker {uuid4().hex}"
    broker = DummyBroker()  # healthcheck() -> True always
    app = _fake_app({name: {"instance": broker, "status": "connected"}})

    for _ in range(CONSECUTIVE_FAILURE_THRESHOLD + 2):
        await _health_tick(app)

    state = app.state.broker_health[name]
    assert state.consecutive_failures == 0
    assert state.failover_triggered is False


@pytest.mark.asyncio
async def test_failures_below_threshold_do_not_trigger_failover(monkeypatch):
    await init_db()
    name = f"Health Below Threshold {uuid4().hex}"
    broker = DummyBroker()

    async def unhealthy():
        return False

    broker.healthcheck = unhealthy
    app = _fake_app({name: {"instance": broker, "status": "connected"}})

    triggered = []
    monkeypatch.setattr(
        broker_health_module,
        "run_failover_exit",
        lambda **kw: triggered.append(kw) or _noop_coro(),
    )

    for _ in range(CONSECUTIVE_FAILURE_THRESHOLD - 1):
        await _health_tick(app)

    assert not triggered
    assert app.state.broker_health[name].consecutive_failures == CONSECUTIVE_FAILURE_THRESHOLD - 1


async def _noop_coro():
    return None


@pytest.mark.asyncio
async def test_threshold_crossed_with_no_failover_configured_only_alerts(monkeypatch):
    await init_db()
    name = f"Health No Target {uuid4().hex}"
    await _seed_connection(name)  # no failover_connection_id set
    broker = DummyBroker()

    async def unhealthy():
        return False

    broker.healthcheck = unhealthy
    app = _fake_app({name: {"instance": broker, "status": "connected"}})

    triggered = []
    monkeypatch.setattr(
        broker_health_module,
        "run_failover_exit",
        lambda **kw: triggered.append(kw) or _noop_coro(),
    )

    for _ in range(CONSECUTIVE_FAILURE_THRESHOLD + 2):
        await _health_tick(app)

    assert not triggered
    assert app.state.broker_health[name].down_alerted is True
    assert app.state.broker_health[name].failover_triggered is False


@pytest.mark.asyncio
async def test_threshold_crossed_with_healthy_target_triggers_failover_exactly_once(monkeypatch):
    await init_db()
    target_name = f"Health Target Healthy {uuid4().hex}"
    down_name = f"Health Down WithTarget {uuid4().hex}"
    await _seed_connection(target_name)
    await _seed_connection(down_name, failover_target_name=target_name)

    down_broker = DummyBroker()

    async def unhealthy():
        return False

    down_broker.healthcheck = unhealthy
    target_broker = DummyBroker()

    app = _fake_app(
        {
            down_name: {"instance": down_broker, "status": "connected"},
            target_name: {"instance": target_broker, "status": "connected"},
        }
    )

    triggered = []

    async def fake_failover_exit(**kw):
        triggered.append(kw)

    monkeypatch.setattr(broker_health_module, "run_failover_exit", fake_failover_exit)

    for _ in range(CONSECUTIVE_FAILURE_THRESHOLD + 3):
        await _health_tick(app)

    assert len(triggered) == 1
    assert triggered[0]["down_connection_name"] == down_name
    assert triggered[0]["failover_broker_name"] == target_name
    assert app.state.broker_health[down_name].failover_triggered is True


@pytest.mark.asyncio
async def test_threshold_crossed_with_unhealthy_target_does_not_trigger(monkeypatch):
    await init_db()
    target_name = f"Health Target Unhealthy {uuid4().hex}"
    down_name = f"Health Down TargetDown {uuid4().hex}"
    await _seed_connection(target_name)
    await _seed_connection(down_name, failover_target_name=target_name)

    down_broker = DummyBroker()
    target_broker = DummyBroker()

    async def unhealthy():
        return False

    down_broker.healthcheck = unhealthy
    target_broker.healthcheck = unhealthy  # target itself is also down

    app = _fake_app(
        {
            down_name: {"instance": down_broker, "status": "connected"},
            target_name: {"instance": target_broker, "status": "connected"},
        }
    )

    triggered = []
    monkeypatch.setattr(
        broker_health_module,
        "run_failover_exit",
        lambda **kw: triggered.append(kw) or _noop_coro(),
    )

    for _ in range(CONSECUTIVE_FAILURE_THRESHOLD + 2):
        await _health_tick(app)

    assert not triggered


@pytest.mark.asyncio
async def test_recovery_resets_failure_state():
    await init_db()
    name = f"Health Recovers {uuid4().hex}"
    broker = DummyBroker()
    healthy_flag = {"value": False}

    async def toggled():
        return healthy_flag["value"]

    broker.healthcheck = toggled
    app = _fake_app({name: {"instance": broker, "status": "connected"}})

    for _ in range(CONSECUTIVE_FAILURE_THRESHOLD + 1):
        await _health_tick(app)
    assert app.state.broker_health[name].consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD

    healthy_flag["value"] = True
    await _health_tick(app)

    state = app.state.broker_health[name]
    assert state.consecutive_failures == 0
    assert state.down_alerted is False
    assert state.failover_triggered is False
