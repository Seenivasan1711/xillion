"""
Does ANY stop/target scale make S11 viable? -- and what does price actually
do after an S11 signal?

Motivation (06_rr_geometry_finding_and_plan.md sections 6b/6c): modelled
round-trip cost is 82-170% of the risk budget at a 40pt stop. Cost is
roughly FIXED per trade, so its share of the trade falls as the trade gets
bigger. This sweeps the stop/target scale to see whether expectancy ever
crosses zero -- and runs a RANDOM-ENTRY CONTROL at every scale, because if
wider stops help random entries just as much, that is geometry, not edge.

Stated BEFORE running (so the result cannot be rationalised afterwards):
  - Cost drag as a share of risk must fall monotonically with scale
    (arithmetic, not a prediction).
  - Absolute PnL should therefore improve with scale for BOTH real and
    random entries.
  - The real question is whether S11's GAP OVER RANDOM ever becomes
    positive and meaningful. Given C3 found S11's entries statistically
    indistinguishable from random, the prediction is that the gap stays
    ~zero at every scale, and both converge toward "slightly negative,
    roughly the cost." If that is what happens, no scale rescues S11,
    because there is no edge to rescue -- and that is the honest answer.

Also measures the MAE/MFE profile with effectively NON-BINDING stops, so
excursions are not truncated by the stop itself. That answers Phase 2's
question directly: how far does price actually travel in our favour after
an S11 signal, and how much heat does it take first? A target beyond the
MFE distribution's bulk is unreachable by construction, no matter how good
the entry is.
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import run_backtests as rb  # noqa: E402
from engine.backtest_engine import BacktestEngine, RiskLimits, Side, SizingConfig  # noqa: E402
from engine.cost_model import CostModel  # noqa: E402
import random_entry_benchmark as reb  # noqa: E402
from strategies.s11_video_liquidity_mtf_scalp import VideoLiquidityMtfScalpStrategy  # noqa: E402

SCALES = [(40, 80), (100, 200), (200, 400), (400, 800), (800, 1600)]
N_RANDOM_RUNS = 200
SEED = 20260924


def engine_for(min_sl, min_tp, zero_cost=False):
    return BacktestEngine(
        cost_model=CostModel.zero() if zero_cost else CostModel(),
        sizing=SizingConfig(mode="fixed_lot", fixed_lots=0.08),
        risk=RiskLimits(
            max_trades_per_session=4, daily_loss_cap_usd=50.0, consecutive_loss_halt=2,
            min_sl_pts=min_sl, min_target_pts=min_tp,
        ),
    )


def main():
    bars = rb.load_all_bars()
    print(f"bars={len(bars)}", flush=True)
    session_index = reb.build_session_index(bars)
    out = {}

    # ── MAE/MFE profile with effectively non-binding stops ──────────────
    print("\n=== MAE/MFE profile (stops wide enough not to truncate) ===", flush=True)
    res = engine_for(5000, 10000).run(bars, VideoLiquidityMtfScalpStrategy())
    mfes = [t.mfe_pts for t in res.trades]
    maes = [t.mae_pts for t in res.trades]
    if mfes:
        def pcts(v):
            v = sorted(v)
            return {p: round(v[int(len(v) * p / 100)], 1) for p in (10, 25, 50, 75, 90)}
        print(f"n={len(mfes)} signals")
        print(f"  MFE (favourable excursion) pts: {pcts(mfes)}")
        print(f"  MAE (adverse excursion)    pts: {pcts(maes)}")
        out["mae_mfe"] = {"n": len(mfes), "mfe": pcts(mfes), "mae": pcts(maes)}
        reach80 = 100 * sum(1 for m in mfes if m >= 80) / len(mfes)
        reach200 = 100 * sum(1 for m in mfes if m >= 200) / len(mfes)
        print(f"  % of signals whose favourable excursion ever reaches  80 pts: {reach80:.1f}%")
        print(f"  % of signals whose favourable excursion ever reaches 200 pts: {reach200:.1f}%")
        out["mae_mfe"]["pct_reaching_80"] = round(reach80, 1)
        out["mae_mfe"]["pct_reaching_200"] = round(reach200, 1)

    # ── Scale sweep, with a random-entry control at every scale ─────────
    print("\n=== Scale sweep: S11 vs a random-entry control at the same scale ===", flush=True)
    print(f"{'stop/target':>12s} {'n':>5s} {'win%':>6s} {'PF':>6s} {'S11 PnL':>10s} "
          f"{'rand p50':>10s} {'gap':>9s}", flush=True)
    rows = []
    for min_sl, min_tp in SCALES:
        r = engine_for(min_sl, min_tp).run(bars, VideoLiquidityMtfScalpStrategy())
        m = rb.compute_metrics(r.trades)
        n = m.get("n", 0)
        if n == 0:
            print(f"{min_sl:5d}/{min_tp:<6d} {0:5d}  -- no trades --", flush=True)
            continue
        sessions = [t.session for t in r.trades]
        pairs = [(abs(t.entry_price - t.stop_price), abs(t.target_price - t.entry_price))
                 for t in r.trades]
        rng = random.Random(SEED)
        pnls = []
        for _ in range(N_RANDOM_RUNS):
            tot = 0.0
            for _ in range(n):
                sess = rng.choice(sessions)
                pool = session_index.get(sess, [])
                if not pool:
                    continue
                idx = rng.choice(pool)
                if idx >= len(bars) - 10:
                    continue
                side = Side.LONG if rng.random() < 0.5 else Side.SHORT
                sp, tp = rng.choice(pairs)
                t = reb.resolve_one_trade(engine_for(min_sl, min_tp), bars, idx, side, sp, tp)
                if t is not None:
                    tot += t.pnl_usd
            pnls.append(tot)
        pnls.sort()
        rp50 = pnls[len(pnls) // 2]
        gap = m["total_pnl"] - rp50
        print(f"{min_sl:5d}/{min_tp:<6d} {n:5d} {m['win_rate']:6.1f} {m['profit_factor']:6.2f} "
              f"{m['total_pnl']:10.2f} {rp50:10.2f} {gap:+9.2f}", flush=True)
        rows.append({"stop": min_sl, "target": min_tp, "n": n, "win_rate": round(m["win_rate"], 1),
                     "pf": round(m["profit_factor"], 3), "s11_pnl": round(m["total_pnl"], 2),
                     "random_p50": round(rp50, 2), "gap": round(gap, 2)})
    out["scale_sweep"] = rows

    with open(Path(__file__).parent / "_s11_scale_experiment.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwritten to _s11_scale_experiment.json", flush=True)


if __name__ == "__main__":
    main()
