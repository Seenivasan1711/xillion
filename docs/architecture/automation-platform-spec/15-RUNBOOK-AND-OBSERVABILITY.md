---
doc_id: 15-RUNBOOK
title: Runbook and Observability
audience: ops
version: 1.0
---

# 15 — RUNBOOK & OBSERVABILITY

---

## 15.1 Alert severity

| Sev | Meaning | Channel | Ack |
|---|---|---|---|
| **P0** | Capital at risk NOW | Telegram + email + **phone** | 5 min → escalate |
| **P1** | Trading impaired | Telegram + email | 30 min |
| **P2** | Degraded, not blocking | Telegram | Next day |
| **P3** | Informational | Daily digest | None |

### P0 alerts — every one of these means stop and look
```
UNEXPECTED_POSITION          position at broker we don't know about
NAKED_SHORT_DETECTED         partial fill left an unhedged short
PROTECTIVE_ORDER_FAILED      position exists without a stop
RECONCILIATION_FAILED        our state ≠ broker state
SQUAREOFF_FAILED             position still open after close
OPS_CEILING_HIT              runaway loop — compliance risk
LOT_SIZE_MISMATCH            exchange changed contract spec
PROP_DD_BREACH               prop firm limit approaching/breached
WATCHDOG_TRIGGERED           main process died with position open
DATA_FEED_CRITICAL           30s+ no ticks with position open
CLOCK_SKEW                   >2s — time-based logic unsafe
```

---

## 15.2 Grafana dashboards

**1. Operations (default screen during market hours)**
System health · positions open · day P&L vs budget · circuit breaker status · kill switch state · OPS usage vs cap · data feed latency · broker latency · job success/failure

**2. Trading**
Equity curve · per-strategy P&L · win rate + **wr_margin** ⭐ · open positions with live P&L and current stop · trades today · signals blocked (by gate) · portfolio heat

**3. Execution quality**
Slippage trend (entry/exit) · fill rates · rejections by reason · spread at entry · cost as % of gross ⭐ · order latency p50/p95/p99

**4. Strategy health**
Per-strategy: decay status · rolling expectancy · MAE/MFE distributions · R-multiple histogram · live vs backtest divergence

**5. Lane B**
Session P&L · DD used vs internal vs firm limit ⭐ · spread by hour · MT5 connection status

---

## 15.3 Key metrics

```python
# Capital protection
position_pnl{strategy,lane}          Gauge
daily_pnl{lane}                      Gauge
portfolio_heat_pct                   Gauge
drawdown_pct{lane}                   Gauge
prop_dd_used_pct{type}               Gauge   # ⭐ Lane B
circuit_breaker_state{breaker}       Gauge
kill_switch_active                   Gauge

# Execution
orders_submitted_total{broker,status}    Counter
order_latency_seconds{broker}            Histogram
slippage_points{side,strategy}           Histogram
ops_used_current{broker}                 Gauge   # ⭐ vs cap of 7

# System
job_duration_seconds{job_id}             Histogram
job_failures_total{job_id}               Counter
data_feed_lag_seconds{source}            Gauge
broker_errors_total{broker,type}         Counter
heartbeat_age_seconds{service}           Gauge

# Business
strategy_win_rate{strategy,window}       Gauge
strategy_wr_margin{strategy}             Gauge   # ⭐ THE number
cost_pct_of_gross{lane}                  Gauge   # ⭐
signals_blocked_total{gate}              Counter
```

---

## 15.4 Incident runbooks

### 🚨 UNEXPECTED_POSITION
```
1. DO NOT auto-close. Kill switch (no flatten) is already active.
2. Query broker: what is it, when opened, which order id?
3. Check audit_log for that order id.
4. Diagnose:
     - Ours, state lost      → adopt into system, place protective orders
     - Duplicate submission  → close the extra, fix idempotency
     - Not ours              → contact broker IMMEDIATELY, possible compromise
5. Only after diagnosis: close or adopt.
6. Post-mortem before re-arming.
```

### 🚨 NAKED_SHORT_DETECTED
```
1. E05 rollback should have force-unwound automatically. Verify it did.
2. If still naked: CLOSE AT MARKET NOW. Cost is irrelevant.
3. Verify flat at broker.
4. Root-cause the leg failure before any multi-leg strategy trades again.
```

### 🚨 SQUAREOFF_FAILED
```
1. Check: broker API down, or leg illiquid?
2. Broker API down → USE THE BROKER'S MOBILE APP. Close manually.
   (This is why it must be installed and logged in — see 14.4 checklist.)
3. Illiquid leg → decide consciously: cross the spread, or carry overnight?
   For an ITM option near expiry, carrying has settlement/STT consequences.
4. Record the outcome; if carried, register it for the next session.
```

### 🚨 PROP_DD_BREACH (Lane B)
```
1. System should have flattened at the internal limit (80% of firm's).
2. Verify flat in MT5.
3. Check the firm's dashboard — does their number match ours?
   If they diverge materially, our DD tracking is wrong. Fix before resuming.
4. Halt Lane B for the day (daily) or indefinitely (max DD) pending review.
```

### ⚠️ RECONCILIATION_FAILED
```
1. Trading is auto-blocked for tomorrow. Leave it blocked.
2. Pull broker statement; compare line by line against orders/fills.
3. Categorise: missing order / extra order / price mismatch / qty mismatch.
4. Correct internal state to match broker (broker is truth).
5. Fix the root cause.
6. Manual sign-off in reconciliation_reports to re-enable trading.
```

### ⚠️ Broker API down mid-session
```
1. New orders already blocked by circuit breaker.
2. Open positions: are broker-side protective orders in place?
     YES → you are protected. Wait.
     NO (software stops only) → MANUAL MONITORING. Use the mobile app.
3. If down >5 min with positions open → close manually via app.
4. If failover configured → switch to secondary broker for exits only.
```

---

## 15.5 Daily operating procedure

```
BEFORE OPEN (08:00-09:15)
  □ Check overnight alerts
  □ Verify P01 passed (auth, health)
  □ Complete 2FA if prompted
  □ Read the pre-market brief (P10)
  □ Confirm armed strategies make sense to you
  □ Confirm kill switch is reachable from your phone

DURING SESSION
  □ Ops dashboard visible
  □ Respond to P0/P1 alerts
  □ Do not intervene in normal operation — that is the system's job
  □ Kill switch is always available if something feels wrong

AFTER CLOSE
  □ Verify X02 flattened everything
  □ Verify M01 reconciled CLEAN
  □ Read the post-market brief (M07)
  □ Note anything surprising for the weekly review

WEEKLY (Saturday)
  □ Review R01/R02/R03/R06 reports
  □ Act on any decay downgrades
  □ Approve or reject R03 parameter recommendations
  □ Verify a backup restores

MONTHLY
  □ R05 performance review
  □ Kill switch live-fire drill
  □ Hand-reconcile one month against broker statements
  □ Re-read the strategy KB's expectancy section — recheck wr_margin honestly
```

---

## 15.6 What "healthy" looks like

```
✅ Reconciliation CLEAN every day
✅ Zero P0 alerts in a normal week
✅ Slippage stable, not trending worse
✅ cost_pct_of_gross < 40%
✅ wr_margin > 0 for every active strategy
✅ Live win rate within 10pp of backtest
✅ Drawdown < backtested max drawdown
✅ Jobs completing within SLA
✅ Some signals blocked every week (gates are working, not decorative)
```

**That last one is easy to misread.** Blocked signals are not lost opportunities — they are the system doing its job. A week with zero blocks means the gates are too loose, not that conditions were perfect.

---

## 15.7 When to stop trading entirely

Stop, and do not restart until reviewed:

```
🛑 Reconciliation failed 2+ days in a row
🛑 Any unexplained position or P&L discrepancy
🛑 Live drawdown > 1.5× backtested max drawdown
🛑 wr_margin negative across ALL strategies for 30+ trades
🛑 A P0 incident whose root cause you have not found
🛑 Prop firm max DD breached
🛑 Any regulatory change you have not yet assessed
🛑 You find yourself wanting to override the system manually
```

**That last one is not a joke.** The urge to override is the signal that either the system is wrong (fix it) or you have stopped trusting it (find out why). Both are reasons to pause, not to intervene mid-trade.
