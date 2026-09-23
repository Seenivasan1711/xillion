# C2 Timeframe Experiment — did moving to M5/M15 fix the cost problem?

**Verdict: no, not as directly tested. The external review's Section C2
claim ("same signal logic, config change only") does not hold up.**

## What was tested

C1's zero-cost diagnostic found 6 of 10 strategies (S01, S03, S06, S07,
S08, S10) have real gross (pre-cost) profit factor >= 1.0 but are
net-negative at real cost — a fixed ~$3.80/trade cost erasing a real but
modest edge on tight M1 stops. The external review's predicted fix: move
from M1 entries to M5/M15 with proportionally wider stops, since cost
stays ~fixed in $ terms while the price swings available to absorb it
grow. Predicted result: "same signal logic, config change only."

Tested directly and honestly: the SAME unmodified strategy code, the SAME
real cost model, run against the same underlying XAUUSD data resampled to
M5 and M15 bars via a generic OHLC resampler
(`timeframe_experiment.py:resample_bars`). No parameter retuning — the
whole point was to test whether simply feeding coarser bars into the
existing code already fixes the cost problem, per the "config change
only" claim.

## Results

| Strategy | M1 PF (baseline) | M5 PF | M5 n | M15 PF | M15 n |
|---|---|---|---|---|---|
| S01 Liquidity Sweep + Displacement + FVG Retest | 0.21 | 0.26 | 56 | 0.28 | 39 |
| S03 Order Block Retest after BOS | 0.23 | 0.18 | 153 | 0.25 | 132 |
| S06 Premium/Discount OTE Fib Retracement | 0.29 | 0.36 | 18 | **1.06** | **7** |
| S07 Market Profile Value-Area Rotation | 0.33 | 0.24 | 89 | 0.28 | 87 |
| S08 BOS Pullback Continuation | 0.19 | 0.44 | **2** | 0.16 | 11 |
| S10 Equal Highs/Lows + RSI Divergence | 0.25 | 0.20 | 141 | 0.22 | 94 |

(M1 baselines are the already-verified v3 numbers from `03_results.md`,
not rerun here — only M5/M15 were executed fresh.)

## Reading this honestly

- **No strategy meaningfully crossed net PF 1.0 on a usable sample.** The
  one number above 1.0 (S06 at M15, PF 1.06) has only **7 trades** — far
  too few to be anything but noise, the same lesson this project already
  learned once from S06's v2→v3 result (n=16, PF 0.86 → n=49, PF 0.29).
  Treat it as "no signal," not "found it."
- **Trade counts often collapsed**, most severely S08 (109 at M1 → 2 at
  M5 → 11 at M15). This is a direct consequence of not retuning: each
  strategy's own lookback/threshold parameters are counted in *bars*, not
  minutes, so `ctx.bars(20)` on M5 bars now looks back 100 minutes instead
  of 20 — the same code fires on qualitatively different, much rarer
  setups at a coarser timeframe, not just "the same setups with more room
  to breathe." That was the implicit assumption behind "config change
  only," and it doesn't hold.
- **Most PFs didn't move much, and several got worse** (S03, S07, S10 all
  slightly worse at both M5 and M15 than their M1 baseline). If the
  cost-vs-edge-ratio mechanism were the dominant effect, PF should have
  moved up consistently across the board as the timeframe coarsened — it
  didn't, which suggests either the underlying price-action patterns are
  genuinely scale-dependent (an M1 FVG/displacement/liquidity-sweep isn't
  simply a "bigger, slower" version of itself at M5/M15 — it may be a
  qualitatively different, less-validated pattern at that scale), or the
  interaction between unadjusted lookback windows and the coarser bars is
  actively hurting more than the reduced cost-drag is helping.

## What this does and doesn't rule out

This rules out the *cheap* version of the fix — "just feed coarser bars
into the same code." It does **not** rule out the underlying idea that a
coarser timeframe with properly-redesigned parameters (lookback windows
converted to be time-equivalent rather than bar-count-equivalent, stop/
target distances redesigned around M5/M15's own structural swing sizes
rather than the M1-calibrated `risk_floor.py` floor) could still work —
that's a real re-engineering task, not a config change, and hasn't been
attempted here per the coordinator's explicit instruction not to retune
in this pass.

## Recommendation

Before investing in that re-engineering effort, it's worth first
confirming C1's gross-edge finding is *robust* — e.g., does the gross edge
on the strongest candidate (S07, gross PF 1.67 at M1) hold up under the
walk-forward/holdout protocol the P3 spec actually calls for (still not
built — see `04_plan.md`), or was even the gross-level result partly an
in-sample artifact? Chasing a timeframe redesign before that check risks
spending real engineering effort on a signal that hasn't been verified
out-of-sample at all yet.
