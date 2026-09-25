"""
D1 swing research (option 1, 2026-09-25). Rules: strategies/swing_suite.py.
Same pre-registered split as custom_research.py (holdout locked behind
--holdout-final). Realistic mode: fixed $RESEARCH_RISK_USD at the stop
(default 50 = 1% of the $5K account; D1 stops are too wide for $25 at the
0.01-lot minimum), swap, and flat by Friday unless RESEARCH_WEEKEND=hold.

Two random baselines, each matched trade-by-trade on stop distance and
holding time (bars) -- a swing trade's result depends heavily on how long
it is held, so the baseline must hold as long:
  random side : random entry day, 50/50 long/short
  same side   : random entry day, the SAME side as the real trade -- this
                is the one that matters on a trending asset: it separates
                entry timing from "gold went up 2020-2026"

  RESEARCH_DATA_SOURCE=mt5 RESEARCH_TIMEFRAME=D1 python swing_research.py --period is
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("RESEARCH_REALISTIC", "1")
os.environ.setdefault("RESEARCH_RISK_USD", "50")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import run_backtests as rb  # noqa: E402
from custom_research import PERIODS  # noqa: E402
from engine.backtest_engine import Side, Signal  # noqa: E402
from engine.cost_model import session_for  # noqa: E402
from strategies.swing_suite import SWING_RULES, SwingRuleStrategy, compute_daily_features  # noqa: E402

N_RANDOM = 1000


def resolve_held(engine, bars, i, side, stop_dist, hold, buckets):
    """One synthetic trade: enter at bars[i].close, resting stop at
    stop_dist, exit at the close `hold` bars later (or earlier on the stop,
    or the Friday cutoff) -- the real trades' own fill/cost/swap machinery."""
    b = bars[i]
    sess = session_for(b.ts)
    spread = engine.cost_model.spread_pts(sess, buckets[i], b.spread_pts)
    e = b.close
    stop = e - stop_dist if side == Side.LONG else e + stop_dist
    far = e + 1e6 if side == Side.LONG else e - 1e6
    pos = engine._open_position(b, Signal(side=side, stop_price=stop, target_price=far), 5000.0, sess, spread, buckets[i])
    if engine._past_friday_cutoff(b.ts):
        return None  # the real engine wouldn't enter here either
    for j in range(i + 1, min(len(bars), i + 1 + hold)):
        x = bars[j]
        px, reason, amb = engine._resolve_intrabar(x, pos)
        if px is None and (engine._past_friday_cutoff(x.ts) or j == i + hold):
            px, reason = x.close, "time"
        if px is not None:
            return engine._close_position(pos, x.ts, px, reason, amb, x, buckets[j])
    return None


def baselines(bars, trades, seed=20260925):
    if not trades:
        return None
    eng = rb.make_engine()
    buckets = eng.vol_buckets(bars)
    ts_index = {b.ts: k for k, b in enumerate(bars)}
    specs = []
    for t in trades:
        hold = max(1, ts_index.get(t.exit_ts, 0) - ts_index.get(t.entry_ts, 0))
        specs.append((t.side, abs(t.entry_price - t.stop_price), hold))
    out = {}
    for mode in ("random_side", "same_side"):
        rng = random.Random(seed)
        totals = []
        for _ in range(N_RANDOM):
            tot = 0.0
            for side, stop_dist, hold in specs:
                if mode == "random_side":
                    side = Side.LONG if rng.random() < 0.5 else Side.SHORT
                tr = None
                for _try in range(5):
                    i = rng.randrange(0, len(bars) - 1)
                    tr = resolve_held(eng, bars, i, side, stop_dist, hold, buckets)
                    if tr is not None:
                        break
                tot += tr.pnl_usd if tr else 0.0
            totals.append(tot)
        totals.sort()
        out[mode] = (totals[int(0.5 * (N_RANDOM - 1))], totals[int(0.95 * (N_RANDOM - 1))])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=sorted(PERIODS), required=True)
    ap.add_argument("--holdout-final", action="store_true")
    args = ap.parse_args()
    if args.period == "holdout" and not args.holdout_final:
        sys.exit("holdout is run once, at the end: pass --holdout-final to confirm")
    assert rb.TIMEFRAME == "D1", "set RESEARCH_TIMEFRAME=D1"
    lo, hi = PERIODS[args.period]
    all_bars = rb.load_all_bars()
    feats = compute_daily_features(all_bars)
    bars = [b for b in all_bars if lo <= b.ts < hi]
    mode = "weekend-hold (evaluation)" if rb.WEEKEND_HOLD else "flat-Friday (master)"
    print(f"D1 {args.period}: {len(bars)} days {bars[0].ts.date()}..{bars[-1].ts.date()} | {mode} | risk ${rb.RISK_USD:g}", flush=True)
    rows, dumped = [], []
    for spec in SWING_RULES:
        trades = rb.make_engine().run(bars, SwingRuleStrategy(spec, feats)).trades
        n = len(trades)
        pnl = sum(t.pnl_usd for t in trades)
        risk = [abs(t.entry_price - t.stop_price) * t.lots * 100 for t in trades]
        yrs = pd.Series([t.pnl_usd for t in trades], index=[t.entry_ts.year for t in trades]).groupby(level=0).sum().round(0).to_dict() if n else {}
        row = {"rule": f"{spec.key} {spec.name}", "n": n, "pnl": round(pnl), "long": sum(t.side == Side.LONG for t in trades),
               "swap": round(sum(t.swap_usd for t in trades)),
               "risk_med": round(pd.Series(risk).median()) if n else None, "risk_max": round(max(risk)) if n else None,
               "years": yrs}
        b = baselines(bars, trades)
        if b:
            row.update({"rnd_p50": round(b["random_side"][0]), "rnd_p95": round(b["random_side"][1]),
                        "same_p50": round(b["same_side"][0]), "same_p95": round(b["same_side"][1]),
                        "beats_same_p95": pnl > b["same_side"][1]})
        rows.append(row)
        print(row, flush=True)
        dumped += [{"key": spec.key, "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side.value, "pnl": t.pnl_usd,
                    "swap": t.swap_usd, "lots": t.lots, "exit_reason": t.exit_reason} for t in trades]
    out = Path(__file__).parent / "_custom"
    out.mkdir(exist_ok=True)
    tag = f"d1_{args.period}_{'wkhold' if rb.WEEKEND_HOLD else 'flatfri'}"
    pd.DataFrame(dumped).to_parquet(out / f"{tag}_trades.parquet")
    pd.DataFrame(rows).to_csv(out / f"{tag}_summary.csv", index=False)


if __name__ == "__main__":
    main()
