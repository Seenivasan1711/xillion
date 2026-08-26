"""
Auto start/stop instances at market open/close (CP9).

Opt-in per instance via StrategyInstance.auto_start -- an instance not
marked for this is left entirely to manual start/stop, same as before this
scheduler existed.

Polls is_market_open() on an interval and reacts to open->closed and
closed->open transitions, rather than hardcoding 9:15/15:30 IST like
xillion.main's _daily_token_refresh does. is_market_open() already encodes
NSE's holiday calendar, so polling means this scheduler doesn't need any
holiday awareness of its own -- it just asks "is the market open right now"
and reacts when the answer changes.
"""

import asyncio
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from xillion.core.market_calendar import is_market_open
from xillion.db.models import StrategyInstance
from xillion.db.session import get_session_factory

logger = structlog.get_logger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 30


async def run_market_hours_scheduler(
    app: FastAPI, poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
) -> None:
    """Runs forever as a background task (see xillion/main.py's lifespan).
    Cancelled on shutdown like the other daily-refresh tasks there."""
    was_open: bool | None = None  # None = baseline not yet established
    while True:
        await asyncio.sleep(poll_interval_seconds)
        try:
            now_open = is_market_open(datetime.now(UTC))
            if was_open is None:
                # First observation after process start: just record where
                # we are, don't fire a start/stop based on an assumed prior
                # state we never actually saw.
                was_open = now_open
                continue
            if now_open and not was_open:
                await _start_auto_instances(app)
            elif not now_open and was_open:
                await _stop_auto_instances(app)
            was_open = now_open
        except Exception as exc:
            logger.error("market hours scheduler tick failed", error=str(exc))


async def _start_auto_instances(app: FastAPI) -> None:
    from xillion.api.instances import start_instance_core

    logger.info("market open — starting auto-start instances")
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(StrategyInstance).where(
                StrategyInstance.auto_start.is_(True),
                StrategyInstance.status != "running",
            )
        )
        instance_ids = [inst.id for inst in result.scalars().all()]

        for instance_id in instance_ids:
            try:
                await start_instance_core(app, db, instance_id)
                logger.info("auto-started instance", instance_id=instance_id)
            except HTTPException as exc:
                logger.warning("auto-start skipped", instance_id=instance_id, detail=exc.detail)
            except Exception as exc:
                logger.error("auto-start failed", instance_id=instance_id, error=str(exc))


async def _stop_auto_instances(app: FastAPI) -> None:
    from xillion.api.instances import stop_instance_core

    logger.info("market closed — stopping auto-start instances")
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(StrategyInstance).where(
                StrategyInstance.auto_start.is_(True),
                StrategyInstance.status == "running",
            )
        )
        instance_ids = [inst.id for inst in result.scalars().all()]

        for instance_id in instance_ids:
            try:
                await stop_instance_core(app, db, instance_id, reason="market_close_auto_stop")
                logger.info("auto-stopped instance", instance_id=instance_id)
            except HTTPException as exc:
                logger.warning("auto-stop skipped", instance_id=instance_id, detail=exc.detail)
            except Exception as exc:
                logger.error("auto-stop failed", instance_id=instance_id, error=str(exc))
