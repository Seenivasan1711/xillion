"""
C2 timeframe experiment (2026-09-23): the C1 zero-cost diagnostic found 6
of 10 strategies have real gross (pre-cost) edge that a fixed ~$3.80/trade
cost erases on tight M1 stops. Per the external review's Section C2, the
predicted fix is moving to a coarser timeframe (M5/M15) with proportionally
wider stops: cost stays ~fixed in $ terms while the per-trade edge grows.

This tests that prediction directly: SAME strategy code, SAME real cost
model, only the bar interval fed to the engine changes. No parameter
retuning -- if a strategy's own lookback/threshold values don't make sense
at M5/M15, that's reported as a finding, not silently patched.

Does not import run_backtests.py (its s04 import is mid-edit by a
concurrent fork) -- reimplements the small pieces needed directly.
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from engine.backtest_engine import Bar, BacktestEngine, RiskLimits, SizingConfig  # noqa: E402
from engine.cost_model import CostModel  # noqa: E402

from strategies.s01_liquidity_sweep_fvg import LiquiditySweepFvgStrategy  # noqa: E402
from strategies.s03_order_block_retest import OrderBlockRetestStrategy  # noqa: E402
from strategies.s06_ote_fib_retracement import OteFibRetracementStrategy  # noqa: E402
from strategies.s07_value_area_rotation import ValueAreaRotationStrategy  # noqa: E402
from strategies.s08_bos_pullback_continuation import BosPullbackContinuationStrategy  # noqa: E402
from strategies.s10_equal_levels_rsi_divergence import (  # noqa: E402
    EqualLevelsRsiDivergenceStrategy,
)

STRATEGIES = [
    ("S01 Liquidity Sweep + Displacement + FVG Retest", LiquiditySweepFvgStrategy, 0.21),
    ("S03 Order Block Retest after BOS", OrderBlockRetestStrategy, 0.23),
    ("S06 Premium/Discount OTE Fib Retracement", OteFibRetracementStrategy, 0.29),
    ("S07 Market Profile Value-Area Rotation", ValueAreaRotationStrategy, 0.33),
    ("S08 BOS Pullback Continuation", BosPullbackContinuationStrategy, 0.19),
    ("S10 Equal Highs/Lows + RSI Divergence", EqualLevelsRsiDivergenceStrategy, 0.25),
]

DATA_DIR = Path(__file__).parent / "data" / "xauusd"


def load_m1_bars() -> list[Bar]:
    frames = [pd.read_parquet(f) for f in sorted(glob.glob(str(DATA_DIR / "*.parquet")))]
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="ts").sort_values("ts")
    return [
        Bar(ts=row.ts, open=row.open, high=row.high, low=row.low, close=row.close, volume=row.volume)
        for row in df.itertuples()
    ]


def resample_bars(bars: list[Bar], interval_minutes: int) -> list[Bar]:
    """Generic OHLC resampler for any interval, not just daily -- groups by
    floor(minute-of-day / interval) within each calendar day, so session
    boundaries (used by session_for()) still land on real clock times."""
    if interval_minutes <= 1:
        return bars
    buckets: dict[tuple, list[Bar]] = {}
    for b in bars:
        minute_of_day = b.ts.hour * 60 + b.ts.minute
        bucket_start_minute = (minute_of_day // interval_minutes) * interval_minutes
        key = (b.ts.date(), bucket_start_minute)
        buckets.setdefault(key, []).append(b)
    out: list[Bar] = []
    for key in sorted(buckets):
        group = buckets[key]
        date, bucket_start_minute = key
        ts = pd.Timestamp(date) + pd.Timedelta(minutes=bucket_start_minute)
        out.append(
            Bar(
                ts=ts.to_pydatetime().replace(tzinfo=group[0].ts.tzinfo),
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
            )
        )
    return out


def make_engine() -> BacktestEngine:
    return BacktestEngine(
        cost_model=CostModel(),
        sizing=SizingConfig(mode="fixed_lot", fixed_lots=0.08),
        risk=RiskLimits(max_trades_per_session=4, daily_loss_cap_usd=50.0, consecutive_loss_halt=2),
    )


def compute_metrics(trades, initial_equity: float = 5000.0) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]
    win_rate = len(wins) / n * 100
    gross_win = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    avg_r = sum(t.r_multiple for t in trades) / n
    total_pnl = sum(t.pnl_usd for t in trades)
    return {"n": n, "win_rate": win_rate, "profit_factor": profit_factor, "avg_r": avg_r, "total_pnl": total_pnl}


def run_all(bars: list[Bar], label: str) -> dict:
    results = {}
    print(f"\n=== {label}: {len(bars)} bars ({bars[0].ts} -> {bars[-1].ts}) ===")
    for name, cls, m1_pf in STRATEGIES:
        strat = cls()
        eng = make_engine()
        res = eng.run(bars, strat)
        m = compute_metrics(res.trades)
        results[name] = m
        pf = m.get("profit_factor", 0)
        print(
            f"{name}: n={m.get('n', 0)} win%={m.get('win_rate', 0):.1f} PF={pf:.2f} "
            f"(M1 baseline PF={m1_pf}) PnL=${m.get('total_pnl', 0):.2f}"
        )
    return results


def main():
    m1_bars = load_m1_bars()
    m5_bars = resample_bars(m1_bars, 5)
    m15_bars = resample_bars(m1_bars, 15)

    all_results = {"M1": {}, "M5": run_all(m5_bars, "M5"), "M15": run_all(m15_bars, "M15")}
    # M1 baseline pulled from the already-committed v3 numbers, not rerun here
    for name, _cls, m1_pf in STRATEGIES:
        all_results["M1"][name] = {"profit_factor": m1_pf}

    import json

    with open(Path(__file__).parent / "_timeframe_experiment_raw.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print("\nWritten to _timeframe_experiment_raw.json")


if __name__ == "__main__":
    main()
