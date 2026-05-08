"""
Append-only audit log with a hash chain.
Every important event (order, lifecycle, config change, risk gate) is recorded here.
"""
import hashlib
import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_hash(prev_hash: str | None, payload_json: str) -> str:
    raw = (prev_hash or "") + payload_json
    return hashlib.sha256(raw.encode()).hexdigest()


class AuditLog:
    """Write audit events to the DB audit_log table."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory
        self._last_hash: str | None = None

    async def _get_last_hash(self, session: AsyncSession) -> str | None:
        from xillion.db.models import AuditLogRecord

        result = await session.execute(
            select(AuditLogRecord.hash).order_by(AuditLogRecord.id.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def record(
        self,
        event_type: str,
        payload: dict,
        actor_type: str = "system",
        actor_id: str | None = None,
    ) -> None:
        from xillion.db.models import AuditLogRecord

        payload_json = json.dumps(payload, default=str)
        async with self._session_factory() as session:
            prev_hash = await self._get_last_hash(session)
            record_hash = _compute_hash(prev_hash, payload_json)
            record = AuditLogRecord(
                ts=_now_iso(),
                actor_type=actor_type,
                actor_id=actor_id,
                event_type=event_type,
                payload_json=payload_json,
                prev_hash=prev_hash,
                hash=record_hash,
            )
            session.add(record)
            await session.commit()
        logger.debug("audit event recorded", event_type=event_type, actor_type=actor_type)
