"""
Auth endpoints: first-run setup, login/logout, TOTP management.
Single-user system — the first account created becomes the only admin.
"""
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.password import hash_password, verify_password
from xillion.auth.session import create_session, delete_session
from xillion.auth.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_secret,
    get_provisioning_uri,
    verify_code,
)
from xillion.db.models import AppUser

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE = "xillion_session"
_COOKIE_MAX_AGE = 8 * 3600


# ── First-run setup ────────────────────────────────────────────────────────────


@router.get("/setup-status")
async def setup_status(db: AsyncSession = Depends(db_dep)):
    result = await db.execute(select(func.count(AppUser.id)))
    count = result.scalar()
    return {"needs_setup": count == 0}


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


@router.post("/setup")
async def setup_first_user(body: SetupRequest, db: AsyncSession = Depends(db_dep)):
    result = await db.execute(select(func.count(AppUser.id)))
    if result.scalar() > 0:
        raise HTTPException(status_code=400, detail="Setup already complete — a user already exists")
    user = AppUser(
        username=body.username,
        password_hash=hash_password(body.password),
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    logger.info("first user created", username=body.username)
    return {"created": True, "username": body.username}


# ── Login / Logout ─────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(db_dep),
):
    result = await db.execute(select(AppUser).where(AppUser.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    if user.totp_secret:
        if not body.totp_code:
            # Signal frontend to show TOTP input
            return {"requires_totp": True}
        secret = decrypt_secret(user.totp_secret)
        if not verify_code(secret, body.totp_code):
            raise HTTPException(status_code=401, detail="Invalid TOTP code")

    user.last_login_at = datetime.now(timezone.utc).isoformat()
    await db.commit()

    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    token = await create_session(db, user.id, ip=ip, user_agent=ua)
    response.set_cookie(_COOKIE, token, max_age=_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return {"authenticated": True, "username": user.username, "has_totp": bool(user.totp_secret)}


@router.post("/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None, alias="xillion_session"),
    db: AsyncSession = Depends(db_dep),
):
    if session_token:
        await delete_session(db, session_token)
    response.delete_cookie(_COOKIE)
    return {"logged_out": True}


@router.get("/me")
async def me(user: AppUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "has_totp": bool(user.totp_secret),
        "last_login_at": user.last_login_at,
    }


# ── TOTP management ────────────────────────────────────────────────────────────


@router.post("/totp/setup")
async def totp_setup_begin(user: AppUser = Depends(get_current_user)):
    """Generate a new TOTP secret. Scan the returned URI with an authenticator app,
    then confirm with /totp/verify to save it."""
    secret = generate_secret()
    uri = get_provisioning_uri(secret, user.username)
    return {"secret": secret, "uri": uri}


class TotpVerifyRequest(BaseModel):
    secret: str
    code: str


@router.post("/totp/verify")
async def totp_setup_verify(
    body: TotpVerifyRequest,
    user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(db_dep),
):
    """Verify the TOTP code against the given secret, then persist and enable TOTP."""
    if not verify_code(body.secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code — try again")
    result = await db.execute(select(AppUser).where(AppUser.id == user.id))
    db_user = result.scalar_one()
    db_user.totp_secret = encrypt_secret(body.secret)
    await db.commit()
    return {"totp_enabled": True}


@router.post("/totp/disable")
async def totp_disable(
    user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(db_dep),
):
    result = await db.execute(select(AppUser).where(AppUser.id == user.id))
    db_user = result.scalar_one()
    db_user.totp_secret = None
    await db.commit()
    return {"totp_disabled": True}
