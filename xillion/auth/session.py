import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.config import get_settings
from xillion.db.models import AppUser
from xillion.db.models import Session as SessionModel


async def create_session(
    db: AsyncSession, user_id: int, ip: str = "", user_agent: str = ""
) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=settings.session_lifetime_hours)
    session = SessionModel(
        id=token,
        user_id=user_id,
        created_at=now.isoformat(),
        expires_at=expires.isoformat(),
        last_seen_at=now.isoformat(),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(session)
    await db.commit()
    return token


async def validate_session(db: AsyncSession, token: str) -> Optional[AppUser]:
    now = datetime.now(timezone.utc)
    result = await db.execute(select(SessionModel).where(SessionModel.id == token))
    session = result.scalar_one_or_none()
    if session is None or session.expires_at < now.isoformat():
        return None
    session.last_seen_at = now.isoformat()
    await db.commit()
    result = await db.execute(select(AppUser).where(AppUser.id == session.user_id))
    return result.scalar_one_or_none()


async def delete_session(db: AsyncSession, token: str) -> None:
    result = await db.execute(select(SessionModel).where(SessionModel.id == token))
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()
