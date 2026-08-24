"""
Signal history API (CP4) -- read access to signal_log, the alert-mode
forward-test dataset. No consumers existed before CP4 (no API, no UI).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, SignalLog, StrategyInstance

router = APIRouter(prefix="/signals", tags=["signals"])


def _row_dict(s: SignalLog, instance_name: Optional[str]) -> dict:
    return {
        "id": s.id,
        "strategy_instance_id": s.strategy_instance_id,
        "strategy_instance_name": instance_name,
        "ts": s.ts,
        "underlying_symbol": s.underlying_symbol,
        "resolved_tradingsymbol": s.resolved_tradingsymbol,
        "signal_type": s.signal_type,
        "tag": s.tag,
        "parent_signal_id": s.parent_signal_id,
        "target_price": float(s.target_price) if s.target_price is not None else None,
        "stop_loss_price": float(s.stop_loss_price) if s.stop_loss_price is not None else None,
        "side": s.side,
        "price": float(s.price) if s.price is not None else None,
        "message": s.message,
        "mode": s.mode,
        "notified": s.notified,
        "notified_at": s.notified_at,
    }


@router.get("")
async def list_signals(
    instance_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Recent signals, newest first. An ENTER row with no EXIT referencing
    it (via parent_signal_id) is still open."""
    stmt = select(SignalLog, StrategyInstance.name).join(
        StrategyInstance, SignalLog.strategy_instance_id == StrategyInstance.id, isouter=True
    )
    if instance_id:
        stmt = stmt.where(SignalLog.strategy_instance_id == instance_id)
    stmt = stmt.order_by(SignalLog.id.desc()).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()
    return {"signals": [_row_dict(s, name) for s, name in rows]}
