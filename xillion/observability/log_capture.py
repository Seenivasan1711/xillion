"""
Captures every structlog event app-wide (wired into structlog.configure()
in xillion/main.py) into a bounded in-memory queue, drained by a background
task started in main.py's lifespan. The drain task persists each entry to
system_log and forwards it to the WebSocket "log" event the Logs page
(frontend/src/pages/Logs.tsx) already expected but that, before this,
nothing in the backend ever actually produced -- the page rendered a live
feed with nothing live to show, and lost everything on reload since there
was no persistence to load from either.

capture_processor runs synchronously on every single logger.info/.warning/
etc. call across the app, so it must never block or raise. It only enqueues
-- the actual DB write and WS broadcast happen on the drain task, off the
hot path.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

_QUEUE_MAXSIZE = 2000
_PRUNE_EVERY_N_WRITES = 200
_RETENTION = timedelta(hours=24)  # matches the Logs page's "scrollback retained for 24h" copy

_queue: "asyncio.Queue[dict] | None" = None


def _get_queue() -> "asyncio.Queue[dict]":
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    return _queue


def capture_processor(logger, method_name, event_dict):
    try:
        fields = {
            k: v
            for k, v in event_dict.items()
            if k not in ("event", "module", "level", "timestamp")
        }
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "level": method_name,
            "source": event_dict.get("module") or "system",
            "message": str(event_dict.get("event", "")),
            "fields": fields,
        }
        _get_queue().put_nowait(entry)
    except Exception:
        # A full queue (drain task falling behind) or any other capture
        # failure must never interrupt the actual log call.
        pass
    return event_dict


async def run_log_persistence() -> None:
    """Runs forever as a background task (see xillion/main.py's lifespan).
    Cancelled on shutdown like the other background tasks there."""
    from xillion.api.ws import broadcast
    from xillion.db.models import SystemLog
    from xillion.db.session import get_session_factory

    queue = _get_queue()
    factory = get_session_factory()
    writes_since_prune = 0

    while True:
        entry = await queue.get()
        try:
            async with factory() as db:
                db.add(
                    SystemLog(
                        ts=entry["ts"],
                        level=entry["level"],
                        source=entry["source"],
                        message=entry["message"],
                        fields_json=json.dumps(entry["fields"], default=str),
                    )
                )
                await db.commit()
        except Exception:
            pass

        try:
            await broadcast({"type": "log", **entry})
        except Exception:
            pass

        writes_since_prune += 1
        if writes_since_prune >= _PRUNE_EVERY_N_WRITES:
            writes_since_prune = 0
            try:
                await _prune_old_logs(factory)
            except Exception:
                pass


async def _prune_old_logs(factory) -> None:
    from sqlalchemy import delete

    from xillion.db.models import SystemLog

    cutoff = (datetime.now(UTC) - _RETENTION).isoformat()
    async with factory() as db:
        await db.execute(delete(SystemLog).where(SystemLog.ts < cutoff))
        await db.commit()
