"""
Broker reconciliation (CP14 / automation-platform-spec 08-JOBS-POSTMARKET.md
M01): "The most important post-market job. Divergence between our state and
the broker's is the root cause of most serious incidents."

Scope note: the full spec reconciles orders, fills, positions, AND funds
(broker P&L vs computed P&L). This implementation covers POSITIONS --
the check the spec itself calls the sharpest ("must be FLAT at EOD for
intraday strategies; any open position -> P0"), and the one X02 (square-off,
xillion/engine/square_off.py) is specifically meant to have already
resolved, so M01 here is the independent verification that X02 actually
worked. Orders/fills reconciliation and funds reconciliation are NOT done
here -- funds specifically needs a "today's realised P&L" broker capability
the Broker ABC doesn't expose today (get_margins() isn't that), and
orders/fills reconciliation is a larger, separate piece of work. Both are
honestly left for a follow-up, not silently skipped.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select

from xillion.core.broker_base import Broker
from xillion.db.models import PositionRecord
from xillion.db.models import ReconciliationReport as ReconciliationReportRecord

logger = structlog.get_logger(__name__)


@dataclass
class PositionMismatch:
    symbol: str
    issue: str  # "broker_only" | "internal_only" | "quantity_mismatch"
    broker_qty: int | None = None
    internal_qty: int | None = None


@dataclass
class ReconciliationResult:
    status: str  # CLEAN | DISCREPANCY | FAILED
    trading_date: date
    checked_at: datetime
    position_mismatches: list[PositionMismatch] = field(default_factory=list)
    eod_open_positions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


async def run_reconciliation(
    broker: Broker,
    broker_name: str,
    db_factory,
    notify: Callable[[str, str, str], Awaitable[None]] | None = None,
) -> ReconciliationResult:
    """Compares the broker's live positions against xillion's own
    PositionRecord table for any strategy still showing a nonzero
    quantity. Persists the result and alerts on anything but CLEAN.
    Never raises -- a broker fetch failure is a FAILED report, not an
    exception, since this job has to produce a record either way."""
    trading_date = _now().date()

    try:
        broker_positions = await broker.get_positions()
    except Exception as exc:
        logger.critical("M01: broker position fetch failed", error=str(exc))
        result = ReconciliationResult(
            status="FAILED",
            trading_date=trading_date,
            checked_at=_now(),
            notes=[f"broker fetch failed: {exc}"],
        )
        await _persist(db_factory, broker_name, result)
        await _alert(
            notify, "M01 RECONCILIATION FAILED", f"Could not reach broker: {exc}", "critical"
        )
        return result

    broker_by_symbol = {p.symbol: p.quantity for p in broker_positions if p.quantity != 0}

    async with db_factory()() as session:
        db_result = await session.execute(
            select(PositionRecord).where(PositionRecord.quantity != 0)
        )
        internal_by_symbol = {r.symbol: r.quantity for r in db_result.scalars().all()}

    all_symbols = set(broker_by_symbol) | set(internal_by_symbol)
    mismatches: list[PositionMismatch] = []
    for symbol in sorted(all_symbols):
        b_qty = broker_by_symbol.get(symbol)
        i_qty = internal_by_symbol.get(symbol)
        if b_qty is not None and i_qty is None:
            mismatches.append(PositionMismatch(symbol, "broker_only", broker_qty=b_qty))
        elif i_qty is not None and b_qty is None:
            mismatches.append(PositionMismatch(symbol, "internal_only", internal_qty=i_qty))
        elif b_qty != i_qty:
            mismatches.append(
                PositionMismatch(symbol, "quantity_mismatch", broker_qty=b_qty, internal_qty=i_qty)
            )

    # EOD rule: for intraday strategies, ANY open position -- broker or
    # internal, matched or not -- is itself a discrepancy. This is the
    # independent check that X02 actually flattened everything.
    eod_open = sorted(all_symbols)

    status = "CLEAN" if not mismatches and not eod_open else "DISCREPANCY"
    result = ReconciliationResult(
        status=status,
        trading_date=trading_date,
        checked_at=_now(),
        position_mismatches=mismatches,
        eod_open_positions=eod_open,
    )

    await _persist(db_factory, broker_name, result)

    if status != "CLEAN":
        detail = (
            f"{len(mismatches)} mismatch(es), {len(eod_open)} position(s) open at EOD: {eod_open}"
        )
        logger.critical("M01: reconciliation DISCREPANCY", detail=detail)
        await _alert(notify, "M01 RECONCILIATION: DISCREPANCY", detail, "critical")
    else:
        logger.info("M01: reconciliation clean")

    return result


async def _persist(db_factory, broker_name: str, result: ReconciliationResult) -> None:
    try:
        async with db_factory()() as session:
            session.add(
                ReconciliationReportRecord(
                    trading_date=result.trading_date.isoformat(),
                    broker_name=broker_name,
                    checked_at=result.checked_at.isoformat(),
                    status=result.status,
                    position_mismatches_json=json.dumps(
                        [
                            {
                                "symbol": m.symbol,
                                "issue": m.issue,
                                "broker_qty": m.broker_qty,
                                "internal_qty": m.internal_qty,
                            }
                            for m in result.position_mismatches
                        ]
                    ),
                    eod_open_positions_json=json.dumps(result.eod_open_positions),
                    notes_json=json.dumps(result.notes),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.error("M01: failed to persist reconciliation report", error=str(exc))


async def unresolved_blocker_exists(db_factory) -> bool:
    """True if the most recent trading day that has any reconciliation
    report includes a non-CLEAN, not-yet-acknowledged one. Used at process
    startup (main.py) so a restart can't silently clear an unresolved M01
    DISCREPANCY -- the in-memory RiskManager.pause_trading() from
    eod_scheduler.py doesn't survive a restart on its own, but the DB
    record does, and the gate must survive until someone actually signs
    off (xillion/api/reconciliation.py)."""
    async with db_factory()() as session:
        latest_date_result = await session.execute(
            select(ReconciliationReportRecord.trading_date)
            .order_by(ReconciliationReportRecord.trading_date.desc())
            .limit(1)
        )
        latest_date = latest_date_result.scalar_one_or_none()
        if latest_date is None:
            return False
        reports_result = await session.execute(
            select(ReconciliationReportRecord).where(
                ReconciliationReportRecord.trading_date == latest_date
            )
        )
        reports = reports_result.scalars().all()
        return any(r.status != "CLEAN" and not r.acknowledged for r in reports)


async def _alert(notify, title: str, body: str, severity: str) -> None:
    if notify is None:
        return
    try:
        await notify(title, body, severity)
    except Exception as exc:
        logger.error("M01: alert failed", error=str(exc))
