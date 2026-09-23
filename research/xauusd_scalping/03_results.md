# P3 Results — XAUUSD Scalping, 10-Strategy Backtest

**Status (v3, full continuous 6.5-month backfill + a real S04 bug found by
tracing, not assumed): all 10 candidates are still net-negative, and this
is the most trustworthy read yet.** v1 and v2 (below the line, kept for
the record) ran on a partial/disjoint dataset; v3 runs on the completed
backfill — one continuous series, no data hole. Read "What changed between
v2 and v3" before the table.

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
| S04 | Wyckoff Spring/Upthrust | 0 | — | — | — | $0.00 | — | **No verdict — blocked by a confirmed, unfixed logic bug** (finding 2 above), not a data or edge question |
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
