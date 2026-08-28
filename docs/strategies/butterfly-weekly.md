# Strategy: Butterfly Weekly

> One file per strategy. Written at Stage 1, updated at every pipeline stage.
> **These files are ingested into the RAG layer (CP8)** — the assistant answers
> "why did this strategy fail last October?" from here, so write for a reader
> with no memory of the conversation.

**Asset class:** options (Nifty / Sensex weekly)
**Broker:** Zerodha (paper/live) or Dhan
**Status:** Stage 1 build (done, 2026-08-29) — implementation at
[strategies/butterfly_weekly.py](../../strategies/butterfly_weekly.py)
**Created:** 2026-08-29 · **Last updated:** 2026-08-29

---

## 1. The rules (plain language)

Full mechanical source:
[knowledge-base/06-BAG-D-DEBIT-AND-EXOTIC.md §D1](knowledge-base/06-BAG-D-DEBIT-AND-EXOTIC.md).
This file states the rules exactly as coded; the KB file has the research
and win-rate citations.

- **Universe:** Nifty weekly or Sensex weekly, chosen via the `underlying`
  param — same as [credit-spread-weekly.md](credit-spread-weekly.md) and
  [iron-condor-weekly.md](iron-condor-weekly.md).
- **The third multi-leg strategy, and the first DEBIT one.** The credit
  spread and iron condor both collect premium; this one pays it. Same
  `xillion/core/multileg.py`/`multileg_execution.py`/`protective_orders.py`
  infrastructure, exercised for the first time against a structure that
  isn't a net credit.
- **Entry timing:** 09:45–10:30 IST (same window as the other two weekly
  strategies), and only when the resolved contract's DTE is at or below
  `entry_dte` (default **1**, not 4 — KB D1's own cycle stage is S4–S5, DTE
  1–0: "needs low time value to be cheap").
- **Structure:** 1:2:1 ratio, equidistant strikes, all one option type
  (`option_type` param, default CE) — buy 1 `wing_offset_strikes` below the
  middle, sell 2 at the middle strike (`middle_offset_strikes` from ATM,
  default 0 = pinned at current ATM), buy 1 `wing_offset_strikes` above.
- **Modeled as 4 orders at 3 distinct strikes, not 3 legs with a 2-lot
  middle order.** The middle strike's 2-lot short is split into two
  independent 1-lot `Leg`s (same symbol, each with its own
  `protects_leg_index` — one pointing at the lower wing, one at the upper).
  `xillion/core/multileg.py`'s naked-short protocol pairs each SHORT leg
  with exactly ONE protecting LONG; a butterfly's middle short is actually
  protected by BOTH wings at once, so splitting it lets the existing
  leg-failure protocol correctly isolate a single wing's failure (see the
  strategy file's own module docstring, and the leg-failure test below) —
  the same generalization the iron condor's independent call/put pairs
  already proved out, reused rather than re-invented. Costs one extra
  chargeable order versus a combined 2-lot sell; judged worth it for
  correctness, the same tradeoff CP11 makes everywhere else.
- **Market view / entry signal — an honest simplification, not real pin
  detection.** KB D1's view is "index pins at a SPECIFIC level at expiry",
  narrower than "no trend", and real pin plays are usually built around
  high-OI round numbers (KB's own "Best use" section) — this codebase
  doesn't warehouse open-interest data anywhere. This strategy reuses the
  iron condor's own range-bound/no-trend signal (15m VWAP+EMA20/EMA50) as
  the entry gate, and pins the middle strike at the current ATM rather than
  any model of where the market is actually likely to settle. Flagged
  here, not hidden — a genuine gap versus the KB's literal framing, the
  same way iron_condor_weekly.py flags its own inherited gaps.
- **Entry filters applied:**
  - Non-positive debit: skip if the middle credit (2× its premium) would
    exceed the wing cost — not a valid long butterfly.
  - `width <= debit`: skip if there's no possible profit at all.
  - Reward:risk floor: skip if `(width − debit) / debit` is below
    `min_reward_to_risk` (default 1.0). **No KB-cited filter number exists
    for D1** the way A1/A2 have explicit credit-adequacy percentages — this
    default is this codebase's own conservative choice, not sourced from a
    specific citation.
  - Range-bound gate, DTE gate (both described above).
- **Entry filters NOT applied (honest gaps, inherited from the other two
  weekly strategies, not repeated in full here):** VIX percentile filter,
  economic event veto, liquidity (bid-ask) filter beyond what a broker's
  Tick actually provides. See
  [credit-spread-weekly.md](credit-spread-weekly.md) for the full
  reasoning on each.
- **Sizing:** `max_loss_per_lot = debit × lot_size` (`max_loss_per_lot()`'s
  existing `BUTTERFLY` branch — the whole loss is the debit paid, already
  capped by construction, unlike a credit structure's `width − credit`),
  `lots = floor(risk_pct × capital / max_loss_per_lot)`. Lots < 1 → skip,
  never round up. **Matches KB D1's own worked example exactly**: 100-wide,
  25 debit, lot 65 → ₹1,625 max loss/lot (`test_max_loss_per_lot_...` in
  `test_multileg.py` already covered this from CP11; this strategy is the
  first thing that actually produces those numbers end-to-end).
- **Multi-leg entry/exit:** both wing (LONG) legs placed before either
  middle-strike (SHORT) leg on entry; both middle-strike legs closed before
  either wing on exit — same `order_entry_sequence`/`order_exit_sequence`
  discipline as the other two strategies.
- **Target:** butterfly value reaches `target_pct_of_max_profit` (default
  50%) of `width − debit` captured.
- **Stop-loss:** butterfly value falls back to having given up
  `stop_pct_of_debit` (default 75%) of the entry debit. **Neither
  percentage is KB-cited for D1** (unlike A1/A2's explicit 50%/2× rules) —
  this codebase's own reasonable defaults, stated honestly in
  `protective_orders.py`'s `butterfly_protective_levels()` docstring.
- **Time stop — deliberately NOT `ProtectiveOrderSpec.time_stop_date`.**
  That field is date-only, and `check_exit_trigger()` fires the instant
  `current_date >= time_stop_date` — using it here with
  `time_stop_date=expiry_date` would force-exit at the very FIRST tick of
  the day this structure exists to be held through (KB D1's whole edge is
  the EOD pin), defeating the strategy entirely. Instead, `on_tick` checks
  its own inline date+time-of-day gate: force-flatten at 15:10 IST on the
  expiry date, ahead of X02's own 15:15 IST broker-level square-off
  backstop (CP14) — this strategy's own careful shorts-first unwind
  (journal entries, GTT cancellation) runs first rather than leaving
  cleanup to X02's blunter enforcement.
- **Protective-order mechanics:** software stop only, monitored every tick
  via `butterfly_value()` (`2×short_middle_ltp − (long_lower_ltp +
  long_upper_ltp)` — the same Σ(short)−Σ(long) "cost to close" convention
  `spread_value()`/`condor_value()` already use, which is what let
  `check_exit_trigger()` be reused completely unmodified for a debit
  structure — see `protective_orders.py`'s own derivation).
  **No broker-native GTT backstop** — same deliberate scope cut as the
  iron condor, for the same reason (splitting a combined threshold across
  independent single-instrument GTTs needs allocation logic that doesn't
  exist yet). The software stop is the primary protection regardless.
- **What edge is this exploiting?** The opposite side of the same
  theta-decay trade the other two strategies make: instead of collecting
  premium and betting the market stays inside a range, this PAYS a small,
  fully-capped premium betting the market pins close to a specific level —
  KB's own framing: "arguably the safest instrument in this entire
  knowledge base" for max-loss certainty, at the cost of a narrower
  ~250-point (in the worked example) profit window and a lower win rate.

## 2. Backtest results (Stage 2)

**Not yet run.** Options-chain backtesting infrastructure exists
(`xillion/data/option_chain.py` + `BacktestEngine`'s
`option_chain_warehouse`) and this strategy's `on_bar`/`on_tick` shape
matches the other two weekly strategies' closely enough that it should
work unmodified — genuinely not yet run, not assumed to work.

| Period | Regime | Trades | Win % | Total P&L | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

- **Parameter sensitivity:** not yet tested
- **Manual spot-check:** not yet done
- **Data source + timeframe used:** n/a

## 3. Paper results (Stage 3)

**Window:** not yet started.

## 4. Live results (Stage 4)

Not started — Stage 2/3 gate this per `docs/process/asset-pipeline.md`.

## 5. Failure log

| Date | What happened | Failure mode | Change made |
|---|---|---|---|
| | | | |

Failure modes: `stopped_out` · `target_missed` · `late_entry` · `slippage` ·
`no_fill` · `gap` · `regime_change` · `data_gap` · `system_error`

## 6. Version history

| Version | Date | Change | Why |
|---|---|---|---|
| v1.0.0 | 2026-08-29 | Initial implementation — 1:2:1 long butterfly, third multi-leg strategy and first debit structure, split-middle-leg design for correct naked-exposure isolation, new `butterfly_value()`/`butterfly_protective_levels()` reusing `check_exit_trigger()` unmodified | Completing the planned multi-leg backlog — condor proved the engine generalizes past 2 legs; the butterfly proves it generalizes past credit structures too |
