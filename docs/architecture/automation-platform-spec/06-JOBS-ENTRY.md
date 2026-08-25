---
doc_id: 06-JOBS-ENTRY
title: Open and Entry Job Specifications (O and E series)
audience: backend
version: 1.0
criticality: E02-E07 are the capital-protecting core
---

# 06 — OPEN & ENTRY JOBS

---

# O-SERIES — MARKET OPEN

## O01 — Opening Range Capture 🟡 P1

**Trigger:** streaming 09:15–09:45 (Lane A) / session open (Lane B)

**Logic:**
```
1. From 09:15, track running high/low of the underlying
2. Snapshot OR at 09:20, 09:30, 09:45 (multiple definitions — strategies choose)
       OR_15 = 09:15-09:30    OR_30 = 09:15-09:45
3. Compute or_range_pts, or_range_pct, or_volume vs 20-day avg
4. Apply the width filter — evidence-backed (KB 05 §C1):
       IF or_range < config.min_or_points (default 40 for Nifty):
              flag OR_TOO_NARROW → ORB strategies do not arm
       The 8-year study: wide ranges (~144pts) returned +30.3% vs narrow (~35pts) +18.6%
5. Persist to opening_range
```

**Outputs:** `or_high`, `or_low`, `or_range_pts`, `or_width_class` (NARROW/NORMAL/WIDE), `or_valid`.

---

## O02 — Open Regime Confirmation 🟡 P1

**Trigger:** 09:45

**Why:** the pre-market regime guess (P05) was made without price action. Now confirm or revise it.

**Logic:**
```
1. Compute realised move so far vs expected move from P06
       realised_pct_of_expected = |spot - open| / expected_move
2. Trend classification:
       ADX(14) on 15-min:  >25 TRENDING | <20 RANGE | else TRANSITIONAL
       Price vs VWAP; 20EMA vs 50EMA
3. Volatility confirmation: opening 30-min realised vol vs implied
4. IF confirmed regime != P05 regime:
       → RE-RUN P08 arming with the new regime
       → log the revision (this is a valuable dataset: how often is the 08:45 guess wrong?)
5. Set session_regime, consumed by E02
```

**Outputs:** `session_regime`, `trend_state`, `adx`, `regime_revised` flag.

---

## O03 — Gap Classification & Veto 🟡 P1

**Trigger:** 09:16

**Why:** gap days break time-based strategies. The 9:20 straddle's worst losses are gap days (KB `04` §B1) — the strategy enters blind into a regime it did not anticipate.

**Logic:**
```
gap_pct = (open - prev_close) / prev_close * 100

Classification (Lane A, Nifty):
    |gap| < 0.25%   → NORMAL     no action
    0.25 - 0.75%    → MODERATE   size x0.75
    0.75 - 1.5%     → LARGE      size x0.5, block time-based entries
    > 1.5%          → EXTREME    BLOCK ALL ENTRIES for 30 min, re-evaluate at 09:45

ALSO:
    IF gap opens beyond prior day's range → regime change flag
    IF gap direction contradicts armed strategy's bias → unarm that strategy
```

**Outputs:** `gap_pct`, `gap_class`, `gap_size_multiplier`, `entries_blocked_until`.

---

# E-SERIES — ENTRY PIPELINE

> **The E-pipeline is strictly sequential. Each stage may only run if the previous passed. No stage may be skipped, including in backtest and paper mode — the paper path must exercise identical code.**

---

## E01 — Signal Generation 🟡 P1

**Trigger:** event — bar close on the strategy's timeframe.

**Logic:**
```
FOR each ARMED strategy (from P08):
    IF now NOT IN strategy.allowed_time_windows:  continue
    signal = strategy.evaluate(market_state, watchlist)
    IF signal:
        signal.id = uuid
        signal.strategy = strategy.name
        signal.direction = LONG | SHORT | NEUTRAL
        signal.structure = [legs...]        # 1 leg for buying, 2 for spread, 4 for condor
        signal.confidence = float
        signal.reason = str                 # MANDATORY — human-readable
        EMIT signal → E02
```

**Strategy plugin contract:**
```python
class Strategy(Protocol):
    name: str
    risk_class: Literal["DEFINED", "UNDEFINED"]
    allowed_regimes: list[str]
    allowed_stages: list[str]          # S1..S5, Lane A
    allowed_time_windows: list[TimeWindow]
    timeframe: str
    min_capital_required: Decimal

    def evaluate(self, state: MarketState, watchlist: Watchlist) -> Signal | None: ...
    def exit_rules(self, position: Position, state: MarketState) -> ExitDecision | None: ...
    def protective_orders(self, fill: Fill) -> list[Order]: ...
```

**Design rule:** strategies are **pure functions of state**. They read; they never place orders, never touch the broker, never mutate anything. This makes them trivially backtestable — the same `evaluate()` runs in the backtest engine and in production.

---

## E02 — Pre-Entry Gate 🔴 P0 ⭐ THE MOST IMPORTANT JOB IN THE SYSTEM

**Trigger:** event — signal received.

**This is the automated pre-entry checklist — the job that replaces the disciplined trader's "should I actually take this?" pause. Every check fails closed.**

```python
GATES = [
    # ---- KILL SWITCH & SYSTEM ----
    ("kill_switch_clear",      lambda: not redis.get("kill_switch:active")),
    ("trading_enabled",        lambda: state.trading_enabled),
    ("system_healthy",         lambda: health.all_green()),
    ("clock_skew_ok",          lambda: abs(clock_skew()) < 2.0),
    ("data_feed_live",         lambda: (now - last_tick).seconds < 5),

    # ---- STRATEGY STATE ----
    ("strategy_armed",         lambda: arming[sig.strategy].armed),
    ("in_time_window",         lambda: now in strat.allowed_time_windows),
    ("not_in_blackout",        lambda: not event_blackout_active()),      # P03
    ("entries_not_blocked",    lambda: now > state.entries_blocked_until), # O03

    # ---- RISK LIMITS ----
    ("daily_loss_ok",          lambda: day_pnl > -risk_budget_today),
    ("consec_losses_ok",       lambda: consecutive_losses < cfg.max_consec_losses),  # default 3
    ("max_positions_ok",       lambda: open_positions < cfg.max_concurrent),
    ("max_trades_today_ok",    lambda: trades_today < cfg.max_trades_per_day),
    ("dd_headroom_ok",         lambda: dd_headroom_pct > 10),             # Lane B critical
    ("exposure_ok",            lambda: net_exposure + new < cfg.max_exposure),
    ("no_duplicate_position",  lambda: not has_position(sig.structure)),

    # ---- MARKET CONDITIONS ----
    ("spread_acceptable",      lambda: all(l.spread_pct < 0.1 for l in sig.legs)),
    ("liquidity_ok",           lambda: all(l.oi > cfg.min_oi for l in sig.legs)),
    ("not_circuit_limit",      lambda: not near_circuit(sig.legs)),
    ("underlying_moving",      lambda: atr_pct > cfg.min_atr_pct),   # dead market filter

    # ---- ECONOMICS (KB 01 §1.4) ----
    ("cost_ratio_ok",          lambda: expected_gross >= 3 * round_trip_cost),
    ("credit_adequate",        lambda: not sig.is_credit or
                                        sig.credit >= 0.15 * sig.width),

    # ---- LANE A SPECIFIC ----
    ("not_naked_on_expiry",    lambda: not (stage=="S5" and strat.risk_class=="UNDEFINED")),
    ("expiry_time_ok",         lambda: not (stage=="S5" and now.time() > time(14,0))),
]

def run_gate(signal) -> GateResult:
    failed = []
    for name, check in GATES:
        try:
            if not check():
                failed.append(name)
        except Exception as e:
            failed.append(f"{name}:ERROR:{e}")   # exception == failure. fail closed.
    audit.write(signal.id, GATES, failed)         # EVERY evaluation logged
    return GateResult(passed=not failed, failed=failed)
```

**Outputs:** pass → `E03`. Fail → log with the exact failing gate names, emit a low-priority notification, discard the signal.

**Acceptance:** for each of the ~24 gates there is a unit test proving a signal is blocked when that gate alone fails.

> **This job's audit log answers the single most valuable operational question: "why didn't it trade?" Never let a signal die silently.**

---

## E03 — Position Sizing Calculator 🔴 P0

**Trigger:** event — gate passed.

**Sizing is not a strategy decision. It is a risk decision, computed centrally, identically, for every strategy.**

```python
def calculate_size(signal, state, config) -> SizeDecision:
    # 1. Rupee risk allowance
    base_risk = state.capital * config.risk_per_trade_pct     # default 1%

    # 2. Apply all multipliers from upstream jobs
    risk = (base_risk
            * arming[signal.strategy].size_multiplier   # P08: regime/vrp/decay
            * state.gap_size_multiplier                 # O03: gap
            * config.global_size_multiplier)            # manual throttle

    # 3. Max loss per lot — STRUCTURE DEPENDENT
    if signal.risk_class == "DEFINED":
        if signal.structure_type in ("CREDIT_SPREAD", "IRON_CONDOR", "IRON_FLY"):
            max_loss_per_lot = (signal.width - signal.credit) * lot_size
        elif signal.structure_type in ("LONG_OPTION", "BUTTERFLY", "CALENDAR"):
            max_loss_per_lot = signal.debit * lot_size
    else:
        # UNDEFINED risk — there is no max loss. Use stop distance as a PROXY
        # and understand it can be exceeded on a gap (KB 04 §B1: >1000pt loss despite stop)
        max_loss_per_lot = signal.stop_distance * lot_size * config.gap_risk_multiplier  # 1.5

    # 4. Lots
    lots = floor(risk / max_loss_per_lot)

    # 5. HARD FLOOR — this is a real and frequent outcome, not an edge case
    if lots < 1:
        return SizeDecision(lots=0, reason="POSITION_TOO_LARGE_FOR_ACCOUNT",
                            suggestion=suggest_alternative(signal, risk))
        # suggest_alternative → narrower width / Sensex (lot 20 vs Nifty 65) / butterfly

    # 6. Ceilings
    lots = min(lots, config.max_lots_per_trade,
                     freeze_qty // lot_size,           # exchange freeze limit
                     margin_available // margin_per_lot)

    return SizeDecision(lots=lots, max_loss_rupees=lots * max_loss_per_lot, ...)
```

**Worked reference (KB `10` §7):** ₹3,00,000 capital @ 1% = ₹3,000 risk.
Nifty 200-wide spread, 30 credit → max loss/lot = 170 × 65 = **₹11,050 → 0 lots.**
Nifty 50-wide, 10 credit → 40 × 65 = ₹2,600 → **1 lot** ✅
Sensex 100-wide, 18 credit → 82 × 20 = ₹1,640 → **1 lot** ✅

**The `lots == 0` path must be a first-class, well-tested outcome with a useful suggestion attached. On a small account it fires often, and a silent no-trade is indistinguishable from a bug.**

---

## E04 — Order Construction & Validation 🔴 P0

**Trigger:** event — sized.

```
1. Build Order objects per leg
2. Assign idempotency_key = sha256(strategy|signal_id|leg_index|date)
3. Determine order type per leg:
       LIMIT at mid+slippage_allowance   (default)
       MARKET only if config.allow_market AND spread < tick*2
       NEVER market on illiquid legs
4. LEG ORDERING — critical for multi-leg (see E05):
       ALWAYS place LONG (protective/buy) legs FIRST, SHORT legs second
       Rationale: if execution fails midway you are left holding a long option
       (defined, small loss) rather than a naked short (unbounded).
5. Validate each order:
       qty is multiple of lot_size and <= freeze_qty
       price is multiple of tick_size
       price within circuit limits
       symbol resolves and is tradeable today
6. Compute expected total cost (STT 0.15% sell-side, brokerage, exchange, GST, stamp)
7. FINAL RISK ENGINE CALL (10-RISK-ENGINE.md) — mandatory, cannot be bypassed
```

**Outputs:** validated `OrderBatch` with ordering, or rejection with reason.

---

## E05 — Order Execution 🔴 P0 ⭐ HIGHEST-RISK CODE IN THE SYSTEM

**Trigger:** event — validated.

> **Indian brokers do not support atomic multi-leg execution.** A 4-leg iron condor is 4 independent orders. Any of them can be rejected, partially filled, or filled at a bad price. **Getting this wrong is how you end up accidentally naked short.** Build and test this before any multi-leg strategy trades live.

```python
async def execute(batch: OrderBatch) -> ExecutionResult:
    filled, failed = [], []

    # Legs are pre-sorted by E04: LONG/protective legs first
    for leg in batch.legs:
        await ops_throttle.acquire()        # token bucket, 7 OPS cap (01 §1.4)

        ack = await broker.place(leg.order, leg.idempotency_key)

        if ack.rejected:
            failed.append(leg)
            break                            # STOP. Do not place remaining legs.

        fill = await wait_for_fill(ack.order_id, timeout=cfg.fill_timeout_sec)  # 5s

        if fill.status == "COMPLETE":
            filled.append(fill)
        elif fill.status == "PARTIAL":
            if fill.filled_qty >= leg.qty * cfg.min_partial_ratio:   # 0.5
                filled.append(fill)
                await broker.cancel(ack.order_id)   # take partial, cancel remainder
            else:
                await broker.cancel(ack.order_id)
                failed.append(leg)
                break
        else:  # timeout / open
            await broker.cancel(ack.order_id)
            failed.append(leg)
            break

    if failed:
        return await rollback(filled, failed, batch)
    return ExecutionResult(success=True, fills=filled)


async def rollback(filled, failed, batch) -> ExecutionResult:
    """
    We hold a partial structure. Decide: complete it, or unwind it.
    THIS FUNCTION PROTECTS YOU FROM THE WORST OUTCOME IN THE SYSTEM.
    """
    risk = assess_partial_structure(filled)

    if risk.has_naked_short:
        # 🚨 UNACCEPTABLE. Unwind immediately at market, whatever it costs.
        alert.p0("NAKED SHORT FROM PARTIAL FILL — force unwinding")
        for f in filled:
            await broker.place(reverse_order(f, type="MARKET"), new_key())
        return ExecutionResult(success=False, action="FORCE_UNWOUND")

    if risk.is_defined_and_acceptable:
        # e.g. we hold the long leg only — bounded loss. Retry the missing leg once.
        retry = await retry_leg(failed[0], attempts=1, widen_price=True)
        if retry.success:
            return ExecutionResult(success=True, fills=filled + [retry.fill])
        # Retry failed: unwind cleanly, we are not naked, so take our time
        alert.p1("Partial structure unwinding — leg unavailable")
        for f in filled:
            await broker.place(reverse_order(f, type="LIMIT"), new_key())
        return ExecutionResult(success=False, action="UNWOUND")

    alert.p0("UNCLASSIFIED PARTIAL STRUCTURE — MANUAL INTERVENTION REQUIRED")
    kill_switch.activate(flatten=False)
    return ExecutionResult(success=False, action="HALTED_FOR_HUMAN")
```

**Acceptance tests (all mandatory before live multi-leg):**
- Leg 1 fills, leg 2 rejected → structure unwinds, no naked short remains
- Short leg fills, long hedge rejected → **force unwind fires within 5 seconds**
- All legs partial-fill at 60% → position opens at 60% size, protective orders sized to match
- Broker returns duplicate ack → idempotency key prevents a double position
- Network timeout after submit → reconciliation on retry finds the real state, no duplicate

---

## E06 — Fill Verification & Reconcile 🔴 P0

**Trigger:** +2s after E05 completes. **This is the "post-entry check" — never trust a submit ack as truth.**

```
1. Query broker.orders() and broker.positions() — SOURCE OF TRUTH
2. Compare against our internal expected state
3. Reconcile:
     a. Order we think filled, broker says not → correct our state, alert
     b. Position at broker we don't know about → 🚨 P0 ALERT, possible duplicate.
        Do NOT auto-close. Halt and require human decision.
     c. Quantity mismatch → adopt broker's number, resize protective orders
     d. Fill price differs from expected → record slippage, continue
4. Compute actual entry cost incl. all charges
5. Compute ACTUAL max loss from real fills — may differ from E03's estimate
6. IF actual_max_loss > planned_max_loss * 1.2:
       → alert, and evaluate immediate exit
7. Write position record with verified state
8. Trigger E07
```

**Never skip this.** A submit acknowledgement is a promise, not a fact. Every serious incident in retail algo trading traces back to internal state diverging from broker state.

---

## E07 — Protective Order Placement 🔴 P0

**Trigger:** event — fill verified.

> **No position exists unprotected. If the protective order cannot be placed, the position is closed.** This is non-negotiable.

```
1. Compute stop level from strategy.protective_orders(fill)
       Structure-dependent (see 07 §T03 for the full matrix):
         Long option     → stop on OPTION PREMIUM (e.g. -30%)
         Credit spread   → stop on SPREAD VALUE (e.g. 2x credit received)
         Directional/gold→ stop on UNDERLYING price
2. Compute target level(s) per strategy
3. Place protective orders:
       IF broker.capabilities().supports_bracket_order:
              place native bracket (SL + target attached)
       ELIF supports_gtt:
              place GTT stop
       ELSE:
              register SOFTWARE stop with T03 engine
              ⚠️ software stops require the system to be ALIVE — K03 watchdog is
                 therefore capital-protecting, not just hygiene
4. VERIFY protective order accepted (query back — do not trust the ack)
5. IF protective order REJECTED after 2 retries:
       🚨 EXIT THE POSITION IMMEDIATELY AT MARKET.
       An unprotected position is not permitted to exist.
6. Register position with T-series monitors
```

**Software-stop caveat that must be in the runbook:** with software stops, a crashed process means an unprotected position. `K03` (heartbeat/watchdog) must therefore alert within 30 seconds and, on total failure, the fallback is a broker-side GTT placed at a wider "disaster stop" level as a backstop. Always place the disaster stop at the broker even when trailing in software.
