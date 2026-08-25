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
from xillion.auth.data_provider_credstore import save_provider_credentials
from xillion.db.models import (
    AppUser,
    AuditLogRecord,
    BacktestRun,
    BacktestTrade,
    Base,
    DailyRiskState,
    DailyStrategyPnl,
    FillRecord,
    JournalNote,
    OrderRecord,
    PositionRecord,
    ReconciliationReport,
    SignalLog,
    SystemLog,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

ZERODHA_NAME = "Zerodha Primary"
ZERODHA_BROKER = "Zerodha"
DHAN_NAME = "Dhan Primary"
DHAN_BROKER = "Dhan"


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


class DhanCredentialsRequest(BaseModel):
    client_id: str
    access_token: str
    pin: str = ""
    totp_secret: str = ""


class DhanCredentialsStatus(BaseModel):
    configured: bool
    client_id: Optional[str] = None
    updated_at: Optional[str] = None


@router.get("/dhan", response_model=DhanCredentialsStatus)
async def get_dhan_status(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    creds = await load_credentials(db, DHAN_NAME)
    if not creds:
        return DhanCredentialsStatus(configured=False)
    rows = await list_credential_names(db)
    updated_at = next((r["updated_at"] for r in rows if r["name"] == DHAN_NAME), None)
    return DhanCredentialsStatus(
        configured=True,
        client_id=creds.get("client_id"),
        updated_at=updated_at,
    )


@router.put("/dhan")
async def put_dhan_credentials(
    body: DhanCredentialsRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    payload = body.model_dump()
    await save_credentials(db, DHAN_NAME, DHAN_BROKER, payload)
    logger.info("dhan credentials saved", user=user.username, client_id=body.client_id)

    # Same real Dhan API token authenticates both order placement (this
    # broker credential) and the DhanHQ historical-data provider -- without
    # this, saving it here left the Data Providers tab's DhanHQ card
    # showing "Not configured" and asking for the identical client ID +
    # access token a second time. Field names differ (data provider side
    # uses the generic api_key/api_secret shape every provider's
    # credential_fields maps onto) but the underlying values are the same.
    try:
        await save_provider_credentials(
            db, "DhanHQ", "DhanHQ",
            {"api_key": body.access_token, "api_secret": body.client_id},
        )
    except Exception as exc:
        logger.warning("failed to sync Dhan credentials to DhanHQ data provider", error=str(exc))

    # Invalidate any cached token so the new credentials are used --
    # DhanBroker keys its cache to a fixed path, same shape as Zerodha's.
    from pathlib import Path

    token_cache = Path("data/dhan_token.json")
    if token_cache.exists():
        token_cache.unlink()

    from xillion.main import _try_connect_dhan

    await _try_connect_dhan(request.app)
    info = request.app.state.broker_instances.get(DHAN_NAME, {})
    return {
        "saved": True,
        "connection_status": info.get("status", "unknown"),
        "last_error": info.get("last_error"),
    }


@router.delete("/dhan")
async def delete_dhan_credentials(
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    from xillion.db.models import BrokerCredential

    row = await db.get(BrokerCredential, DHAN_NAME)
    if row:
        await db.delete(row)
        await db.commit()

    info = request.app.state.broker_instances.get(DHAN_NAME, {})
    instance = info.get("instance")
    if instance:
        try:
            await instance.disconnect()
        except Exception:
            pass
    request.app.state.broker_instances.pop(DHAN_NAME, None)
    logger.info("dhan credentials deleted", user=user.username)
    return {"deleted": True}


NOTIFICATIONS_NAME = "Telegram"
NOTIFICATIONS_BROKER = "Telegram"  # not a broker -- reuses BrokerCredential's
# generic (name, encrypted_payload) shape rather than a second table for
# one row of data. See xillion/main.py's _load_telegram_credentials.


class NotificationSettings(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    on_strategy_start_stop: bool = True
    on_order_filled: bool = True
    on_order_rejected: bool = True
    on_drawdown_breach: bool = True
    on_kill_switch: bool = True


@router.get("/notifications", response_model=NotificationSettings)
async def get_notifications(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    creds = await load_credentials(db, NOTIFICATIONS_NAME)
    if not creds:
        return NotificationSettings()
    return NotificationSettings(**creds)


@router.put("/notifications")
async def put_notifications(
    body: NotificationSettings,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    await save_credentials(db, NOTIFICATIONS_NAME, NOTIFICATIONS_BROKER, body.model_dump())
    request.app.state.telegram.configure(body.telegram_bot_token, body.telegram_chat_id)
    logger.info("notification settings saved", user=user.username, telegram_configured=bool(body.telegram_bot_token))
    return {"saved": True}


@router.post("/notifications/test")
async def test_notifications(
    request: Request,
    user: AppUser = Depends(get_current_user),
):
    """Send a real Telegram message right now, using the currently SAVED
    bot token/chat ID (Save first, then Test) -- this is the same live
    notifier real alerts go through, so a successful test genuinely proves
    alerts will work, not just that the form values look valid."""
    ok, detail = await request.app.state.telegram.send_test()
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"sent": True}


RISK_LIMITS_NAME = "Risk Limits"
RISK_LIMITS_BROKER = "Settings"  # same BrokerCredential reuse as Notifications


class RiskLimits(BaseModel):
    daily_loss_pct: float = 2.0
    per_trade_risk_pct: float = 0.5
    max_open_positions: int = 5
    position_size_cap: float = 50_000.0
    ops_limit: int = 10
    burst_window: int = 60


@router.get("/risk-limits", response_model=RiskLimits)
async def get_risk_limits(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    creds = await load_credentials(db, RISK_LIMITS_NAME)
    if not creds:
        return RiskLimits()
    return RiskLimits(**creds)


@router.put("/risk-limits")
async def put_risk_limits(
    body: RiskLimits,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Persists these values so the UI round-trips correctly -- it does
    NOT yet feed live RiskManager enforcement. That reads its limits from
    xillion/config.py's default_* settings (env-configured) and each
    StrategyInstance's own risk_limits_json, and this tab's field shape
    doesn't cleanly map onto either (e.g. per_trade_risk_pct and
    burst_window have no equivalent there today). Wiring real enforcement
    needs a design decision on what "global" limits mean given risk is
    actually account-wide + per-instance, not a single flat set -- noted
    as an open gap in task-tracker.md rather than guessed at, since a
    wrong mapping here would be a real safety issue for a live trading
    system, not just a cosmetic bug."""
    await save_credentials(db, RISK_LIMITS_NAME, RISK_LIMITS_BROKER, body.model_dump())
    logger.info("risk limit preferences saved (not yet wired to enforcement)", user=user.username)
    return {"saved": True}


# ── Danger zone ──────────────────────────────────────────────────────────────

# Tables cleared by /reset-data: trade history, log records, strategy run
# data. Deliberately excludes broker/data-provider credentials & connections,
# strategy/broker/data-provider class registrations, StrategyInstance
# configs, and all cached market data (bar/bar_coverage/option_chain_snapshot/
# instrument/market_holiday) -- matches the UI's own "credentials and
# settings are preserved" copy.
_RESET_DATA_MODELS = [
    FillRecord, BacktestTrade,  # children first -- both FK into rows deleted below
    OrderRecord, PositionRecord, BacktestRun, SignalLog, SystemLog,
    JournalNote, AuditLogRecord, DailyRiskState, DailyStrategyPnl, ReconciliationReport,
]


@router.post("/reset-data")
async def reset_data(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    for model in _RESET_DATA_MODELS:
        await db.execute(model.__table__.delete())
    await db.commit()
    logger.warning("all trade/log/run data reset", user=user.username)
    return {"reset": True}


@router.post("/wipe")
async def wipe_everything(
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Deletes every row in every table -- reversed topological table order
    (Base.metadata.sorted_tables) so FK-dependent rows always go before
    what they reference, without having to hand-maintain the order as the
    schema grows. Once app_user is empty, GET /auth/setup-status naturally
    reports "needs setup" -- that's the existing first-run flow, not a
    separate mode this has to invent."""
    for table in reversed(Base.metadata.sorted_tables):
        await db.execute(table.delete())
    await db.commit()
    logger.warning("full data wipe executed", user=user.username)
    return {"wiped": True}
