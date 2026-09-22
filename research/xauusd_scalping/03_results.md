# P3 Results — XAUUSD Scalping, 10-Strategy Backtest

**Status (v2, after fixing two real bugs found in v1): all 10 candidates
are still net-negative, but this is now a real result, not an artifact.**
v1 of this run (below the line, kept for the record) had two bugs that
made every number meaningless; both are fixed, and v2's numbers are what
should actually inform the P4 decision. Read "What changed between v1 and
v2" before the table — the short version: none of the 10 are recommendable
as-is, but the failure mode is now "priced-in cost drag on a tight,
underpowered sample," not "broken harness."

## Data actually used (honest accounting)

The background Dukascopy backfill is still running (has been the whole
time this analysis was done) and grew the dataset mid-session:

| Segment | Bars (M1), v1 → v2 | Span |
|---|---|---|
| `XAUUSD_2026-03.parquet` | 19,916 → 28,676 | 2026-03-01 23:00 → grows as backfill proceeds |
| `XAUUSD_2026-09.parquet` | 3,480 → 3,480 (unchanged) | 2026-09-14 00:00 → 2026-09-16 23:59 |
| **Combined** | **23,396 → 53,033** | still two windows ~6 months apart, not one continuous series |

A real walk-forward (6mo train / 1mo test) is still not possible on this
— the March/September gap is a data hole, not a resolution issue, and
only the backfill (still in progress) closes it. What this run does
instead: pool both windows into one backtest per strategy (`all`), and
separately run each window alone (`march`, `sept`) as a crude "does this
look the same in two different periods" sanity check — not a substitute
for the spec's actual validation protocol. **Every strategy's trade count
is still below the 200-trade underpowered threshold** (max 73 trades, up
from a max of 42 in v1 as more data arrived). Nothing below should be read
as a statistically meaningful edge/no-edge verdict yet — it's a
directional read that's at least no longer contaminated by the v1 bugs.

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
it, at least not on this little data. S02 and S04 still fire zero
signals — investigated at the code level (not just accepted): S04's own
module docstring already flags this as expected (`range_min_days=5`
needs more daily bars than ~16 real calendar days provides); S02 needs a
10-day HTF liquidity pool (`htf_lookback_days=10`) from the same thin
daily-bar count, which is a plausible non-bug explanation but hasn't been
verified by tracing an actual near-miss the way S05's bug was — flagged,
not silently written off.

## Results table (v2, pooled `all`, both windows combined — n still below 200 for every row)

| # | Strategy | Trades | Win% | PF | Avg R | Total PnL | Max DD% | Verdict |
|---|---|---|---|---|---|---|---|---|
| S01 | Liquidity Sweep + Displacement + FVG Retest | 43 | 37.2 | 0.25 | -0.56 | -$141.15 | 2.9 | Discard (underpowered + negative) |
| S02 | Multi-Timeframe Liquidity + CHoCH | 0 | — | — | — | $0.00 | — | Discard (no signals fired — plausible per gate strictness below, not confirmed) |
| S03 | Order Block Retest after BOS | 70 | 35.7 | 0.29 | -0.56 | -$234.07 | 5.5 | Discard (underpowered + negative) |
| S04 | Wyckoff Spring/Upthrust | 0 | — | — | — | $0.00 | — | Discard (no signals fired — expected given <16 days of daily bars, per its own docstring) |
| S05 | NR7/Inside-Bar Compression Breakout | 69 | 21.7 | 0.15 | -0.90 | -$346.20 | 7.5 | Discard (worst of the 10 — high frequency, poor win rate) |
| S06 | Premium/Discount OTE Fib Retracement | 16 | 56.2 | 0.86 | -0.02 | -$8.09 | 0.8 | Discard, but closest to breakeven — most underpowered (n=16), worth a rerun first once more data lands |
| S07 | Market Profile Value-Area Rotation | 34 | 55.9 | 0.45 | -0.32 | -$72.55 | 1.6 | Discard (underpowered + negative) |
| S08 | BOS Pullback Continuation | 73 | 34.2 | 0.25 | -0.62 | -$264.48 | 5.8 | Discard (underpowered + negative) |
| S09 | Session Liquidity Run + Reversal | 20 | 45.0 | 0.50 | -0.32 | -$45.13 | 1.1 | Discard (underpowered + negative) |
| S10 | Equal Highs/Lows + RSI Divergence | 72 | 40.3 | 0.24 | -0.62 | -$253.05 | 5.1 | Discard (underpowered + negative) |

All 10 are net-negative; none clear a profit factor of 1.0. **S06** (OTE
Fib retracement) stands out as the one worth revisiting first once more
data lands — highest win rate (56.2%), best profit factor (0.86, closest
to breakeven of any candidate), and by far the smallest sample (n=16,
meaning its true PF could plausibly sit anywhere from clearly negative to
clearly positive). Everything else has enough trades now (34-73) that
"just needs more data to turn positive" is a weaker excuse than for S06 —
their negative PF is a more real signal at this point, not just noise.

Session breakdown (all strategies): trade volume concentrates heavily in
`asia`/`dead_zone` (the worst spread tier), simply because that's when
this backfill's earliest-collected March data starts (23:00 UTC onward)
— a data-collection-order artifact, not evidence about which session is
actually best/worst for these strategies. Don't read the session split as
a real edge finding yet.

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

Zero of the 10 keep/keep-with-caveats, and this is now a real (if
underpowered) result rather than a bug artifact. S06 is the one candidate
whose negative result is most plausibly a sample-size fluke rather than a
real negative edge — everything else has enough trades now that "discard"
is a real verdict, not just "wait for more data." Per the honesty clause:
reporting this plainly rather than forcing a top-5 pick out of results
that don't support one.

## What P4 needs before it can proceed on solid ground

1. More real backfilled data (still running in the background) — every
   strategy's trade count needs to clear 200 before a verdict is solid;
   S06 in particular needs far more than 16 trades before "closest to
   breakeven" can be trusted as a real signal rather than luck.
2. S02/S04's zero-signal explanation is plausible from reading the code
   (both need more consecutive days of history than currently exist) but
   hasn't been verified against a real near-miss the way S05's original
   bug was — worth confirming once more data exists, in case it's masking
   a second implementation defect the same way the stop/cost mismatch was
   masking one for S03/S05/S07/S08/S10 in v1.
3. Given all 10 are negative even with the sizing fix, it's also worth
   asking whether `min_sl_pts=40`/`min_target_pts=80` (this fix's own
   floor values, derived from the cost table's DEAD_ZONE figures) are
   too conservative for the LONDON/LONDON_NY_OVERLAP sessions where real
   spread is far tighter — a session-aware floor instead of one fixed
   number is the natural next refinement, not a re-tune toward a target.

Re-running this exact script (`run_backtests.py`) after any of the above
changes takes minutes, not hours — the harness and toolkit underneath are
sound; it's data volume and per-session sizing granularity that aren't
there yet for a P4 rulebook.
