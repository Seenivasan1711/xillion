# S11 (video-sourced) — encoding bug found and fixed, then a real verdict

**Verdict: no demonstrable edge.** After fixing a confirmed encoding bug
that had suppressed it to 1 trade, S11 produces a real 90-trade sample and
lands statistically **indistinguishable from randomly-timed entries** with
the same session mix and risk/reward profile. Its thin gross edge (PF
1.036) is explained by the same structural effect that explained 5 of the
other strategies' gross edges, not by the entry logic predicting anything.

Source and rule specification:
`05_consolidated_findings_and_strategy_request.md` section 8.1.
Implementation: `strategies/s11_video_liquidity_mtf_scalp.py`.

## Results

| Run | n | Win% | PF | Avg R | Total PnL |
|---|---|---|---|---|---|
| v1 (buggy encoding), real cost | 1 | 0.0 | 0.00 | -1.28 | -$7.00 |
| v1 (buggy encoding), zero cost | 1 | 0.0 | 0.00 | -1.00 | -$3.20 |
| **v2 (restructured), real cost** | **90** | **35.6** | **0.19** | **-0.67** | **-$342.11** |
| **v2 (restructured), zero cost** | **90** | **35.6** | **1.036** | **+0.02** | **+$7.13** |

Random-entry benchmark (500 runs, same methodology as `03b`, same session
mix and (stop, target) pairs resampled from S11's own real trades,
resolved through the real engine's tested fill/cost logic):

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S11 | 90 | -$342.11 | -$430.27 | **-$346.18** | -$265.56 | **Indistinguishable from random** |

S11's real result (-$342.11) sits essentially **on top of the random
median** (-$346.18). Its entry timing adds nothing measurable over
throwing darts with the same risk profile in the same sessions.

Cost drag: ($7.13 − (−$342.11)) / 90 = **$3.88/trade** — consistent with
the ~$3.80/trade measured across every other strategy in this project, an
independent sanity check that the new code isn't mispricing anything.

## v1 → v2: the encoding bug, and how it was found

v1 produced 1 trade in 6.5 months. Rather than accept that as a market
finding, every gate was instrumented and survivors counted across 34,871
sampled bars (`s11_funnel.py`):

| Stage | Survivors | Note |
|---|---|---|
| Bars checked | 34,871 | every 5th bar |
| 1H break-of-structure fired | 15,632 | 45% |
| + 15m BOS fired, same direction | 8,767 | 25% — the hard alignment filter was **not** the bottleneck |
| + 15m order block mitigated | **82** | **99.1% of survivors died here** |
| + swing found to watch | 82 | no loss |
| → actual trade | **1** | second ~99% collapse |

**A prediction was made before measuring and turned out wrong**: the
expectation was that the hard 1H/15m alignment filter (the
implementation's own flagged "ambiguity #1" — the video treats alignment
as a soft preference) would be the bottleneck. It wasn't; 25% of bars
cleared it comfortably. Recorded because the point of measuring instead of
assuming is that the measurement wins.

**Actual root cause**: v1 required, on the same bar, a 15m break of
structure to be *firing* AND price to be *simultaneously inside the order
block that caused that break*. Near-mutually-exclusive by construction — a
BOS fires precisely because price moved decisively **away** from that
zone. The video describes a sequence unfolding over time (structure
shifts → price *later* returns to the zone → sweep → confirm → enter),
which v1 collapsed into one bar's worth of conjunctions.

**v2 fix**: an explicit state machine (IDLE → ARMED → MITIGATED → entry),
with the structural bias and the marked zone held as **persistent state**
— recorded when a BOS fires, then remembered — rather than re-required to
be firing on every later bar. This is a correctness fix, not a loosening:
"the structure has officially shifted bullish, now look for longs" is a
*state* in the source material, and v1 encoded it as an instantaneous
event.

**A prior expectation was stated before running v2**: a correct sequential
encoding should produce low hundreds of trades; under ~20 would mean the
restructure missed the real problem; thousands would mean a gate had been
broken open and it was no longer the video's strategy. **Result: 90** —
inside the acceptable range, so the restructure is accepted as a genuine
fix rather than rationalized after the fact.

## Two lifetimes the video never specifies (ambiguity #5)

The state machine needs finite lifetimes or it leaks stale setups forever:
how long a marked zone stays valid waiting for price to return
(`max_arm_bars`, set to ~1 trading day) and how long to wait for a sweep
after mitigation (`max_wait_after_mitigation_bars`, ~1 hour). The video
gives neither. Both were set to round, human-plausible trading values and
**were not swept for a best-performing setting** — tuning them against
backtest P&L would be precisely the curve-fitting this project's honesty
clause prohibits.

## Where this leaves S11

It joins the majority group: real gross edge too thin to matter (PF 1.036,
weaker than every other gross-positive strategy except S08's 1.00), and no
measurable entry-timing skill once compared against a fair random
baseline. It is **not** a candidate for P4.

Worth stating plainly, since the source material was a confident video
citing $566K in profits: **that claim was never evidence about this
strategy's mechanics**, and nothing here contradicts or confirms it — a
different account size, different discretion, different execution, and
(by the video's own admission) at least one trade where the stop-loss was
manually removed mid-trade. What was testable here was the mechanical rule
set, and the mechanical rule set does not beat random entry on 6.5 months
of real XAUUSD data.

## The recurring pattern this is the third instance of

- **S02**: lookback window too small to ever produce the daily bars its
  own gate required.
- **S04**: range check requiring every day to touch both range extremes
  simultaneously.
- **S11 v1**: a just-fired break of structure required to coincide with a
  retest of the very zone it broke away from.

**Standing prior for this codebase: a near-zero signal count has meant
"structurally unsatisfiable condition combination" 3 times out of 3 —
never "the market didn't offer this setup."** Any future strategy
reporting near-zero trades should be instrumented and traced before its
result is believed.
