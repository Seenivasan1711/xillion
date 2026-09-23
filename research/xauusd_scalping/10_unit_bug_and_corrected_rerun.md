# 10 — The 100x points-vs-price unit bug, and the corrected re-run

**Date: 2026-09-24.** Supersedes the cost conclusions in `07` (Finding 2),
`09` (leverage), the S11 scale sweep, and the pre-fix `03b` benchmark.
Correction-history entry: `08_correction_history.md` #18.

---

## 1. What was wrong

The research engine mixes two units that are both called "points":

| Where | Unit actually used | Example |
|---|---|---|
| Bars (Dukascopy parquet), stops, targets, strategy params (`min_sl_pts=3.0`, `sl_buffer_pts=0.5`) | **price, dollars/oz** | 3.0 = a $3.00 stop |
| `cost_model.py` spread table + slippage | **MT5 points, $0.01** | 30 = a $0.30 spread |
| `SizingConfig.point_value_usd = 1.0` | **$ per MT5 point per lot** | 1 lot = 100oz → $1 per $0.01 |

Nothing converted between them. Three consequences:

1. **Costs 100x too large.** `entry_price = bar.close + entry_cost_pts`, so a
   London 28pt ($0.28) spread moved the fill by **$14**, not $0.14. Same on
   exit.
2. **The engine's cost-clearing floor was 100x too wide.** `min_sl_pts=40`,
   `min_target_pts=80` were derived from the spread table (in points) but
   applied as **$40 / $80** of price. Every trade in 03/03b/03d ran with a
   $40 stop and an $80 target, not the strategies' own structural levels.
3. **USD P&L 100x too small / fixed-fractional size 100x too big.** A price
   difference in dollars was multiplied by $1 "per point". R-multiples looked
   sane only because numerator and denominator shared the error.

**Proof from one real trade** (`_s11_trades_real.json`, first row, NY session):
entry 5093.875, stop 5133.875 (**exactly $40.00** away), exit 5153.875
(**exactly $20.00** past the stop = NY/MEDIUM spread 30/2 + slippage 5,
applied as dollars).

**Why it wasn't caught:** Rakesh's live MT5 spread reading (bid 4284.50 /
ask 4284.81 = $0.31 = 31pts) was compared against the *table value* 30 and
"matched" — but the engine never applied $0.30, it applied $30. The check
validated the input, not what the engine did with it.

**How it was caught:** a 40-"point" stop and an 8-"point" median hourly move
are implausible against gold's real ~$40/day range, so the units were traced
through one real trade.

## 2. The fix

- `engine/cost_model.py`: `POINT_SIZE = 0.01`, documented as the only
  points↔price conversion.
- `engine/backtest_engine.py`: entry cost, exit cost, floor, P&L, sizing and
  MAE/MFE all convert through `POINT_SIZE`. Prices stay in dollars internally.
- The floor now means what its docstring says: 40/80 points = **$0.40/$0.80**,
  which is below every strategy's own `min_sl_pts=3.0` ($3), so **strategies
  now trade their own structural stops/targets again** — as specified in
  `01_shortlist_v2.md`. (The floor in `signals/risk_floor.py` was itself a
  response to this bug: its docstring compares a "$3 stop" to "27-108pt
  costs" that were really $0.27-$1.08.)
- Tests: the 6 engine tests that encoded the old units were re-derived by
  hand (e.g. $5 move × 1 lot = **$500**, not $5). New
  `test_units_match_the_real_broker_not_100x_off` pins real broker economics:
  0.08 lot × $5 move = $40, 28pt spread = $0.14 per side. 37/37 research
  tests pass.

**Realistic cost now:** ~$0.28-$0.55 round-trip spread + ~$0.08 slippage +
$0.05/oz commission ≈ **$0.40-$0.70 per oz**, i.e. ~13-23% of a $3 stop — a
real but no-longer-fatal drag.

## 3. What survives, what is void

| Earlier conclusion | Status |
|---|---|
| `07` Finding 1: S11 signals ≈ coin flip, **cost-free** walk-forward | **Survives** — never touched the cost model. (Its "40/80" distances were in price dollars, as the rest of the code.) |
| `07` Finding 2: "spread exceeds the move", cost = 98% of risk | **VOID** — artifact of the 100x bug |
| `09`: leverage cannot fix it (cost/risk 110% at any size) | **VOID** — the cost/risk ratio was wrong; the general point (leverage scales a negative expectancy, never fixes it) still holds as arithmetic |
| `08` #12 R:R geometry bug (2:1 → 0.90:1) | Mechanism real, **magnitude was 100x inflated** — with real costs the distortion is ~$0.2 on a $3+ stop |
| `03b` random-entry benchmark (pre-fix: 0/10 beat random) | **VOID** — re-run below |
| S11 scale sweep, "stops collide with the $50 cap" | **VOID in magnitude** — P&L was 100x understated; re-run pending |
| App's own Sweep-Reversal backtest (`xillion/engine`, -$12,705) | **Not affected** — different engine, units verified correct (avg loss $129.56 at 0.08 lot ≈ $16 of price). Its 5bps slippage overstates cost by ~$0.5/trade (~$800 of the loss); verdict stands |

## 4. Corrected re-run — all 10 strategies, real costs, spec risk limits

Config (unchanged from `run_backtests.make_engine()`): 0.08 lot fixed,
$50 daily loss cap, 4 trades/session, 2-consecutive-loss halt, 174,554 M1
bars 2026-03-01 → 2026-09-16.

| Strategy | Trades | Net P&L | Random p5 / p50 / p95 | vs random |
|---|---|---|---|---|
| S01 Liquidity Sweep + FVG Retest | 209 | -$2,382.80 | -$3,694 / -$705 / +$2,521 | indistinguishable |
| S02 MTF Liquidity + CHoCH | 0 | $0.00 | — | untestable (structurally never fires, known) |
| S03 Order Block Retest after BOS | 484 | -$3,493.84 | -$3,769 / -$2,124 / -$216 | indistinguishable |
| S04 Wyckoff Spring/Upthrust | 3 | +$1,582.39 | -$198 / -$127 / +$1,593 | indistinguishable (n=3, meaningless) |
| S05 NR7/Inside-Bar Breakout | 566 | -$3,686.90 | -$4,067 / -$2,776 / -$1,613 | indistinguishable |
| S06 OTE Fib Retracement | 72 | -$640.01 | -$1,925 / -$338 / +$1,614 | indistinguishable |
| **S07 Value-Area Rotation** | **204** | **+$411.69** | -$2,397 / **-$736** / +$1,310 | indistinguishable — but **+$1,148 above the random median**, the best of ten |
| S08 BOS Pullback Continuation | 25 | +$301.10 | -$695 / -$80 / +$462 | indistinguishable (n=25, too small) |
| S09 Session Liquidity Run + Reversal | 154 | -$247.79 | -$3,187 / -$611 / +$2,008 | indistinguishable |
| S10 Equal Highs/Lows + RSI Div | 476 | -$4,244.97 | -$3,592 / -$1,895 / -$346 | **worse than random** |

Config (unchanged from `run_backtests.make_engine()`): 0.08 lot fixed, $50
daily loss cap, 4 trades/session, 2-consecutive-loss halt, 174,554 M1 bars
2026-03-01 → 2026-09-16. Random benchmark: 500 matched runs per strategy
(same entry timestamps' sessions, same stop/target distances, random
direction/timing), seed-fixed — full output in `03b_random_entry_benchmark.md`.
S01 detail: win 15.8%, PF 0.70, -0.33R/trade, maxDD 59.6%.

**Reading the random bands.** With correct costs the bands are now *wide*
(S01's spans $6,200) — random trades at real cost genuinely swing both ways
over ~200 trades. That's the honest statistical reality of a 6.5-month
sample: to separate a strategy from luck at this size, it has to make well
over ~$1,300 on ~200 trades. None does.

## 5. What this means for next steps

**Decision rule (stated before results):** candidate = net-positive with
n ≥ 100 **and** above the random 95th percentile. **Result: no strategy
qualifies.** One passes half: **S07 is net-positive on 204 trades** (+$412)
and beats the random median by $1,148, but sits below p95 (+$1,310).

**What changed vs. the pre-fix verdict** — materially, and in the direction
that matters:

| | Pre-fix (100x costs) | Corrected |
|---|---|---|
| Worse than random | 6 of 10 | 1 of 10 (S10) |
| Net-positive with n ≥ 100 | 0 | 1 (S07) |
| "Costs make M1 structurally impossible" | claimed | **false** — real cost ≈ 13-23% of a $3 stop |

So M1 XAUUSD is **not dead** — it was never tested at real cost until now.
It is also **not proven**: nothing clears the luck bar on 6.5 months.

**Next, in order (XAUUSD first, then forex — Rakesh's direction):**
1. **Backfill more XAUUSD history** (Dukascopy, 2-3 years — resumable,
   runs detached for ~a day). This is the single biggest lever: a longer
   sample narrows the random band, so a real edge like S07's (if it is one)
   can actually be distinguished from luck. Every later test reuses it.
2. **S07 focused study on the longer data:** re-run + random benchmark,
   then the walk-forward/holdout the spec requires (never run yet —
   deliberately, until a strategy earned it). Also S07 at M5/M15, where
   costs are an even smaller share of the move.
3. **Re-run the other survivors cheaply on the longer data** (S01, S09 —
   inside the band, not below it); drop S10 (worse than random).
4. **Forex:** download EURUSD/GBPUSD (same Dukascopy downloader, needs a
   per-pair price divisor + point size) and run the same toolkit + random
   benchmark. Needs a per-symbol `POINT_SIZE`/spread table — the fix in §2
   makes that a clean parameter rather than a hidden constant.
