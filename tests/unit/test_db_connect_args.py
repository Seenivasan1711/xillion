"""
Tests for hosted-Postgres (Supabase/Render) connect-arg handling.

Note: xillion.db.migrations.env cannot be imported directly (it executes
alembic.context calls at module level, only valid inside an active Alembic
run) -- that's why the connect-args logic it uses lives in xillion.db.session
as a plain, safely-importable function instead of being duplicated in env.py.
"""
import ssl

from xillion.db.session import async_connect_args_for, sync_connect_args_for


def test_async_sqlite_gets_check_same_thread():
    assert async_connect_args_for("sqlite+aiosqlite:///./data/xillion.db") == {"check_same_thread": False}


def test_async_postgres_gets_encrypted_but_unverified_ssl_and_disables_statement_cache():
    # Must match sync_connect_args_for's sslmode=require semantics (encrypted,
    # not verified) -- asyncpg's ssl=True shortcut verifies against system CAs,
    # which fails against Supabase's pooler cert. See session.py's comment.
    url = "postgresql+asyncpg://postgres.abcxyz:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    args = async_connect_args_for(url)
    assert args["statement_cache_size"] == 0
    assert isinstance(args["ssl"], ssl.SSLContext)
    assert args["ssl"].verify_mode == ssl.CERT_NONE
    assert args["ssl"].check_hostname is False


def test_async_unknown_scheme_gets_no_special_args():
    assert async_connect_args_for("mysql+aiomysql://x") == {}


def test_sync_migration_postgres_requires_sslmode():
    url = "postgresql://postgres.abcxyz:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    assert sync_connect_args_for(url) == {"sslmode": "require"}


def test_sync_migration_sqlite_needs_no_ssl():
    assert sync_connect_args_for("sqlite:///./data/xillion.db") == {}
