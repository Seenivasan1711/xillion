"""
MongoDB context store for trades + backtest results (2026-09-22,
task-tracker.md's SESSION SPRINT item 15).

Deliberately a *separate* store from the main Postgres DB, not a
replacement for it -- Postgres remains the system of record for real
trading state (positions, orders, risk). This is a write-through copy of
already-persisted trades and backtest runs, shaped for later consumption
by JEV/a local LLM (a document per trade/run, easy to embed/retrieve),
which is a different access pattern than Postgres's normalized tables
serve well. Rakesh's explicit call to use MongoDB here rather than
extending Postgres further, after this was flagged as an option.

Best-effort, always: every write is fire-and-forget from the caller's
perspective and never raises. A Mongo outage or missing MONGODB_URI must
never affect real trading -- same principle as TelegramNotifier.send()
swallowing its own failures. Empty MONGODB_URI (the default) means every
function here is a no-op with a debug log line, not a silent pretend-success.
"""

from __future__ import annotations

from typing import Any

import structlog

from xillion.config import get_settings

logger = structlog.get_logger(__name__)

_client: Any = None
_client_uri: str | None = None  # tracks which URI _client was built from


def _get_db() -> Any:
    """Lazily creates (or reuses) the Motor client for the currently
    configured MONGODB_URI. Rebuilds the client if the URI changed since
    the last call (e.g. saved via Settings without a process restart) --
    same "applied immediately" expectation as TelegramNotifier.configure().
    Returns None if unconfigured."""
    global _client, _client_uri

    uri = get_settings().mongodb_uri
    if not uri:
        return None

    if _client is None or _client_uri != uri:
        from motor.motor_asyncio import AsyncIOMotorClient

        if _client is not None:
            _client.close()
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        _client_uri = uri

    return _client.get_default_database()


async def record_trade(doc: dict) -> None:
    """One document per closed trade -- mirrors the shape already written
    to Postgres's PositionRecord/trade_closed WS event (symbol, side, qty,
    entry/exit price+ts, pnl, tag, strategy_instance_id), plus whatever
    extra context the caller adds (e.g. mode). Collection: "trades"."""
    db = _get_db()
    if db is None:
        logger.debug("mongo_context_store: not configured, skipping trade record")
        return
    try:
        await db["trades"].insert_one(dict(doc))
    except Exception as exc:
        logger.error("mongo_context_store: record_trade failed", error=str(exc))


async def record_backtest_run(doc: dict) -> None:
    """One document per backtest run -- params, metrics, and the full trade
    list together (unlike Postgres's normalized BacktestRun/BacktestTrade
    tables), since a single self-contained document per run is exactly the
    retrieval shape a RAG-style context feed wants: "here's everything
    about this one run." Collection: "backtest_runs"."""
    db = _get_db()
    if db is None:
        logger.debug("mongo_context_store: not configured, skipping backtest record")
        return
    try:
        await db["backtest_runs"].insert_one(dict(doc))
    except Exception as exc:
        logger.error("mongo_context_store: record_backtest_run failed", error=str(exc))
