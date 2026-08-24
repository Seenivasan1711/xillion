"""
Read the persisted system log (CP9) -- see xillion/observability/log_capture.py
for how entries get here. Gives the Logs page (frontend/src/pages/Logs.tsx)
history to load on mount; the live tail still comes over the "log" WebSocket
event the same capture pipeline broadcasts.
"""
import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, SystemLog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/logs", tags=["logs"])

_LEVEL_GROUPS = {
    "err": ("error", "critical"),
    "warn": ("warning", "warn"),
    "info": ("info",),
    "debug": ("debug",),
}


def _row_dict(row: SystemLog) -> dict:
    try:
        fields = json.loads(row.fields_json)
    except (TypeError, ValueError):
        fields = {}
    return {
        "id": row.id,
        "ts": row.ts,
        "level": row.level,
        "source": row.source,
        "message": row.message,
        "fields": fields,
    }


@router.get("")
async def list_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    level: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Most recent `limit` entries, oldest first (matches how the frontend
    appends to its scrollback and scrolls to the bottom)."""
    query = select(SystemLog).order_by(SystemLog.id.desc()).limit(limit)
    if level and level in _LEVEL_GROUPS:
        query = query.where(SystemLog.level.in_(_LEVEL_GROUPS[level]))
    result = await db.execute(query)
    rows = list(reversed(result.scalars().all()))
    return {"logs": [_row_dict(r) for r in rows]}
