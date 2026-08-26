"""
_ensure_broker_connection (xillion/api/instances.py) used to just grab the
first BrokerConnection DB row that happened to exist, full stop -- nothing
anywhere in the codebase ever creates a "Zerodha Primary"/"Dhan Primary"
row, so a stale "Default Paper" placeholder from early testing meant EVERY
instance ever created (even ones made long after a real broker was
connected) silently pointed at it forever. Found 2026-08-26: a real,
genuinely-connected Dhan paper instance got "No live tick source" because
start_instance_core looks up BrokerConnection.name and matches it against
app.state.broker_instances, and "Default Paper" is never a key there.
"""

from datetime import UTC

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from xillion.api.instances import _ensure_broker_connection
from xillion.db.models import BrokerClass, BrokerConnection
from xillion.db.session import get_session_factory, init_db


def _now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


async def _seed_broker_class(session, name: str) -> BrokerClass:
    # get_session_factory() caches one engine for the whole test session
    # (see xillion/db/session.py), so the in-memory SQLite DB persists
    # across every test function, not just within this file -- broker_class
    # .name has a real unique constraint, so this must reuse an existing
    # row rather than blindly inserting a duplicate on a later test.
    existing = (
        await session.execute(select(BrokerClass).where(BrokerClass.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    bc = BrokerClass(
        name=name,
        module_path=f"brokers/{name.lower()}.py",
        class_name=f"{name}Broker",
        version="1.0.0",
        capabilities_json="{}",
        discovered_at=_now(),
        last_seen_at=_now(),
    )
    session.add(bc)
    await session.flush()
    return bc


def _request_with(broker_instances: dict) -> object:
    app = FastAPI()
    app.state.broker_instances = broker_instances
    return type("R", (), {"app": app})()


@pytest.mark.asyncio
async def test_creates_a_dhan_primary_row_when_dhan_is_connected_and_nothing_else_exists():
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await _seed_broker_class(session, "Dhan")
        await session.commit()

        request = _request_with(
            {
                "Dhan Primary": {
                    "name": "Dhan Primary",
                    "broker_name": "Dhan",
                    "status": "connected",
                },
            }
        )
        conn_id = await _ensure_broker_connection(session, "paper", request)

        conn = await session.get(BrokerConnection, conn_id)
        assert conn.name == "Dhan Primary"


@pytest.mark.asyncio
async def test_reuses_the_existing_dhan_primary_row_on_a_second_call():
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await _seed_broker_class(session, "Dhan")
        await session.commit()

        request = _request_with(
            {
                "Dhan Primary": {
                    "name": "Dhan Primary",
                    "broker_name": "Dhan",
                    "status": "connected",
                },
            }
        )
        first_id = await _ensure_broker_connection(session, "paper", request)
        second_id = await _ensure_broker_connection(session, "paper", request)

        assert first_id == second_id


@pytest.mark.asyncio
async def test_prefers_zerodha_when_both_connected():
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await _seed_broker_class(session, "Zerodha")
        await _seed_broker_class(session, "Dhan")
        await session.commit()

        request = _request_with(
            {
                "Zerodha Primary": {
                    "name": "Zerodha Primary",
                    "broker_name": "Zerodha",
                    "status": "connected",
                },
                "Dhan Primary": {
                    "name": "Dhan Primary",
                    "broker_name": "Dhan",
                    "status": "connected",
                },
            }
        )
        conn_id = await _ensure_broker_connection(session, "paper", request)

        conn = await session.get(BrokerConnection, conn_id)
        assert conn.name == "Zerodha Primary"


@pytest.mark.asyncio
async def test_falls_back_to_default_paper_when_nothing_is_connected():
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await _seed_broker_class(session, "Paper")
        await session.commit()

        request = _request_with({})
        conn_id = await _ensure_broker_connection(session, "paper", request)

        conn = await session.get(BrokerConnection, conn_id)
        assert conn.name == "Default Paper"


@pytest.mark.asyncio
async def test_ignores_a_broker_instances_entry_that_failed_to_connect():
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await _seed_broker_class(session, "Paper")
        await session.commit()

        request = _request_with(
            {
                "Dhan Primary": {"name": "Dhan Primary", "broker_name": "Dhan", "status": "error"},
            }
        )
        conn_id = await _ensure_broker_connection(session, "paper", request)

        conn = await session.get(BrokerConnection, conn_id)
        assert (
            conn.name == "Default Paper"
        ), "a failed connection attempt must not be treated as usable"
