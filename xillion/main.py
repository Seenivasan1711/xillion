"""
FastAPI application entry point.
In production, also serves the built React frontend from frontend/dist/.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from xillion import __version__
from xillion.api import auth as auth_router
from xillion.api import (
    backtest,
    brokers,
    data,
    data_providers,
    health,
    instances,
    signals,
    strategies,
    ws,
)
from xillion.api import journal as journal_router
from xillion.api import logs as logs_router
from xillion.api import portfolio as portfolio_router
from xillion.api import positions as positions_router
from xillion.api import risk as risk_router
from xillion.api import settings as settings_router
from xillion.api import trades as trades_router
from xillion.config import get_settings
from xillion.core.plugin_loader import PluginLoader
from xillion.core.risk import RiskManager
from xillion.data.bar_aggregator import BarAggregator
from xillion.data.bus import MarketDataBus
from xillion.db.plugin_sync import sync_registry_to_db
from xillion.db.session import get_session_factory, init_db, init_warehouse_db
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
        structlog.processors.CallsiteParameterAdder(
            [structlog.processors.CallsiteParameter.MODULE]
        ),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        capture_processor,
        structlog.dev.ConsoleRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


async def _load_zerodha_credentials() -> dict | None:
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


async def _load_telegram_credentials() -> tuple[str, str]:
    """Same DB-first, env-fallback pattern as _load_zerodha_credentials --
    reuses the BrokerCredential encrypted store under the name "Telegram"
    even though it isn't a broker; that table is really just generic
    encrypted app-secret storage, and adding a second table for one row
    of data wasn't worth it. Returns ("", "") if genuinely unconfigured
    anywhere -- TelegramNotifier treats that as disabled, not an error."""
    from xillion.auth.credstore import load_credentials
    from xillion.db.session import get_session_factory

    async with get_session_factory()() as db:
        creds = await load_credentials(db, "Telegram")
    if creds and creds.get("telegram_bot_token"):
        return creds["telegram_bot_token"], creds.get("telegram_chat_id", "")

    s = get_settings()
    return s.telegram_bot_token, s.telegram_chat_id


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
            "connected_at": datetime.now(UTC).isoformat(),
        }
        logger.info("zerodha: connected successfully")

        # Start broadcasting ticks to WebSocket clients + MarketDataBus.
        # _try_connect_zerodha can run more than once (daily token refresh,
        # manual reconnect, settings save) -- without cancelling the prior
        # broadcaster, each run leaked a supervised task sitting forever on
        # `await self._tick_queue.get()` against a disconnected broker.
        old = getattr(app.state, "zerodha_broadcaster", None)
        if old is not None:
            old.cancel()
        app.state.zerodha_broadcaster = supervise(
            "tick_broadcaster",
            lambda: _tick_broadcaster(broker, app.state.bus),
            notifier=app.state.telegram,
        )
    except Exception as exc:
        logger.error("zerodha: failed to connect", error=str(exc))
        asyncio.create_task(
            app.state.telegram.alert(
                title="Zerodha connect failed",
                body=f"No live prices/orders until this is fixed: {exc}",
                severity="critical",
            )
        )
        app.state.broker_instances["Zerodha Primary"] = {
            "name": "Zerodha Primary",
            "broker_name": "Zerodha",
            "instance": None,
            "status": "error",
            "last_error": str(exc),
            "connected_at": None,
        }


async def _load_dhan_credentials() -> dict | None:
    """Same DB-first, env-fallback pattern as _load_zerodha_credentials."""
    from xillion.auth.credstore import load_credentials
    from xillion.db.session import get_session_factory

    async with get_session_factory()() as db:
        creds = await load_credentials(db, "Dhan Primary")
    if creds and creds.get("client_id"):
        return creds

    s = get_settings()
    if s.dhan_primary_client_id and s.dhan_primary_access_token:
        return {
            "client_id": s.dhan_primary_client_id,
            "access_token": s.dhan_primary_access_token,
            "pin": s.dhan_primary_pin,
            "totp_secret": s.dhan_primary_totp_secret,
        }
    return None


async def _try_connect_dhan(app: FastAPI) -> None:
    """CP15: same shape as _try_connect_zerodha -- attempt to connect Dhan
    if credentials are configured. Non-fatal; a missing/failed Dhan
    connection never blocks the app or Zerodha from working."""
    creds = await _load_dhan_credentials()
    if creds is None:
        logger.info("dhan: no credentials configured — skipping auto-connect")
        app.state.broker_instances.pop("Dhan Primary", None)
        return

    prev = app.state.broker_instances.get("Dhan Primary")
    if prev and prev.get("instance"):
        try:
            await prev["instance"].disconnect()
        except Exception:
            pass

    try:
        from brokers.dhan import DhanBroker

        broker = DhanBroker(notifier=app.state.telegram)
        await broker.connect(creds)
        app.state.broker_instances["Dhan Primary"] = {
            "name": "Dhan Primary",
            "broker_name": "Dhan",
            "instance": broker,
            "status": "connected",
            "last_error": None,
            "connected_at": datetime.now(UTC).isoformat(),
        }
        logger.info("dhan: connected successfully")

        # Same broadcaster Zerodha uses (broker-agnostic -- see
        # _tick_broadcaster) -- without this, DhanBroker.tick_stream() is
        # never drained and its ticks never reach app.state.bus, so paper
        # mode never sees a price even once Dhan is connected.
        #
        # _try_connect_dhan can run more than once (daily token refresh,
        # manual reconnect, settings save) -- without cancelling the prior
        # broadcaster, each run leaked a supervised task sitting forever on
        # `await self._tick_queue.get()` against a disconnected broker.
        old = getattr(app.state, "dhan_broadcaster", None)
        if old is not None:
            old.cancel()
        app.state.dhan_broadcaster = supervise(
            "dhan_tick_broadcaster",
            lambda: _tick_broadcaster(broker, app.state.bus),
            notifier=app.state.telegram,
        )
    except Exception as exc:
        logger.error("dhan: failed to connect", error=str(exc))
        asyncio.create_task(
            app.state.telegram.alert(
                title="Dhan connect failed",
                body=f"No Dhan orders/prices until this is fixed: {exc}",
                severity="warning",  # not critical -- Zerodha remains the primary broker
            )
        )
        app.state.broker_instances["Dhan Primary"] = {
            "name": "Dhan Primary",
            "broker_name": "Dhan",
            "instance": None,
            "status": "error",
            "last_error": str(exc),
            "connected_at": None,
        }


async def _daily_dhan_refresh(app: FastAPI) -> None:
    """CP15: at 6:30 AM IST (15 min after Zerodha's, avoiding a startup
    thundering-herd on both brokers' auth endpoints at once), re-run Dhan
    connect. Unlike Zerodha's refresh, this doesn't force-delete the cached
    token first -- DhanBroker.connect() already validates the cached/
    provided token and only falls through to PIN+TOTP auto-refresh if it's
    actually invalid, so a no-op re-validation on a still-good token is
    cheap and correct here."""
    import zoneinfo
    from datetime import timedelta

    IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    while True:
        now = datetime.now(IST)
        target = now.replace(hour=6, minute=30, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        logger.info("dhan: running daily token refresh")
        try:
            await _try_connect_dhan(app)
        except Exception as exc:
            logger.error("dhan daily token refresh failed", error=str(exc))


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


def _select_instrument_cache_broker(app: FastAPI) -> tuple:
    """Pick which connected broker's instrument dump refreshes the shared
    `instrument` table. Zerodha preferred when both are connected (matches
    the existing convention of Zerodha as primary broker elsewhere in this
    file) -- refreshing from both would be wrong anyway, since the table is
    truncate-and-reload, not additive, and a second broker's own dump would
    just overwrite the first's.

    Was hardcoded to Zerodha-only, which meant a Dhan-only setup (no
    Zerodha connected at all) never populated the `instrument` table --
    resolve_strike() reads it via load_instrument_rows() and would silently
    find zero rows, so a Dhan-only paper/live instance could start and run
    but could never actually resolve an option strike to trade. Found
    2026-08-26 while a real Dhan-only paper instance sat at 0 trades."""
    for name in ("Zerodha Primary", "Dhan Primary"):
        info = app.state.broker_instances.get(name)
        broker = info.get("instance") if info else None
        if broker is not None:
            return broker, name
    return None, None


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
            broker, source = _select_instrument_cache_broker(app)
            if broker is None:
                logger.warning("instrument cache refresh skipped — no broker connected")
                continue
            count = await refresh_instrument_cache(broker, get_session_factory)
            logger.info("instrument cache refresh complete", row_count=count, source=source)
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
    # The warehouse DB (bar/bar_coverage/option_chain_snapshot) is always a
    # plain local SQLite file, never Alembic-managed even in production --
    # see Settings.backtest_database_url -- so create_all() always runs for
    # it, unconditionally, unlike the main DB above.
    await init_warehouse_db()

    plugin_loader = PluginLoader()
    registry = await plugin_loader.discover_all()
    app.state.plugin_loader = plugin_loader
    async with get_session_factory()() as session:
        await sync_registry_to_db(registry, session)

    bus = MarketDataBus()
    app.state.bus = bus

    risk = RiskManager()
    app.state.risk = risk

    telegram_token, telegram_chat_id = await _load_telegram_credentials()
    telegram = TelegramNotifier(telegram_token, telegram_chat_id)
    app.state.telegram = telegram
    risk.set_notify(telegram.alert)

    engine = StrategyEngine(bus=bus, risk_manager=risk)
    engine.set_registry(registry)
    app.state.strategy_engine = engine

    # Type annotations aren't valid on a non-self attribute assignment
    # (mypy: "Type cannot be declared in assignment to non-self attribute"),
    # so these are plain dict literals, not `: dict = {}`.
    app.state.broker_instances = {}
    app.state.backfill_jobs = {}

    # Connect configured brokers (non-blocking — errors are logged, not raised)
    await _try_connect_zerodha(app)
    await _try_connect_dhan(app)  # CP15 -- no-ops cleanly if not configured

    # Schedule daily token + instrument-dump refresh
    refresh_task = supervise(
        "daily_token_refresh", lambda: _daily_token_refresh(app), notifier=telegram
    )
    dhan_refresh_task = supervise(
        "daily_dhan_refresh", lambda: _daily_dhan_refresh(app), notifier=telegram
    )
    instrument_refresh_task = supervise(
        "daily_instrument_refresh", lambda: _daily_instrument_refresh(app), notifier=telegram
    )
    market_scheduler_task = supervise(
        "market_hours_scheduler", lambda: run_market_hours_scheduler(app), notifier=telegram
    )
    log_persistence_task = supervise("log_persistence", run_log_persistence, notifier=telegram)
    daily_digest_task = supervise("daily_digest", lambda: run_daily_digest(app), notifier=telegram)
    weekly_digest_task = supervise(
        "weekly_digest", lambda: run_weekly_digest(app), notifier=telegram
    )
    # CP14: X02 (square-off, 15:15 IST) then M01 (reconciliation, 15:45 IST)
    # -- deliberately separate supervised tasks, see eod_scheduler.py's
    # docstring for why they aren't one combined job.
    square_off_task = supervise(
        "eod_square_off", lambda: run_square_off_scheduler(app), notifier=telegram
    )
    reconciliation_task = supervise(
        "eod_reconciliation", lambda: run_reconciliation_scheduler(app), notifier=telegram
    )

    logger.info("xillion ready")
    yield

    refresh_task.cancel()
    dhan_refresh_task.cancel()
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
