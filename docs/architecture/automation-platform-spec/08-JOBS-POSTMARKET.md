---
doc_id: 08-JOBS-POSTMARKET
title: Exit and Post-Market Job Specifications (X and M series)
audience: backend, data
version: 1.0
---

# 08 — EXIT & POST-MARKET JOBS

---

# X-SERIES — EXIT

## X01 — Exit Execution 🔴 P0

**Trigger:** event — any exit signal (stop hit, target hit, time stop, event flatten, kill switch, strategy exit rule).

```
1. Determine exit reason (enum — never free text; this drives M-series analysis)
       STOP_HIT | TARGET_HIT | TRAIL_HIT | TIME_STOP | EVENT_FLATTEN
       | STRATEGY_EXIT | SQUARE_OFF | KILL_SWITCH | MANUAL | RISK_BREACH

2. Determine urgency:
       KILL_SWITCH / RISK_BREACH / STOP_HIT  → MARKET orders, speed over price
       TARGET_HIT / STRATEGY_EXIT            → LIMIT at mid, allow 3 improvement attempts
       SQUARE_OFF                            → LIMIT first, escalate to MARKET at T-2min

3. LEG ORDERING ON EXIT — the inverse of entry (E04):
       Close SHORT legs FIRST, then LONG legs.
       Rationale: if exit fails midway, you are left holding LONGS (bounded)
       rather than naked SHORTS (unbounded). Mirror image of the entry rule.

4. Cancel any resting protective orders BEFORE placing exits
       (else you may double-exit and open a reverse position — a real, common bug)

5. Execute with the same throttle and idempotency discipline as E05
6. On partial exit fill → retry remainder, escalate to MARKET after 2 attempts
```

**Acceptance:** protective order cancellation is verified before exit orders are placed; a test proves no reverse position can be opened by a race between a resting stop and a manual exit.

---

## X02 — Square-off Enforcer 🔴 P0

**Trigger:** Lane A 15:15 IST · Lane B2 (MCX) 23:15 IST · Lane B1 configurable.

**The single most important scheduled job in the system. It must never fail.**

```
15:15  Warning pass  — alert any still-open positions
15:18  Soft exit     — LIMIT orders at mid
15:22  Aggressive    — LIMIT at bid/ask (cross the spread)
15:25  MARKET        — take whatever price exists
15:28  VERIFY        — query broker; anything still open → 🚨 P0 ALERT + phone escalation
15:30  Market closes

Special cases:
  - Expiry day (S5): run the whole ladder 45 minutes earlier (starts 14:00,
    per the flat-by-2pm rule in KB 05 §C6)
  - If a leg is illiquid and unfillable → alert immediately; a human must decide
    (letting an ITM option go to expiry has physical settlement / STT consequences)
  - IF broker API is down at square-off → 🚨 PHONE ESCALATION. This is the
    scenario that justifies having the broker's mobile app installed and logged in.
```

**Design rule:** this job is independent of every other job. It does not check whether strategies are armed, whether the risk engine is happy, or whether the monitor loop is running. **It queries the broker for open positions and closes them.** It must work when everything else is broken.

**Acceptance:** with the entire application stack stopped except the scheduler and broker adapter, X02 still flattens all positions.

---

## X03 — Exit Fill Verification 🔴 P0

**Trigger:** +2s after X01/X02.

```
1. Query broker positions — confirm flat (or expected remainder)
2. IF position still open → retry exit (max 3), then escalate
3. Compute realised P&L including ALL exit costs
4. Record: exit price, slippage vs intended, exit reason, duration
5. Close the position record; write to trade journal (M02 consumes this)
6. Release the position's risk allocation back to the daily budget
```

---

# M-SERIES — POST-MARKET

## M01 — Broker Reconciliation 🔴 P0

**Trigger:** Lane A 15:45 · Lane B 23:45.

**The most important post-market job. Divergence between our state and the broker's is the root cause of most serious incidents.**

```
1. Fetch from broker: all orders today, all trades/fills, positions, ledger/funds
2. Fetch our internal records for the same period
3. Three-way reconcile:

   ORDERS:   ours vs broker's order book
       broker order we have no record of  → 🚨 P0 (did something else place it?)
       our order absent at broker         → investigate submit failure
       status mismatch                    → adopt broker's, log discrepancy

   FILLS:    every fill matched on qty AND price
       price mismatch  → record as slippage, feed M04
       qty mismatch    → 🚨 P0

   POSITIONS: must be FLAT at EOD for intraday strategies
       any open position → 🚨 P0, immediate alert

   FUNDS:    broker's realised P&L vs our computed P&L
       tolerance: ₹10 (rounding). Beyond that → 🚨 P0

4. Write reconciliation_report with status CLEAN | DISCREPANCY | FAILED
5. IF status != CLEAN:
       → block tomorrow's trading (P01 checks this)
       → require manual sign-off to resume
```

**That last rule is deliberately harsh. An unreconciled day means you do not know your true position or P&L. Trading on top of that compounds an unknown error.**

---

## M02 — Trade Journal Writer 🟡 P1

**Trigger:** 15:50 (Lane A) / 23:50 (Lane B)

Writes the record that everything analytical downstream depends on. **Automating the journal is the highest-leverage thing here** — manual journalling is the discipline that fails first.

```
Per closed trade, capture:

  IDENTITY      trade_id, strategy, lane, instrument, structure_type, risk_class
  TIMING        signal_time, entry_time, exit_time, duration, cycle_stage, session_window
  ENTRY         intended price, actual fill, slippage, legs, lots, entry cost
  EXIT          exit reason (enum), intended vs actual, slippage, exit cost
  SIZING        risk allocated, max loss planned, max loss actual, size multipliers applied
  P&L           gross, all costs itemised, net, R-multiple, % of max profit/loss
  EXCURSION     MAE, MFE, time-to-MAE, time-to-MFE       ← from T01
  CONTEXT       VIX, IV rank, VRP state, regime, trend state, ADX, gap class,
                expected move, DTE, events active
  STOPS         initial stop, every stop movement (from stop_history), final stop
  DECISIONS     which gates passed, arming reasons, adjustments made
```

**Why the context block matters:** six months from now, `R02`/`R03` will ask "does this strategy work in low-VIX regimes?" That question is only answerable if regime was recorded at trade time. Capturing it costs nothing now and is impossible to reconstruct later.

---

## M03 — P&L & Cost Attribution 🟡 P1

**Trigger:** 15:55

```
1. Aggregate day: gross P&L, total costs, net P&L, per strategy / lane / structure
2. ITEMISE COSTS — this is the headline number of the whole report:
       STT (0.15% sell-side premium), brokerage, exchange transaction charges,
       GST (18% on brokerage+txn), stamp duty, SEBI fees
3. Compute:
       cost_as_pct_of_gross     ← 🚨 the number to watch
       cost_per_trade, cost_per_lot, cost_per_leg
4. IF cost_as_pct_of_gross > 40% → ALERT: strategy economics are marginal
5. Update running totals: WTD, MTD, YTD; equity curve point
```

**Context (KB `07` Reality Anchor):** SEBI found 71% of aggregate retail F&O losses were transaction costs, not bad directional calls. Making cost a first-class, daily-visible metric rather than a footnote is one of the highest-value design decisions in this system.

---

## M04 — Slippage & Execution Quality 🟢 P2

**Trigger:** 16:00

```
Per trade and rolling:
    entry_slippage = actual_fill - intended_price   (signed, in your favour = negative)
    exit_slippage  = same for exits
    Break down by: order type, time of day, structure, leg count, spread at entry,
                   liquidity state (T08 flags)

Alerts:
    avg slippage > cfg.max_avg_slippage           → execution is degrading
    slippage trending worse week-over-week        → investigate (broker? liquidity? size?)
    any single fill > 3x avg slippage             → flag for review

Feed back into:
    E04 (widen limit prices where slippage is chronic)
    The BACKTEST slippage assumption — this is REAL DATA replacing a guess.
```

**This job closes the loop between backtest assumptions and reality.** After ~50 live trades you can replace the backtest's assumed slippage with measured slippage — at which point backtest results become meaningfully more trustworthy.

---

## M05 — Strategy Metrics Update 🟡 P1

**Trigger:** 16:05

```
Per strategy, update rolling windows (20, 50, 100 trades and all-time):

    win_rate
    avg_win, avg_loss, win_loss_ratio
    expectancy      = (win_rate * avg_win) - (loss_rate * avg_loss)
    profit_factor   = gross_profit / gross_loss
    BREAK_EVEN_WIN_RATE_REQUIRED = stop / (stop + target)    ← from config
    wr_margin       = actual_win_rate - break_even_win_rate  ← 🚨 THE KEY METRIC
    max_drawdown, current_drawdown, longest_losing_streak
    sharpe (daily returns), avg R-multiple
    avg MAE / MFE
```

**`wr_margin` is the single most important number in the system.** From KB `07`: a strategy managed at 50% target / 200% stop needs an **80% win rate just to break even**. A 72% win rate with that management is *losing money* while looking successful. Surfacing `wr_margin` — actual minus required — turns a comforting statistic into an honest one.

```
IF wr_margin < 0 for 30+ consecutive trades → flag for R02 decay review
```

---

## M06 — Regime Log Writer 🟢 P2

**Trigger:** 16:10

Records the day's market conditions independent of whether you traded, building a regime history you can later join against trade outcomes.

```
Daily row: VIX (O/H/L/C), VIX percentile, IV rank, realised vol, IV-RV spread,
           VRP estimate, trend state, ADX, day range, gap, volume vs avg,
           expected move vs realised move, cycle stage, events
```

**Value:** after a year you can answer "what kind of day does this strategy actually make money on?" — the question that drives `P08` arming rules. Without this table, that question stays a hunch.

---

## M07 — Post-Market Brief 🟢 P2

**Trigger:** 16:15 → Telegram

```
📉 POST-MARKET — Tue 26 Aug 2026

P&L         Gross +₹4,820 | Costs −₹1,340 | NET +₹3,480
            Costs = 27.8% of gross ✅ (threshold 40%)

TRADES      3 taken, 2 wins, 1 loss
  ✅ butterfly_expiry    +₹2,100  (+1.8R)  exit TARGET_HIT     14:02
  ✅ credit_spread_0dte  +₹1,890  (+1.1R)  exit TRAIL_HIT      13:40
  ❌ credit_spread_0dte    −₹510  (−0.4R)  exit TIME_STOP      12:15

SIGNALS BLOCKED  4
  2x spread_acceptable  (chain illiquid 11:40-12:10)
  1x cost_ratio_ok      (target too small vs cost)
  1x max_trades_today_ok

STRATEGY HEALTH
  butterfly_expiry     WR 68% (n=34) | req 25% | margin +43% ✅
  credit_spread_0dte   WR 71% (n=52) | req 80% | margin −9%  ⚠️ REVIEW

EXECUTION   Avg entry slip 0.8 pts | exit slip 1.4 pts | no anomalies
RECON       ✅ CLEAN — flat, funds match
LANE B      London session +$142 | DD used 1.2% of 4.0%
```

**Note the `credit_spread_0dte` line.** A 71% win rate looks good and is quietly losing money against an 80% requirement. That single line is why this report exists.

---

## M08 — Data Archival & Backup 🟡 P1

**Trigger:** 16:30

```
1. Flush tick buffers → Parquet, partitioned by date/symbol
2. Compact DuckDB; run integrity check
3. pg_dump Postgres → compressed
4. Encrypt and push to off-box storage (rclone → any S3-compatible or personal NAS)
5. Verify backup integrity (restore a random table to a temp DB and compare row counts)
6. Prune: raw ticks > 1yr → downsample to 1-min; keep option chains forever
7. Report DB sizes, growth rate, disk headroom
```

**Backup verification is the point.** An unverified backup is a hypothesis. Restore-test weekly, automatically. Storage math from `02` §2.6: the entire option chain history runs under 2 GB/year — there is no reason to ever delete it.
