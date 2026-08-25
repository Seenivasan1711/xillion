---
doc_id: 10-RISK-ENGINE
title: Risk Engine and Kill Switches
audience: backend
version: 1.0
criticality: HIGHEST — no order reaches a broker without passing this
---

# 10 — RISK ENGINE

**The risk engine is not a job. It is a mandatory gate in the order path.** Every order — from every strategy, in every lane, in live and paper mode — passes through it. There is no bypass flag, no admin override, no "just this once" path. If the risk engine is unreachable, orders are blocked.

---

## 10.1 Layered controls

Modelled on institutional pre-trade risk architecture, adapted for a single-trader system.

```
Layer 1  STRATEGY      strategy's own logic (may decline to signal)
Layer 2  PRE-ENTRY GATE (E02)   ~24 checks, fails closed
Layer 3  SIZING (E03)           risk-based, central, non-negotiable
Layer 4  RISK ENGINE  ◄── THIS DOCUMENT — final gate before the wire
Layer 5  BROKER                 broker's own margin/limit checks
Layer 6  EXCHANGE               circuit limits, freeze qty
```

Layers 4 and below cannot be influenced by strategy code.

---

## 10.2 Order-level checks (synchronous, on every order)

```python
def validate_order(order, ctx) -> RiskDecision:
    checks = [
        # --- SANITY / FAT FINGER ---
        ("qty_positive",        order.qty > 0),
        ("qty_lot_multiple",    order.qty % ctx.lot_size == 0),
        ("qty_within_freeze",   order.qty <= ctx.freeze_qty),
        ("qty_sane",            order.qty <= ctx.max_qty_per_order),
        ("price_tick_multiple", order.price % ctx.tick_size == 0),
        ("price_collar",        0.5*ctx.ltp <= order.price <= 1.5*ctx.ltp),   # fat finger
        ("price_within_circuit",ctx.lower_circuit <= order.price <= ctx.upper_circuit),
        ("notional_sane",       order.notional <= ctx.max_notional_per_order),

        # --- STATE ---
        ("kill_switch_clear",   not ctx.kill_switch_active),
        ("trading_enabled",     ctx.trading_enabled),
        ("market_open",         ctx.market_is_open),
        ("symbol_tradeable",    ctx.symbol_tradeable_today),

        # --- CAPITAL ---
        ("margin_sufficient",   ctx.margin_available >= ctx.margin_required * 1.2),
        ("within_daily_risk",   ctx.risk_used + order.risk <= ctx.risk_budget),
        ("within_exposure",     ctx.exposure + order.exposure <= ctx.max_exposure),

        # --- BEHAVIOURAL / RUNAWAY ---
        ("not_duplicate",       not seen_recently(order.idempotency_key)),
        ("ops_budget_ok",       ops_bucket.has_token()),
        ("not_self_trade",      not would_cross_own_order(order)),
        ("order_count_sane",    ctx.orders_today < ctx.max_orders_per_day),
        ("modify_rate_ok",      ctx.modifies_this_position_60s < 12),

        # --- LANE B PROP FIRM (hard account-ending limits) ---
        ("prop_daily_dd_ok",    ctx.lane != "B" or ctx.daily_dd_used < ctx.internal_daily_dd),
        ("prop_max_dd_ok",      ctx.lane != "B" or ctx.max_dd_used < ctx.internal_max_dd),
    ]
    failed = [n for n, ok in checks if not ok]
    audit.write_risk_decision(order, checks, failed)
    if failed:
        return RiskDecision(approved=False, reasons=failed)
    ops_bucket.consume()
    return RiskDecision(approved=True)
```

**`price_collar` is the fat-finger guard.** A bug that computes a price 10× off gets stopped here rather than at the exchange. This check has saved more retail accounts than any other single control.

---

## 10.3 The OPS token bucket — SEBI compliance

```python
class OPSTokenBucket:
    """
    Enforces < 10 orders/sec (SEBI algo registration threshold, 01 §1.1).
    We cap at 7 with a hard ceiling of 9. Per broker, per second.
    """
    def __init__(self, rate=7, burst=9):
        self.rate, self.burst = rate, burst

    def has_token(self) -> bool:
        # Redis sliding window per broker per second
        count = redis.zcount(f"ops:{broker}", now-1000, now)
        return count < self.rate

    def consume(self):
        count = redis.zcount(f"ops:{broker}", now-1000, now)
        if count >= self.burst:
            alert.p0(f"OPS CEILING HIT — compliance risk")
            kill_switch.activate(flatten=False)      # runaway loop protection
            raise OPSLimitExceeded()
        redis.zadd(f"ops:{broker}", {uuid(): now})
```

**Hitting the burst ceiling means a runaway loop.** The correct response is to stop trading, not to throttle and continue — a loop that generates 9 orders/second will generate 9,000.

---

## 10.4 Circuit breakers (evaluated by T01 every second)

```yaml
circuit_breakers:

  # ---- DAILY LOSS ----
  daily_loss_soft:
    threshold: 60%   # of daily risk budget
    action: reduce_size_50pct
  daily_loss_hard:
    threshold: 100%
    action: block_new_entries         # existing positions keep their stops
  daily_loss_critical:
    threshold: 150%
    action: FLATTEN_ALL + kill_switch

  # ---- CONSECUTIVE LOSSES ----
  consecutive_losses:
    threshold: 3                       # research-paper rule (KB 05 §C5)
    action: block_new_entries_rest_of_day

  # ---- DRAWDOWN ----
  account_drawdown:
    threshold: 10%
    action: reduce_size_50pct_until_new_high     # anti-martingale, R04

  # ---- LANE B PROP FIRM (account-ending) ----
  prop_daily_dd:
    warn: 50%      of internal limit (4.0%)  -> alert
    reduce: 70%                              -> size 50%
    block: 90%                               -> block new entries
    flatten: 100%                            -> FLATTEN + halt for the day
  prop_max_dd:
    warn: 50%      of internal limit (8.0%)
    block: 80%
    flatten: 95%                             -> FLATTEN + halt indefinitely, manual review

  # ---- SYSTEM ----
  data_staleness:
    threshold: 5s no ticks
    action: block_new_entries
  data_staleness_critical:
    threshold: 30s
    action: FLATTEN_ALL     # cannot manage what you cannot see
  broker_errors:
    threshold: 5 errors in 60s
    action: block_new_entries + alert
  unexpected_position:
    threshold: any
    action: kill_switch + P0 alert       # never auto-close an unknown position
```

**Note `data_staleness_critical` flattens.** Holding a leveraged position with no price feed is worse than exiting at a mediocre price. This is the ordering that separates capital preservation from optimisation.

---

## 10.5 Kill switch (K01)

**Must work when everything else is broken.**

### Activation paths
```
1. Telegram command  /kill                  ← primary human path, works from a phone
2. Automatic         circuit breaker trip
3. API endpoint      POST /kill  (authenticated)
4. File sentinel     touch /var/run/trading/KILL   ← works even if the app is wedged
5. Scheduled         X02 escalation failure
```

### Execution sequence
```
1. SET Redis kill_switch:active = true       (all order paths check this first)
2. BLOCK all new orders immediately
3. CANCEL all open/resting orders across all brokers
4. IF flatten_on_kill (default TRUE for Lane B, CONFIGURABLE for Lane A):
       close all positions at MARKET
   ELSE:
       leave positions but VERIFY protective orders are in place at the broker
5. VERIFY: query brokers, confirm the intended end state
6. ALERT: Telegram + email + phone escalation if unacknowledged in 5 min
7. WRITE kill_switch_event with full state snapshot
8. REQUIRE MANUAL RE-ARM — the system does not resume on its own, ever
```

**Why manual re-arm:** a kill switch fired because something was wrong. Automatic resumption re-enters the same conditions that caused the trip.

### The dead-man's switch
```
K03 (heartbeat) writes a timestamp every 30s.
A SEPARATE, MINIMAL watchdog process — not the main app — checks it.
IF no heartbeat for 120s:
    → assume the main system is dead
    → the watchdog itself cancels orders and flattens via a direct broker call
    → alert with phone escalation
```

**The watchdog must be a separate process with its own broker credentials and minimal dependencies.** If it imports the main application, it dies with it and provides nothing. This is the last line of defence for software-managed stops (`06` §E07).

---

## 10.6 Position-level limits

```yaml
limits:
  risk_per_trade_pct: 1.0            # of capital
  max_concurrent_positions: 3
  max_positions_per_strategy: 1
  max_trades_per_day: 5              # SEBI data: profitable traders traded LESS
  max_lots_per_trade: 5
  max_portfolio_heat_pct: 6.0        # sum of open risk / capital
  max_portfolio_delta: 200           # Nifty-equivalent points
  max_notional_per_order: 2000000
  max_orders_per_day: 50
```

**`max_trades_per_day: 5` is a deliberate choice, not a placeholder.** SEBI's study found profitable traders placed *fewer* trades, and the cost data shows why: at 71% of aggregate retail losses being transaction costs, every additional trade is a guaranteed cost against an uncertain edge.

---

## 10.7 What the risk engine deliberately does NOT do

- ❌ Does not predict market direction
- ❌ Does not decide whether a strategy is good
- ❌ Does not override strategy exits (except flatten paths)
- ❌ Does not auto-close unknown positions — it halts and asks a human
- ❌ Does not resume after a kill — ever

**Its only job is to ensure that when a strategy is wrong, the loss is the size you chose in advance.**

---

## 10.8 Testing requirements

The risk engine has the strictest test requirements in the system.

```
Unit          every check has a test proving it blocks when it alone fails
Property      hypothesis: no input produces an approved order exceeding limits
Integration   full order path with a mock broker, verifying gate enforcement
Chaos         kill Redis / Postgres / broker mid-order → verify fail-closed
Failover      kill the main process with a position open → verify watchdog flattens
Compliance    generate 20 orders in 1s → verify OPS ceiling halts the system
Drill         monthly live-fire kill switch test in paper mode
```

**Acceptance for go-live: 100% branch coverage on the risk engine module.** Not 80%. Every branch. This is the module where an untested path costs real money.

---

# K-SERIES — CROSS-CUTTING JOB SPECS

These run independently of the trading lifecycle and can interrupt any job.

## K01 — Kill Switch Controller 🔴 P0

**Trigger:** always-on listener (Telegram poller + file watcher + HTTP endpoint + circuit-breaker subscriber).

Full behaviour specified in §10.5 above. Implementation requirements:
```
□ Runs as its own process/task, independent of the job runner
□ Subscribes to CircuitBreakerTripped events
□ Polls the file sentinel every 1s
□ Telegram command handler: /kill, /kill_flatten, /status, /rearm
□ Writes kill_switch_events with a full state snapshot
□ /rearm requires an explicit confirmation phrase, never a single tap
```

## K02 — Alert Router 🔴 P0

**Trigger:** always-on; consumes an internal alert queue.

```
1. Receive alert {severity, code, message, context}
2. Deduplicate: suppress identical code within cfg.dedupe_window (default 300s)
   EXCEPT P0 — never suppress P0
3. Route by severity (12 §alerts.escalation)
4. Track acknowledgement; unacked P0 after 5 min → escalate to phone
5. Persist every alert; expose alert rate as a metric
6. IF the alert channel itself fails → write to a local file AND
   attempt the secondary channel. An alert system that fails silently is worse
   than none, because it creates false confidence.
```

## K03 — Heartbeat & Watchdog 🔴 P0

**Trigger:** every 30s (heartbeat writer) / every 30s (external watchdog).

```
HEARTBEAT (inside main app)
   write redis heartbeat:{service} = now, every 30s, per service

WATCHDOG (SEPARATE PROCESS — minimal deps, own broker credentials)
   every 30s:
       for each expected service:
           age = now - heartbeat:{service}
           IF age > 60s  → P1 alert
           IF age > 120s → assume dead:
                 - query broker directly for open positions
                 - IF positions exist: cancel orders + FLATTEN
                 - P0 alert with phone escalation
```

> **The watchdog must not import the main application.** If it shares dependencies, it dies with them and protects nothing. It needs only: a broker client, a Redis client, and an alert client. This is the last line of defence for software-managed stops (`06` §E07).

## K04 — Audit Log Writer 🔴 P0

**Trigger:** event-driven, synchronous on the critical path for order events.

```
Captures (append-only, 5-year retention per SEBI, 01 §1.1):
    every order submitted / modified / cancelled
    every risk decision (approved and rejected)
    every gate evaluation
    every kill switch event
    every config change
    every manual intervention
    every stop movement

Requirements:
    □ Append-only; no UPDATE or DELETE permitted on the table (enforce via grants)
    □ Order-event writes are synchronous — an unlogged order must not reach the broker
    □ Non-critical events may be async-buffered
    □ Include actor (job id / 'human' / 'watchdog'), timestamp, full payload
```

## K05 — Config Validator 🟡 P1

**Trigger:** on config change + 08:00 daily.

```
1. Load and validate against the Pydantic schema
2. Cross-field checks:
       risk_per_trade_pct * max_concurrent_positions <= daily_risk_budget_pct
       internal prop DD limits < firm's published limits
       max_orders_per_second < compliance threshold
       every strategy's instruments exist in the instruments block
       every strategy's broker is enabled
3. Sanity bounds: risk_per_trade_pct <= 5, max_trades_per_day <= 50
4. IF mode == live: verify live_confirmed AND the CLI flag
5. On failure → REFUSE TO START (never fall back to defaults)
6. Diff against the previous version; log every change to audit_log
```
