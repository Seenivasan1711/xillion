"""
Trades endpoint — returns matched entry/exit trade pairs computed via FIFO
matching on FillRecord rows. One row = one complete round-trip trade.
"""
from collections import defaultdict, deque
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, FillRecord, OrderRecord, StrategyInstance

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


def _match_fills(rows: list[tuple]) -> list[dict[str, Any]]:
    """
    FIFO-match BUY and SELL fills into round-trip trades.

    Each row is (FillRecord, strategy_instance_id, instance_name, mode).
    Returns a list of matched trade dicts sorted by exit_ts descending.
    """
    # queues[key] = deque of open lots: {qty, price, ts, mode, instance_name}
    queues: dict[tuple, deque] = defaultdict(deque)
    matched: list[dict] = []

    for fill, instance_id, instance_name, mode in sorted(rows, key=lambda r: r[0].ts):
        key = (fill.symbol, instance_id or "")

        if fill.side == "BUY":
            queues[key].append({
                "qty": fill.quantity,
                "price": float(fill.price),
                "ts": fill.ts,
                "instance_name": instance_name or instance_id or "unknown",
                "mode": mode or "paper",
            })
        else:  # SELL closes a long position
            remaining = fill.quantity
            while remaining > 0 and queues[key]:
                entry = queues[key][0]
                close_qty = min(remaining, entry["qty"])
                pnl = (float(fill.price) - entry["price"]) * close_qty

                matched.append({
                    "id": f"{fill.order_id}-{int(close_qty)}",
                    "symbol": fill.symbol,
                    "instance_id": instance_id or "",
                    "instance_name": entry["instance_name"],
                    "side": "LONG",
                    "quantity": int(close_qty),
                    "entry_price": entry["price"],
                    "exit_price": float(fill.price),
                    "entry_ts": str(entry["ts"]),
                    "exit_ts": str(fill.ts),
                    "pnl": round(pnl, 2),
                    "mode": entry["mode"],
                })

                entry["qty"] -= close_qty
                remaining -= close_qty
                if entry["qty"] == 0:
                    queues[key].popleft()

    # Sort newest exit first
    matched.sort(key=lambda t: t["exit_ts"], reverse=True)
    return matched


@router.get("")
async def list_trades(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    symbol: Optional[str] = Query(None),
    instance_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
):
    # Load fills joined with their order + strategy instance
    stmt = (
        select(
            FillRecord,
            OrderRecord.strategy_instance_id,
            StrategyInstance.name,
            StrategyInstance.mode,
        )
        .join(OrderRecord, FillRecord.order_id == OrderRecord.id)
        .outerjoin(
            StrategyInstance,
            OrderRecord.strategy_instance_id == StrategyInstance.id,
        )
    )

    if symbol:
        stmt = stmt.where(FillRecord.symbol == symbol.upper())
    if instance_id:
        stmt = stmt.where(OrderRecord.strategy_instance_id == instance_id)
    if date_from:
        stmt = stmt.where(FillRecord.ts >= date_from)

    rows = (await db.execute(stmt)).all()

    all_trades = _match_fills(list(rows))
    total = len(all_trades)
    offset = (page - 1) * limit
    page_trades = all_trades[offset : offset + limit]

    return {"trades": page_trades, "total": total, "page": page, "limit": limit}
