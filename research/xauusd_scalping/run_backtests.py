"""
P3 backtest runner: loads all real M1 XAUUSD data currently on disk, runs
all 10 shortlisted strategies (01_shortlist_v2.md) through the harness,
and prints the metrics 03_results.md is built from.

Data reality, honestly (2026-09-22): the background Dukascopy backfill has
NOT yet produced a continuous 3-6 month series -- it has two disjoint real
windows (2026-03-01 to 2026-03-13, and 2026-09-14 to 2026-09-16), ~16
calendar days of real M1 bars total. A proper 6-month-train/1-month-test
walk-forward is not meaningful on this sample. This runner does the
honest thing available instead: run each strategy across the full pooled
dataset, report March-window vs September-window separately (a basic
"does it look the same in two different periods" check, not a real
walk-forward), and flag every result's sample size plainly rather than
pretend statistical power that doesn't exist yet. Re-run this script once
the backfill has produced a real multi-month continuous series for the
validation protocol this was actually designed for.
"""

from __future__ import annotations

import functools
import glob
import os
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from engine.backtest_engine import Bar, BacktestEngine, RiskLimits, SizingConfig  # noqa: E402
from engine.cost_model import CostModel  # noqa: E402
from engine.instruments import (  # noqa: E402
    equivalent_lots,
    get_instrument,
    measure_price_scale,
    scale_strategy_params,
)

from strategies.s01_liquidity_sweep_fvg import LiquiditySweepFvgStrategy  # noqa: E402
from strategies.s02_mtf_liquidity_choch import MtfLiquidityChochStrategy  # noqa: E402
from strategies.s03_order_block_retest import OrderBlockRetestStrategy  # noqa: E402
from strategies.s04_wyckoff_spring_upthrust import WyckoffSpringUpthrustStrategy  # noqa: E402
from strategies.s05_nr7_inside_bar_breakout import Nr7InsideBarBreakoutStrategy  # noqa: E402
from strategies.s06_ote_fib_retracement import OteFibRetracementStrategy  # noqa: E402
from strategies.s07_value_area_rotation import ValueAreaRotationStrategy  # noqa: E402
from strategies.s08_bos_pullback_continuation import BosPullbackContinuationStrategy  # noqa: E402
from strategies.s09_session_liquidity_run_reversal import (  # noqa: E402
    SessionLiquidityRunReversalStrategy,
)
from strategies.s10_equal_levels_rsi_divergence import (  # noqa: E402
    EqualLevelsRsiDivergenceStrategy,
)
from strategies.s11_video_liquidity_mtf_scalp import VideoLiquidityMtfScalpStrategy  # noqa: E402

STRATEGIES = [
    ("S01 Liquidity Sweep + Displacement + FVG Retest", LiquiditySweepFvgStrategy),
    ("S02 Multi-Timeframe Liquidity + CHoCH", MtfLiquidityChochStrategy),
    ("S03 Order Block Retest after BOS", OrderBlockRetestStrategy),
    ("S04 Wyckoff Spring/Upthrust", WyckoffSpringUpthrustStrategy),
    ("S05 NR7/Inside-Bar Compression Breakout", Nr7InsideBarBreakoutStrategy),
    ("S06 Premium/Discount OTE Fib Retracement", OteFibRetracementStrategy),
    ("S07 Market Profile Value-Area Rotation", ValueAreaRotationStrategy),
    ("S08 BOS Pullback Continuation", BosPullbackContinuationStrategy),
    ("S09 Session Liquidity Run + Reversal", SessionLiquidityRunReversalStrategy),
    ("S10 Equal Highs/Lows + RSI Divergence", EqualLevelsRsiDivergenceStrategy),
    # Appended (not inserted) 2026-09-25 so S01-S10 keep their benchmark
    # seed index. M1-native: it builds its own H1/M15 view and its lifetimes
    # are counted in M1 bars, so only meaningful at RESEARCH_TIMEFRAME=M1.
    ("S11 Video MTF Liquidity + Structure Scalp", VideoLiquidityMtfScalpStrategy),
]

def selected_strategies() -> list[tuple[int, str, type]]:
    """(index in STRATEGIES, name, class), optionally filtered by
    RESEARCH_STRATEGIES=S07 or S03,S07 (name prefixes). The index is the
    position in the FULL list, so random_entry_benchmark's per-strategy seed
    (SEED + index) -- and thus its random draws -- are identical whether a
    strategy runs alone or with all ten."""
    wanted = [w.strip().upper() for w in os.environ.get("RESEARCH_STRATEGIES", "").split(",") if w.strip()]
    rows = [(i, name, cls) for i, (name, cls) in enumerate(STRATEGIES)]
    if not wanted:
        return rows
    picked = [r for r in rows if any(r[1].upper().startswith(w + " ") for w in wanted)]
    if len(picked) != len(wanted):
        raise ValueError(f"RESEARCH_STRATEGIES={wanted} matched {[r[1] for r in picked]}")
    return picked


# Which symbol this run is for. Env var rather than argv so that
# random_entry_benchmark.py (which imports this module) follows it too:
#   RESEARCH_SYMBOL=EURUSD python run_backtests.py
SYMBOL = os.environ.get("RESEARCH_SYMBOL", "XAUUSD").upper()
UNDERPOWERED_THRESHOLD = 200
# Spread charged per trade: "table" = the session x volatility table (today's
# broker level, the default), "broker" = the broker's own measured spread for
# that exact minute (MT5 feed only; what those trades would really have paid).
SPREAD_MODE = os.environ.get("RESEARCH_SPREAD", "table").lower()
if SPREAD_MODE not in ("table", "broker"):
    raise ValueError(f"RESEARCH_SPREAD={SPREAD_MODE!r}, expected 'table' or 'broker'")


# RESEARCH_REALISTIC=1: trade it the way Rakesh's FundingPips 2-Step Flex
# $5K account would -- swap charged, a fixed $RESEARCH_RISK_USD (default 25,
# so two stop-outs = his $50 daily stop) at the stop in 0.01-lot steps, and
# flat by Friday close (master-account rule). Off by default so every earlier
# fixed-0.08-lot result stays reproducible.
REALISTIC = os.environ.get("RESEARCH_REALISTIC", "0") == "1"
RISK_USD = float(os.environ.get("RESEARCH_RISK_USD", "25"))

# Bar timeframe the strategies run on (step (a), 2026-09-25): M1 bars are
# resampled to M5/M15/H1 before the strategies see them. Strategy gold-dollar
# distances are scaled by the MEASURED ratio of median bar range (TF / M1),
# never guessed -- see timeframe_scale().
TIMEFRAMES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}
TIMEFRAME = os.environ.get("RESEARCH_TIMEFRAME", "M1").upper()
if TIMEFRAME not in TIMEFRAMES:
    raise ValueError(f"RESEARCH_TIMEFRAME={TIMEFRAME!r}, expected one of {list(TIMEFRAMES)}")


def _load_m1(symbol: str | None = None) -> list[Bar]:
    data_dir = get_instrument(symbol or SYMBOL).data_dir
    frames = [pd.read_parquet(f) for f in sorted(glob.glob(str(data_dir / "*.parquet")))]
    if not frames:
        raise FileNotFoundError(f"no parquet data in {data_dir} -- run data/download_dukascopy.py first")
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="ts").sort_values("ts")
    if SPREAD_MODE == "broker" and "spread_pts" not in df:
        raise ValueError(f"RESEARCH_SPREAD=broker needs per-bar spread_pts -- {data_dir} has none "
                         "(only the MT5 feed does: RESEARCH_DATA_SOURCE=mt5)")
    spreads = df["spread_pts"].tolist() if "spread_pts" in df else [None] * len(df)
    if SPREAD_MODE == "broker":
        real = int(df["spread_pts"].notna().sum())
        print(f"RESEARCH_SPREAD=broker: real per-minute spread on {real:,}/{len(df):,} bars "
              f"(tick-imported); the rest use the table", flush=True)
    return [
        Bar(ts=row.ts, open=row.open, high=row.high, low=row.low, close=row.close, volume=row.volume,
            spread_pts=None if sp is None or sp != sp else float(sp))
        for row, sp in zip(df.itertuples(), spreads, strict=True)
    ]


@functools.cache
def _load_cached(symbol: str) -> tuple:
    return tuple(_load_m1(symbol))


def load_all_bars(symbol: str | None = None) -> list[Bar]:
    """All bars for the active symbol/feed, at RESEARCH_TIMEFRAME."""
    m1 = list(_load_cached((symbol or SYMBOL).upper()))
    minutes = TIMEFRAMES[TIMEFRAME]
    if minutes == 1:
        return m1
    if SPREAD_MODE == "broker":
        raise ValueError("RESEARCH_SPREAD=broker is per-minute; use the table above M1")
    from timeframe_experiment import resample_bars

    return resample_bars(m1, minutes)


@functools.cache
def timeframe_scale() -> float:
    """Median bar high-low at RESEARCH_TIMEFRAME / median at M1, same data.
    Multiplies the strategies' gold-dollar distances (min_sl_pts etc.), the
    same way price_scale does across symbols. 1.0 at M1."""
    if TIMEFRAMES[TIMEFRAME] == 1:
        return 1.0
    from statistics import median

    m1 = list(_load_cached(SYMBOL))
    tf = load_all_bars()
    return median(b.high - b.low for b in tf) / median(b.high - b.low for b in m1)


@functools.cache
def instrument():
    """The active symbol's spec. For anything but XAUUSD, price_scale is
    MEASURED here from real overlapping data (never guessed) and printed."""
    if SYMBOL == "XAUUSD":
        if TIMEFRAMES[TIMEFRAME] == 1:
            return get_instrument("XAUUSD")
        scale = timeframe_scale()
        print(f"XAUUSD {TIMEFRAME}: measured timeframe scale={scale:.3f} (median bar range vs M1); "
              "strategy distance params scaled by it", flush=True)
        return get_instrument("XAUUSD", price_scale=scale)
    if TIMEFRAMES[TIMEFRAME] != 1:
        raise ValueError("RESEARCH_TIMEFRAME above M1 is XAUUSD-only for now (forex parked)")
    scale = measure_price_scale(load_all_bars(SYMBOL), load_all_bars("XAUUSD"))
    inst = get_instrument(SYMBOL, price_scale=scale)
    print(f"{SYMBOL}: measured price_scale={scale:.6f} (median daily range vs XAUUSD), "
          f"equivalent lots={equivalent_lots(inst):.3f}, spread measured={inst.spread_is_measured}", flush=True)
    return inst


def make_engine() -> BacktestEngine:
    inst = instrument()
    if inst.symbol == "XAUUSD":
        cost, lots = CostModel(use_bar_spread=SPREAD_MODE == "broker", charge_swap=REALISTIC), 0.08
    else:
        cost, lots = CostModel.for_instrument(inst), equivalent_lots(inst)
    sizing = (
        SizingConfig(mode="fixed_risk_usd", risk_usd=RISK_USD, lot_step=0.01, point_value_usd=inst.point_value_usd)
        if REALISTIC
        else SizingConfig(mode="fixed_lot", fixed_lots=lots, point_value_usd=inst.point_value_usd)
    )
    return BacktestEngine(
        cost_model=cost,
        sizing=sizing,
        risk=RiskLimits(max_trades_per_session=4, daily_loss_cap_usd=50.0, consecutive_loss_halt=2,
                        flat_before_weekend=REALISTIC),
    )


def make_strategy(cls):
    """Strategy instance with its gold-dollar distance params scaled to the
    active symbol (identity for XAUUSD)."""
    inst = instrument()
    if inst.price_scale == 1.0:
        return cls()
    params_cls = sys.modules[cls.__module__].Params
    return cls(scale_strategy_params(params_cls(), inst))


def results_suffix() -> str:
    """'' for XAUUSD on Dukascopy (keeps existing output filenames), else
    '_eurusd', '_mt5', '_eurusd_mt5' -- so caches from different symbols or
    feeds can never be read back as each other's."""
    from engine.instruments import data_source

    suffix = "" if SYMBOL == "XAUUSD" else f"_{SYMBOL.lower()}"
    if data_source() != "dukascopy":
        suffix = f"{suffix}_{data_source()}"
    if TIMEFRAME != "M1":
        suffix = f"{suffix}_{TIMEFRAME.lower()}"
    if REALISTIC:
        suffix = f"{suffix}_real{RISK_USD:g}"
    return suffix if SPREAD_MODE == "table" else f"{suffix}_brokerspread"


def compute_metrics(trades, initial_equity=5000.0) -> dict:
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
    equity = initial_equity
    peak = equity
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_usd
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100 if peak > 0 else 0)
    ambiguous = sum(1 for t in trades if t.ambiguous_bar)
    return {
        "n": n,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_r": avg_r,
        "total_pnl": total_pnl,
        "max_dd_pct": max_dd,
        "ambiguous_bars": ambiguous,
        "underpowered": n < UNDERPOWERED_THRESHOLD,
    }


def session_breakdown(trades) -> dict:
    out: dict[str, dict] = {}
    sessions = sorted({t.session for t in trades})
    for s in sessions:
        out[s] = compute_metrics([t for t in trades if t.session == s])
    return out


def monte_carlo(trades, n_sims=5000, seed=42) -> dict:
    if not trades:
        return {}
    pnls = [t.pnl_usd for t in trades]
    rng = random.Random(seed)
    monthly_like = []
    max_dds = []
    for _ in range(n_sims):
        shuffled = pnls[:]
        rng.shuffle(shuffled)
        equity = 5000.0
        peak = equity
        dd = 0.0
        for p in shuffled:
            equity += p
            peak = max(peak, equity)
            dd = max(dd, (peak - equity) / peak * 100 if peak > 0 else 0)
        monthly_like.append(sum(shuffled))
        max_dds.append(dd)
    monthly_like.sort()
    max_dds.sort()

    def pct(arr, p):
        idx = min(len(arr) - 1, int(len(arr) * p))
        return arr[idx]

    return {
        "pnl_p5": pct(monthly_like, 0.05),
        "pnl_p50": pct(monthly_like, 0.50),
        "pnl_p95": pct(monthly_like, 0.95),
        "dd_p95": pct(max_dds, 0.95),
    }


def main():
    all_bars = load_all_bars()
    instrument()  # prints the measured scale up front for non-XAUUSD runs
    march_bars = [b for b in all_bars if b.ts.month == 3]
    sept_bars = [b for b in all_bars if b.ts.month == 9]
    print(f"Total bars: {len(all_bars)} ({all_bars[0].ts} -> {all_bars[-1].ts})")
    print(f"March window: {len(march_bars)} bars, September window: {len(sept_bars)} bars")
    print()

    results = {}
    for _idx, name, cls in selected_strategies():
        strat_all = make_strategy(cls)
        eng_all = make_engine()
        res_all = eng_all.run(all_bars, strat_all)

        strat_mar = make_strategy(cls)
        res_mar = make_engine().run(march_bars, strat_mar)

        strat_sep = make_strategy(cls)
        res_sep = make_engine().run(sept_bars, strat_sep)

        m_all = compute_metrics(res_all.trades)
        m_mar = compute_metrics(res_mar.trades)
        m_sep = compute_metrics(res_sep.trades)
        mc = monte_carlo(res_all.trades)
        sess = session_breakdown(res_all.trades)

        results[name] = {
            "all": m_all,
            "march": m_mar,
            "sept": m_sep,
            "mc": mc,
            "session": sess,
            "ambiguous_total": res_all.ambiguous_bar_count,
        }
        print(f"{name}: n={m_all.get('n', 0)} win%={m_all.get('win_rate', 0):.1f} "
              f"PF={m_all.get('profit_factor', 0):.2f} avgR={m_all.get('avg_r', 0):.3f} "
              f"PnL=${m_all.get('total_pnl', 0):.2f} maxDD%={m_all.get('max_dd_pct', 0):.1f} "
              f"[march n={m_mar.get('n', 0)} PnL=${m_mar.get('total_pnl', 0):.2f}] "
              f"[sept n={m_sep.get('n', 0)} PnL=${m_sep.get('total_pnl', 0):.2f}]")

    import json
    out = Path(__file__).parent / f"_backtest_results_raw{results_suffix()}.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nRaw results written to {out.name}")


if __name__ == "__main__":
    main()
