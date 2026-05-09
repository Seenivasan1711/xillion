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
from xillion.api import backtest, brokers, health, instances, strategies, ws
from xillion.api import auth as auth_router
from xillion.config import get_settings
from xillion.core.plugin_loader import PluginLoader
from xillion.core.risk import RiskManager
from xillion.data.bus import MarketDataBus
from xillion.db.session import init_db
from xillion.engine.strategy_engine import StrategyEngine

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if not settings.is_production else logging.INFO
    ),
)
logger = structlog.get_logger(__name__)

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


async def _try_connect_zerodha(app: FastAPI) -> None:
    """Attempt to connect Zerodha if credentials are configured. Non-fatal."""
    s = get_settings()
    if not s.zerodha_primary_api_key:
        logger.info("zerodha: no credentials configured — skipping auto-connect")
        return

    try:
        from brokers.zerodha import ZerodhaBroker

        broker = ZerodhaBroker()
        creds = {
            "api_key": s.zerodha_primary_api_key,
            "api_secret": s.zerodha_primary_api_secret,
            "user_id": s.zerodha_primary_user_id,
            "password": s.zerodha_primary_password,
            "totp_secret": s.zerodha_primary_totp_secret,
        }
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
        asyncio.create_task(_tick_broadcaster(broker, app.state.bus))
    except Exception as exc:
        logger.error("zerodha: failed to connect", error=str(exc))
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
    try:
        async for tick in broker.tick_stream():
            # Publish to strategy runners via the data bus
            await bus.publish_tick(tick)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("xillion starting", version=__version__, env=settings.app_env)

    await init_db()

    plugin_loader = PluginLoader()
    registry = await plugin_loader.discover_all()
    app.state.plugin_loader = plugin_loader

    bus = MarketDataBus()
    app.state.bus = bus

    risk = RiskManager()
    app.state.risk = risk

    engine = StrategyEngine(bus=bus, risk_manager=risk)
    engine.set_registry(registry)
    app.state.strategy_engine = engine

    app.state.broker_instances: dict = {}

    # Connect configured brokers (non-blocking — errors are logged, not raised)
    await _try_connect_zerodha(app)

    # Schedule daily token refresh
    refresh_task = asyncio.create_task(_daily_token_refresh(app))

    logger.info("xillion ready")
    yield

    refresh_task.cancel()
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
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(instances.router, prefix="/api")
app.include_router(brokers.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
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
