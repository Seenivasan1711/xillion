"""
Step (c) research runner (2026-09-25): indicator rules I01-I08 and the
price-action shortlist S01-S11, traded the way Rakesh's FundingPips $5K
account would be (RESEARCH_REALISTIC: $25 risk/trade in 0.01 lots, swap,
flat by Friday close), on a PRE-REGISTERED split:

    is       2020-01-01 .. 2024-06-30   explore, build rules
    val      2024-07-01 .. 2025-06-30   a candidate must also work here
    holdout  2025-07-01 .. end          run ONCE, at the very end

The holdout is refused unless --holdout-final is passed, so it can't be
peeked at by accident. Features are computed on the full series (they are
causal -- tests/test_indicator_suite.py), but the engine only trades bars
inside the chosen period.

Writes, per run: _custom/<tf>_<period>_trades.parquet (every trade, tagged
with entry context for the condition analysis) and a printed summary with a
random-entry band (same sessions, same stop/target distances, same costs).

  RESEARCH_DATA_SOURCE=mt5 RESEARCH_TIMEFRAME=M15 python custom_research.py --period is
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("RESEARCH_REALISTIC", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import random_entry_benchmark as reb  # noqa: E402
import run_backtests as rb  # noqa: E402
from engine.backtest_engine import Side  # noqa: E402
from engine.cost_model import session_for  # noqa: E402
from strategies.indicator_suite import INDICATOR_RULES, IndicatorRuleStrategy, compute_features  # noqa: E402

PERIODS = {
    "is": (datetime(2020, 1, 1, tzinfo=UTC), datetime(2024, 7, 1, tzinfo=UTC)),
    "val": (datetime(2024, 7, 1, tzinfo=UTC), datetime(2025, 7, 1, tzinfo=UTC)),
    "holdout": (datetime(2025, 7, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC)),
}
OUT = Path(__file__).parent / "_custom"
N_RANDOM = 300


def context_tags(feats: pd.DataFrame, ts, side: Side) -> dict:
    r = feats.loc[ts]
    sign = 1 if side == Side.LONG else -1
    return {
        "hour": ts.hour, "weekday": ts.weekday(), "session": session_for(ts).value,
        "adx": r["adx"], "rsi14": r["rsi14"],
        "with_ema200": bool(sign * (r["close"] - r["ema200"]) > 0),
        "ema50_over_200": bool(sign * (r["ema50"] - r["ema200"]) > 0),
        "with_supertrend": bool(r["supertrend_up"] == (side == Side.LONG)),
        "atr": r["atr"],
    }


def random_band(bars, trades, n_runs=N_RANDOM, seed=20260925):
    """Same idea as random_entry_benchmark.main, for one trade list."""
    if not trades:
        return None
    engine = rb.make_engine()
    buckets = engine.vol_buckets(bars)
    idx = reb.build_session_index(bars)
    sessions = [t.session for t in trades]
    rr = [(abs(t.entry_price - t.stop_price), abs(t.target_price - t.entry_price)) for t in trades]
    rng = random.Random(seed)
    totals = []
    for _ in range(n_runs):
        tot = 0.0
        for _ in range(len(trades)):
            pool = idx.get(rng.choice(sessions), [])
            if not pool:
                continue
            i = rng.choice(pool)
            side = Side.LONG if rng.random() < 0.5 else Side.SHORT
            s, t = rng.choice(rr)
            tr = reb.resolve_one_trade(rb.make_engine(), bars, i, side, s, t, buckets)
            tot += tr.pnl_usd if tr else 0.0
        totals.append(tot)
    totals.sort()
    q = lambda p: totals[int(p * (len(totals) - 1))]  # noqa: E731
    return q(0.05), q(0.50), q(0.95)


def summarise(name, trades, bars, with_random=True):
    pnl = sum(t.pnl_usd for t in trades)
    n = len(trades)
    if n == 0:
        return {"name": name, "n": 0}
    wins = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
    losses = -sum(t.pnl_usd for t in trades if t.pnl_usd < 0)
    months = pd.Series([t.pnl_usd for t in trades], index=[t.entry_ts.strftime("%Y-%m") for t in trades]).groupby(level=0).sum()
    out = {
        "name": name, "n": n, "pnl": round(pnl, 2), "pf": round(wins / losses, 2) if losses else None,
        "win%": round(100 * sum(t.pnl_usd > 0 for t in trades) / n, 1),
        "months+%": round(100 * (months > 0).mean(), 0),
        "swap": round(sum(t.swap_usd for t in trades), 2),
    }
    if with_random:
        band = random_band(bars, trades)
        out.update({"rnd_p50": round(band[1], 0), "rnd_p95": round(band[2], 0), "beats_p95": pnl > band[2]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=sorted(PERIODS), required=True)
    ap.add_argument("--holdout-final", action="store_true", help="required to run the holdout")
    ap.add_argument("--only", default="", help="comma list of keys, e.g. I01,S08")
    ap.add_argument("--no-random", action="store_true")
    args = ap.parse_args()
    if args.period == "holdout" and not args.holdout_final:
        sys.exit("holdout is run once, at the end: pass --holdout-final to confirm")
    if not rb.REALISTIC:
        sys.exit("custom_research is meant for RESEARCH_REALISTIC=1")

    lo, hi = PERIODS[args.period]
    all_bars = rb.load_all_bars()
    feats = compute_features(all_bars)
    bars = [b for b in all_bars if lo <= b.ts < hi]
    print(f"{rb.TIMEFRAME} {args.period}: {len(bars):,} bars {bars[0].ts} .. {bars[-1].ts}", flush=True)
    only = {k.strip().upper() for k in args.only.split(",") if k.strip()}

    jobs = [(r.key, lambda r=r: IndicatorRuleStrategy(r, feats)) for r in INDICATOR_RULES]
    jobs += [(name.split()[0], lambda cls=cls: rb.make_strategy(cls)) for _i, name, cls in rb.selected_strategies()
             if not (name.startswith("S11") and rb.TIMEFRAME != "M1")]
    rows, dumped = [], []
    for key, make in jobs:
        if only and key not in only:
            continue
        strat = make()
        trades = rb.make_engine().run(bars, strat).trades
        label = getattr(strat, "name", "") or key
        s = summarise((label if label.startswith(key) else f"{key} {label}")[:44], trades, bars, with_random=not args.no_random)
        rows.append(s)
        print(s, flush=True)
        for t in trades:
            dumped.append({"key": key, "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side.value,
                           "pnl": t.pnl_usd, "r": t.r_multiple, "swap": t.swap_usd, "lots": t.lots,
                           "exit_reason": t.exit_reason, **context_tags(feats, t.entry_ts, t.side)})
    OUT.mkdir(exist_ok=True)
    tag = f"{rb.TIMEFRAME.lower()}_{args.period}" + (f"_{'_'.join(sorted(only))}" if only else "")
    pd.DataFrame(dumped).to_parquet(OUT / f"{tag}_trades.parquet")
    pd.DataFrame(rows).to_csv(OUT / f"{tag}_summary.csv", index=False)
    print(f"wrote {OUT}/{tag}_*", flush=True)


if __name__ == "__main__":
    main()
