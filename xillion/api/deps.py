"""
FastAPI dependencies: DB session, current user.
"""
from typing import AsyncGenerator, Optional

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.auth.session import validate_session
from xillion.db.models import AppUser
from xillion.db.session import get_session_factory


async def db_dep() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def get_current_user(
    session_token: Optional[str] = Cookie(None, alias="xillion_session"),
    db: AsyncSession = Depends(db_dep),
) -> AppUser:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await validate_session(db, session_token)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Session expired or account inactive")
    return user


async def get_current_user_optional(
    session_token: Optional[str] = Cookie(None, alias="xillion_session"),
    db: AsyncSession = Depends(db_dep),
) -> Optional[AppUser]:
    if not session_token:
        return None
    return await validate_session(db, session_token)
