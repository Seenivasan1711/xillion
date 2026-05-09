"""
Settings endpoints — manage broker credentials, app preferences.
"""
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.credstore import (
    list_credential_names,
    load_credentials,
    save_credentials,
)
from xillion.db.models import AppUser

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

ZERODHA_NAME = "Zerodha Primary"
ZERODHA_BROKER = "Zerodha"


class ZerodhaCredentialsRequest(BaseModel):
    api_key: str
    api_secret: str
    user_id: str
    password: str
    totp_secret: str


class ZerodhaCredentialsStatus(BaseModel):
    configured: bool
    api_key_preview: Optional[str] = None
    user_id: Optional[str] = None
    updated_at: Optional[str] = None


@router.get("/zerodha", response_model=ZerodhaCredentialsStatus)
async def get_zerodha_status(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    creds = await load_credentials(db, ZERODHA_NAME)
    if not creds:
        return ZerodhaCredentialsStatus(configured=False)
    rows = await list_credential_names(db)
    updated_at = next((r["updated_at"] for r in rows if r["name"] == ZERODHA_NAME), None)
    api_key = creds.get("api_key", "")
    return ZerodhaCredentialsStatus(
        configured=True,
        api_key_preview=f"{api_key[:4]}…{api_key[-4:]}" if len(api_key) >= 8 else "set",
        user_id=creds.get("user_id"),
        updated_at=updated_at,
    )


@router.put("/zerodha")
async def put_zerodha_credentials(
    body: ZerodhaCredentialsRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    payload = body.model_dump()
    await save_credentials(db, ZERODHA_NAME, ZERODHA_BROKER, payload)
    logger.info("zerodha credentials saved", user=user.username, user_id=body.user_id)

    # Invalidate any cached token so the new credentials are used
    from pathlib import Path

    token_cache = Path("data/zerodha_token.json")
    if token_cache.exists():
        token_cache.unlink()

    # Trigger a reconnect attempt with the new credentials
    from xillion.main import _try_connect_zerodha

    await _try_connect_zerodha(request.app)
    info = request.app.state.broker_instances.get(ZERODHA_NAME, {})
    return {
        "saved": True,
        "connection_status": info.get("status", "unknown"),
        "last_error": info.get("last_error"),
    }


@router.delete("/zerodha")
async def delete_zerodha_credentials(
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    from xillion.db.models import BrokerCredential

    row = await db.get(BrokerCredential, ZERODHA_NAME)
    if row:
        await db.delete(row)
        await db.commit()

    info = request.app.state.broker_instances.get(ZERODHA_NAME, {})
    instance = info.get("instance")
    if instance:
        try:
            await instance.disconnect()
        except Exception:
            pass
    request.app.state.broker_instances.pop(ZERODHA_NAME, None)
    logger.info("zerodha credentials deleted", user=user.username)
    return {"deleted": True}
