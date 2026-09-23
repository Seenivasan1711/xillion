# XAUUSD Scalping Research — Consolidated Findings & Request for New/Combined Strategy Ideas

**Purpose of this file:** self-contained enough to hand to a different LLM
(no other project context needed) and get back a concrete, prioritized
plan for what to backtest next — new strategy ideas, ways to combine the
existing 10, and/or fixes to the existing ones — grounded in what's
already been tried, what worked, what didn't, and why. If you are that
LLM, read this in full before answering; the honesty-clause section at
the end is not optional color, it's a hard constraint on any answer you
give.

---

## Your role

You are acting as a senior quantitative strategy researcher and systematic
trading strategy builder, specializing in short-timeframe (scalping)
FX/metals systems. You've been handed a real research program's full
history below — what was hypothesized, what was actually tested against
real market data, what the numbers actually showed, and what's still
unresolved. Your job: **propose specific, testable next steps** — new
strategy mechanisms, combinations of the existing ones, or concrete fixes
to existing ones — that this team should backtest next, and say exactly
how each one should be validated so the answer that comes back is
trustworthy rather than another false positive.

Do not just say "try more indicators" or "optimize the parameters." Every
suggestion must be a specific, mechanistic trading idea (what triggers
entry, what defines direction, what invalidates the setup) or a specific,
falsifiable combination of the existing 10 (e.g., "only take S07's signal
when S03's order-block condition also holds within N bars" — that level
of specificity), plus the exact test protocol to check it honestly.

---

## 1. The account and goal this is for

- **Instrument**: XAUUSD (spot gold) only, no other instruments in scope.
- **Account**: FundingPips 1-Step Flex, $5,000, prop-firm-style — 12%
  total profit target, no daily-consistency rule. Hard constraints already
  baked into every backtest: max 4 trades/session, $50 max daily loss,
  halt for the day after 2 consecutive losses.
- **Position size tested throughout**: fixed 0.08 lots (see §6 for a real
  account's actual 0.10-lot trade log for comparison).
- **Realistic target math** (from the original research brief, worth
  keeping in view): a 60% win rate at 2.5:1 R:R (expectancy 1.6R/trade) is
  not realistic — no published intraday gold system sustains it. Realistic
  pairings are closer to ~60% win at ~0.8-1.0R, or ~40% at ~2.5R. The
  original target was $30-60/day; that requires roughly 2R/day net at
  ~$20/R, which collides with the $50 daily loss cap at realistic
  trade-frequency and expectancy — this collision is a known, accepted
  constraint, not something to solve by increasing lot size past what the
  daily cap allows.
- **Data**: 174,554 real M1 (1-minute) OHLC bars, Dukascopy tick data
  resampled, one continuous series, 2026-03-01 to 2026-09-16 (~6.5
  months). No synthetic data anywhere in the results below.

## 2. Architecture (so your suggestions fit the existing system)

- Every strategy is a class implementing `on_bar(bar, ctx) -> Signal | None`
  — reacts to one new closed bar at a time, no lookahead (`ctx.bars(n)`
  returns only already-closed history).
- Signal detection is built from two composable toolkits, callable
  independently (any new strategy should do the same, not reinvent
  detection logic):
  - `signals/price_action.py` — liquidity sweep, displacement candle, fair
    value gap (+ retest), break of structure / change of character, order
    block, NR7/inside-bar, range spring/upthrust (Wyckoff), equal
    highs/lows, multi-level liquidity run.
  - `signals/indicators.py` — VWAP σ-bands, RSI, EMA, ADX, and others —
    demoted to a confirmation/confidence layer, not the primary trigger,
    per this project's own explicit direction (price action/institutional-
    liquidity concepts lead; indicators support).
  - `signals/confidence.py` — a weighted 0-100 confidence scorer that
    combines multiple component signals; exists but isn't yet driving any
    entry/no-entry decision in the current 10 strategies — a plausible
    place to plug in a combined-strategy idea (see §7).
- A shared, tested, event-driven backtest engine
  (`engine/backtest_engine.py`) handles SL/TP resolution (pessimistic
  same-bar-ambiguity rule: if one bar's range contains both stop and
  target, the stop is recorded as hit), gap-through-stop fills at the gap
  price not the stop price, and enforces the account risk rules above.
- A cost model (`engine/cost_model.py`) charges commission + spread +
  slippage per session, sized off a real spread table. **Known defect,
  unfixed as of this writing**: the model is documented as
  session×volatility-bucket but volatility-bucket is dead code — every
  trade is costed at a hardcoded "medium volatility" regardless of actual
  conditions. This didn't change any conclusion below (constant across
  every comparison made), but any new strategy will be costed the same
  slightly-imprecise way until this is fixed.
- A shared `signals/risk_floor.py` widens (never shrinks) any strategy's
  stop/target to a minimum cost-clearing distance (currently `min_sl_pts
  =40`, `min_target_pts=80`, read off the cost table's own worst-case
  round-trip figures) — this exists specifically because the first
  backtest pass found 5 of 10 strategies losing on effectively every trade
  from stops narrower than the cost of entering.

## 3. The 10 strategies tested, and why these 10

Chosen deliberately to be **price-action/institutional-liquidity-led**,
not indicator-led — an earlier first-pass shortlist of indicator-based
ideas (VWAP mean reversion, EMA pullback, session opening-range breakout,
Keltner squeeze, rolling high/low breakout) was explicitly rejected by the
project owner for not matching how larger market participants are
believed to actually operate (liquidity engineering, stop hunts, order
flow), and redone. These 10 are the result of that redo:

| # | Strategy | Core mechanism |
|---|---|---|
| S01 | Liquidity Sweep + Displacement + FVG Retest | Price sweeps a marked level, a strong displacement candle confirms direction, entry on retest of the fair value gap left behind |
| S02 | Multi-Timeframe Liquidity + CHoCH | Daily-timeframe equal-highs/lows (a liquidity pool) get swept, then an intraday change-of-character confirms before entry |
| S03 | Order Block Retest after BOS | A break-of-structure identifies the impulse move; entry on retest of the last opposite-color candle before that impulse (the "order block") |
| S04 | Wyckoff Spring/Upthrust | A multi-day range forms; a false breakout beyond it that gets reclaimed is traded as a reversal |
| S05 | NR7/Inside-Bar Compression Breakout | A 7-bar narrow-range or inside-bar compression pattern, traded on breakout |
| S06 | Premium/Discount OTE Fib Retracement | Entry in the "optimal trade entry" zone (62-79% Fibonacci retracement) of a recent impulse leg |
| S07 | Market Profile Value-Area Rotation | Fade back toward the point of control when price extends beyond the value area high/low in a balance/range day |
| S08 | BOS Pullback Continuation | Enter on a pullback after a confirmed break of structure, continuation-style |
| S09 | Session Liquidity Run + Reversal | Price runs through 2+ marked liquidity levels in one direction within a session, then reverses |
| S10 | Equal Highs/Lows + RSI Divergence | Equal-level liquidity pool + RSI divergence as confluence for a reversal |

Each also has an indicator-based confidence layer available (not
currently gating entries, just computed) per the project's explicit
instruction to keep indicators around "for better confidence-level markup
later," rather than discard them entirely.

## 4. What's already been found — read this before proposing anything

### 4.1 Real-cost backtest (the "v3" result, full 6.5-month dataset)

Pooled backtest (not yet a proper walk-forward — see §5's honesty-clause
section), fixed 0.08 lots, real session-based costs, full FundingPips risk
rules enforced:

| # | Strategy | Trades | Win% | PF (real cost) | Avg R | Total PnL |
|---|---|---|---|---|---|---|
| S01 | Liquidity Sweep+Displacement+FVG | 114 | 34.2 | 0.21 | -0.64 | -$416.29 |
| S02 | MTF Liquidity+CHoCH | 0 | — | — | — | $0.00 |
| S03 | Order Block Retest after BOS | 178 | 37.6 | 0.23 | -0.60 | -$612.94 |
| S04 | Wyckoff Spring/Upthrust | 0 | — | — | — | $0.00 |
| S05 | NR7/Inside-Bar Breakout | 174 | 26.4 | 0.13 | -0.85 | -$811.50 |
| S06 | OTE Fib Retracement | 49 | 42.9 | 0.29 | -0.51 | -$146.06 |
| S07 | Value-Area Rotation | 106 | 44.3 | 0.33 | -0.43 | -$278.77 |
| S08 | BOS Pullback Continuation | 109 | 33.9 | 0.19 | -0.67 | -$419.31 |
| S09 | Session Liquidity Run+Reversal | 72 | 30.6 | 0.23 | -0.70 | -$278.57 |
| S10 | Equal Levels+RSI Divergence | 172 | 39.0 | 0.25 | -0.57 | -$564.07 |

At face value: all 10 net-negative. **This is not the full story — read
4.2.**

S02 and S04 fire zero signals for two *different*, now-diagnosed reasons:
- **S04**: a confirmed, real logic bug. Its "is this actually a trading
  range" check requires every single day in a 5-day window to touch both
  the range's top and bottom simultaneously — real, noisy daily bars
  almost never do both, so it fires essentially never (traced directly:
  852 of 873 sampled real windows failed this exact check). A redesign
  (three independent gates — trend/range via a corrected Kaufman
  Efficiency Ratio, containment via a random-walk envelope, boundary
  validity via a touch-count) is in progress; not final as of this
  writing.
- **S02**: no confirmed bug — its equal-level-pool detection does fire
  occasionally on real data (rare but real, tight 0.15% tolerance), it
  just hasn't coincided with an immediate liquidity sweep of that pool in
  the checks run so far. Likely genuine parameter rarity, not fully
  confirmed bug-free.

### 4.2 The critical finding: cost vs. no-edge (read this carefully)

Re-ran the exact same 10 strategies' exact same trades with the cost
model set to **zero** (spread/slippage/commission all removed, nothing
else changed) to separate "the entry logic doesn't work" from "the entry
logic works but a fixed per-trade cost is bigger than the edge":

| # | Strategy | Real-cost PF | **Gross (zero-cost) PF** |
|---|---|---|---|
| S01 | 0.21 | **1.07** |
| S03 | 0.23 | **1.18** |
| S05 | 0.13 | 0.69 |
| S06 | 0.29 | **1.37** |
| S07 | 0.33 | **1.67** |
| S08 | 0.19 | **1.00** |
| S09 | 0.23 | 0.92 |
| S10 | 0.25 | **1.28** |

**6 of the 8 strategies that fire at all (S01, S03, S06, S07, S08, S10)
have real, positive gross expectancy** — verified this isn't a diagnostic
artifact: the cost actually extracted per trade is a consistent ~$3.80
(e.g. S07: $126.87 gross → -$278.77 net = $405.64 total cost / 106 trades
= $3.83/trade; S01: $3.79/trade), a believable magnitude for a 0.08-lot
position, not a bug. **Only S05 and S09 look genuinely edge-less even
before cost.**

**In plain terms**: for 6 of these 10, the entry logic is correctly
picking moves that go the right way often enough — they're only losing
money today because a roughly-fixed ~$3.80/trade cost (dominated by
spread+slippage on a tight stop) is bigger than the thin per-trade margin.
For S05 and S09, the entry logic itself doesn't work — no cost reduction
fixes that.

### 4.3 The obvious fix (coarser timeframe) was tested and does NOT work as expected

Given 4.2, the obvious next move is: trade on a coarser candle (5-minute
or 15-minute instead of 1-minute) so the same ~$3.80 fixed cost is a
smaller fraction of a naturally wider price swing. **Tested directly,
same code, same real cost model, no parameter changes** (deliberately, to
test the "just change the timeframe" version of the fix on its own
terms):

| Strategy | M1 PF (baseline) | M5 PF (n) | M15 PF (n) |
|---|---|---|---|
| S01 | 0.21 | 0.26 (56) | 0.28 (39) |
| S03 | 0.23 | 0.18 (153) | 0.25 (132) |
| S06 | 0.29 | 0.36 (18) | 1.06 (**n=7**) |
| S07 | 0.33 | 0.24 (89) | 0.28 (87) |
| S08 | 0.19 | 0.44 (**n=2**) | 0.16 (11) |
| S10 | 0.25 | 0.20 (141) | 0.22 (94) |

**No strategy meaningfully crosses net PF 1.0 on a usable sample.** The
one number above 1.0 (S06 at M15) has only 7 trades — treat as noise, not
a finding (this project already got burned once by an n=16 result for
this exact strategy that resolved to strongly negative once the sample
grew to n=49 — see the full history in `03_results.md` if you want the
detail). Several strategies got *worse* at a coarser timeframe, not
better.

**Root cause, diagnosed**: every strategy's lookback/threshold parameters
are counted in bars, not minutes. Unchanged code on M5 bars looks back 5x
further in real time than on M1 — it isn't trading "the same setups with
more room to breathe," it's now reacting to a qualitatively different,
much rarer class of setup. One strategy's trade count collapsed from 109
(M1) to 2 (M5) to 11 (M15) purely from this effect. **This rules out the
cheap version of the timeframe fix, not the underlying idea** — a proper
version would need each strategy's parameters redesigned to be
time-equivalent (not bar-count-equivalent) at the new timeframe, which is
real engineering, not yet attempted.

### 4.4 Still open / in progress as of this writing

- S04's three-gate redesign (§4.1) — implementation in progress, not
  finalized, not yet re-tested against real data end-to-end.
- A random-entry benchmark (same session mix, same stop/target profile,
  same costs, same risk limits as each real strategy, entries randomized)
  is being built to answer: are the 8 firing strategies' results actually
  distinguishable from noise at all, or would random entries with the
  same risk profile produce similar-looking numbers? Not complete as of
  this writing.
- **No real walk-forward or holdout validation has been run yet.**
  Everything above is a single pooled backtest over the whole 6.5-month
  dataset — in-sample by construction. The original research spec calls
  for a sealed 60/20/20 train/validation/holdout split, anchored
  walk-forward (6-month train / 1-month test, rolling), parameter-
  sensitivity heatmaps (reject a config that's a lone spike — require
  neighboring parameter values retain ≥70% of the expectancy), and a
  200-trade minimum before a result is treated as anything other than
  underpowered. None of that has been built yet. **Every number in this
  document could still partially or fully be an in-sample artifact** —
  this is the single biggest open risk in everything reported above, and
  should weigh heavily on how much confidence to place in the "6 of 10
  have real gross edge" finding specifically.

## 5. Honesty clause — this constrains any answer you give

This project has an explicit, standing rule, quoted from the original
research brief and enforced throughout: **do not tune toward a target
number.** If an honest answer is "this doesn't work," that is the most
useful result, not a failure. Concretely, this means:

- Any threshold or parameter you propose must be justified from
  first-principles reasoning (a derivation, a standard convention, a
  measured instrument property) — not chosen because it produces a nicer
  backtest number.
- Any new detector or combination should be validated first against
  synthetic data with known ground truth where possible (e.g., testing a
  trend/range classifier against synthetic mean-reverting vs. trending
  series, not against real gold P&L) before ever being checked against
  real trade outcomes.
- State your expected outcome (e.g., "this filter should reduce trade
  count by X% and should not reverse any strategy's win-rate ranking") **before**
  it's tested — a result wildly outside that stated expectation is a
  signal to debug, not to retune until it looks plausible.
- Any result with fewer than ~200 out-of-sample trades should be labeled
  UNDERPOWERED and not treated as a real verdict either way (see §4.3's
  n=7 example of exactly this trap).
- If your honest assessment is "none of these ideas are likely to clear a
  200-trade, walk-forward-validated, real-cost profit factor above 1.0,"
  say so plainly rather than manufacturing a plausible-sounding new
  strategy to avoid an unsatisfying answer.

## 6. Real account context (for realism calibration, not backtest data)

The project owner also trades this instrument manually/semi-manually on a
real MT5 account (separate from this backtest research — not the same
system, no shared code path). A recent trade history export, 0.10 lots,
XAUUSD, 2026-09-10 to 2026-09-21 (transcribed from a screenshot, exact
values):

| Time (open) | Side | Lots | Entry | SL | TP | Time (close) | Exit | Commission | Profit |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-10 15:16:17 | sell | 0.10 | 4372.94 | — | — | 2026-09-10 15:16:47 | 4372.41 | -0.50 | +5.30 |
| 2026-09-10 19:27:45 | buy | 0.10 | 4362.33 | 4368.25 | — | 2026-09-10 19:28:38 | 4362.60 | -0.50 | +2.70 |
| 2026-09-10 19:29:06 | buy | 0.10 | 4363.37 | 4367.19 | — | 2026-09-10 19:29:45 | 4363.68 | -0.50 | +3.10 |
| 2026-09-18 13:55:49 | buy | 0.10 | 4378.46 | — | — | 2026-09-18 13:56:43 | 4378.83 | -0.50 | +3.70 |
| 2026-09-21 13:54:26 | sell | 0.10 | 4347.22 | — | — | 2026-09-21 13:56:10 | 4348.49 | -0.50 | -12.70 |
| 2026-09-21 14:17:02 | sell | 0.10 | 4350.84 | — | — | 2026-09-21 14:18:08 | 4352.80 | -0.50 | -19.60 |
| 2026-09-21 14:20:13 | sell | 0.10 | 4353.43 | 4347.16 | — | 2026-09-21 14:21:31 | 4354.22 | -0.50 | -7.90 |
| 2026-09-21 14:22:04 | sell | 0.10 | 4354.55 | 4346.28 | — | 2026-09-21 14:34:28 | 4358.74 | -0.50 | -41.90 |
| 2026-09-21 14:24:08 | sell | 0.10 | 4352.40 | 4348.45 | — | 2026-09-21 14:34:29 | 4358.72 | -0.50 | -63.20 |
| 2026-09-21 14:28:51 | buy | 0.10 | 4353.87 | 4356.51 | — | 2026-09-21 14:29:18 | 4353.44 | -0.50 | -4.30 |
| 2026-09-21 14:31:57 | buy | 0.10 | 4356.65 | — | — | 2026-09-21 14:32:12 | 4356.93 | -0.50 | +2.80 |
| 2026-09-21 14:32:28 | sell | 0.10 | 4356.44 | 4347.24 | — | 2026-09-21 14:34:30 | 4358.67 | -0.50 | -22.30 |
| 2026-09-21 14:35:55 | buy | 0.10 | 4359.81 | — | — | 2026-09-21 14:36:53 | 4360.14 | -0.50 | +3.30 |

Session total shown: Profit -125.20, Commission -31.00 (across the fuller
session this excerpt is from, more trades than shown above), net -94.20.

**What's useful here, read carefully — this is anecdotal, real-world
context, not backtest evidence, and should not be treated as validating
or invalidating any strategy above:**

- **Real spread/commission at 0.10 lots is genuinely small per trade**
  (-$0.50 commission shown here) — broadly consistent in order of
  magnitude with this project's own modeled ~$3.80/trade total cost at
  0.08 lots (commission is only part of that $3.80; spread+slippage make
  up the rest and aren't visible as a separate line in a retail MT5
  statement, but are real).
- **Every winning trade above is small and fast** (+$2.70 to +$5.30,
  closed in 30-75 seconds).
- **Every large loss above is a trade with no S/L set** (blank in the
  table) or one left to run well past a reasonable exit (12+ minutes on
  what looks like a scalp entry, one losing -$63.20 — over 12x the size
  of the largest win shown). This is a real, human-discretion failure
  mode (no hard stop, hope, let it run) — not a strategy-logic failure,
  but directly relevant: it's the exact reason this project's backtest
  engine enforces a hard stop on every simulated trade and the
  `risk_floor.py` cost-clearing minimum stop distance exists. **Any
  strategy you propose must have an unconditional, mechanical stop-loss
  with no discretionary override** — the real-world cost of not having
  one is visible directly in this data (a handful of undisciplined trades
  produced more damage than the ~10 disciplined small trades' combined
  gains).
- Price level context: XAUUSD traded around $4,350-4,380 in this
  September excerpt, consistent with the backtest dataset's own price
  trajectory (~$5,100 in March, declining toward ~$4,350 by September) —
  same real underlying instrument and period, not a different market
  regime than what's been backtested.

## 7. What we're asking you for

Given everything above, propose a prioritized set of next backtests. For
each proposal, be specific about:

1. **The exact mechanism** — entry trigger, direction logic, invalidation
   condition — not a vague concept.
2. **Whether it's a new strategy, a modification of an existing one, or a
   combination of 2+ existing ones** (e.g., a specific confluence rule
   using the existing toolkit's primitives — `liquidity_sweep`,
   `displacement_candle`, `fair_value_gap`, `break_of_structure`,
   `change_of_character`, `order_block`, `equal_highs_lows`, plus
   `IndicatorSignals`' RSI/EMA/ADX/VWAP as confirmation).
3. **Why you think it's more likely to survive real costs and a real
   walk-forward** than the 10 already tested — ideally grounded in
   something specific from §4 (e.g., "S07 and S03 have the highest gross
   PF and overlapping liquidity-based logic — does requiring both to agree
   within N bars cut trade count but raise PF enough to survive cost,
   tested against a random pairing as a control?").
4. **The exact validation protocol** for testing it, honoring §5 — sample
   size needed, whether it needs synthetic pre-validation, what result
   would make you say "debug, don't retune."

You do not need to write code — a precise enough specification that this
team can implement and test it is the deliverable. If your honest
conclusion is that none of the 10 tested so far, and no combination of
them, is likely to clear a real bar, say that plainly and suggest what
would need to be fundamentally different (a different instrument, a
different timeframe philosophy, a different data source) rather than
proposing an 11th minor variant of the same idea.
