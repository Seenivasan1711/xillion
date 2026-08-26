"""
Data warehouse API (CP3) -- coverage inspection + backfill jobs.

Coverage tells you what's already cached in Postgres (bar_coverage, written
by BarWarehouse). Backfill drives the warehouse to fill a requested range in
the background so a multi-year request returns a job id immediately instead
of blocking the HTTP request for however long the fetch takes.
"""

import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.data_provider_credstore import load_provider_credentials
from xillion.data.coverage import BarCoverageRepository
from xillion.data.repository import BarRepository
from xillion.data.warehouse import BarWarehouse
from xillion.db.models import AppUser, BarCoverage
from xillion.db.session import get_session_factory

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/data", tags=["data"])


@router.get("/coverage")
async def get_coverage(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """What's already cached, per (symbol, exchange, timeframe, provider)."""
    result = await db.execute(select(BarCoverage).order_by(BarCoverage.updated_at.desc()))
    rows = result.scalars().all()
    return {
        "coverage": [
            {
                "symbol": r.symbol,
                "exchange": r.exchange,
                "timeframe": r.timeframe,
                "provider_name": r.provider_name,
                "from_date": r.from_date,
                "to_date": r.to_date,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]
    }


class BackfillRequest(BaseModel):
    provider_name: str
    symbol: str
    exchange: str = "NFO"
    instrument_type: str = "option"
    timeframe: str = "1d"
    from_date: date
    to_date: date


async def _run_backfill_job(
    app_state, job_id: str, body: BackfillRequest, credentials, broker
) -> None:
    job = app_state.backfill_jobs[job_id]
    job["status"] = "running"
    session_factory = get_session_factory()
    warehouse = BarWarehouse(BarRepository(session_factory), BarCoverageRepository(session_factory))
    provider_cls = app_state.plugin_loader.registry.data_providers[body.provider_name]
    try:
        bars = await warehouse.get_bars(
            provider_cls(),
            body.symbol,
            body.exchange,
            body.timeframe,
            body.from_date,
            body.to_date,
            instrument_type=body.instrument_type,
            credentials=credentials,
            broker=broker,
        )
        job["status"] = "done"
        job["bars_fetched"] = len(bars)
        logger.info("backfill job done", job_id=job_id, bars_fetched=len(bars))
    except Exception as exc:  # a background task's exception is otherwise silently swallowed
        logger.error("backfill job failed", job_id=job_id, error=str(exc))
        job["status"] = "failed"
        job["error"] = str(exc)
    job["finished_at"] = datetime.now(UTC).isoformat()


@router.post("/backfill")
async def start_backfill(
    body: BackfillRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(503, "Plugin loader not available")
    provider_cls = loader.registry.data_providers.get(body.provider_name)
    if provider_cls is None:
        raise HTTPException(404, f"Data provider '{body.provider_name}' not found")

    provider = provider_cls()
    caps = provider.capabilities
    credentials = None
    if caps.requires_credentials:
        credentials = await load_provider_credentials(db, body.provider_name)
        if credentials is None:
            raise HTTPException(
                422,
                f"'{body.provider_name}' needs credentials — configure it under Settings → Data Providers",
            )
    broker = None
    if caps.requires_broker:
        broker_instances = getattr(request.app.state, "broker_instances", {})
        connected = next(
            (
                info["instance"]
                for info in broker_instances.values()
                if info.get("status") == "connected"
            ),
            None,
        )
        if connected is None:
            raise HTTPException(
                422,
                f"'{body.provider_name}' needs a connected broker — connect one under Settings → Brokers",
            )
        broker = connected

    job_id = str(uuid4())
    request.app.state.backfill_jobs[job_id] = {
        "id": job_id,
        "provider_name": body.provider_name,
        "symbol": body.symbol,
        "exchange": body.exchange,
        "timeframe": body.timeframe,
        "from_date": body.from_date.isoformat(),
        "to_date": body.to_date.isoformat(),
        "status": "queued",
        "bars_fetched": None,
        "error": None,
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
    }
    asyncio.create_task(_run_backfill_job(request.app.state, job_id, body, credentials, broker))
    logger.info(
        "backfill job queued", job_id=job_id, provider=body.provider_name, symbol=body.symbol
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/backfill")
async def list_backfill_jobs(request: Request):
    jobs = getattr(request.app.state, "backfill_jobs", {})
    return {"jobs": list(jobs.values())}


@router.get("/backfill/{job_id}")
async def get_backfill_status(job_id: str, request: Request):
    jobs = getattr(request.app.state, "backfill_jobs", {})
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Backfill job '{job_id}' not found")
    return job
