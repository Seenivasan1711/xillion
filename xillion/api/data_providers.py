"""
Historical data provider API endpoints — list discovered providers, manage
credentials for the ones that need their own API key.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.data_provider_credstore import (
    list_provider_credential_names,
    save_provider_credentials,
)
from xillion.db.models import AppUser, DataProviderCredential

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/data-providers", tags=["data-providers"])


@router.get("/classes")
async def list_data_provider_classes(
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """List all discovered data providers, with configured/connected status."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        return {"providers": [], "errors": {}}
    registry = loader.registry
    configured_names = {row["name"] for row in await list_provider_credential_names(db)}
    broker_instances = getattr(request.app.state, "broker_instances", {})
    any_broker_connected = any(
        info.get("status") == "connected" for info in broker_instances.values()
    )

    providers = []
    for name, cls in registry.data_providers.items():
        caps = cls.capabilities
        if caps.requires_credentials:
            configured = name in configured_names
        elif caps.requires_broker:
            configured = any_broker_connected
        else:
            configured = True  # no credentials, no broker — always usable (e.g. free NSE bhavcopy)
        providers.append(
            {
                "name": cls.name,
                "version": cls.version,
                "description": cls.description,
                "credential_fields": [
                    {"key": k, "label": label, "type": input_type}
                    for k, label, input_type in cls.credential_fields
                ],
                "capabilities": {
                    "supports_equity": caps.supports_equity,
                    "supports_futures": caps.supports_futures,
                    "supports_options": caps.supports_options,
                    "supports_forex": caps.supports_forex,
                    "requires_credentials": caps.requires_credentials,
                    "requires_broker": caps.requires_broker,
                    "max_lookback_days": caps.max_lookback_days,
                },
                "configured": configured,
            }
        )
    return {"providers": providers, "errors": registry.errors}


class ProviderCredentialsRequest(BaseModel):
    payload: dict


@router.put("/{name}/credentials")
async def put_provider_credentials(
    name: str,
    body: ProviderCredentialsRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None or name not in loader.registry.data_providers:
        raise HTTPException(404, f"Data provider '{name}' not found")
    await save_provider_credentials(db, name, name, body.payload)
    logger.info("data provider credentials saved", provider=name, user=user.username)

    # "Twelve Data (Gold History)" is also read by the live Twelve Data
    # BROKER (brokers/twelve_data_feed.py, via main.py's
    # _load_twelve_data_api_key) -- same account/key, one place to enter
    # it. Reconnect immediately, same save-then-reconnect flow
    # Zerodha/Dhan's Settings cards already use, so a saved key takes
    # effect without a process restart. Non-fatal if it fails -- this
    # endpoint's job is saving the credential, not guaranteeing the feed
    # connects (e.g. a bad key still saves, just won't connect).
    if name == "Twelve Data (Gold History)":
        try:
            from xillion.main import _try_connect_twelve_data

            await _try_connect_twelve_data(request.app)
        except Exception as exc:
            logger.error("twelve_data: reconnect after credential save failed", error=str(exc))

    return {"saved": True}


@router.delete("/{name}/credentials")
async def delete_provider_credentials(
    name: str,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    row = await db.get(DataProviderCredential, name)
    if row:
        await db.delete(row)
        await db.commit()
    logger.info("data provider credentials deleted", provider=name, user=user.username)
    return {"deleted": True}
