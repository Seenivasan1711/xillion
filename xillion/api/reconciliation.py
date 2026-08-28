"""
M01 reconciliation reports: list + manual sign-off (CP14's own design says a
non-CLEAN day "blocks tomorrow's trading, require manual sign-off to
resume" -- xillion/engine/eod_scheduler.py does the blocking, this is the
sign-off). See docs/architecture/automation-platform-spec/08-JOBS-POSTMARKET.md M01.
"""

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, ReconciliationReport
from xillion.db.session import get_session_factory
from xillion.engine.reconciliation import unresolved_blocker_exists

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


def _serialize(r: ReconciliationReport) -> dict:
    return {
        "id": r.id,
        "trading_date": r.trading_date,
        "broker_name": r.broker_name,
        "checked_at": r.checked_at,
        "status": r.status,
        "position_mismatches": json.loads(r.position_mismatches_json),
        "eod_open_positions": json.loads(r.eod_open_positions_json),
        "notes": json.loads(r.notes_json),
        "acknowledged": r.acknowledged,
        "acknowledged_at": r.acknowledged_at,
        "acknowledged_by": r.acknowledged_by,
    }


@router.get("/reports")
async def list_reports(
    limit: int = 20,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(
        select(ReconciliationReport).order_by(ReconciliationReport.id.desc()).limit(limit)
    )
    reports = result.scalars().all()
    return {"reports": [_serialize(r) for r in reports]}


@router.post("/reports/{report_id}/acknowledge")
async def acknowledge_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    from datetime import UTC, datetime

    report = await db.get(ReconciliationReport, report_id)
    if report is None:
        raise HTTPException(404, "Reconciliation report not found")

    report.acknowledged = True
    report.acknowledged_at = datetime.now(UTC).isoformat()
    report.acknowledged_by = user.username
    await db.commit()
    logger.info(
        "reconciliation report acknowledged",
        report_id=report_id,
        trading_date=report.trading_date,
        status=report.status,
        user=user.username,
    )

    # Re-run the same check the startup gate uses (xillion/engine/
    # reconciliation.py) -- only resume if the latest trading day's reports
    # are now all CLEAN or acknowledged. A second broker's still-open
    # DISCREPANCY on the same day correctly keeps the gate up.
    resumed = False
    if not await unresolved_blocker_exists(get_session_factory):
        # RiskManager.pause_trading()/resume_trading() is a single global
        # flag with no "who paused it" tracking -- as of this writing, M01's
        # gate (eod_scheduler.py) is its only caller, so resuming here is
        # safe. If another pause reason is ever wired to the same flag,
        # this needs a reason-aware gate instead of a bare boolean.
        risk = getattr(request.app.state, "risk", None)
        if risk is not None:
            risk.resume_trading()
            resumed = True
            logger.info("trading resumed -- all reconciliation reports for the day signed off")

    return {"acknowledged": True, "trading_resumed": resumed}
