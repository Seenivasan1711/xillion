"""
Backtest metrics: Sharpe, Sortino, max drawdown, win rate, profit factor, etc.
Input: list of closed trades with entry/exit prices and PnL.
Output: a flat dict suitable for JSON storage.
"""
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class ClosedTrade:
    pnl: float
    entry_price: float
    exit_price: float
    quantity: int
    # Populated by position_math.apply_fill. Optional so older callers and
    # tests keep working, but the BacktestTrade table needs them non-null,
    # so anything persisting a run must supply them.
    symbol: str = ""
    side: str = ""              # "LONG" | "SHORT"
    entry_ts: Optional[datetime] = None
    exit_ts: Optional[datetime] = None
    tag: str = ""


def compute_metrics(
    trades: list[ClosedTrade],
    equity_curve: list[float],
    initial_capital: float,
    risk_free_rate: float = 0.0,
) -> dict:
    if not trades and not equity_curve:
        return _empty_metrics()

    # ── Portfolio-level metrics come from the equity curve ─────────────────
    # The curve is authoritative for "how much money do I have": it already
    # includes fees and marks open positions to market. Deriving these from
    # closed trades alone used to zero out every metric for a strategy that
    # was still holding a winning position.
    realised_pnl = sum(t.pnl for t in trades)
    if equity_curve:
        final_capital = equity_curve[-1]
        total_pnl = final_capital - initial_capital
    else:
        total_pnl = realised_pnl
        final_capital = initial_capital + total_pnl

    # ── Trade-level stats come from closed trades ──────────────────────────
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]

    win_rate = len(winners) / len(trades) if trades else 0.0
    avg_win = sum(t.pnl for t in winners) / len(winners) if winners else 0.0
    avg_loss = sum(abs(t.pnl) for t in losers) / len(losers) if losers else 0.0
    gross_loss = sum(abs(t.pnl) for t in losers)
    # None (not inf) when there are no losses — inf is not valid JSON.
    profit_factor = (
        sum(t.pnl for t in winners) / gross_loss if gross_loss > 0 else None
    )
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # Returns from equity curve
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] != 0:
            returns.append((equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1])

    sharpe = _sharpe(returns, risk_free_rate) if returns else 0.0
    sortino = _sortino(returns, risk_free_rate) if returns else 0.0  # may be None
    max_dd, max_dd_pct = _max_drawdown(equity_curve)
    cagr = _cagr(initial_capital, final_capital, len(equity_curve))

    return {
        "total_return_pct": round((total_pnl / initial_capital) * 100, 2) if initial_capital else 0,
        "total_pnl": round(total_pnl, 2),
        "realised_pnl": round(realised_pnl, 2),
        "final_capital": round(final_capital, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3) if sortino is not None else None,
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct * 100, 2),
        "trade_count": len(trades),
        "win_count": len(winners),
        "loss_count": len(losers),
        "win_rate_pct": round(win_rate * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "expectancy": round(expectancy, 2),
    }


def _empty_metrics() -> dict:
    return {k: 0 for k in [
        "total_return_pct", "total_pnl", "realised_pnl", "final_capital", "cagr_pct",
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "max_drawdown_pct",
        "trade_count", "win_count", "loss_count", "win_rate_pct",
        "avg_win", "avg_loss", "profit_factor", "expectancy",
    ]}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    excess = [r - risk_free for r in returns]
    std = _std(excess)
    if std == 0:
        return 0.0
    return _mean(excess) / std * math.sqrt(252)  # annualised daily


def _sortino(returns: list[float], risk_free: float = 0.0) -> float:
    """Returns None when there is no downside deviation — a Sortino of
    "infinity" is not representable in JSON and used to break the API
    response, so callers must render the no-downside case as "—"."""
    excess = [r - risk_free for r in returns]
    downside = [r for r in excess if r < 0]
    if not downside:
        return None
    downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
    if downside_std == 0:
        return None
    return _mean(excess) / downside_std * math.sqrt(252)


def _max_drawdown(equity_curve: list[float]) -> tuple[float, float]:
    if not equity_curve:
        return 0.0, 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = peak - value
        dd_pct = dd / peak if peak != 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
    return max_dd, max_dd_pct


def _cagr(initial: float, final: float, num_bars: int, bars_per_year: int = 252) -> float:
    if initial <= 0 or num_bars == 0:
        return 0.0
    years = num_bars / bars_per_year
    if years == 0:
        return 0.0
    return (final / initial) ** (1 / years) - 1
