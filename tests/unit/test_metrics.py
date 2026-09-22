"""
compute_metrics: found a real crash 2026-09-22 running Gold Sweep-
Reversal's first real 6-month backtest, which lost more than its
starting capital. (final/initial) raised to a fractional power when
final <= 0 evaluates to a complex number in Python (not an error), which
silently corrupted every metric downstream until round() finally raised
on it -- so the whole backtest result was lost instead of just reporting
a bad CAGR.
"""

from xillion.engine.metrics import ClosedTrade, compute_metrics


def _trade(pnl: float) -> ClosedTrade:
    return ClosedTrade(pnl=pnl, entry_price=100.0, exit_price=100.0, quantity=1)


def test_wiped_out_account_reports_minus_100pct_cagr_not_a_crash():
    trades = [_trade(-6000.0)]
    equity_curve = [5000.0, -1000.0]  # lost more than the starting capital
    metrics = compute_metrics(trades=trades, equity_curve=equity_curve, initial_capital=5000.0)
    assert metrics["cagr_pct"] == -100.0
    assert metrics["final_capital"] == -1000.0


def test_normal_profitable_run_still_computes_a_real_cagr():
    trades = [_trade(500.0)]
    equity_curve = [5000.0, 5500.0]
    metrics = compute_metrics(trades=trades, equity_curve=equity_curve, initial_capital=5000.0)
    assert metrics["cagr_pct"] > 0
