# P3 Results — XAUUSD Scalping, 10-Strategy Backtest

**Status: none of the 10 candidates are recommendable yet.** This is not a
"tune and resubmit" result — it's a data-volume and cost-calibration
problem that has to be fixed before a P3 verdict can mean anything. Read
the two "why this isn't a real result" sections before the table.

## Data actually used (honest accounting)

The background Dukascopy backfill has **not** produced the 3-6 month
continuous series the build spec (`00_build_prompts.md`) assumes. What
exists on disk right now:

| Segment | Bars (M1) | Span |
|---|---|---|
| `XAUUSD_2026-03.parquet` | 19,916 | 2026-03-01 23:00 → 2026-03-13 20:59 |
| `XAUUSD_2026-09.parquet` | 3,480 | 2026-09-14 00:00 → 2026-09-16 23:59 |
| **Combined** | **23,396** | ~16 calendar days, split into two windows 6 months apart |

A real walk-forward (6mo train / 1mo test) is not possible on this. What
this run does instead: pool both windows into one backtest per strategy
(`all`), and separately run each window alone (`march`, `sept`) as a crude
"does this look the same in two different periods" sanity check — not a
substitute for the spec's actual validation protocol. **Every single
strategy's trade count is far below the 200-trade underpowered threshold**
(max 42 trades). Nothing below should be read as a statistically
meaningful edge/no-edge verdict — it's a directional first look.

## Bug found and fixed during this run (engine, not strategies)

The first backtest pass produced 0-3 trades total per strategy across
23k bars regardless of strategy logic — the tell of a shared bug, not 10
independently silent strategies. Root cause:
`BacktestEngine.run()`'s `consecutive_losses` counter was never reset on
day rollover, unlike its sibling risk limits (`daily_pnl`, `trades_today`,
`halted_today`, all reset in the day-change block). `daily_loss_cap_usd`
is documented and tested as a **per-day** circuit breaker
(`test_daily_loss_cap_halts_new_entries_for_the_rest_of_the_day`);
`consecutive_loss_halt` had no equivalent test and, once tripped anywhere
in the run, silently halted every subsequent day for the rest of the
entire backtest. Fixed in `engine/backtest_engine.py` (one-line reset
alongside the others) and locked in with a new mirroring regression test,
`test_consecutive_loss_halt_resets_on_a_new_day`, in `tests/test_engine.py`.
All 25 research-pipeline tests pass; production suite (`tests/`) untouched
by this change and still green.

## Second finding: stop distances vs. the cost model (needs attention before P4)

After the halt fix, 5 of the 10 strategies show a suspicious **exact 0.0%
win rate** across 20-42 trades each (S03, S05, S07, S08, S10) — every
single trade lost. Traced one (`s05_nr7_inside_bar_breakout.py`) by hand:
the strategy computes `stop`/`target` off the *raw* `bar.close` it
observes, then the engine independently marks up the actual fill with
`entry_cost_pts` (half-spread + slippage — 9 to 100+ points depending on
session/vol bucket per `cost_model.py`'s pessimistic table). Several
strategies use very tight absolute stop distances (e.g. `min_sl_pts=3.0`,
or NR7-bar-range-derived targets that can be a handful of points). When
the cost markup exceeds the strategy's own risk unit, **the "target" ends
up on the losing side of the actual fill price before the trade is even
placed** — not a signal-quality failure, a stop-sizing-vs-cost-model
mismatch. This is exactly the harness doc's own warning ("costs are the
whole game at this timeframe") showing up concretely. Two strategies
(S02, S04) fired zero signals at all across the full 23k bars — plausible
on its face (S04's Wyckoff spring needs a multi-day range and only ~16
calendar days of daily bars exist; S02 is a strict multi-timeframe
alignment gate) but not yet root-caused to the same depth as S05, flagged
here rather than silently accepted.

**Recommendation, not yet actioned**: before any of these 10 are re-run
for a real verdict, each strategy's stop/target sizing needs to be
expressed relative to the session/vol-bucket cost at entry time (or at
minimum, ATR-scaled instead of a fixed point count), not a raw price
delta computed before the engine's own cost markup is known.

## Results table (pooled `all`, both windows combined — n far below 200 for every row)

| # | Strategy | Trades | Win% | PF | Avg R | Total PnL | Max DD% | Verdict |
|---|---|---|---|---|---|---|---|---|
| S01 | Liquidity Sweep + Displacement + FVG Retest | 29 | 6.9 | 0.06 | -1.52 | -$103.73 | 2.1 | Discard (underpowered + negative) |
| S02 | Multi-Timeframe Liquidity + CHoCH | 0 | — | — | — | $0.00 | — | Discard (no signals fired — needs investigation, not a pass) |
| S03 | Order Block Retest after BOS | 40 | 0.0 | 0.00 | -1.77 | -$172.79 | 3.5 | Discard (stop/cost mismatch suspected) |
| S04 | Wyckoff Spring/Upthrust | 0 | — | — | — | $0.00 | — | Discard (no signals fired — plausible given <16 days of daily bars, not root-caused) |
| S05 | NR7/Inside-Bar Compression Breakout | 42 | 0.0 | 0.00 | -1.73 | -$183.84 | 3.7 | Discard (confirmed stop/cost mismatch, see above) |
| S06 | Premium/Discount OTE Fib Retracement | 6 | 0.0 | 0.00 | -1.85 | -$24.02 | 0.5 | Discard (underpowered + negative) |
| S07 | Market Profile Value-Area Rotation | 20 | 0.0 | 0.00 | -1.79 | -$84.70 | 1.7 | Discard (stop/cost mismatch suspected) |
| S08 | BOS Pullback Continuation | 41 | 0.0 | 0.00 | -1.68 | -$189.16 | 3.8 | Discard (stop/cost mismatch suspected) |
| S09 | Session Liquidity Run + Reversal | 14 | 7.1 | 0.04 | -1.32 | -$48.11 | 1.0 | Discard (underpowered + negative) |
| S10 | Equal Highs/Lows + RSI Divergence | 40 | 0.0 | 0.00 | -1.74 | -$179.08 | 3.6 | Discard (stop/cost mismatch suspected) |

Session breakdown (all strategies): losses concentrate heavily in the
`asia`/`dead_zone` sessions (worst spread tier in the cost table) —
consistent with the stop/cost mismatch theory, not with a session-timing
edge failing. No strategy shows a session where it's convincingly
profitable even before the mismatch is fixed.

Monte Carlo note: trade-order shuffling was run (5,000 sims/strategy) but
since total P&L is order-invariant under shuffling, the PnL percentiles
it produces are trivially identical to the actual total — only max-drawdown
*path* varies under shuffling. Reported `max_dd_pct` above is the actual
(non-shuffled) run; shuffling added no new information at this trade count
and isn't tabulated separately here.

## Bottom line

Zero of the 10 keep/keep-with-caveats. This isn't "the strategies don't
work" — it's "this run can't yet distinguish a real edge from stop-sizing
and sample-size artifacts." Per the honesty clause: reporting this
plainly rather than forcing a top-5 pick out of a run that can't support
one.

## What P4 needs before it can proceed on solid ground

1. More real backfilled data (ideally a continuous multi-month window, not
   two 6-months-apart 16-day fragments) — the backfill should keep running.
2. Stop/target sizing revisited per strategy so it isn't structurally
   swallowed by the session/vol-bucket cost markup (see finding above).
3. S02/S04 zero-signal root-cause (verify the gate conditions are reachable
   at all against real data, vs. a real implementation bug).

Re-running this exact script (`run_backtests.py`) after any of the above
changes takes minutes, not hours — the harness and toolkit underneath are
sound; it's the strategy parameterization and data volume that aren't
ready for a P4 rulebook yet.
