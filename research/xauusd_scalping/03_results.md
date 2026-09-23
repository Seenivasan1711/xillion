# P3 Results — XAUUSD Scalping, 10-Strategy Backtest

> ## ⚠️ ALL NUMBERS IN THIS FILE ARE PROVISIONAL (2026-09-24)
> A mechanical risk/reward bug was found after these were produced:
> `apply_floor` sets a 40/80 (2:1) stop/target against the pre-cost
> reference price, but the engine fills at `ref ± entry_cost` (median 23
> pts), turning the real structure into ~63/57 (**0.90:1**) from the
> actual fill. Proven by an exact identity — `stop_dist + target_dist ==
> 120.0` on 90/90 S11 trades and the large majority of every other
> strategy's. Breakeven win rate needed jumps from 33.3% to 52.6%, which
> no strategy here reaches.
> **Every "this strategy is net-negative" conclusion below was measured
> through that handicap and must be re-run before being treated as a
> verdict.** It also means C1's zero-cost run was silently restoring the
> intended 2:1 geometry as well as removing cost — two effects conflated.
> Full detail and the resulting plan: `06_rr_geometry_finding_and_plan.md`.

**Status (2026-09-24, most current read): read the PHASE 1 RE-RUN section
immediately below — it supersedes every table in this file.** The C1/C2/C3
sections that follow are kept as the record of how the investigation
progressed, but all of their numbers were measured through the R:R
geometry bug. In particular, C3's finding that S07 was the one strategy
distinguishable from random **is void** — on corrected geometry S07 is
among the worst of the eleven (see `07_conclusion_m1_scalping_verdict.md`).

## PHASE 1 RE-RUN (2026-09-24) — all 10 on CORRECTED geometry

These supersede every table below. Same strategies, same data, run through
the engine after the R:R geometry fix (floor enforced against the actual
fill), the `VolBucket` wiring, and the O(n²) fix.

| # | n | Win% (old → **new**) | PF (old → **new**) | PnL (new) |
|---|---|---|---|---|
| S01 | 144 | 34.2 → **13.9** | 0.21 → **0.08** | -$739.33 |
| S02 | 0 | — | — | $0.00 |
| S03 | 245 | 37.6 → **8.2** | 0.23 → **0.04** | -$1,413.81 |
| S04 | 3 | — → 33.3 | — → 1.14 | +$1.45 *(n=3, meaningless)* |
| S05 | 238 | 26.4 → **9.2** | 0.13 → **0.05** | -$1,342.18 |
| S06 | 56 | 42.9 → **28.6** | 0.29 → **0.20** | -$203.83 |
| **S07** | 128 | 44.3 → **10.2** | 0.33 → **0.05** | -$745.02 |
| S08 | 159 | 33.9 → **8.8** | 0.19 → **0.05** | -$917.85 |
| S09 | 86 | 30.6 → **20.9** | 0.23 → **0.18** | -$378.86 |
| S10 | 237 | 39.0 → **11.0** | 0.25 → **0.07** | -$1,302.54 |

**Every strategy collapsed, and S07 — the only one that had beaten a random
baseline — collapsed hardest.** Its earlier advantage was measured through
the broken geometry, so that credential is void until re-measured. This
makes the picture *more* unified: it was never "ten bad strategies and one
promising one"; the apparent differences were substantially a geometry
artifact.

**Sanity-checked that the collapse is mechanically real, not a broken fix.**
At the measured 31pt spread, entry cost is 18.5pts, so the fill sits that
far above the decision price. From that decision price the market must
travel **+98.5 pts to win but only −21.5 pts to lose — a 4.6:1 adverse
ratio.** A driftless random walk would win ~18% of the time, and the engine
resolves same-bar ties as stops, pushing it lower. Observed: 8.2-28.6%,
clustering near 10%. Consistent.

*(Caveat: these figures used commission $3.50/side — the process had
already imported the cost model before the correction to $2.50 landed.
Effect is $0.16/trade, e.g. S01 reads -$739.33 here vs -$716.29 with the
corrected value. Directionally irrelevant; noted for accuracy.)*

---

## C1 — zero-cost diagnostic (external review finding, verified directly)

An external review of this project's own P3 v3 results made a specific,
falsifiable prediction (their Section C1): re-run the same 10 strategies'
exact trade logic with the cost model zeroed out, and check whether gross
(pre-cost) expectancy is positive or negative. If gross is positive, the
"8 of 10 negative" verdict is a cost-engineering problem (fixable,
config-level); if gross is also negative, it's a real no-edge problem.

Ran it for real (`run_backtests_zerocost.py`, same strategies, same bars,
`CostModel.zero()` in place of the real cost model — same trades, only the
fill/PnL math changes):

| # | Strategy | n | Real-cost PF (v3) | **Gross (zero-cost) PF** | Verdict |
|---|---|---|---|---|---|
| S01 | Liquidity Sweep + Displacement + FVG Retest | 114 | 0.21 | **1.07** | Real gross edge, killed by cost |
| S02 | Multi-Timeframe Liquidity + CHoCH | 0 | — | — | N/A, still fires no signals |
| S03 | Order Block Retest after BOS | 178 | 0.23 | **1.18** | Real gross edge, killed by cost |
| S04 | Wyckoff Spring/Upthrust | 0 (at the time) | — | — | Range-detector bug since fixed — now fires 2 trades, underpowered, see "S04's three-gate redesign" below |
| S05 | NR7/Inside-Bar Compression Breakout | 174 | 0.13 | 0.69 | Negative even gross — genuinely no edge |
| S06 | Premium/Discount OTE Fib Retracement | 49 | 0.29 | **1.37** | Real gross edge, killed by cost |
| S07 | Market Profile Value-Area Rotation | 106 | 0.33 | **1.67** | Real gross edge, killed by cost — the strongest of the 10 |
| S08 | BOS Pullback Continuation | 109 | 0.19 | **1.00** | Breakeven gross, killed by cost |
| S09 | Session Liquidity Run + Reversal | 72 | 0.23 | 0.92 | Negative even gross — genuinely no edge |
| S10 | Equal Highs/Lows + RSI Divergence | 172 | 0.25 | **1.28** | Real gross edge, killed by cost |

**Verified this isn't an artifact**: spot-checked the actual $ extracted by
cost per strategy (e.g. S07: $126.87 gross → -$278.77 net = $405.64 total
cost across 106 trades = $3.83/trade average; S01: $3.79/trade average) —
a believable, consistent magnitude for a 0.08-lot position, not a bug in
the diagnostic script.

**What this means**: only S05 and S09 look like genuinely no-edge signals.
The other 6 (S01, S03, S06, S07, S08, S10) have real, if modest, gross
expectancy that a fixed per-trade cost (~$3.80, dominated by spread+
slippage on a tight M1 stop) is currently erasing. **This directly matches
the external review's own predicted lever**: move from M1 entries to
M5/M15 with proportionally wider stops (8-15pt instead of the current
`risk_floor.py` floor's still-tight-relative-to-cost M1 sizing) — cost
stays roughly fixed in $ terms while the stop distance (and therefore the
per-trade edge available to absorb it) grows, cutting cost's share of the
trade from double digits down to single digits. Same signal logic, no new
strategy needed. This is now the single highest-value next step — see
`docs/status/task-tracker.md`'s XAUUSD section for what's actually running.

The v1-v3 sections below remain accurate as a record of what was tested
and found at each stage — they're just not the final word on whether these
10 candidates have any edge, which is why C1 sits above them now.

## C2 — timeframe experiment: the "config change only" fix doesn't hold

Tested the obvious next step: move the 6 gross-positive strategies from M1
entries to M5/M15 bars, same code, real cost, no retuning — per the
external review's own claim that this should work as "same signal logic,
config change only," since a fixed ~$3.80/trade cost should bite less
hard against a coarser bar's naturally wider price swings.

**Result: no.** Full table and reasoning in
`research/xauusd_scalping/03c_timeframe_experiment.md`. Headline: no
strategy meaningfully crosses net PF 1.0 on a usable sample (the one
above-1.0 result, S06 at M15, has only 7 trades — the same underpowered-
noise trap this project already learned from S06 once before). Several
strategies got *worse*, not better, at a coarser timeframe. Root cause:
every strategy's lookback/threshold parameters are counted in **bars**,
not minutes — unchanged code on M5 bars looks back 5x further in real
time than on M1, so it fires on qualitatively different, much rarer
setups, not "the same setups with more room to breathe." Trade counts
collapsed accordingly (S08: 109 at M1 → 2 at M5 → 11 at M15).

**This doesn't kill the idea, it kills the cheap version of it.** A
proper timeframe redesign (lookback windows converted to be
time-equivalent, not bar-count-equivalent; stop/target distances
redesigned around each timeframe's own structural swing sizes rather than
the M1-calibrated `risk_floor.py` floor) is a real re-engineering task,
untested here by design (no retuning in this pass, to test the "config
change only" claim honestly on its own terms).

**Recommendation before investing in that redesign** (from the fork that
ran this experiment, and it's sound): confirm C1's gross-edge finding is
*robust* first — does S07's gross PF 1.67 (the strongest candidate) hold
up under the real walk-forward/holdout protocol P3 was always supposed to
use (still not built — see `04_plan.md`), or was even the gross-level
result partly an in-sample artifact? Spending real engineering effort on
a timeframe redesign before that check risks polishing a signal that
hasn't been verified out-of-sample at all.

**Also found in the same pass, unrelated to this experiment's conclusion
but a real defect**: `engine/cost_model.py`'s `VolBucket` classification
is dead code — `entry_cost_pts`/`exit_cost_pts` are called with
`VolBucket.MEDIUM` hardcoded at both call sites in `backtest_engine.py`
(confirmed directly, `_open_position` and `_close_position`), so despite
being documented as a "session×volatility-bucket cost model," costs have
never actually varied by realized volatility in any run this project has
done — only by session. Constant across every comparison run so far, so
it doesn't invalidate C1/C2's conclusions, but it means every backtest's
absolute cost numbers are less realistic than the harness's own
documentation claims (probably understating cost in high-vol regimes,
overstating it in low-vol ones). See D28 in
`decisions-and-open-questions.md`.

## C3 — random-entry benchmark: only S07 actually beats random

C1 found 6 strategies with gross PF >= 1.0 and framed the question as
"cost vs. no-edge." That framing itself needed a check: does the
strategy's specific entry TIMING actually add value, or would a random
entry with the same session mix, the same (stop, target) distances, and
the same real cost do just as well? Built a proper benchmark to answer
this (`random_entry_benchmark.py`): for each strategy, resampled its own
real trades' session distribution and (stop_pts, target_pts) pairs into
500 runs of n randomly-timed entries each, resolved through the exact
same tested engine fill/cost logic real trades use (not reimplemented).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S01 | 114 | -$416.29 | -$527.37 | -$428.10 | -$334.91 | Indistinguishable from random |
| S03 | 178 | -$612.94 | -$777.96 | -$675.27 | -$565.53 | Indistinguishable from random |
| S05 | 174 | -$811.50 | -$775.44 | -$665.83 | -$543.58 | **Worse than random** |
| S06 | 49 | -$146.06 | -$235.06 | -$179.83 | -$119.51 | Indistinguishable from random |
| **S07** | 106 | -$278.77 | -$490.15 | -$403.16 | -$318.31 | **Beats random (real signal)** |
| S08 | 109 | -$419.31 | -$508.01 | -$417.21 | -$331.15 | Indistinguishable from random |
| S09 | 72 | -$278.57 | -$348.82 | -$261.55 | -$188.52 | Indistinguishable from random |
| S10 | 172 | -$564.07 | -$756.96 | -$645.67 | -$549.50 | Indistinguishable from random |

Full detail, methodology, and the documented simplifications (500 runs
not 1,000 — a real O(n²) cost in `BacktestEngine.run()` made the original
plan too slow, see below; random entries don't interact through the
day-level risk limits the way real trades do):
`03b_random_entry_benchmark.md`.

**Reading this against C1 together**: of the 6 strategies with gross
pre-cost edge, only **S07** is actually distinguishable from a
same-profile random entry. The other 5 (S01, S03, S06, S08, S10) — despite
having real gross PF >= 1.0 — perform statistically the same as randomly
timing an entry with their own session mix and R:R shape. The most likely
explanation: their apparent gross edge comes from the R:R/session
structure itself (e.g. `risk_floor.py`'s asymmetric floor, or a favorable
directional bias in the sessions they happen to trade) being favorable in
this window, not from the entry signal actually predicting anything. S07
is the one candidate where the entry logic itself appears to be adding
real value beyond that structural effect. **S05 is confirmed worse than
random** — not just no-edge, actively anti-correlated with a good outcome.

This substantially narrows the P4 candidate list: **S07 is now the
single strongest candidate**, not one of six roughly-equal ones. It's
still net-negative at real cost (-$278.77) and still needs real
out-of-sample validation (see C2's own recommendation) before it means
anything — but it's the only one of the 10 with two independent pieces of
evidence (gross PF 1.67, and a statistically real edge over random) rather
than one.

**Also found in this pass, a separate real performance defect**:
`BacktestEngine.run()` reconstructs a full copy of the running history
list on every bar the strategy is flat (`StrategyContext(history=list(
history), ...)`) — O(n) per call, O(n²) over a full backtest. This is
almost certainly why full 174k-bar runs take many minutes even for
strategies with trivial per-bar logic (matches every full-run timing
observed this session). Not fixed here (out of scope for this diagnostic)
— worth fixing alongside the VolBucket fix (D28) when the walk-forward
harness gets built, since both compound into that build's own runtime.

## S04's three-gate redesign — done, verified, fires 2 trades (underpowered)

The redesign scoped as a standalone external design question
(`S04_range_detection_design_question.md`) is complete and independently
verified (code read line-by-line, test suite rerun, real-data result
reproduced from scratch): the old "every day touches both extremes"
check is replaced by three independent gates (G1 trend/range via a
correctly-denominated Kaufman Efficiency Ratio, G2 containment via a
random-walk envelope using a real measured instrument constant
`sigma_to_atr=1.4628` — computed from real data, not guessed — G3
boundary validity via a touch count), plus a same-window tautology bug
found and fixed along the way (the range-defining window was including
"today," so today's own bars could never penetrate a range that already
contained them) and a real performance regression found and fixed (full
daily resampling on every M1 bar cost ~40 minutes per run; per-calendar-
day caching in the strategy — not the shared detector function, which
stays pure — cut this to 64 seconds, verified against the naive result
with 0 mismatches).

**Honest result**: gate pass rate on real data is **7.12%** (this
project's own independent spot-check: 6.62% on a coarser sample) —
somewhat below the 10-25% prior-expectation band stated before checking,
though not under the "<2%, debug don't retune" trigger. The synthetic
OU-vs-trending-GBM confusion matrix (the anti-curve-fitting validation
step, checked against synthetic ground truth, never against real gold
P&L) came back TPR=0.633 (target >=0.70, **not met**) and FPR=0.150
(target <=0.20, met) — reported as measured, not re-seeded to chase a
better number. **S04 fires 2 real trades over the full 6.5-month dataset**
(win rate 50%, PF 1.69, avg R 0.76) — explicitly UNDERPOWERED (n=2 vs the
200-trade threshold), and far below the design's own expectation of
~1-5 signals/month (would predict 6.5-32 over 6.5 months); of 14 raw gate
fires, only 2 became real trades, the rest blocked by the engine's
open-position/risk-limit constraints. This gap was not closed by loosening
any threshold — doing so under time pressure to make S04 "work" would be
exactly the curve-fitting this whole exercise exists to avoid. **S04's
honest status is now "logic bug fixed, but the fixed detector is more
conservative than its own design predicted, and still produces an
underpowered, unverdictable sample."**

---

## Data actually used (honest accounting)

The background Dukascopy backfill (`--from 2026-03-01 --to 2026-09-14`,
PID 27860) **completed on 2026-09-23** — verified by the process actually
exiting (not just the manifest count) and by reading the combined parquet
files directly:

| Segment | Bars (M1) | Span |
|---|---|---|
| `XAUUSD_2026-03.parquet` | 28,676 | 2026-03-01 23:00 → 2026-03-31 |
| `XAUUSD_2026-04.parquet` | 25,737 | full month |
| `XAUUSD_2026-05.parquet` | 25,134 | full month |
| `XAUUSD_2026-06.parquet` | 25,439 | full month |
| `XAUUSD_2026-07.parquet` | 29,039 | full month |
| `XAUUSD_2026-08.parquet` | 25,800 | full month |
| `XAUUSD_2026-09.parquet` | 14,729 | 2026-09-01 → 2026-09-16 23:59 |
| **Combined** | **174,554** | **one continuous series, 2026-03-01 → 2026-09-16, no gap** |

This is the first run with enough continuous history for the spec's
actual validation protocol to become meaningful in principle (a real
6mo-train/1mo-test walk-forward is now data-feasible) — **that upgrade
hasn't been built yet**; `run_backtests.py` still does the same pooled
`all` + `march`/`sept`-subset run as before. Building the real walk-forward
harness is the next concrete step before a P4 verdict can be called solid,
not just "more data," now that more data exists.

## What changed between v1 and v2

Two real bugs, found by noticing implausible patterns in v1's output
rather than trusting the numbers at face value (per this repo's own
"verify against reality" standing instruction):

1. **Engine bug** (`engine/backtest_engine.py`): `consecutive_loss_halt`
   never reset on day rollover, unlike its tested sibling
   `daily_loss_cap_usd` — once any strategy hit 2 consecutive losses
   anywhere in the run, it silently halted every subsequent day for good.
   This alone explains v1's absurd 0-3-trades-per-strategy-regardless-
   of-logic pattern. Fixed with a one-line reset + a new regression test,
   `test_consecutive_loss_halt_resets_on_a_new_day`.
2. **Strategy sizing bug** (all 10 strategy files): stop/target distances
   were computed off the raw `bar.close` a strategy observed, then the
   engine independently marks up the real fill price by
   `entry_cost_pts` (half-spread + slippage, 9-100+ points depending on
   session/vol bucket per `cost_model.py`'s table). Several strategies'
   structural targets (e.g. NR7-bar-range-derived, or a 3-point
   `min_sl_pts` floor) were smaller than that markup, so the "target"
   ended up on the losing side of the actual fill before the trade was
   even placed — explaining v1's suspicious exact-0.0%-win-rate rows.
   Fixed with a new shared helper, `signals/risk_floor.py`
   (`apply_floor`), applied at every one of the 10 strategies' signal
   construction sites. It only **widens** a stop/target that's narrower
   than a realistic cost-clearing floor (`min_sl_pts=40`,
   `min_target_pts=80`, read directly off the cost table's own DEAD_ZONE
   round-trip figures, not chosen to make any number look better) — it
   never shrinks an already-wide structural level, and it does not
   guarantee (and did not produce) a positive result.

Effect of the fix: win rates went from an implausible flat 0% (5 of 10
strategies) to a believable 21-56% range across all strategies that fired
at all — evidence the fix addressed a real defect rather than just moving
numbers around. Every strategy is still net-negative (see table): with
wider, cost-clearing stops, the realistic loss on a losing trade is
simply bigger than before, and none of these 10 candidates' win rates
clear the profit factor threshold that would make that trade-off worth
it, at least not on this little data.

## What changed between v2 and v3 (S02/S04, traced properly this time)

v2 left S02/S04's zero signals as "plausible, not confirmed" — hand-waved
to "not enough daily history." With the full continuous dataset now on
disk, that excuse no longer holds, so both got actually traced (real data,
not synthetic) instead of reasoned about from the docstring:

1. **Real bug, confirmed and partially fixed — S04's lookback window**:
   both S02 (`ctx.bars(3000)`, ~2 trading days) and S04
   (`ctx.bars(5000)`, ~3.5 trading days) requested far fewer M1 bars than
   their own daily-resampled logic needs (S04's `range_min_days=5`, S02's
   `htf_lookback_days=10`) — a structural bug independent of total dataset
   size, since `ctx.bars(n)` returns the last `n` raw bars, not `n` days.
   Widened to 12,000 (S04, ~8.3 trading days) and 25,000 (S02, ~17 trading
   days) — verified directly against real data that this now yields 24
   daily bars from a 25,000-bar window, ample margin above both
   thresholds. **This fix alone did not change either strategy's trade
   count** (see finding 2) but is real and stays — the old windows could
   never have worked at any data volume.
2. **Real bug, confirmed, NOT fixed yet — S04's range-tightness check is
   nearly unsatisfiable on real data**: traced `range_spring_upthrust`
   directly against ~850 real 5-day windows sampled across the full
   backfill. 852 of 873 returned `"not a tight enough range"`, only 21
   `"not enough daily history"` (early in the run, before 5 days
   existed) — direct proof the "needs more days" story was wrong, not
   just unconfirmed. Root cause: the check requires **every** day in the
   window to have its high near the range top **and** its low near the
   range bottom simultaneously (`price_action.py`'s `is_real_range`) —
   real intraday-resampled daily bars almost never do both at once,
   tolerance or no tolerance. Tried two candidate fixes to see if this
   was a quick patch: relaxing the per-day AND to an OR still fired 0/852
   times; a standard trend/range "efficiency ratio" fires on ~98% of
   windows on this instrument (gold's daily H-L noise swamps the ratio
   regardless of whether the period was actually trending), making it
   uselessly non-discriminating here. **Left unfixed rather than ship a
   guessed threshold under time pressure** — a real range-vs-trend
   detector needs a properly chosen volatility/ADX-style criterion, which
   is a small design task in its own right, not a one-line fix, and
   guessing one now risks exactly the kind of untested, possibly-lucky
   heuristic the honesty clause warns against. S04 stays at n=0,
   correctly labeled as "blocked by a known, undiagnosed-fix logic bug,"
   not "discard, no edge."
3. **S02: no bug found, most likely genuine parameter rarity, not
   confirmed with full certainty**: `equal_highs_lows` at
   `tolerance_pct=0.15` (~$7-8 on ~$5,100 gold) did find real equal-level
   pools on real data (5 of 852 sampled 10-day daily windows), just never
   coincided with an immediate sweep of that same pool in the same coarse
   check — consistent with a genuinely tight, rare parameter combination
   rather than a structural defect like S04's. A full incremental trace
   (mimicking the strategy's actual bar-by-bar pending-sweep state
   machine, not this point-sampled proxy) would be needed to fully rule
   out a subtler bug, but nothing found so far points to one.

## Results table (v3, pooled `all`, full continuous 6.5-month series)

| # | Strategy | Trades | Win% | PF | Avg R | Total PnL | Max DD% | Verdict |
|---|---|---|---|---|---|---|---|---|
| S01 | Liquidity Sweep + Displacement + FVG Retest | 114 | 34.2 | 0.21 | -0.64 | -$416.29 | 8.4 | Discard (negative, sample now credible) |
| S02 | Multi-Timeframe Liquidity + CHoCH | 0 | — | — | — | $0.00 | — | No verdict yet — likely genuine parameter rarity (see finding 3 above), not confirmed with full certainty |
| S03 | Order Block Retest after BOS | 178 | 37.6 | 0.23 | -0.60 | -$612.94 | 12.4 | Discard (negative, sample now credible) |
| S04 | Wyckoff Spring/Upthrust | 2 | 50.0 | 1.69 | 0.76 | $5.45 | 0.16 | **Underpowered (n=2)** — logic bug since fixed (three-gate redesign), see the dedicated section below; too few trades for any real verdict |
| S05 | NR7/Inside-Bar Compression Breakout | 174 | 26.4 | 0.13 | -0.85 | -$811.50 | 16.2 | Discard (worst of the 10, negative, sample now credible) |
| S06 | Premium/Discount OTE Fib Retracement | 49 | 42.9 | 0.29 | -0.51 | -$146.06 | 3.1 | Discard — the n=16/PF=0.86 result was sample-size noise, not signal: 3x the trades (49) drops PF to 0.29, resolving toward negative like the rest, not toward breakeven |
| S07 | Market Profile Value-Area Rotation | 106 | 44.3 | 0.33 | -0.43 | -$278.77 | 5.8 | Discard (negative, sample now credible) |
| S08 | BOS Pullback Continuation | 109 | 33.9 | 0.19 | -0.67 | -$419.31 | 8.4 | Discard (negative, sample now credible) |
| S09 | Session Liquidity Run + Reversal | 72 | 30.6 | 0.23 | -0.70 | -$278.57 | 5.9 | Discard (negative, sample now credible) |
| S10 | Equal Highs/Lows + RSI Divergence | 172 | 39.0 | 0.25 | -0.57 | -$564.07 | 11.3 | Discard (negative, sample now credible) |

8 of 10 are net-negative on a now-credible sample (72-178 trades, most
clearing or close to the 200-trade threshold) — no exceptions this time,
no "wait for more data" caveat left to hide behind. **S06, the one
candidate v2 flagged as "possibly just noise," resolved toward negative,
not positive** — a genuinely useful result: it confirms the v2 caveat was
right to withhold judgment, and confirms the answer once enough data
existed was "no," not "yes." S02 and S04 have no real verdict yet, for two
different and now-distinguished reasons — S04 because of a confirmed logic
bug blocking every signal, S02 because of what looks like genuine
parameter rarity (needs a finer trace to fully confirm).

Session breakdown (all strategies, now genuinely meaningful with a full
continuous dataset — the v2 "collection-order artifact" caveat no longer
applies): every session bucket (`asia`, `london`, `london_ny_overlap`,
`ny`, `dead_zone`) is negative for every strategy that traded, no
exceptions. `asia` carries the most trades for most strategies (highest
raw signal frequency, not better performance) and `dead_zone` the fewest.
No session shows a real edge for any of these 10 — this isn't a
session-timing problem masking an otherwise-real edge.

Monte Carlo note: trade-order shuffling was run (5,000 sims/strategy) but
since total P&L is order-invariant under shuffling, the PnL percentiles
it produces are trivially identical to the actual total — only max-drawdown
*path* varies under shuffling. Reported `max_dd_pct` above is the actual
(non-shuffled) run; shuffling added no new information at this trade count
and isn't tabulated separately here. This is a limitation of this
analysis script, not the underlying trades — worth a real block-bootstrap
or per-session Monte Carlo once there's enough data per session to make
that meaningful.

## Bottom line

Zero of the 10 keep/keep-with-caveats. 8 of 10 now have a credible,
full-dataset negative verdict with no "wait for more data" excuse left —
including S06, whose earlier "closest to breakeven" result explicitly
resolved toward negative once the sample tripled, confirming it was noise,
not signal. The remaining 2 (S02, S04) have no verdict at all yet, and for
two different reasons that matter for what happens next: S04 is blocked by
a confirmed, real logic bug (not a market question — the detector can't
fire regardless of whether the edge exists), while S02's zero signals look
like genuine parameter rarity, not a defect. Per the honesty clause:
reporting this plainly rather than forcing a top-5 pick out of results
that don't support one, and not quietly patching S04 with a guessed
threshold just to get it un-stuck.

## What P4 needs before it can proceed on solid ground

1. **S04's range-tightness detector needs an actual redesign** (a
   volatility/ADX-style range-vs-trend criterion, not the current
   both-edges-every-day check) before this strategy has any verdict at
   all — this is now the single highest-value next step, since it's the
   only one of the 10 still genuinely undetermined rather than resolved
   negative.
2. S02 would benefit from a real incremental trace (mimicking its actual
   bar-by-bar pending-sweep state machine) to fully rule out a subtler
   bug the way S04's was found — not urgent, since nothing found so far
   points to one, but not fully closed either.
3. Given 8 of 10 are negative even with the sizing fix and a full
   6.5-month sample, it's also worth asking whether
   `min_sl_pts=40`/`min_target_pts=80` (this fix's own
   floor values, derived from the cost table's DEAD_ZONE figures) are
   too conservative for the LONDON/LONDON_NY_OVERLAP sessions where real
   spread is far tighter — a session-aware floor instead of one fixed
   number is the natural next refinement, not a re-tune toward a target.

Re-running this exact script (`run_backtests.py`) after any of the above
changes takes ~15-40 minutes on the full dataset (S02/S04's widened
lookback windows are the expensive part — each re-resamples up to 25,000
M1 bars to daily on every single bar). Data volume is no longer the
blocker it was in v1/v2 — it's S04's detector logic and the fixed floor's
session-granularity that are the open items for a P4 rulebook now.
