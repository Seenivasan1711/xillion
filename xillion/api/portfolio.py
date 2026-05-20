"""
Portfolio summary endpoint — aggregates PnL, equity, drawdown, and trade stats
for the Dashboard hero card and equity curve.
"""
from datetime import date
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import (
    AppUser,
    DailyRiskState,
    DailyStrategyPnl,
    FillRecord,
    OrderRecord,
    StrategyInstance,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary")
async def portfolio_summary(
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    today = date.today().isoformat()

    # Today's aggregated risk state (written when DB persistence is active)
    risk_row = await db.scalar(
        select(DailyRiskState).where(DailyRiskState.trading_date == today)
    )
    pnl_today_realised = float(risk_row.account_realised_pnl) if risk_row else 0.0
    pnl_today_unrealised = float(risk_row.account_unrealised_pnl) if risk_row else 0.0
    pnl_today = pnl_today_realised + pnl_today_unrealised

    # Fallback: sum live P&L from in-memory strategy contexts when DB is not yet
    # populated (DB persistence for fills/positions is a Phase 10 item).
    engine = getattr(request.app.state, "strategy_engine", None)
    if pnl_today == 0.0 and engine:
        for runner in engine.list_runners():
            try:
                pnl_today += float(runner._ctx.realised_pnl_today())
            except Exception:
                pass

    # Capital totals from all instances
    cap_row = (
        await db.execute(
            select(
                func.sum(StrategyInstance.capital_allocation),
                func.count(StrategyInstance.id),
            )
        )
    ).one()
    total_capital = float(cap_row[0] or 0)

    # Running instances only (= open trades)
    run_row = (
        await db.execute(
            select(
                func.sum(StrategyInstance.capital_allocation),
                func.count(StrategyInstance.id),
            ).where(StrategyInstance.status == "running")
        )
    ).one()
    running_capital = float(run_row[0] or 0)
    open_trades = int(run_row[1] or 0)
    capital_used_pct = (running_capital / total_capital * 100) if total_capital > 0 else 0.0

    # Today's per-strategy trade count
    today_row = (
        await db.execute(
            select(
                func.sum(DailyStrategyPnl.trade_count),
            ).where(DailyStrategyPnl.trading_date == today)
        )
    ).one()
    closed_trades_today = int(today_row[0] or 0)

    # Historical daily PnL grouped by date → cumulative equity curve
    hist = (
        await db.execute(
            select(
                DailyStrategyPnl.trading_date,
                func.sum(
                    DailyStrategyPnl.realised_pnl + DailyStrategyPnl.unrealised_pnl
                ),
            )
            .group_by(DailyStrategyPnl.trading_date)
            .order_by(DailyStrategyPnl.trading_date)
        )
    ).all()

    running_equity = total_capital
    historical_equity: list[dict] = []
    for trading_date, daily_pnl in hist:
        running_equity += float(daily_pnl or 0)
        historical_equity.append({"ts": trading_date, "value": round(running_equity, 2)})

    equity_total = (historical_equity[-1]["value"] if historical_equity else total_capital) + pnl_today

    # Intraday curve from today's fills — running realised PnL throughout the session.
    # SELL proceeds minus BUY costs gives a rough directional curve; proper per-trade
    # matching would require entry/exit pairing which isn't tracked in FillRecord alone.
    fills = (
        await db.execute(
            select(
                FillRecord.ts,
                FillRecord.side,
                FillRecord.quantity,
                FillRecord.price,
                FillRecord.fees,
            )
            .where(FillRecord.ts >= today)
            .order_by(FillRecord.ts)
        )
    ).all()

    running_intraday = total_capital
    intraday_curve: list[dict] = []
    for fill_ts, side, qty, price, fees in fills:
        delta = float(price) * int(qty)
        if side == "SELL":
            running_intraday += delta - float(fees)
        else:
            running_intraday -= delta + float(fees)
        intraday_curve.append({"ts": str(fill_ts), "value": round(running_intraday, 2)})

    # Drawdown % of daily loss cap from risk manager
    drawdown_pct = 0.0
    loss_budget_pct = 0.0
    risk = getattr(request.app.state, "risk", None)
    if risk:
        status = risk.status()
        daily_loss_limit_str = status.get("account_daily_loss") or "0"
        try:
            daily_loss_limit = float(daily_loss_limit_str)
        except (TypeError, ValueError):
            daily_loss_limit = 0.0
        if daily_loss_limit > 0 and pnl_today < 0:
            loss_budget_pct = min(100.0, -pnl_today / daily_loss_limit * 100)
        # Drawdown relative to equity — max daily loss as % of equity
        if equity_total > 0 and pnl_today < 0:
            drawdown_pct = min(100.0, -pnl_today / equity_total * 100)

    avg_trade_pnl = (pnl_today / closed_trades_today) if closed_trades_today > 0 else 0.0

    # Win rate from FIFO-matched fills for today
    win_rate = 0.0
    try:
        from xillion.api.trades import _match_fills
        fill_rows = (
            await db.execute(
                select(
                    FillRecord,
                    OrderRecord.strategy_instance_id,
                    StrategyInstance.name,
                    StrategyInstance.mode,
                )
                .join(OrderRecord, FillRecord.order_id == OrderRecord.id)
                .outerjoin(StrategyInstance, OrderRecord.strategy_instance_id == StrategyInstance.id)
                .where(FillRecord.ts >= today)
            )
        ).all()
        matched_today = _match_fills(list(fill_rows))
        if matched_today:
            wins_today = sum(1 for t in matched_today if t["pnl"] > 0)
            win_rate = round(wins_today / len(matched_today) * 100, 1)
    except Exception:
        pass

    return {
        "pnl_today": round(pnl_today, 2),
        "pnl_today_pct": round((pnl_today / equity_total * 100) if equity_total > 0 else 0, 2),
        "equity_total": round(equity_total, 2),
        "intraday_curve": intraday_curve,
        "historical_equity": historical_equity,
        "drawdown_pct": round(drawdown_pct, 2),
        "capital_used_pct": round(capital_used_pct, 2),
        "loss_budget_pct": round(loss_budget_pct, 2),
        "open_trades": open_trades,
        "closed_trades_today": closed_trades_today,
        "win_rate": win_rate,
        "avg_trade_pnl": round(avg_trade_pnl, 2),
    }
