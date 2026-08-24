"""
End-to-end: a captured log entry actually lands in system_log and is
broadcast, and GET /api/logs (xillion/api/logs.py) returns what's persisted
in the shape the frontend expects (oldest first, optional level filter).
"""
import asyncio

import pytest

from xillion.api.logs import _row_dict, list_logs
from xillion.db.models import SystemLog
from xillion.db.session import get_session_factory, init_db
from xillion.observability import log_capture
from xillion.observability.log_capture import run_log_persistence


@pytest.fixture(autouse=True)
def _reset_queue():
    log_capture._queue = None
    yield
    log_capture._queue = None


async def _drain_one():
    """Runs run_log_persistence() just long enough to drain whatever is
    already queued, then cancels it -- the real task runs forever."""
    task = asyncio.create_task(run_log_persistence())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_a_captured_entry_is_persisted_to_system_log():
    await init_db()
    log_capture.capture_processor(
        None, "error", {"event": "broker disconnected", "module": "brokers.zerodha", "reason": "timeout"}
    )

    await _drain_one()

    factory = get_session_factory()
    async with factory() as db:
        from sqlalchemy import select
        result = await db.execute(select(SystemLog).where(SystemLog.message == "broker disconnected"))
        row = result.scalars().first()

    assert row is not None
    assert row.level == "error"
    assert row.source == "brokers.zerodha"
    d = _row_dict(row)
    assert d["fields"] == {"reason": "timeout"}


@pytest.mark.asyncio
async def test_list_logs_returns_oldest_first_and_respects_limit():
    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        for i in range(5):
            db.add(SystemLog(
                ts=f"2026-01-01T00:00:0{i}+00:00", level="info", source="test",
                message=f"entry {i}", fields_json="{}",
            ))
        await db.commit()

        result = await list_logs(limit=3, level=None, db=db, user=None)

    messages = [row["message"] for row in result["logs"]]
    # Oldest-first among the 3 most recent rows.
    assert messages == ["entry 2", "entry 3", "entry 4"]


@pytest.mark.asyncio
async def test_list_logs_filters_by_level_group():
    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        db.add(SystemLog(ts="2026-01-01T00:00:00+00:00", level="info", source="t", message="info one", fields_json="{}"))
        db.add(SystemLog(ts="2026-01-01T00:00:01+00:00", level="error", source="t", message="error one", fields_json="{}"))
        db.add(SystemLog(ts="2026-01-01T00:00:02+00:00", level="critical", source="t", message="critical one", fields_json="{}"))
        await db.commit()

        result = await list_logs(limit=100, level="err", db=db, user=None)

    messages = {row["message"] for row in result["logs"]}
    assert "error one" in messages
    assert "critical one" in messages
    assert "info one" not in messages
