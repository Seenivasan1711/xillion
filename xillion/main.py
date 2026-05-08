"""
FastAPI application entry point.
In production, also serves the built React frontend from frontend/dist/.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from xillion import __version__
from xillion.api import backtest, brokers, health, strategies, ws
from xillion.config import settings
from xillion.core.plugin_loader import PluginLoader
from xillion.core.risk import RiskManager
from xillion.data.bus import MarketDataBus
from xillion.db.session import init_db
from xillion.engine.strategy_engine import StrategyEngine

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if not settings.is_production else logging.INFO
    ),
)
logger = structlog.get_logger(__name__)

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


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

    logger.info("xillion ready")
    yield
    logger.info("xillion shutting down")


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
app.include_router(strategies.router, prefix="/api")
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
        index = _FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
