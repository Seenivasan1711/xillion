"""
Broker failover exit (2026-08-29): xillion/engine/broker_failover.py.
EXIT ONLY, matching automation-platform-spec 15-RUNBOOK-AND-OBSERVABILITY.md's
"switch to secondary broker for exits only" -- the down broker is
unreachable by definition, so this trusts xillion's own PositionRecord
(scoped to strategy instances configured on the down connection) rather
than querying the down broker directly like square_off.py does.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from brokers._dummy import DummyBroker
from xillion.db.models import BrokerClass, BrokerConnection, PositionRecord, StrategyInstance
from xillion.db.session import get_session_factory, init_db
from xillion.engine.broker_failover import run_failover_exit


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _seed_connection(name: str) -> int:
    unique = uuid4().hex
    factory = get_session_factory()
    async with factory() as session:
        bc = BrokerClass(
            name=f"Failover Test Class {unique}",
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
        await session.commit()
        return conn.id


async def _seed_instance(connection_id: int) -> str:
    instance_id = f"failover-test-{uuid4().hex}"
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            StrategyInstance(
                id=instance_id,
                strategy_class_id=1,
                strategy_class_version="1.0.0",
                name="Failover Test Instance",
                mode="live",
                status="running",
                broker_connection_id=connection_id,
                instruments_json="[]",
                timeframe="5m",
                params_json="{}",
                capital_allocation=100000,
                risk_limits_json="{}",
                created_at=_now_iso(),
                updated_at=_now_iso(),
            )
        )
        await session.commit()
    return instance_id


async def _seed_position(instance_id: str, symbol: str, quantity: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            PositionRecord(
                strategy_instance_id=instance_id,
                symbol=symbol,
                quantity=quantity,
                avg_price=100.0,
                realised_pnl=0.0,
                last_price=100.0,
                updated_at=_now_iso(),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_no_instances_on_down_connection_is_clean():
    await init_db()
    down_id = await _seed_connection("Failover Down Empty")
    broker = DummyBroker()

    result = await run_failover_exit(
        down_id, "Failover Down Empty", broker, "Failover Target", get_session_factory
    )
    assert result.status == "CLEAN"
    assert broker.calls == []


@pytest.mark.asyncio
async def test_instance_with_no_open_positions_is_clean():
    await init_db()
    down_id = await _seed_connection("Failover Down NoPos")
    await _seed_instance(down_id)
    broker = DummyBroker()

    result = await run_failover_exit(
        down_id, "Failover Down NoPos", broker, "Failover Target", get_session_factory
    )
    assert result.status == "CLEAN"


@pytest.mark.asyncio
async def test_open_long_position_is_exited_with_a_sell_via_failover_broker():
    await init_db()
    down_id = await _seed_connection("Failover Down Long")
    instance_id = await _seed_instance(down_id)
    await _seed_position(instance_id, "FAILOVER_SYM_LONG", 65)
    broker = DummyBroker()

    result = await run_failover_exit(
        down_id, "Failover Down Long", broker, "Failover Target", get_session_factory
    )
    assert result.status == "FLATTENED"
    assert result.exited == ["FAILOVER_SYM_LONG"]
    place_calls = [c for c in broker.calls if c[0] == "place_order"]
    assert len(place_calls) == 1
    req = place_calls[0][1]["request"]
    assert req.symbol == "FAILOVER_SYM_LONG"
    assert req.side.value == "SELL"
    assert req.quantity == 65
    assert req.tag == "BROKER_FAILOVER_EXIT"


@pytest.mark.asyncio
async def test_open_short_position_is_exited_with_a_buy():
    await init_db()
    down_id = await _seed_connection("Failover Down Short")
    instance_id = await _seed_instance(down_id)
    await _seed_position(instance_id, "FAILOVER_SYM_SHORT", -40)
    broker = DummyBroker()

    result = await run_failover_exit(
        down_id, "Failover Down Short", broker, "Failover Target", get_session_factory
    )
    assert result.status == "FLATTENED"
    req = [c for c in broker.calls if c[0] == "place_order"][0][1]["request"]
    assert req.side.value == "BUY"
    assert req.quantity == 40


@pytest.mark.asyncio
async def test_positions_on_a_different_connection_are_not_touched():
    await init_db()
    down_id = await _seed_connection("Failover Down Isolated")
    other_id = await _seed_connection("Failover Other Connection")
    other_instance = await _seed_instance(other_id)
    await _seed_position(other_instance, "FAILOVER_SYM_OTHER", 10)
    broker = DummyBroker()

    result = await run_failover_exit(
        down_id, "Failover Down Isolated", broker, "Failover Target", get_session_factory
    )
    assert result.status == "CLEAN"
    assert broker.calls == []


@pytest.mark.asyncio
async def test_a_failed_exit_order_is_reported_not_raised():
    await init_db()
    down_id = await _seed_connection("Failover Down Failing")
    instance_id = await _seed_instance(down_id)
    await _seed_position(instance_id, "FAILOVER_SYM_FAIL", 20)
    broker = DummyBroker()

    async def failing_place_order(request):
        raise RuntimeError("secondary broker rejected the order")

    broker.place_order = failing_place_order

    alerts = []

    async def notify(title, body, severity):
        alerts.append((title, severity))

    result = await run_failover_exit(
        down_id,
        "Failover Down Failing",
        broker,
        "Failover Target",
        get_session_factory,
        notify=notify,
    )
    assert result.status == "FAILED"
    assert result.failed_to_exit == ["FAILOVER_SYM_FAIL"]
    assert any(severity == "critical" for _, severity in alerts)


@pytest.mark.asyncio
async def test_multiple_open_positions_across_instances_are_all_exited():
    await init_db()
    down_id = await _seed_connection("Failover Down Multi")
    instance_a = await _seed_instance(down_id)
    instance_b = await _seed_instance(down_id)
    await _seed_position(instance_a, "FAILOVER_SYM_MULTI_A", 15)
    await _seed_position(instance_b, "FAILOVER_SYM_MULTI_B", 30)
    broker = DummyBroker()

    result = await run_failover_exit(
        down_id, "Failover Down Multi", broker, "Failover Target", get_session_factory
    )
    assert result.status == "FLATTENED"
    assert sorted(result.exited) == ["FAILOVER_SYM_MULTI_A", "FAILOVER_SYM_MULTI_B"]
