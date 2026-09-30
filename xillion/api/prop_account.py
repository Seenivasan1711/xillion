"""
Prop account limits API (2026-09-30): FundingPips settings + live-from-
closed-trades status. See xillion/engine/prop_account.py for the rules and
the "closed trades only" scope.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.credstore import load_credentials, save_credentials
from xillion.db.models import AppUser, MyTrade
from xillion.engine.prop_account import (
    PHASE_TARGET_PCT,
    ClosedTrade,
    PropConfig,
    PropStatus,
    compute_status,
    crossed,
    next_reset,
    warning_text,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/prop-account", tags=["prop-account"])

# Same "generic credential store for app settings" reuse as Risk Limits /
# Notifications in xillion/api/settings.py -- no migration needed.
CONFIG_NAME = "Prop Account"
CONFIG_BROKER = "Settings"


class PropConfigBody(BaseModel):
    account: str = ""
    firm: str = "FundingPips"
    program: str = "2-Step Flex"
    phase: str = "phase1"
    start_balance: float = 5000.0
    start_date: str = "2026-01-01"
    daily_loss_pct: float = 4.0
    max_loss_pct: float = 12.0
    personal_daily_stop_usd: float = 50.0
    warn_at_pct: float = 80.0
    min_profitable_day_pct: float = 0.5


async def load_config(db: AsyncSession) -> PropConfig:
    raw = await load_credentials(db, CONFIG_NAME) or {}
    known = {f.name for f in fields(PropConfig)}
    return PropConfig(**{k: v for k, v in raw.items() if k in known})


async def status_for(
    db: AsyncSession, cfg: PropConfig | None = None, now: datetime | None = None
) -> tuple[PropConfig, PropStatus]:
    from dataclasses import replace

    from sqlalchemy import func

    from xillion.api.my_trades import net_pnl

    cfg = cfg or await load_config(db)
    if not cfg.account:
        top = (
            await db.execute(
                select(MyTrade.account)
                .group_by(MyTrade.account)
                .order_by(func.count().desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        cfg = replace(cfg, account=top or "")
    rows = (
        (
            await db.execute(
                select(MyTrade).where(
                    MyTrade.account == cfg.account, MyTrade.close_time.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    trades = [
        ClosedTrade(close_time=datetime.fromisoformat(t.close_time), net_pnl=p)
        for t in rows
        if t.close_time is not None and (p := net_pnl(t)) is not None
    ]
    return cfg, compute_status(cfg, trades, now)


def status_dict(cfg: PropConfig, st: PropStatus) -> dict:
    return {
        "config": asdict(cfg) | {"profit_target_pct": cfg.profit_target_pct},
        "server_day": st.server_day,
        "next_reset_utc": next_reset().isoformat(),
        "balance": st.balance,
        "today_pnl": st.today_pnl,
        "total_pnl": st.total_pnl,
        "level": st.level,
        "limits": [
            {
                "name": lim.name,
                "limit_usd": round(lim.limit_usd, 2),
                "used_usd": round(lim.used_usd, 2),
                "used_pct": round(lim.used_pct, 1),
                "level": lim.level,
            }
            for lim in st.limits
        ],
        "target_usd": st.target_usd,
        "target_progress_pct": st.target_progress_pct,
        "trading_days": st.trading_days,
        "profitable_days": st.profitable_days,
        "trades_counted": st.trades_counted,
        "basis": "closed trades only (open positions not included)",
    }


async def warn_if_crossed(
    request: Request | None, cfg: PropConfig, before: PropStatus, after: PropStatus
) -> list[str]:
    """Telegram warning for every limit whose level got worse. Returns the
    names warned about (also useful to the caller/tests)."""
    worse = crossed(before, after)
    if not worse:
        return []
    notifier = getattr(getattr(request, "app", None), "state", None)
    notifier = getattr(notifier, "telegram", None)
    severity = "critical" if any(lim.level == "breach" for lim in worse) else "warn"
    if notifier is not None:
        try:
            await notifier.alert("Prop account limit", warning_text(cfg, after, worse), severity)
        except Exception as exc:  # a failed alert must never fail the import
            logger.warning("prop limit alert failed", error=str(exc))
    logger.info("prop limit crossed", limits=[lim.name for lim in worse], level=after.level)
    return [lim.name for lim in worse]


@router.get("/config")
async def get_config(db: AsyncSession = Depends(db_dep), user: AppUser = Depends(get_current_user)):
    cfg = await load_config(db)
    return asdict(cfg) | {"profit_target_pct": cfg.profit_target_pct}


@router.put("/config")
async def put_config(
    body: PropConfigBody,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    if body.phase not in PHASE_TARGET_PCT:
        raise HTTPException(422, f"phase must be one of {sorted(PHASE_TARGET_PCT)}")
    if body.start_balance <= 0:
        raise HTTPException(422, "start_balance must be positive")
    try:
        datetime.fromisoformat(body.start_date)
    except ValueError as exc:
        raise HTTPException(422, "start_date must be YYYY-MM-DD") from exc
    await save_credentials(db, CONFIG_NAME, CONFIG_BROKER, body.model_dump())
    return {"saved": True}


@router.get("/status")
async def get_status(db: AsyncSession = Depends(db_dep), user: AppUser = Depends(get_current_user)):
    cfg, st = await status_for(db)
    return status_dict(cfg, st)
