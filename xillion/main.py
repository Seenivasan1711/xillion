"""
FastAPI application entry point.
In production, also serves the built React frontend from frontend/dist/.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from xillion import __version__
from xillion.api import backtest, brokers, data, data_providers, health, instances, journal as journal_router, logs as logs_router, positions as positions_router, risk as risk_router, signals, strategies, ws
from xillion.api import auth as auth_router
from xillion.api import portfolio as portfolio_router
from xillion.api import settings as settings_router
from xillion.api import trades as trades_router
from xillion.config import get_settings
from xillion.core.plugin_loader import PluginLoader
from xillion.core.risk import RiskManager
from xillion.data.bar_aggregator import BarAggregator
from xillion.data.bus import MarketDataBus
from xillion.db.plugin_sync import sync_registry_to_db
from xillion.db.session import get_session_factory, init_db
from xillion.engine.digest_scheduler import run_daily_digest, run_weekly_digest
from xillion.engine.eod_scheduler import run_reconciliation_scheduler, run_square_off_scheduler
from xillion.engine.market_scheduler import run_market_hours_scheduler
from xillion.engine.strategy_engine import StrategyEngine
from xillion.notifications.telegram import TelegramNotifier
from xillion.observability.log_capture import capture_processor, run_log_persistence
from xillion.observability.task_supervisor import supervise

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if not settings.is_production else logging.INFO
    ),
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.CallsiteParameterAdder([structlog.processors.CallsiteParameter.MODULE]),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        capture_processor,
        structlog.dev.ConsoleRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


async def _load_zerodha_credentials() -> Optional[dict]:
    """Prefer credentials from the encrypted DB store; fall back to env vars."""
    from xillion.auth.credstore import load_credentials
    from xillion.db.session import get_session_factory

    async with get_session_factory()() as db:
        creds = await load_credentials(db, "Zerodha Primary")
    if creds and creds.get("api_key"):
        return creds

    s = get_settings()
    if s.zerodha_primary_api_key:
        return {
            "api_key": s.zerodha_primary_api_key,
            "api_secret": s.zerodha_primary_api_secret,
            "user_id": s.zerodha_primary_user_id,
            "password": s.zerodha_primary_password,
            "totp_secret": s.zerodha_primary_totp_secret,
        }
    return None


async def _try_connect_zerodha(app: FastAPI) -> None:
    """Attempt to connect Zerodha if credentials are configured. Non-fatal."""
    creds = await _load_zerodha_credentials()
    if creds is None:
        logger.info("zerodha: no credentials configured — skipping auto-connect")
        app.state.broker_instances.pop("Zerodha Primary", None)
        return

    # If a previous instance exists, disconnect it cleanly
    prev = app.state.broker_instances.get("Zerodha Primary")
    if prev and prev.get("instance"):
        try:
            await prev["instance"].disconnect()
        except Exception:
            pass

    try:
        from brokers.zerodha import ZerodhaBroker

        broker = ZerodhaBroker(notifier=app.state.telegram)
        await broker.connect(creds)
        app.state.broker_instances["Zerodha Primary"] = {
            "name": "Zerodha Primary",
            "broker_name": "Zerodha",
            "instance": broker,
            "status": "connected",
            "last_error": None,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("zerodha: connected successfully")

        # Start broadcasting ticks to WebSocket clients + MarketDataBus
        supervise("tick_broadcaster", lambda: _tick_broadcaster(broker, app.state.bus), notifier=app.state.telegram)
    except Exception as exc:
        logger.error("zerodha: failed to connect", error=str(exc))
        asyncio.create_task(app.state.telegram.alert(
            title="Zerodha connect failed",
            body=f"No live prices/orders until this is fixed: {exc}",
            severity="critical",
        ))
        app.state.broker_instances["Zerodha Primary"] = {
            "name": "Zerodha Primary",
            "broker_name": "Zerodha",
            "instance": None,
            "status": "error",
            "last_error": str(exc),
            "connected_at": None,
        }


async def _tick_broadcaster(broker, bus: "MarketDataBus") -> None:
    """Forward broker ticks to the MarketDataBus (strategies) and WebSocket clients (UI)."""
    logger.info("tick broadcaster started")
    bar_aggregator = BarAggregator(bus)
    try:
        async for tick in broker.tick_stream():
            # Publish to strategy runners via the data bus
            await bus.publish_tick(tick)
            # Turn ticks into bars for on_bar-subscribed strategies -- see
            # xillion/data/bar_aggregator.py's docstring for why this exists.
            await bar_aggregator.on_tick(tick)
            # Broadcast to connected UI clients
            await ws.broadcast(
                {
                    "type": "tick",
                    "symbol": tick.symbol,
                    "ltp": str(tick.ltp),
                    "ts": tick.ltt.isoformat() if hasattr(tick.ltt, "isoformat") else str(tick.ltt),
                    "volume": tick.volume,
                    "bid": str(tick.bid) if tick.bid else None,
                    "ask": str(tick.ask) if tick.ask else None,
                }
            )
    except asyncio.CancelledError:
        logger.info("tick broadcaster cancelled")
    except Exception as exc:
        logger.error("tick broadcaster error", error=str(exc))


async def _daily_token_refresh(app: FastAPI) -> None:
    """At 6:15 AM IST, reconnect Zerodha to refresh the access token."""
    import zoneinfo

    IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    while True:
        now = datetime.now(IST)
        # Next refresh: 6:15 AM IST same day or next day
        target = now.replace(hour=6, minute=15, second=0, microsecond=0)
        if now >= target:
            # Next day
            from datetime import timedelta
            target = target + timedelta(days=1)
        sleep_secs = (target - now).total_seconds()
        logger.info("zerodha: token refresh scheduled", sleep_seconds=int(sleep_secs))
        await asyncio.sleep(sleep_secs)
        logger.info("zerodha: running daily token refresh")
        try:
            info = app.state.broker_instances.get("Zerodha Primary")
            if info and info.get("instance"):
                await info["instance"].disconnect()
            # Remove cached token so fresh login runs
            from pathlib import Path
            token_file = Path("data/zerodha_token.json")
            if token_file.exists():
                token_file.unlink()
            await _try_connect_zerodha(app)
        except Exception as exc:
            logger.error("daily token refresh failed", error=str(exc))


async def _daily_instrument_refresh(app: FastAPI) -> None:
    """At 8:45 AM IST (after the 6:15 AM token refresh, before 9:15 market
    open), refresh the cached options instrument dump."""
    import zoneinfo

    from xillion.core.instrument_cache import refresh_instrument_cache
    from xillion.db.session import get_session_factory

    IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    while True:
        now = datetime.now(IST)
        target = now.replace(hour=8, minute=45, second=0, microsecond=0)
        if now >= target:
            from datetime import timedelta
            target = target + timedelta(days=1)
        sleep_secs = (target - now).total_seconds()
        logger.info("instrument cache refresh scheduled", sleep_seconds=int(sleep_secs))
        await asyncio.sleep(sleep_secs)
        try:
            info = app.state.broker_instances.get("Zerodha Primary")
            broker = info.get("instance") if info else None
            if broker is None:
                logger.warning("instrument cache refresh skipped — Zerodha not connected")
                continue
            count = await refresh_instrument_cache(broker, get_session_factory)
            logger.info("instrument cache refresh complete", row_count=count)
        except Exception as exc:
            logger.error("instrument cache refresh failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("xillion starting", version=__version__, env=settings.app_env)

    if settings.is_production:
        # Production schema is owned by Alembic migrations (run before this
        # process starts, see Dockerfile). Skipping create_all() here avoids
        # a race: with --workers 2, every worker's lifespan runs concurrently,
        # and concurrent CREATE TABLE statements for the same missing table
        # can hit Postgres's "duplicate key value violates unique constraint
        # pg_type_typname_nsp_index" (see migrations/versions/003_broker_credential.py).
        logger.info("skipping create_all() in production — using Alembic-managed schema")
    else:
        await init_db()

    plugin_loader = PluginLoader()
    registry = await plugin_loader.discover_all()
    app.state.plugin_loader = plugin_loader
    async with get_session_factory()() as session:
        await sync_registry_to_db(registry, session)

    bus = MarketDataBus()
    app.state.bus = bus

    risk = RiskManager()
    app.state.risk = risk

    telegram = TelegramNotifier()
    app.state.telegram = telegram
    risk.set_notify(telegram.alert)

    engine = StrategyEngine(bus=bus, risk_manager=risk)
    engine.set_registry(registry)
    app.state.strategy_engine = engine

    app.state.broker_instances: dict = {}
    app.state.backfill_jobs: dict = {}

    # Connect configured brokers (non-blocking — errors are logged, not raised)
    await _try_connect_zerodha(app)

    # Schedule daily token + instrument-dump refresh
    refresh_task = supervise("daily_token_refresh", lambda: _daily_token_refresh(app), notifier=telegram)
    instrument_refresh_task = supervise("daily_instrument_refresh", lambda: _daily_instrument_refresh(app), notifier=telegram)
    market_scheduler_task = supervise("market_hours_scheduler", lambda: run_market_hours_scheduler(app), notifier=telegram)
    log_persistence_task = supervise("log_persistence", run_log_persistence, notifier=telegram)
    daily_digest_task = supervise("daily_digest", lambda: run_daily_digest(app), notifier=telegram)
    weekly_digest_task = supervise("weekly_digest", lambda: run_weekly_digest(app), notifier=telegram)
    # CP14: X02 (square-off, 15:15 IST) then M01 (reconciliation, 15:45 IST)
    # -- deliberately separate supervised tasks, see eod_scheduler.py's
    # docstring for why they aren't one combined job.
    square_off_task = supervise("eod_square_off", lambda: run_square_off_scheduler(app), notifier=telegram)
    reconciliation_task = supervise("eod_reconciliation", lambda: run_reconciliation_scheduler(app), notifier=telegram)

    logger.info("xillion ready")
    yield

    refresh_task.cancel()
    instrument_refresh_task.cancel()
    market_scheduler_task.cancel()
    log_persistence_task.cancel()
    daily_digest_task.cancel()
    weekly_digest_task.cancel()
    square_off_task.cancel()
    reconciliation_task.cancel()
    # Disconnect all brokers on shutdown
    for info in app.state.broker_instances.values():
        instance = info.get("instance")
        if instance:
            try:
                await instance.disconnect()
            except Exception:
                pass
    logger.info("xillion shutdown complete")


app = FastAPI(
    title="Xillion",
    description="Personal Algorithmic Trading Platform",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(instances.router, prefix="/api")
app.include_router(risk_router.router, prefix="/api")
app.include_router(brokers.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(data_providers.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(signals.router, prefix="/api")
app.include_router(journal_router.router, prefix="/api")
app.include_router(logs_router.router, prefix="/api")
app.include_router(positions_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(portfolio_router.router, prefix="/api")
app.include_router(trades_router.router, prefix="/api")
app.include_router(ws.router)

# Serve React frontend (production build)
if _FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
