"""
Orders/fills half of M01 (2026-08-29 follow-up to CP14's position-only
reconciliation): today's OrderRecord rows vs. broker.get_orders_today(),
matched by broker_order_id. See xillion/engine/reconciliation.py's module
docstring for exactly what's covered (order-level status/fill-quantity/
fill-price) vs. honestly not (per-FILL granularity, funds).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Order, OrderStatus, Side
from xillion.core.events import OrderType as OT
from xillion.db.models import BrokerClass, BrokerConnection, OrderRecord
from xillion.db.session import get_session_factory, init_db
from xillion.engine.reconciliation import run_reconciliation


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _seed_connection(name: str) -> int:
    unique = uuid4().hex
    factory = get_session_factory()
    async with factory() as session:
        bc = BrokerClass(
            name=f"Orders Recon Test Class {unique}",
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


async def _seed_order_record(
    connection_id: int,
    broker_order_id: str | None,
    status: str = "FILLED",
    filled_quantity: int = 65,
    avg_fill_price: float | None = 100.0,
    submitted_at: str | None = None,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            OrderRecord(
                id=str(uuid4()),
                broker_order_id=broker_order_id,
                broker_connection_id=connection_id,
                symbol="ORDERS_RECON_SYM",
                exchange="NSE",
                side="BUY",
                quantity=65,
                filled_quantity=filled_quantity,
                order_type="MARKET",
                status=status,
                avg_fill_price=avg_fill_price,
                submitted_at=submitted_at or _now_iso(),
                updated_at=_now_iso(),
            )
        )
        await session.commit()


def _broker_order(
    broker_order_id: str,
    status: OrderStatus = OrderStatus.FILLED,
    filled_quantity: int = 65,
    avg_fill_price: Decimal | None = Decimal("100.0"),
) -> Order:
    now = datetime.now(UTC)
    return Order(
        client_order_id=str(uuid4()),
        broker_order_id=broker_order_id,
        symbol="ORDERS_RECON_SYM",
        side=Side.BUY,
        quantity=65,
        order_type=OT.MARKET,
        status=status,
        submitted_at=now,
        updated_at=now,
        filled_quantity=filled_quantity,
        avg_fill_price=avg_fill_price,
    )


@pytest.mark.asyncio
async def test_matching_orders_are_clean():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker Clean")
    await _seed_order_record(conn_id, "BO-CLEAN-1")
    broker = DummyBroker()

    async def get_orders_today():
        return [_broker_order("BO-CLEAN-1")]

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker Clean", get_session_factory)
    assert result.status == "CLEAN"
    assert result.order_mismatches == []


@pytest.mark.asyncio
async def test_broker_only_order_is_flagged():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker BrokerOnly")
    broker = DummyBroker()

    async def get_orders_today():
        return [_broker_order("BO-BROKER-ONLY")]

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker BrokerOnly", get_session_factory)
    assert result.status == "DISCREPANCY"
    mismatch = next(m for m in result.order_mismatches if m.broker_order_id == "BO-BROKER-ONLY")
    assert mismatch.issue == "broker_only"
    _ = conn_id  # seeded so the connection lookup succeeds; no OrderRecord needed for this case


@pytest.mark.asyncio
async def test_internal_only_order_is_flagged():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker InternalOnly")
    await _seed_order_record(conn_id, "BO-INTERNAL-ONLY")
    broker = DummyBroker()

    async def get_orders_today():
        return []

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(
        broker, "Orders Recon Broker InternalOnly", get_session_factory
    )
    assert result.status == "DISCREPANCY"
    mismatch = next(m for m in result.order_mismatches if m.broker_order_id == "BO-INTERNAL-ONLY")
    assert mismatch.issue == "internal_only"


@pytest.mark.asyncio
async def test_status_mismatch_is_flagged():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker StatusMismatch")
    await _seed_order_record(conn_id, "BO-STATUS", status="PENDING")
    broker = DummyBroker()

    async def get_orders_today():
        return [_broker_order("BO-STATUS", status=OrderStatus.FILLED)]

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(
        broker, "Orders Recon Broker StatusMismatch", get_session_factory
    )
    assert result.status == "DISCREPANCY"
    mismatch = next(m for m in result.order_mismatches if m.broker_order_id == "BO-STATUS")
    assert mismatch.issue == "status_mismatch"
    assert mismatch.internal_status == "PENDING"
    assert mismatch.broker_status == "FILLED"


@pytest.mark.asyncio
async def test_fill_quantity_mismatch_is_flagged():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker FillQty")
    await _seed_order_record(conn_id, "BO-FILLQTY", filled_quantity=50)
    broker = DummyBroker()

    async def get_orders_today():
        return [_broker_order("BO-FILLQTY", filled_quantity=65)]

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker FillQty", get_session_factory)
    assert result.status == "DISCREPANCY"
    mismatch = next(m for m in result.order_mismatches if m.broker_order_id == "BO-FILLQTY")
    assert mismatch.issue == "fill_mismatch"
    assert mismatch.internal_filled_qty == 50
    assert mismatch.broker_filled_qty == 65


@pytest.mark.asyncio
async def test_fill_price_mismatch_beyond_tolerance_is_flagged():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker FillPrice")
    await _seed_order_record(conn_id, "BO-FILLPRICE", avg_fill_price=100.0)
    broker = DummyBroker()

    async def get_orders_today():
        return [_broker_order("BO-FILLPRICE", avg_fill_price=Decimal("105.0"))]

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker FillPrice", get_session_factory)
    assert result.status == "DISCREPANCY"
    assert any(m.broker_order_id == "BO-FILLPRICE" for m in result.order_mismatches)


@pytest.mark.asyncio
async def test_fill_price_mismatch_within_tolerance_is_not_flagged():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker FillPriceOk")
    await _seed_order_record(conn_id, "BO-FILLPRICE-OK", avg_fill_price=100.0)
    broker = DummyBroker()

    async def get_orders_today():
        return [_broker_order("BO-FILLPRICE-OK", avg_fill_price=Decimal("100.005"))]

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(
        broker, "Orders Recon Broker FillPriceOk", get_session_factory
    )
    assert result.status == "CLEAN"
    assert result.order_mismatches == []


@pytest.mark.asyncio
async def test_orders_from_a_different_broker_connection_are_not_compared():
    """A second broker's own order (different BrokerConnection) with an id
    this run's broker doesn't know about must not leak into THIS run's
    mismatch list -- each reconciliation run is scoped to its own broker
    connection."""
    await init_db()
    other_conn_id = await _seed_connection("Orders Recon Broker Other")
    await _seed_order_record(other_conn_id, "BO-OTHER-BROKER")

    await _seed_connection("Orders Recon Broker Isolated")
    broker = DummyBroker()

    async def get_orders_today():
        return []

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker Isolated", get_session_factory)
    assert result.status == "CLEAN"
    assert not any(m.broker_order_id == "BO-OTHER-BROKER" for m in result.order_mismatches)


@pytest.mark.asyncio
async def test_orders_from_a_prior_day_are_ignored():
    await init_db()
    conn_id = await _seed_connection("Orders Recon Broker OldOrder")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await _seed_order_record(conn_id, "BO-YESTERDAY", submitted_at=yesterday)
    broker = DummyBroker()

    async def get_orders_today():
        return []

    broker.get_orders_today = get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker OldOrder", get_session_factory)
    assert result.status == "CLEAN"
    assert not any(m.broker_order_id == "BO-YESTERDAY" for m in result.order_mismatches)


@pytest.mark.asyncio
async def test_order_fetch_failure_forces_discrepancy_even_with_clean_positions():
    await init_db()
    await _seed_connection("Orders Recon Broker FetchFail")
    broker = DummyBroker()

    async def failing_get_orders_today():
        raise RuntimeError("orders endpoint down")

    broker.get_orders_today = failing_get_orders_today

    result = await run_reconciliation(broker, "Orders Recon Broker FetchFail", get_session_factory)
    assert result.status == "DISCREPANCY"
    assert any("order fetch failed" in n for n in result.notes)


@pytest.mark.asyncio
async def test_missing_broker_connection_row_does_not_force_discrepancy():
    """No BrokerConnection is seeded for this broker_name at all -- e.g. a
    broker used in a test or never formally registered. The order check
    should skip cleanly (with a note) rather than treat that as evidence
    of a problem; position reconciliation is what actually ran here."""
    await init_db()
    broker = DummyBroker()  # get_positions() -> [], get_orders_today() -> []

    result = await run_reconciliation(
        broker, "Orders Recon Broker Never Registered", get_session_factory
    )
    assert result.status == "CLEAN"
    assert any("order check skipped" in n for n in result.notes)
