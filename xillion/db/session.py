"""
Async SQLAlchemy session factory. Single source of truth for DB connections.
"""

import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from xillion.config import settings


def async_connect_args_for(url: str) -> dict:
    """connect_args for the async (asyncpg/aiosqlite) engine used by the app."""
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql"):
        # Hosted Postgres (Supabase, Render, ...) requires TLS, but asyncpg's
        # `ssl=True` shortcut means "encrypt AND verify against system-trusted
        # CAs" -- stricter than the sslmode=require behavior used on the sync
        # (Alembic) side below, which only requires encryption. Supabase's
        # pooler cert isn't chained to a standard trusted root, so `ssl=True`
        # fails verification even though the connection itself is fine.
        # Build an explicit context that matches sslmode=require's semantics:
        # encrypted, not verified.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        # Prepared-statement caching is disabled because Supabase's pooled
        # connection (PgBouncer in transaction mode) doesn't support
        # server-side prepared statements -- harmless to disable on a direct
        # connection too.
        return {"ssl": ctx, "statement_cache_size": 0}
    return {}


def sync_connect_args_for(url: str) -> dict:
    """connect_args for the sync (psycopg2) engine Alembic migrations use.
    Shared here (rather than duplicated in migrations/env.py) so it's a
    plain importable function -- env.py itself can't be imported outside
    an active Alembic run."""
    if url.startswith("postgresql"):
        return {"sslmode": "require"}  # hosted Postgres (Supabase, Render, ...)
    return {}


def _make_engine():
    url = settings.get_async_database_url()
    return create_async_engine(
        url,
        echo=not settings.is_production,
        connect_args=async_connect_args_for(url),
        # Supabase's pooler (PgBouncer/Supavisor) silently drops or recycles
        # idle connections server-side; without pre_ping, SQLAlchemy hands
        # out the stale connection from its pool and the next query fails
        # with "connection was closed in the middle of operation" -- hit for
        # real 2026-08-26 a few minutes into a long-running backfill script.
        # pre_ping validates (and transparently replaces) a connection before
        # each checkout; recycle proactively retires connections before the
        # pooler does it out from under us. Only meaningful for Postgres --
        # sqlite has no pooler and no such failure mode.
        pool_pre_ping=url.startswith("postgresql"),
        pool_recycle=300 if url.startswith("postgresql") else -1,
    )


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def init_db() -> None:
    """Create all tables (dev convenience). Production uses Alembic migrations."""
    from xillion.db.models import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
