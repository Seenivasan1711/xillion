---
doc_id: 07-JOBS-INTRADE
title: In-Trade Job Specifications (T-series)
audience: backend
version: 1.0
criticality: T01, T03 are capital-protecting
---

# 07 — IN-TRADE JOBS (T01–T10)

These run continuously while any position is open. **This is where the discretionary trader's screen-watching gets replaced.**

---

## T01 — Position & P&L Monitor 🔴 P0

**Trigger:** every 1 second while any position is open (event-driven off the WS tick stream; 1s timer as fallback).

**This is the heartbeat of every other T-job. It computes state; the others act on it.**

```python
async def monitor_tick():
    for pos in open_positions():
        q = {leg.symbol: broker.quote(leg.symbol) for leg in pos.legs}

        # ---- Mark-to-market (use the price you'd actually GET, not mid) ----
        # Long leg exits at BID, short leg exits at ASK. Marking at mid overstates P&L.
        current_value = sum(
            q[leg.symbol].bid * leg.qty if leg.side == "LONG"
            else -q[leg.symbol].ask * leg.qty
            for leg in pos.legs
        )
        pos.unrealised_pnl = (current_value - pos.entry_value) * lot_size
        pos.unrealised_pnl_net = pos.unrealised_pnl - pos.entry_cost - est_exit_cost(pos)

        # ---- Progress metrics that downstream jobs consume ----
        pos.pnl_pct_of_max_profit = pos.unrealised_pnl / pos.max_profit
        pos.pnl_pct_of_max_loss   = pos.unrealised_pnl / pos.max_loss
        pos.r_multiple            = pos.unrealised_pnl / pos.initial_risk
        pos.mae = min(pos.mae, pos.unrealised_pnl)     # max adverse excursion
        pos.mfe = max(pos.mfe, pos.unrealised_pnl)     # max favourable excursion
        pos.time_in_trade = now - pos.entry_time

        # ---- Aggregate account state ----
        write_redis(f"position:{pos.id}", pos)
        emit_metric("position_pnl", pos.unrealised_pnl_net, tags={...})

    day = aggregate_day_pnl()
    check_daily_circuit_breakers(day)      # → 10-RISK-ENGINE §4
```

**Critical detail — MAE/MFE tracking.** Recording max adverse and max favourable excursion per trade is what later tells you whether your stop is too tight (many trades stopped out then recovered) or your target too far (many trades reached 80% of target then reversed). This is the raw material for `R03` parameter tuning and costs nothing to collect.

**Outputs:** live position state in Redis, metrics to Prometheus, aggregate day P&L.

**Failure:** quote unavailable for a leg → mark with last-known, flag `STALE_MARK`, alert if stale > 30s. **Never silently mark a leg at its entry price** — that hides losses.

---

## T02 — Greeks Drift Monitor 🟢 P2 (Lane A)

**Trigger:** every 30s.

**Why:** an options position's risk profile changes even when the underlying does not move. A delta-neutral condor at entry can be materially directional two hours later.

```
For each options position:
    1. Fetch/compute live Greeks per leg; aggregate to net position Greeks
    2. Compare to entry Greeks:
           delta_drift = |net_delta_now - net_delta_entry|
           gamma_now, theta_now, vega_now
    3. Alert conditions:
           delta_drift > cfg.max_delta_drift          → position has become directional
           |net_delta| > cfg.max_abs_delta            → breach of neutrality mandate
           gamma > cfg.max_gamma                      → gamma risk escalating (near expiry/ATM)
           theta flipped sign                         → structure no longer earning time
    4. On breach → notify T07 (adjustment) and log
```

**Expiry-day escalation (KB `02` §B3):** on S5, gamma explodes — a 50-point Nifty move can swing ATM premium 35–45 points. On expiry day, run this job every 10s instead of 30s, and lower the gamma alert threshold.

---

## T03 — Stop Loss Trailing Engine 🔴 P0 ⭐

**Trigger:** every 1s (price-based trails) and on bar close (indicator-based trails).

> **The most-requested feature and the easiest to get subtly wrong.** Two rules govern everything below:
> **(1) A trailing stop only ever moves in the favourable direction. It never loosens.**
> **(2) What you trail on depends on the structure — trailing an options credit spread on the underlying's price is a category error.**

### 3.1 What to trail ON — the structure matrix

| Structure | Trail on | Why |
|---|---|---|
| Long option (directional) | **Option premium** | Your P&L *is* the premium |
| Directional futures / XAUUSD | **Underlying price** | Linear instrument |
| Credit spread | **Spread net value** | P&L = credit received − current spread value |
| Iron condor / fly | **Total structure value** | Same reasoning; both sides matter |
| Short straddle/strangle | **Combined premium** | And separately guard each leg |
| Butterfly / calendar | **Structure value** | Debit paid is the max loss; trail toward locking gains |

**Never** trail a credit spread on the underlying's spot price. The relationship between spot and spread value is non-linear and changes with time and IV — the stop will fire at the wrong times in both directions.

### 3.2 Trailing algorithms — implement all, select per strategy config

```python
# ---------- 1. FIXED POINT / PERCENT TRAIL ----------
def fixed_trail(pos, cfg):
    if pos.direction == "LONG":
        candidate = pos.high_water_mark - cfg.trail_points
    else:
        candidate = pos.low_water_mark + cfg.trail_points
    return ratchet(pos, candidate)


# ---------- 2. ATR / CHANDELIER TRAIL ----------
# Chandelier Exit (standard: period 22, multiplier 3.0):
#   LONG  stop = highest_high(period) - ATR(period) * multiplier
#   SHORT stop = lowest_low(period)   + ATR(period) * multiplier
# For intraday scalping use shorter periods (14/10) and multiplier 1.5-2.5.
def chandelier_trail(pos, cfg, bars):
    atr = ATR(bars, cfg.atr_period)
    if pos.direction == "LONG":
        candidate = highest_high(bars, cfg.atr_period) - atr * cfg.atr_mult
    else:
        candidate = lowest_low(bars, cfg.atr_period) + atr * cfg.atr_mult
    return ratchet(pos, candidate)


# ---------- 3. STRUCTURE / SWING TRAIL ----------
def structure_trail(pos, cfg, bars):
    # Trail behind the most recent confirmed swing point + a buffer
    if pos.direction == "LONG":
        candidate = last_swing_low(bars, cfg.swing_lookback) - cfg.buffer
    else:
        candidate = last_swing_high(bars, cfg.swing_lookback) + cfg.buffer
    return ratchet(pos, candidate)


# ---------- 4. R-MULTIPLE STEP TRAIL (recommended default) ----------
# Discrete, auditable, easy to backtest. Stop moves in steps as profit accrues.
R_LADDER = [
    (1.0, 0.0),    # at +1.0R → stop to breakeven
    (1.5, 0.5),    # at +1.5R → lock +0.5R
    (2.0, 1.0),    # at +2.0R → lock +1.0R
    (3.0, 2.0),    # at +3.0R → lock +2.0R
]
def r_ladder_trail(pos, cfg):
    locked = None
    for trigger_r, lock_r in R_LADDER:
        if pos.r_multiple >= trigger_r:
            locked = lock_r
    if locked is None:
        return pos.stop                       # not yet triggered, leave initial stop
    candidate = pos.entry_price + (locked * pos.initial_risk_per_unit * pos.sign)
    return ratchet(pos, candidate)


# ---------- 5. PREMIUM-DECAY TRAIL (option BUYING) ----------
# Long options bleed theta. A stop that doesn't tighten with time lets theta
# convert a winner into a loser. Tighten the trail as the day progresses.
def premium_decay_trail(pos, cfg):
    elapsed = (now - pos.entry_time).seconds / cfg.expected_hold_seconds
    tightening = 1.0 - min(elapsed * cfg.decay_tighten_factor, 0.6)   # floor at 40%
    trail_amt = pos.peak_premium * cfg.trail_pct * tightening
    return ratchet(pos, pos.peak_premium - trail_amt)


# ---------- 6. CREDIT-BASED TRAIL (option SELLING) ----------
# Trail on how much of the collected credit has been captured.
def credit_trail(pos, cfg):
    captured = (pos.credit_received - pos.current_spread_value) / pos.credit_received
    if captured >= 0.5:
        # 50% captured → tighten stop so a full reversal cannot occur
        candidate_value = pos.credit_received * (1 - captured * cfg.lock_ratio)
        return ratchet_value(pos, candidate_value)
    return pos.stop_value


# ---------- THE RATCHET — the only way a stop is ever written ----------
def ratchet(pos, candidate):
    """A stop NEVER loosens. This function is the single enforcement point."""
    if pos.direction == "LONG":
        return max(pos.stop, candidate)
    return min(pos.stop, candidate)
```

### 3.3 Execution of a stop update

```
1. Compute candidate stop via the strategy's configured algorithm
2. Apply ratchet (never loosens)
3. Skip the update unless it moves by > cfg.min_stop_move
       (default: 2 ticks. Prevents order-modify spam and OPS burn)
4. Enforce a modify-rate limit: max 1 stop modify per position per 5 seconds
5. IF broker supports native trailing SL → modify the broker order
   ELSE → update software stop; if breached, fire X01 immediately
6. Log every stop movement to stop_history (feeds R03 analysis)
```

### 3.4 Gold-lane specifics (Lane B)

```
- XAUUSD moves in large point terms. Use ATR-based trailing, never fixed pips.
- WIDEN the trail during the 22:30-00:00 IST rollover window — spreads widen
  materially and a normal-width trail will be stopped out by the spread alone.
- Session-aware: tighten the trail entering the Asian session (05:30 IST), when
  gold typically drifts and a wide trail just gives back profit.
- Prop-firm interaction: if daily DD is >70% consumed, tighten ALL trails
  aggressively. Protecting the account mandate outranks maximising one trade.
```

**Acceptance tests:**
- Stop never widens under any input sequence (property test with `hypothesis`)
- Ratchet holds across restart (stop persisted, reloaded correctly)
- Modify-rate limit prevents >1 modify/5s under a rapidly trending tick stream
- Gap through stop → position exits at next available price, loss recorded correctly

---

## T04 — Partial Exit / Scale-Out Engine 🟡 P1

**Trigger:** every 1s.

**Why:** booking part of the position converts an unrealised gain into a realised one and lowers the variance of the outcome. Most strategy sources describe some form of "book 50–70%, trail the rest."

```
scale_out_ladder (per strategy config), e.g.:
    at +1.0R  → exit 50% of position, move stop on remainder to breakeven
    at +2.0R  → exit 25% more
    remaining 25% → trail with T03 until stopped

For CREDIT structures instead use profit capture:
    at 50% of max credit captured → close entire position   ← the most-cited rule
    (KB 03 §A1/A2: closing at 50% raises realised win rate materially)

Execution notes:
    - Partial exit qty MUST be a whole number of lots
    - If position is 1 lot, scaling out is impossible → skip, log SCALE_SKIP_MIN_SIZE
      (this is common on small accounts and must not error)
    - After any partial, RECOMPUTE protective order quantities to match remainder
      — an oversized stop on a reduced position will reverse you into a new position
```

**That last point is a real and dangerous bug class. After every partial exit, the protective order must be modified to the new quantity, and the modification verified.**

---

## T05 — Breakeven Shift Engine 🟡 P1

**Trigger:** every 1s.

Simple, high-value, and separated from T03 because it fires once and has different semantics.

```
IF pos.r_multiple >= cfg.breakeven_trigger_r      (default 1.0)
   AND NOT pos.breakeven_moved:
       new_stop = pos.entry_price + (cfg.breakeven_buffer * pos.sign)
       # buffer covers round-trip COST so "breakeven" is truly zero, not a small loss
       # cfg.breakeven_buffer should default to the round-trip cost in points
       apply_stop(pos, new_stop)
       pos.breakeven_moved = True
       log("BREAKEVEN_SHIFT", pos.id)
```

**Detail that matters:** a naive breakeven stop at the entry price still loses money, because you pay costs twice. Set the buffer to at least the round-trip cost so a "breakeven" exit is actually flat.

---

## T06 — Time Stop Enforcer 🟡 P1

**Trigger:** every 10s.

```
FOR each position:
    IF time_in_trade > strategy.max_hold_duration → EXIT (reason TIME_STOP)
    IF now > strategy.hard_exit_time              → EXIT
    IF stage == "S5" AND now.time() >= 14:00      → EXIT   # expiry gamma rule
    IF Lane B AND now approaching rollover (22:30 IST) AND cfg.no_hold_rollover → EXIT
```

**Rationale (KB `05` §C6):** on expiry day, sources converge on being flat by 14:00 — "the final 90 minutes destroy accounts." A time stop is the cheapest risk control in the system: it costs nothing and caps the duration of exposure to conditions you did not model.

---

## T07 — Adjustment Trigger 🔵 P3 (Lane A, Phase 5)

**Trigger:** every 60s.

**Build last. Adjustments are where good systems go to die** — they convert a bounded loss into an unbounded campaign. Only build after the base system is profitable, and even then keep the rules narrow.

```
Candidate adjustments for a threatened credit spread / condor:
    ROLL_UNTESTED_SIDE   — move the safe side closer for extra credit
    ROLL_OUT             — move to a later expiry
    ADD_HEDGE            — buy a protective option
    CLOSE_TESTED_SIDE    — take the loss on one side, keep the other

MANDATORY GUARDRAILS:
    - Max 1 adjustment per position, ever
    - An adjustment may NEVER increase max loss
    - An adjustment may NEVER convert a defined-risk position to undefined risk
    - If the adjustment's cost > 50% of remaining credit → just close instead
    - Adjustments disabled entirely on S5 (expiry day)
```

---

## T08 — Spread & Liquidity Degradation Monitor 🟡 P1

**Trigger:** every 5s.

```
FOR each open position leg:
    current_spread_pct = (ask - bid) / mid * 100
    IF current_spread_pct > entry_spread_pct * cfg.spread_degradation_factor  (2.0):
          flag LIQUIDITY_DEGRADED
          → block scale-outs (you'd get a bad fill)
          → widen software stops slightly to avoid a spread-driven stop-out
          → if severe and position is profitable, consider exiting while you still can
    IF bid == 0 OR ask == 0 → 🚨 P0: the leg is untradeable. Alert immediately.
```

**Why it matters:** liquidity vanishes exactly when you need it — late on expiry day, during news, at gold's rollover. A stop calculated in normal conditions becomes unreachable in stressed ones. Detecting the change is what lets the other jobs adapt.

---

## T09 — Event Proximity Guard 🟡 P1

**Trigger:** every 60s.

```
FOR each upcoming event in event_blackouts:
    minutes_to_event = event.time - now

    IF minutes_to_event <= cfg.pre_event_flatten_minutes (default 15):
        FOR each open position:
            IF pos.risk_class == "UNDEFINED":
                  EXIT NOW (reason: PRE_EVENT_FLATTEN)   ← non-negotiable
            ELIF pos.risk_class == "DEFINED":
                  IF cfg.flatten_defined_before_events: EXIT
                  ELSE: tighten stops, log EVENT_HOLD_DEFINED
    IF minutes_to_event <= 30:
        block all new entries (E02 gate handles this)
```

**Lane B note:** US CPI (13:30 UTC / 19:00 IST) and FOMC (19:00 UTC / 00:30 IST) move gold 50–150+ pips in seconds, with spread blowouts. An undefined-risk gold position held through CPI is not a trade, it is a coin flip with a leveraged stake.

---

## T10 — Correlation & Exposure Aggregator 🟢 P2

**Trigger:** every 30s.

```
1. Compute net exposure across ALL positions and BOTH lanes
2. Detect concentration:
       - Multiple positions same underlying, same direction → aggregate delta
       - Lane A + Lane B both risk-on (e.g. long Nifty calls + short gold)
         → these are correlated through the same macro driver
3. IF aggregate_delta > cfg.max_portfolio_delta → block same-direction entries
4. IF total_risk_at_stake > cfg.max_total_risk  → block ALL new entries
5. Compute portfolio heat = sum(open position risk) / capital
       heat > 6% → warn; heat > 10% → block new entries
```

**The scenario this prevents:** three "independent" 1%-risk positions that are actually the same bet expressed three ways. You believe you are risking 1%; you are risking 3% on one idea. Portfolio heat is the number that makes this visible.
