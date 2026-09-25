"""D1 swing machinery (2026-09-25): exit hook, trading-day D1 bars, causal features."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from research.xauusd_scalping.engine.backtest_engine import Bar, BacktestEngine, RiskLimits, Side, Signal
from research.xauusd_scalping.engine.cost_model import CostModel
from research.xauusd_scalping.strategies.swing_suite import compute_daily_features


def _daily(n, seed=3):
    rng = np.random.default_rng(seed)
    px = 1800 + np.cumsum(rng.normal(0, 15, n))
    out, d = [], datetime(2021, 1, 4, 21, 55, tzinfo=UTC)
    while len(out) < n:
        if d.weekday() < 5:
            i = len(out)
            o = px[i - 1] if i else px[i]
            out.append(Bar(ts=d, open=o, high=max(o, px[i]) + 5, low=min(o, px[i]) - 5, close=px[i]))
        d += timedelta(days=1)
    return out


def test_daily_features_are_causal():
    bars = _daily(600)
    full = compute_daily_features(bars)
    part = compute_daily_features(bars[:400])
    pd.testing.assert_frame_equal(part, full.iloc[:400], check_freq=False)


class _EnterThenExitOnThirdBar:
    def __init__(self):
        self.i = 0

    def on_bar(self, bar, ctx):
        self.i += 1
        if self.i == 2:
            return Signal(side=Side.LONG, stop_price=bar.close - 1000, target_price=bar.close + 1000)
        return None

    def exit_signal(self, bar, ctx, position):
        return bar.ts == self.exit_ts


def test_exit_signal_hook_exits_at_that_bars_close():
    bars = _daily(10)
    s = _EnterThenExitOnThirdBar()
    s.exit_ts = bars[4].ts
    e = BacktestEngine(CostModel.zero(), risk=RiskLimits(min_sl_pts=None, min_target_pts=None))
    tr = e.run(bars, s).trades
    assert len(tr) == 1 and tr[0].exit_reason == "signal_exit" and tr[0].exit_ts == bars[4].ts
    assert tr[0].exit_price == bars[4].close


def test_daily_trading_bars_follow_the_ny_1700_roll():
    import os
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "from datetime import datetime, UTC, timedelta\n"
        "from engine.backtest_engine import Bar\n"
        "import run_backtests as rb\n"
        "t0 = datetime(2026, 1, 18, 23, 0, tzinfo=UTC)  # Sunday reopen -> Monday\n"
        "m1 = [Bar(ts=t0 + timedelta(minutes=i), open=1, high=2, low=0.5, close=1.5) for i in range(60 * 30)]\n"
        "d = rb.daily_trading_bars(m1)\n"
        "assert len(d) == 2, len(d)\n"
        "assert d[0].ts == datetime(2026, 1, 19, 21, 59, tzinfo=UTC), d[0].ts  # Monday bar ends 16:59 EST\n"
    )
    here = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "-c", code], cwd=here, env={**os.environ, "RESEARCH_DATA_SOURCE": "dukascopy"},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
