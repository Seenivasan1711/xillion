"""
Strategy journal API (CP6) -- read the combined signal_log/backtest_trade
journal, manually annotate entries auto-classification can't honestly tag,
inspect a strategy's version history, and export to docs/strategies/<name>.md.
"""
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, JournalNote, StrategyClass, StrategyVersionHistory
from xillion.db.session import get_session_factory
from xillion.engine.journal import JournalEntry, build_journal
from xillion.engine.strategy_export import write_strategy_markdown

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/journal", tags=["journal"])


def _entry_dict(e: JournalEntry) -> dict:
    return {
        "source": e.source, "source_id": e.source_id,
        "strategy_instance_id": e.strategy_instance_id,
        "symbol": e.symbol, "side": e.side,
        "entry_price": e.entry_price, "exit_price": e.exit_price,
        "entry_ts": e.entry_ts, "exit_ts": e.exit_ts,
        "pnl": e.pnl, "target_price": e.target_price, "stop_loss_price": e.stop_loss_price,
        "outcome": e.outcome, "tag": e.tag,
    }


async def _notes_for(db: AsyncSession, entries: list[JournalEntry]) -> dict[tuple[str, str], dict]:
    if not entries:
        return {}
    keys = [(e.source, e.source_id) for e in entries]
    result = await db.execute(
        select(JournalNote).where(
            JournalNote.source.in_({k[0] for k in keys}),
            JournalNote.source_id.in_({k[1] for k in keys}),
        )
    )
    rows = result.scalars().all()
    return {(r.source, r.source_id): {"failure_mode": r.failure_mode, "change_made": r.change_made} for r in rows}


@router.get("")
async def get_journal(
    instance_id: Optional[str] = Query(None),
    strategy_name: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    strategy_class_id = None
    if strategy_name:
        cls = (await db.execute(select(StrategyClass).where(StrategyClass.name == strategy_name))).scalar_one_or_none()
        if cls is None:
            raise HTTPException(404, f"Strategy '{strategy_name}' not found")
        strategy_class_id = cls.id

    entries = await build_journal(
        get_session_factory(), strategy_instance_id=instance_id,
        strategy_class_id=strategy_class_id, limit=limit,
    )
    notes = await _notes_for(db, entries)

    rows = []
    for e in entries:
        d = _entry_dict(e)
        note = notes.get((e.source, e.source_id))
        if note:
            d["manual_failure_mode"] = note["failure_mode"]
            d["change_made"] = note["change_made"]
        rows.append(d)
    return {"entries": rows}


class JournalNoteRequest(BaseModel):
    source: str
    source_id: str
    failure_mode: Optional[str] = None
    change_made: Optional[str] = None


@router.put("/note")
async def put_journal_note(
    body: JournalNoteRequest,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    row = await db.get(JournalNote, (body.source, body.source_id))
    now = datetime.now(timezone.utc).isoformat()
    if row is None:
        row = JournalNote(source=body.source, source_id=body.source_id, updated_at=now)
        db.add(row)
    row.failure_mode = body.failure_mode
    row.change_made = body.change_made
    row.updated_at = now
    await db.commit()
    return {"saved": True}


@router.get("/versions/{strategy_name}")
async def get_strategy_versions(
    strategy_name: str,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    cls = (await db.execute(select(StrategyClass).where(StrategyClass.name == strategy_name))).scalar_one_or_none()
    if cls is None:
        raise HTTPException(404, f"Strategy '{strategy_name}' not found")
    rows = (await db.execute(
        select(StrategyVersionHistory)
        .where(StrategyVersionHistory.strategy_class_id == cls.id)
        .order_by(StrategyVersionHistory.id)
    )).scalars().all()
    return {
        "strategy_name": strategy_name,
        "versions": [
            {"version": r.version, "code_hash": r.code_hash, "recorded_at": r.recorded_at}
            for r in rows
        ],
    }


class ExportRequest(BaseModel):
    strategy_name: str


@router.post("/export")
async def export_journal(
    body: ExportRequest,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Write docs/strategies/<slug>.md's Failure log + Version history
    sections from real journal data. Sections 1-4 (rules, backtest/paper/
    live results) are untouched -- see xillion/engine/strategy_export.py."""
    cls = (await db.execute(select(StrategyClass).where(StrategyClass.name == body.strategy_name))).scalar_one_or_none()
    if cls is None:
        raise HTTPException(404, f"Strategy '{body.strategy_name}' not found")

    entries = await build_journal(get_session_factory(), strategy_class_id=cls.id, limit=500)
    notes = await _notes_for(db, entries)
    version_rows = (await db.execute(
        select(StrategyVersionHistory)
        .where(StrategyVersionHistory.strategy_class_id == cls.id)
        .order_by(StrategyVersionHistory.id)
    )).scalars().all()

    path = write_strategy_markdown(body.strategy_name, entries, notes, list(version_rows))
    logger.info("strategy markdown exported", strategy=body.strategy_name, path=str(path), entry_count=len(entries))
    return {"path": str(path.relative_to(path.parent.parent.parent)), "entry_count": len(entries)}
