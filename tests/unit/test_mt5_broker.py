"""
MT5FundingPipsBroker (Gold Lane B1) -- the poll/report queue mechanics,
since there's no real MT5 terminal in this environment (same "structurally
correct, unverified end-to-end" position as brokers/dhan.py before real
credentials existed). See the module's own docstring for why this broker
looks nothing like zerodha.py/dhan.py.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from brokers.mt5_funding_pips import (
    MT5FundingPipsBroker,
    _lots_to_quantity,
    _quantity_to_lots,
)
from xillion.core.events import Order, OrderRequest, OrderStatus, OrderType, Side, Tick
from xillion.db.session import get_session_factory, init_db


async def _broker(name: str = "MT5 Test") -> MT5FundingPipsBroker:
    await init_db()
    b = MT5FundingPipsBroker(connection_name=name)
    await b.connect({})
    return b


def test_micro_lot_conversion_round_trips():
    assert _quantity_to_lots(100) == Decimal("1")
    assert _quantity_to_lots(1) == Decimal("0.01")
    assert _lots_to_quantity(Decimal("0.10")) == 10
    assert _lots_to_quantity(Decimal("2.5")) == 250


@pytest.mark.asyncio
async def test_place_order_queues_a_pending_row_and_returns_submitted():
    broker = await _broker()
    req = OrderRequest(
        symbol="XAUUSD",
        side=Side.BUY,
        quantity=10,  # 0.10 lot
        order_type=OrderType.MARKET,
    )
    order = await broker.place_order(req)

    assert order.status == OrderStatus.SUBMITTED
    assert order.client_order_id == req.client_order_id

    fetched = await broker.get_order(req.client_order_id)
    assert fetched.symbol == "XAUUSD"
    assert fetched.quantity == 10  # round-trips through the lots conversion unchanged
    assert fetched.status == OrderStatus.SUBMITTED


@pytest.mark.asyncio
async def test_poll_endpoint_shape_matches_what_the_broker_queued():
    """Not a full FastAPI TestClient round-trip (no real HTTP layer needed
    to prove the contract) -- exercises the exact DB read/mutate logic
    xillion/api/mt5_bridge.py's poll() handler performs, so a real bridge
    polling this would see a PLACE action for a fresh order and it flips to
    ACKED so a second poll doesn't return it again."""
    from sqlalchemy import select

    broker = await _broker("MT5 Poll Test")
    req = OrderRequest(symbol="XAUUSD", side=Side.SELL, quantity=100, order_type=OrderType.MARKET)
    await broker.place_order(req)

    from xillion.db.models import MT5PendingOrder

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(MT5PendingOrder).where(
                MT5PendingOrder.broker_connection_name == "MT5 Poll Test",
                MT5PendingOrder.status == "PENDING",
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].client_order_id == req.client_order_id
        rows[0].status = "ACKED"
        await db.commit()

    async with factory() as db:
        result = await db.execute(
            select(MT5PendingOrder).where(
                MT5PendingOrder.broker_connection_name == "MT5 Poll Test",
                MT5PendingOrder.status == "PENDING",
            )
        )
        assert result.scalars().all() == []  # not returned a second time


@pytest.mark.asyncio
async def test_cancel_order_marks_cancel_requested_not_deleted():
    broker = await _broker("MT5 Cancel Test")
    req = OrderRequest(symbol="XAUUSD", side=Side.BUY, quantity=50, order_type=OrderType.MARKET)
    await broker.place_order(req)

    ok = await broker.cancel_order(req.client_order_id)
    assert ok is True

    row = await broker._get_pending_order(req.client_order_id)
    assert row.status == "CANCEL_REQUESTED"


@pytest.mark.asyncio
async def test_cancel_order_returns_false_for_unknown_id():
    broker = await _broker("MT5 Cancel Unknown")
    assert await broker.cancel_order("does-not-exist") is False


@pytest.mark.asyncio
async def test_cancel_order_returns_false_once_already_filled():
    broker = await _broker("MT5 Cancel Filled")
    req = OrderRequest(symbol="XAUUSD", side=Side.BUY, quantity=10, order_type=OrderType.MARKET)
    await broker.place_order(req)
    row = await broker._get_pending_order(req.client_order_id)
    row.status = "FILLED"

    factory = get_session_factory()
    async with factory() as db:
        db.add(row)
        await db.merge(row)
        await db.commit()

    assert await broker.cancel_order(req.client_order_id) is False


@pytest.mark.asyncio
async def test_ingest_tick_and_order_update_reach_the_live_streams():
    broker = await _broker("MT5 Stream Test")

    await broker.ingest_tick(Tick(symbol="XAUUSD", ltp=Decimal("2650.5"), ltt=datetime.now(UTC)))
    stream = broker.tick_stream()
    tick = await stream.__anext__()
    assert tick.symbol == "XAUUSD"
    assert tick.ltp == Decimal("2650.5")

    order = Order(
        client_order_id="abc",
        symbol="XAUUSD",
        side=Side.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        status=OrderStatus.FILLED,
        submitted_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await broker.ingest_order_update(order)
    gen = broker.order_event_stream()
    received = await gen.__anext__()
    assert received.client_order_id == "abc"
    assert received.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_healthcheck_false_when_no_bridge_has_ever_reported():
    broker = await _broker("MT5 Health Never")
    assert await broker.healthcheck() is False


@pytest.mark.asyncio
async def test_healthcheck_true_when_bridge_reported_recently():
    from xillion.db.models import MT5BridgeState

    broker = await _broker("MT5 Health Fresh")
    factory = get_session_factory()
    async with factory() as db:
        db.add(
            MT5BridgeState(
                broker_connection_name="MT5 Health Fresh",
                positions_json="[]",
                margins_json="{}",
                holdings_json="[]",
                updated_at=datetime.now(UTC).isoformat(),
            )
        )
        await db.commit()

    assert await broker.healthcheck() is True


@pytest.mark.asyncio
async def test_healthcheck_false_once_stale():
    from xillion.db.models import MT5BridgeState

    broker = await _broker("MT5 Health Stale")
    factory = get_session_factory()
    stale_ts = (datetime.now(UTC) - timedelta(seconds=999)).isoformat()
    async with factory() as db:
        db.add(
            MT5BridgeState(
                broker_connection_name="MT5 Health Stale",
                positions_json="[]",
                margins_json="{}",
                holdings_json="[]",
                updated_at=stale_ts,
            )
        )
        await db.commit()

    assert await broker.healthcheck() is False


@pytest.mark.asyncio
async def test_get_positions_reads_bridge_reported_snapshot():
    import json

    from xillion.db.models import MT5BridgeState

    broker = await _broker("MT5 Positions Test")
    factory = get_session_factory()
    async with factory() as db:
        db.add(
            MT5BridgeState(
                broker_connection_name="MT5 Positions Test",
                positions_json=json.dumps(
                    [
                        {
                            "symbol": "XAUUSD",
                            "quantity": 100,
                            "avg_price": "2650.00",
                            "last_price": "2655.00",
                            "realised_pnl": "0",
                            "unrealised_pnl": "5.00",
                        }
                    ]
                ),
                margins_json="{}",
                holdings_json="[]",
                updated_at=datetime.now(UTC).isoformat(),
            )
        )
        await db.commit()

    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "XAUUSD"
    assert positions[0].quantity == 100
    assert positions[0].unrealised_pnl == Decimal("5.00")


@pytest.mark.asyncio
async def test_get_history_not_implemented_is_explicit_not_silent():
    broker = await _broker("MT5 History Test")
    with pytest.raises(NotImplementedError):
        await broker.get_history("XAUUSD", "1d", None, None)
