"""
Funds half of M01 (2026-08-29 follow-up to CP14's position-only
reconciliation, and the last piece CP14's own scope note flagged as still
open): Broker.get_realised_pnl_today() vs. DailyStrategyPnl (xillion's own
internally computed figure, from actual fill prices -- see
strategy_engine.py's persist_trade_close). See
xillion/engine/reconciliation.py's module docstring and _reconcile_funds
for the full design.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from brokers._dummy import DummyBroker
from xillion.core.broker_base import BrokerCapabilities
from xillion.db.models import (
    BrokerClass,
    BrokerConnection,
    DailyStrategyPnl,
    StrategyInstance,
)
from xillion.db.session import get_session_factory, init_db
from xillion.engine.reconciliation import run_reconciliation


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


async def _seed_connection(name: str) -> int:
    unique = uuid4().hex
    factory = get_session_factory()
    async with factory() as session:
        bc = BrokerClass(
            name=f"Funds Recon Test Class {unique}",
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
    instance_id = f"funds-recon-test-{uuid4().hex}"
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            StrategyInstance(
                id=instance_id,
                strategy_class_id=1,
                strategy_class_version="1.0.0",
                name="Funds Recon Test Instance",
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


async def _seed_daily_pnl(
    instance_id: str, realised_pnl: float, trading_date: str | None = None
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            DailyStrategyPnl(
                trading_date=trading_date or _today(),
                strategy_instance_id=instance_id,
                realised_pnl=realised_pnl,
                unrealised_pnl=0.0,
                trade_count=1,
            )
        )
        await session.commit()


def _funds_broker(realised_pnl_today) -> DummyBroker:
    """A DummyBroker with supports_realised_pnl_query flipped on and
    get_realised_pnl_today() stubbed -- same monkeypatch-the-instance
    pattern test_orders_reconciliation.py already uses for
    get_orders_today()."""
    broker = DummyBroker()
    broker.capabilities = BrokerCapabilities(supports_realised_pnl_query=True)

    async def _get_realised_pnl_today() -> Decimal:
        return realised_pnl_today

    broker.get_realised_pnl_today = _get_realised_pnl_today
    return broker


@pytest.mark.asyncio
async def test_matching_funds_are_clean():
    await init_db()
    conn_id = await _seed_connection("Funds Recon Broker Clean")
    instance_id = await _seed_instance(conn_id)
    await _seed_daily_pnl(instance_id, 1250.0)

    broker = _funds_broker(Decimal("1250.0"))
    result = await run_reconciliation(broker, "Funds Recon Broker Clean", get_session_factory)

    assert result.status == "CLEAN"
    assert result.funds_mismatch is None


@pytest.mark.asyncio
async def test_mismatch_beyond_tolerance_is_flagged():
    await init_db()
    conn_id = await _seed_connection("Funds Recon Broker Mismatch")
    instance_id = await _seed_instance(conn_id)
    await _seed_daily_pnl(instance_id, 1000.0)

    broker = _funds_broker(Decimal("1050.0"))
    result = await run_reconciliation(broker, "Funds Recon Broker Mismatch", get_session_factory)

    assert result.status == "DISCREPANCY"
    assert result.funds_mismatch is not None
    # Compared as Decimal rather than exact string match -- the internal
    # figure round-trips through SQLite's Numeric storage, whose str()
    # formatting isn't itself the thing under test here.
    assert Decimal(result.funds_mismatch.broker_realised_pnl) == Decimal("1050.0")
    assert Decimal(result.funds_mismatch.internal_realised_pnl) == Decimal("1000")
    assert Decimal(result.funds_mismatch.diff) == Decimal("50.0")


@pytest.mark.asyncio
async def test_mismatch_within_tolerance_is_not_flagged():
    await init_db()
    conn_id = await _seed_connection("Funds Recon Broker WithinTolerance")
    instance_id = await _seed_instance(conn_id)
    await _seed_daily_pnl(instance_id, 1000.0)

    broker = _funds_broker(Decimal("1000.50"))
    result = await run_reconciliation(
        broker, "Funds Recon Broker WithinTolerance", get_session_factory
    )

    assert result.status == "CLEAN"
    assert result.funds_mismatch is None


@pytest.mark.asyncio
async def test_broker_without_the_capability_is_a_clean_skip():
    """A broker that never declares supports_realised_pnl_query (the
    default) must not force DISCREPANCY -- a capability that was never
    promised isn't evidence of anything wrong. DummyBroker's own default
    BrokerCapabilities() has this False."""
    await init_db()
    await _seed_connection("Funds Recon Broker NoCapability")
    broker = DummyBroker()

    result = await run_reconciliation(
        broker, "Funds Recon Broker NoCapability", get_session_factory
    )

    assert result.status == "CLEAN"
    assert result.funds_mismatch is None
    assert any("doesn't support it" in n for n in result.notes)


@pytest.mark.asyncio
async def test_fetch_failure_forces_discrepancy():
    await init_db()
    await _seed_connection("Funds Recon Broker FetchFail")
    broker = DummyBroker()
    broker.capabilities = BrokerCapabilities(supports_realised_pnl_query=True)

    async def _failing() -> Decimal:
        raise RuntimeError("positions endpoint down")

    broker.get_realised_pnl_today = _failing

    result = await run_reconciliation(broker, "Funds Recon Broker FetchFail", get_session_factory)

    assert result.status == "DISCREPANCY"
    assert result.funds_mismatch is None
    assert any("funds fetch failed" in n for n in result.notes)


@pytest.mark.asyncio
async def test_missing_broker_connection_row_does_not_force_discrepancy():
    """Same clean-skip stance as the orders check's own version of this
    case -- a broker never formally registered shouldn't block on a check
    that has nothing to compare against."""
    await init_db()
    broker = _funds_broker(Decimal("500.0"))

    result = await run_reconciliation(
        broker, "Funds Recon Broker Never Registered", get_session_factory
    )

    assert result.status == "CLEAN"
    assert result.funds_mismatch is None
    assert any("funds check skipped" in n for n in result.notes)


@pytest.mark.asyncio
async def test_a_second_brokers_daily_pnl_does_not_leak_into_this_ones_comparison():
    """Cross-broker-connection isolation, same as the orders check's own
    equivalent test -- DailyStrategyPnl for an instance on a DIFFERENT
    connection must not be summed into this connection's internal figure."""
    await init_db()
    other_conn_id = await _seed_connection("Funds Recon Broker Other")
    other_instance_id = await _seed_instance(other_conn_id)
    await _seed_daily_pnl(other_instance_id, 5000.0)

    this_conn_id = await _seed_connection("Funds Recon Broker Isolated")
    this_instance_id = await _seed_instance(this_conn_id)
    await _seed_daily_pnl(this_instance_id, 100.0)

    broker = _funds_broker(Decimal("100.0"))
    result = await run_reconciliation(broker, "Funds Recon Broker Isolated", get_session_factory)

    assert result.status == "CLEAN"
    assert result.funds_mismatch is None
