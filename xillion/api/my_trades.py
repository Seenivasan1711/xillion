"""
My Trades API (2026-09-26): Rakesh's own trades -- imported from an MT5
History report or entered by hand -- tagged by setup, with per-setup stats.
Separate from /journal, which is strategy-generated signals and backtests.

Re-importing an overlapping report is safe: rows are keyed by (account, MT5
position ticket); an existing row gets its broker numbers refreshed but
keeps every tag/note the user added.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from statistics import mean

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, MyTrade
from xillion.engine.mt5_history_report import parse_account, parse_positions

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/my-trades", tags=["my-trades"])

# Units per 1.0 lot, for turning a stop distance into money (R-multiple).
# Unknown symbols get no R rather than a guessed one.
CONTRACT_SIZE = {"XAUUSD": 100.0, "EURUSD": 100_000.0, "GBPUSD": 100_000.0}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _f(x) -> float | None:
    return None if x is None else float(x)


def net_pnl(t: MyTrade) -> float | None:
    if t.profit is None:
        return None
    return float(t.profit) + float(t.commission or 0) + float(t.swap or 0)


def r_multiple(t: MyTrade) -> float | None:
    """Net P&L in units of the money at risk at the stop. Uses the stop as
    recorded -- for an MT5 import that's the S/L at close, so a stop that was
    trailed to breakeven understates the original risk (flagged in the UI)."""
    size = CONTRACT_SIZE.get((t.symbol or "").upper().rstrip(".").split(".")[0])
    pnl = net_pnl(t)
    if size is None or pnl is None or t.stop_loss is None:
        return None
    risk = abs(float(t.open_price) - float(t.stop_loss)) * float(t.volume_lots) * size
    return pnl / risk if risk > 0 else None


async def _prop_status(db: AsyncSession):
    """Prop-account status BEFORE a change is committed (the pending ORM
    objects aren't flushed yet), so the after-commit status can be compared."""
    from xillion.api.prop_account import status_for

    with db.no_autoflush:
        return await status_for(db)


async def _warn_limits(db: AsyncSession, request: Request | None, cfg, before) -> None:
    from xillion.api.prop_account import status_for, warn_if_crossed

    _cfg, after = await status_for(db, cfg)
    await warn_if_crossed(request, cfg, before, after)


def _row(t: MyTrade) -> dict:
    return {
        "id": t.id,
        "account": t.account,
        "source": t.source,
        "external_id": t.external_id,
        "symbol": t.symbol,
        "side": t.side,
        "volume_lots": _f(t.volume_lots),
        "open_time": t.open_time,
        "open_price": _f(t.open_price),
        "close_time": t.close_time,
        "close_price": _f(t.close_price),
        "stop_loss": _f(t.stop_loss),
        "take_profit": _f(t.take_profit),
        "commission": _f(t.commission),
        "swap": _f(t.swap),
        "profit": _f(t.profit),
        "net_pnl": net_pnl(t),
        "r_multiple": r_multiple(t),
        "setup_tag": t.setup_tag,
        "reason": t.reason,
        "followed_plan": t.followed_plan,
        "notes": t.notes,
    }


class ManualTrade(BaseModel):
    account: str = "fundingpips"
    symbol: str = "XAUUSD"
    side: str  # BUY | SELL
    volume_lots: float
    open_time: str  # ISO; naive = UTC
    open_price: float
    close_time: str | None = None
    close_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    commission: float = 0.0
    swap: float = 0.0
    profit: float | None = None
    setup_tag: str | None = None
    reason: str | None = None
    followed_plan: bool | None = None
    notes: str | None = None


class TradeTags(BaseModel):
    setup_tag: str | None = None
    reason: str | None = None
    followed_plan: bool | None = None
    notes: str | None = None


def _iso_utc(s: str | None) -> str | None:
    if s is None:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise HTTPException(422, f"bad timestamp {s!r}") from exc
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


@router.get("")
async def list_trades(
    setup: str | None = Query(None),
    account: str | None = Query(None),
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    q = select(MyTrade).order_by(MyTrade.open_time.desc())
    if setup:
        q = q.where(MyTrade.setup_tag == setup)
    if account:
        q = q.where(MyTrade.account == account)
    rows = (await db.execute(q)).scalars().all()
    return [_row(t) for t in rows]


@router.get("/accounts")
async def list_accounts(
    db: AsyncSession = Depends(db_dep), user: AppUser = Depends(get_current_user)
):
    from sqlalchemy import func

    rows = (await db.execute(select(MyTrade.account, func.count()).group_by(MyTrade.account))).all()
    return [{"account": a, "trades": n} for a, n in sorted(rows, key=lambda r: -r[1])]


@router.post("")
async def create_trade(
    body: ManualTrade,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
    request: Request = None,  # type: ignore[assignment]  # injected by FastAPI; None in direct calls
):
    side = body.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(422, "side must be BUY or SELL")
    if body.volume_lots <= 0:
        raise HTTPException(422, "volume_lots must be positive")
    t = MyTrade(
        **body.model_dump(exclude={"side", "open_time", "close_time"}),
        side=side,
        open_time=_iso_utc(body.open_time),
        close_time=_iso_utc(body.close_time),
        source="manual",
        created_at=_now(),
    )
    cfg, before = await _prop_status(db)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    await _warn_limits(db, request, cfg, before)
    return _row(t)


@router.patch("/{trade_id}")
async def tag_trade(
    trade_id: int,
    body: TradeTags,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    t = await db.get(MyTrade, trade_id)
    if t is None:
        raise HTTPException(404, "trade not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, (v.strip() or None) if isinstance(v, str) else v)
    t.updated_at = _now()
    await db.commit()
    return _row(t)


@router.delete("/{trade_id}")
async def delete_trade(
    trade_id: int, db: AsyncSession = Depends(db_dep), user: AppUser = Depends(get_current_user)
):
    t = await db.get(MyTrade, trade_id)
    if t is None:
        raise HTTPException(404, "trade not found")
    if t.source != "manual":
        # An imported trade is a broker record; deleting it would just come
        # back on the next import. Tag it instead.
        raise HTTPException(409, "only manually entered trades can be deleted")
    await db.delete(t)
    await db.commit()
    return {"deleted": trade_id}


@router.post("/import")
async def import_mt5_report(
    file: UploadFile = File(...),
    account: str | None = Query(None),
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
    request: Request = None,  # type: ignore[assignment]  # injected by FastAPI; None in direct calls
):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "report larger than 20 MB")
    try:
        positions, warnings = parse_positions(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Key trades by the MT5 login in the report header, so two accounts'
    # position tickets can never collide; an explicit ?account= overrides.
    meta = parse_account(raw)
    account = account or meta.login or "fundingpips"
    existing = {
        t.external_id: t
        for t in (
            await db.execute(
                select(MyTrade).where(
                    MyTrade.account == account,
                    MyTrade.external_id.in_([p.ticket for p in positions]),
                )
            )
        )
        .scalars()
        .all()
    }
    added = updated = 0
    for p in positions:
        fields = dict(
            symbol=p.symbol,
            side=p.side,
            volume_lots=p.volume_lots,
            open_time=p.open_time,
            open_price=p.open_price,
            close_time=p.close_time,
            close_price=p.close_price,
            stop_loss=p.stop_loss,
            take_profit=p.take_profit,
            commission=p.commission,
            swap=p.swap,
            profit=p.profit,
        )
        t = existing.get(p.ticket)
        if t is None:
            added += 1
            if not dry_run:
                db.add(
                    MyTrade(
                        account=account,
                        source="mt5_import",
                        external_id=p.ticket,
                        created_at=_now(),
                        **fields,
                    )
                )
        else:
            updated += 1
            if not dry_run:
                for k, v in fields.items():
                    setattr(t, k, v)
                t.updated_at = _now()
    if not dry_run:
        cfg, before = await _prop_status(db)
        await db.commit()
        await _warn_limits(db, request, cfg, before)
    logger.info("mt5 report import", account=account, added=added, updated=updated, dry_run=dry_run)
    return {
        "account": account,
        "server": meta.server,
        "is_demo": meta.is_demo,
        "parsed": len(positions),
        "added": added,
        "updated": updated,
        "dry_run": dry_run,
        "warnings": warnings,
    }


def _group_stats(trades: Sequence[MyTrade]) -> dict:
    closed = [(t, p) for t in trades if (p := net_pnl(t)) is not None]
    pnls = [p for _t, p in closed]
    rs = [r for r in (r_multiple(t) for t, _p in closed) if r is not None]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    return {
        "n": len(closed),
        "net_pnl": round(sum(pnls), 2),
        "win_rate": round(100 * len(wins) / len(closed), 1) if closed else None,
        "avg_win": round(mean(wins), 2) if wins else None,
        "avg_loss": round(mean(losses), 2) if losses else None,
        "profit_factor": round(sum(wins) / sum(losses), 2) if losses else None,
        "avg_r": round(mean(rs), 3) if rs else None,
        "n_with_r": len(rs),
    }


@router.get("/stats")
async def trade_stats(
    account: str | None = Query(None),
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    q = select(MyTrade)
    if account:
        q = q.where(MyTrade.account == account)
    trades = (await db.execute(q)).scalars().all()
    by_setup: dict[str, list[MyTrade]] = {}
    for t in trades:
        by_setup.setdefault(t.setup_tag or "(untagged)", []).append(t)
    return {
        "overall": _group_stats(trades),
        "by_setup": {k: _group_stats(v) for k, v in sorted(by_setup.items())},
        "followed_plan": {
            "yes": _group_stats([t for t in trades if t.followed_plan is True]),
            "no": _group_stats([t for t in trades if t.followed_plan is False]),
        },
    }
