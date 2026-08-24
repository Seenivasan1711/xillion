---
name: xillion-new-strategy
description: Start a new trading strategy through the xillion asset pipeline — create its doc from the template, encode the rules, and set up Stage 1. Use when the user brings strategy rules ("here's my strategy from the course", "add a new setup", "build this strategy") for any asset class (options, gold, forex, stocks, crypto).
---

# New strategy — Stage 1 of the pipeline

Every strategy goes through the same 6 stages defined in
`docs/process/asset-pipeline.md`. **No stage starts until the previous one's
exit criterion is met** — that rule is what keeps unvalidated strategies away
from real money. This skill covers Stage 1 (build) done right.

## Steps

### 1. Write the doc BEFORE the code
Copy `docs/strategies/_TEMPLATE.md` → `docs/strategies/<name>.md` and fill
**section 1 (the rules)** with the user:

- Entry condition, exit condition, target, stop-loss — *exact*, not vibes
- Position sizing, filters (time-of-day, volatility, regime)
- **"What edge is this exploiting?"** — if the user can't answer, flag it now;
  a strategy without a stated edge can't be debugged when it stops working

If any rule is ambiguous, ask — a misencoded rule wastes an entire
backtest-paper-live cycle before anyone notices.

### 2. Choose the implementation route
- **Condition-builder / params route**: if the rules are threshold/crossover
  logic on standard indicators, prefer configuring an existing generic
  strategy (`strategies/` has SMA cross, price-level cross, RSI threshold)
  or extending the params of one — no new file
- **Plugin route**: genuinely custom logic (multi-leg options, custom
  indicators) → copy `strategies/_template.py`, follow its contract rules
  (no broker imports, everything through `ctx`)

### 3. Encoding rules that have burned us before
- Use `bar.timeframe`, **never** `self.timeframe`, in `ctx.history()` calls —
  the hardcoded-timeframe bug silently produced 0-trade backtests
- Derivatives need their contract multiplier resolved
  (`xillion/core/contracts.py`); NIFTY lot = 65
- Both entry AND exit must emit signals — entry-only strategies can't be
  paper-validated properly
- Instruments come from the instance config, not hardcoded in the class

### 4. Verify Stage 1's exit criterion
- Strategy auto-discovered (check Strategies page or `strategy_class` table)
- Instance creatable in the UI; params form renders correctly
- A dry run / small backtest executes without errors — use `/xillion-verify`
  standards: run it, don't assume it

### 5. Close out
- Update `docs/status/task-tracker.md`: set the asset's S1 cell 🟡 or ✅
- The strategy doc from step 1 is committed alongside the code
- State clearly what Stage 2 needs next (usually: warehouse data coverage for
  the target period + a hand-verifiable backtest sample)

## Hard rules

- Never skip ahead: no paper before a passed backtest, no live before a
  passed paper soak. If the user pushes to skip, point at the pipeline doc's
  reasoning and get explicit confirmation
- Failure log discipline starts at Stage 1 — every surprising behaviour goes
  in the strategy doc's section 5 immediately, not "later"
