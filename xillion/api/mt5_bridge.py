"""
MT5 bridge API — the hand-off point between brokers/mt5_funding_pips.py
(runs inside this backend) and mt5_bridge/bridge.py (a separate local
process, run on the machine with the real MT5 terminal open). See both
files' module docstrings for why this exists at all instead of a normal
broker plugin.

Auth: same session-cookie auth as every other endpoint (get_current_user)
-- the bridge logs in as a real xillion user (mt5_bridge/bridge.py's own
XILLION_MT5_BRIDGE_USERNAME/PASSWORD/TOTP_CODE env vars), same pattern
xillion-mcp already uses, not a separate auth mechanism invented for this.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from xillion.api.deps import get_current_user
from xillion.core.events import Tick
from xillion.db.models import AppUser, MT5BridgeState, MT5BridgeTick, MT5PendingOrder
from xillion.db.session import get_session_factory

router = APIRouter(prefix="/mt5-bridge", tags=["mt5-bridge"])


def _broker(request: Request, connection_name: str):
    instances = getattr(request.app.state, "broker_instances", {})
    info = instances.get(connection_name)
    if info is None:
        raise HTTPException(404, f"no connected broker named '{connection_name}'")
    return info["instance"]


@router.get("/poll")
async def poll(connection_name: str, request: Request, user: AppUser = Depends(get_current_user)):
    """The bridge calls this every cycle: what orders need placing/
    cancelling, and what symbols need a live quote. PENDING orders are
    marked ACKED here so a slow bridge cycle doesn't get the same order
    twice; if the bridge crashes after acking but before executing, that
    order needs a human to check MT5 directly -- same "can't silently
    retry a real order" caution as every other broker in this codebase."""
    broker = _broker(request, connection_name)
    factory = get_session_factory()

    async with factory() as db:
        result = await db.execute(
            select(MT5PendingOrder).where(
                MT5PendingOrder.broker_connection_name == connection_name,
                MT5PendingOrder.status.in_(["PENDING", "CANCEL_REQUESTED"]),
            )
        )
        rows = result.scalars().all()
        orders_out = []
        for row in rows:
            orders_out.append(
                {
                    "client_order_id": row.client_order_id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity_lots": row.quantity,
                    "order_type": row.order_type,
                    "price": row.price,
                    "stop_loss": row.stop_loss,
                    "take_profit": row.take_profit,
                    "action": "CANCEL" if row.status == "CANCEL_REQUESTED" else "PLACE",
                }
            )
            if row.status == "PENDING":
                row.status = "ACKED"
                row.updated_at = datetime.now(UTC).isoformat()
        await db.commit()

    return {"orders": orders_out, "subscribe_symbols": broker.subscribed_symbols()}


class ReportFill(BaseModel):
    client_order_id: str
    status: str  # FILLED | REJECTED | CANCELLED
    mt5_ticket_id: str | None = None
    avg_fill_price: str | None = None
    error_message: str | None = None


class ReportTick(BaseModel):
    symbol: str
    ltp: str
    bid: str | None = None
    ask: str | None = None


class ReportPosition(BaseModel):
    symbol: str
    quantity: int
    avg_price: str
    last_price: str
    realised_pnl: str = "0"
    unrealised_pnl: str = "0"


class ReportBody(BaseModel):
    fills: list[ReportFill] = []
    ticks: list[ReportTick] = []
    positions: list[ReportPosition] = []
    margins: dict = {}


@router.post("/report")
async def report(
    connection_name: str,
    body: ReportBody,
    request: Request,
    user: AppUser = Depends(get_current_user),
):
    """The bridge calls this after each poll cycle to report fills, live
    quotes, and the account snapshot. Fills/ticks are also pushed straight
    into the live broker instance's in-memory queues (same process, no
    extra round-trip) so a running strategy sees them immediately rather
    than waiting for its own next DB read."""
    broker = _broker(request, connection_name)
    factory = get_session_factory()
    now = datetime.now(UTC).isoformat()

    async with factory() as db:
        for fill in body.fills:
            result = await db.execute(
                select(MT5PendingOrder).where(
                    MT5PendingOrder.client_order_id == fill.client_order_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                continue  # stale report for an order we no longer track -- ignore, don't crash
            row.status = fill.status
            row.mt5_ticket_id = fill.mt5_ticket_id
            row.avg_fill_price = fill.avg_fill_price
            row.error_message = fill.error_message
            row.updated_at = now

        for tick in body.ticks:
            existing = await db.get(MT5BridgeTick, tick.symbol)
            if existing is None:
                db.add(
                    MT5BridgeTick(
                        symbol=tick.symbol,
                        broker_connection_name=connection_name,
                        ltp=tick.ltp,
                        bid=tick.bid,
                        ask=tick.ask,
                        updated_at=now,
                    )
                )
            else:
                existing.ltp = tick.ltp
                existing.bid = tick.bid
                existing.ask = tick.ask
                existing.updated_at = now

        if body.positions or body.margins:
            import json

            state = await db.get(MT5BridgeState, connection_name)
            positions_json = json.dumps([p.model_dump() for p in body.positions])
            margins_json = json.dumps(body.margins)
            if state is None:
                db.add(
                    MT5BridgeState(
                        broker_connection_name=connection_name,
                        positions_json=positions_json,
                        margins_json=margins_json,
                        holdings_json="[]",
                        updated_at=now,
                    )
                )
            else:
                state.positions_json = positions_json
                state.margins_json = margins_json
                state.updated_at = now

        await db.commit()

    for fill in body.fills:
        pending = await broker._get_pending_order(fill.client_order_id)
        if pending is not None:
            await broker.ingest_order_update(broker._row_to_order(pending))

    for tick in body.ticks:
        await broker.ingest_tick(
            Tick(
                symbol=tick.symbol,
                ltp=_dec(tick.ltp),
                ltt=datetime.now(UTC),
                bid=_dec(tick.bid) if tick.bid else None,
                ask=_dec(tick.ask) if tick.ask else None,
            )
        )

    return {"status": "ok"}


def _dec(value: str):
    from decimal import Decimal

    return Decimal(value)
