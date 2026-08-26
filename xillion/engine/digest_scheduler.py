"""
Schedules the daily/weekly maintenance digest (CP10) -- see
xillion/engine/digest.py for what actually goes into the message. Same
sleep-until-next-fixed-clock-time pattern as xillion/main.py's
_daily_token_refresh/_daily_instrument_refresh, deliberately unlike
market_scheduler.py's transition-detection polling: a digest is a calendar
event ("every day at 4pm"), not a reaction to market state, so there's
nothing to detect a transition on.
"""

import asyncio
import zoneinfo
from datetime import UTC, datetime, timedelta

import structlog

from xillion.engine.digest import build_digest, format_digest_message

logger = structlog.get_logger(__name__)

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

DAILY_HOUR = 16  # 4pm IST -- after the 3:30pm market close
DAILY_MINUTE = 0
WEEKLY_WEEKDAY = 6  # Sunday (Python: Monday=0 .. Sunday=6)
WEEKLY_HOUR = 18
WEEKLY_MINUTE = 0


async def _send_digest(app, since: datetime, period_label: str) -> None:
    from xillion.db.session import get_session_factory

    report = await build_digest(get_session_factory(), since=since, period_label=period_label)
    message = format_digest_message(report)
    telegram = getattr(app.state, "telegram", None)
    if telegram is not None:
        await telegram.send(message)
    logger.info(
        "digest sent",
        period=period_label,
        trade_count=report.trade_count,
        total_pnl=report.total_pnl,
        error_count=report.error_count,
    )


async def run_daily_digest(app) -> None:
    while True:
        now = datetime.now(IST)
        target = now.replace(hour=DAILY_HOUR, minute=DAILY_MINUTE, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await _send_digest(
                app, since=datetime.now(UTC) - timedelta(hours=24), period_label="Daily"
            )
        except Exception as exc:
            logger.error("daily digest failed", error=str(exc))


async def run_weekly_digest(app) -> None:
    while True:
        now = datetime.now(IST)
        days_ahead = (WEEKLY_WEEKDAY - now.weekday()) % 7
        target = (now + timedelta(days=days_ahead)).replace(
            hour=WEEKLY_HOUR, minute=WEEKLY_MINUTE, second=0, microsecond=0
        )
        if target <= now:
            target += timedelta(days=7)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await _send_digest(
                app, since=datetime.now(UTC) - timedelta(days=7), period_label="Weekly"
            )
        except Exception as exc:
            logger.error("weekly digest failed", error=str(exc))
