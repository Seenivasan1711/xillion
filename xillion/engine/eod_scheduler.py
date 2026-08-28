"""
Fires X02 (square-off) and M01 (reconciliation) at fixed clock times daily
(CP14). Same sleep-until-next-fixed-clock-time pattern as digest_scheduler.py
-- these are calendar events ("every trading day at 15:15/15:45 IST"), not
reactions to market-open/close state, so market_scheduler.py's transition-
detection polling doesn't fit here.

Deliberately separate loops, not one combined job: X02 must run even if
M01's reconciliation logic has a bug, and M01's "was X02 actually clean"
check is only meaningful if it runs strictly after X02 has had time to act
-- coupling them into one function risks a failure in one silently taking
out the other, which is exactly the fragility this pair of jobs exists to
guard against everywhere else in the system.
"""

import asyncio
import zoneinfo
from datetime import datetime, time, timedelta

import structlog

from xillion.core.broker_base import Broker
from xillion.core.market_calendar import is_market_open
from xillion.engine.reconciliation import run_reconciliation
from xillion.engine.square_off import run_square_off

logger = structlog.get_logger(__name__)

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

SQUARE_OFF_TIME = time(15, 15)  # Lane A -- automation-platform-spec X02
RECONCILIATION_TIME = time(15, 45)  # Lane A -- automation-platform-spec M01


def _next_occurrence(now: datetime, target: time) -> datetime:
    candidate = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def _connected_brokers(app) -> list[tuple[str, Broker]]:
    """(name, broker instance) for every currently-connected broker --
    X02/M01 run against whatever's actually connected, not a fixed list."""
    out = []
    for name, info in getattr(app.state, "broker_instances", {}).items():
        instance = info.get("instance") if isinstance(info, dict) else None
        if instance is not None:
            out.append((name, instance))
    return out


async def run_square_off_scheduler(app) -> None:
    """Runs forever as a background task. Skips a trading holiday/weekend
    automatically -- is_market_open() already encodes the calendar, so if
    the market never opened today there's nothing to square off."""
    while True:
        now = datetime.now(IST)
        target = _next_occurrence(now, SQUARE_OFF_TIME)
        await asyncio.sleep((target - now).total_seconds())
        if not is_market_open(datetime.now(IST).replace(hour=12, minute=0)):
            # Checked at midday IST on the target's own date -- a holiday
            # has no open session at all, so there's nothing to flatten.
            logger.info("X02: skipped -- not a trading day")
            continue
        try:
            notifier = getattr(app.state, "telegram", None)
            for name, broker in await _connected_brokers(app):
                report = await run_square_off(broker, notify=notifier.alert if notifier else None)
                logger.info("X02 square-off ran", broker=name, status=report.status)
        except Exception as exc:
            logger.error("X02 scheduler tick failed", error=str(exc))


async def run_reconciliation_tick(app) -> None:
    """One M01 run across every connected broker, plus the trading gate
    (08-JOBS-POSTMARKET.md M01: a non-CLEAN day "blocks tomorrow's trading,
    require manual sign-off to resume"). Split out from the scheduler loop
    below so it's directly testable without the sleep-until-clock-time
    wrapper -- see tests/unit/test_eod_scheduler.py."""
    from xillion.db.session import get_session_factory

    notifier = getattr(app.state, "telegram", None)
    risk = getattr(app.state, "risk", None)
    any_not_clean = False
    for name, broker in await _connected_brokers(app):
        result = await run_reconciliation(
            broker,
            broker_name=name,
            db_factory=get_session_factory,
            notify=notifier.alert if notifier else None,
        )
        logger.info("M01 reconciliation ran", broker=name, status=result.status)
        if result.status != "CLEAN":
            any_not_clean = True
    # pause_trading() is idempotent -- safe to call again if already paused.
    if any_not_clean and risk is not None:
        risk.pause_trading()
        logger.critical("M01: trading paused pending manual reconciliation sign-off")
        if notifier:
            await notifier.alert(
                "Trading paused",
                "M01 reconciliation was not CLEAN -- new orders are blocked until "
                "you acknowledge the report (Settings -> Risk -> Reconciliation).",
                "critical",
            )


async def run_reconciliation_scheduler(app) -> None:
    while True:
        now = datetime.now(IST)
        target = _next_occurrence(now, RECONCILIATION_TIME)
        await asyncio.sleep((target - now).total_seconds())
        if not is_market_open(datetime.now(IST).replace(hour=12, minute=0)):
            logger.info("M01: skipped -- not a trading day")
            continue
        try:
            await run_reconciliation_tick(app)
        except Exception as exc:
            logger.error("M01 scheduler tick failed", error=str(exc))
