---
doc_id: 05-JOBS-PREMARKET
title: Pre-Market Job Specifications (P-series)
audience: backend
version: 1.0
---

# 05 — PRE-MARKET JOBS (P01–P10)

**Spec template:** every job below defines Trigger · Inputs · Logic · Outputs · Failure mode · Alerts · Acceptance.

---

## P01 — System Health & Auth Refresh 🔴 P0

**Trigger:** 08:00 IST, then hourly during session. Also on demand after any auth error.

**Why it exists:** SEBI mandates daily session expiry (`01` §1.1). A stale token discovered at 09:20 means a missed session. Discover it at 08:00 when there is time to fix it.

**Inputs:** broker credentials (vault), static IP config, last token state.

**Logic:**
```
FOR each configured broker adapter:
    1. Verify static IP matches whitelisted IP        # else orders will be rejected
    2. Check token validity; if expiring < 4h → refresh via OAuth
    3. IF refresh requires 2FA → send Telegram prompt, WAIT (max 30 min)
    4. Call broker.health() → auth ok, market data flowing, clock skew
    5. Verify clock skew < 2s vs NTP                  # halt if worse
    6. Ping Postgres, Redis, DuckDB
    7. Verify disk free > 20%
    8. Check yesterday's M01 reconciliation CLOSED CLEAN
       IF unresolved break → BLOCK TRADING, alert
    9. Write health_status row
```

**Outputs:** `system_health` row; Redis `health:*` flags; `trading_enabled` boolean.

**Failure:** any check fails → `trading_enabled = false`, P0 alert, all downstream P-jobs skip.

**Acceptance:** with a deliberately expired token, job detects it, prompts 2FA, and on no response within 30 min sets `trading_enabled=false` and alerts.

---

## P02 — Market Calendar & Holiday Check 🟡 P1

**Trigger:** 08:05

**Logic:**
```
1. Load exchange holiday calendar (NSE/BSE/MCX) from config, verified against exchange API
2. IF today is a holiday → trading_enabled = false, exit cleanly
3. Compute: is today an expiry day? For which instrument?
   Nifty  → Tuesday weekly (BSE Sensex → Thursday)
   IF holiday falls on expiry day → expiry moves to PREVIOUS trading day  ← handle this
4. Compute cycle stage S1..S5 for the active weekly contract
5. Flag special sessions: muhurat, budget day, half-day
```

**Outputs:** `is_trading_day`, `is_expiry_day`, `cycle_stage`, `days_to_expiry`, `special_session`.

> ⚠️ The holiday-shifted expiry rule is a classic source of live bugs. A strategy that assumes "Tuesday = expiry" will mis-price and mis-size on any week where Tuesday is a holiday. Test this case explicitly.

---

## P03 — Economic Event Calendar Ingest 🟡 P1

**Trigger:** 08:10

**Inputs:** economic calendar source (self-hosted scrape or free API), event impact config.

**Logic:**
```
1. Fetch events for today + next 2 days
2. Classify: HIGH / MEDIUM / LOW impact
   LANE A high-impact: RBI policy, India CPI/WPI, Union Budget, GDP,
                       US Fed decision, US CPI, monthly F&O expiry
   LANE B high-impact: FOMC (19:00 UTC), US CPI (13:30 UTC), NFP (1st Fri 13:30 UTC),
                       ECB, US PPI, London Gold Fix (10:30 UTC)
3. For each event compute blackout window:
       blackout_start = event_time - config.pre_event_minutes   (default 30)
       blackout_end   = event_time + config.post_event_minutes  (default 15)
4. Write to event_blackouts table
```

**Outputs:** `event_blackouts` rows consumed by `E02` gate and `T09` guard.

**Failure:** calendar source unreachable → **fail closed**: assume a high-impact event exists today, reduce size to 50%, alert. Do not assume "no events."

---

## P04 — Overnight & Global Cues Scan 🟢 P2

**Trigger:** 08:30

**Logic (Lane A):** GIFT Nifty level vs prior Nifty close → implied gap %; US indices close; Asian markets; Brent crude; USD/INR; US 10Y/30Y yields; overnight news scan.

**Logic (Lane B):** DXY, US real yields, COMEX gold settlement, overnight XAUUSD range, ETF flows if available.

**Outputs:** `implied_gap_pct`, `global_risk_tone` (RISK_ON / RISK_OFF / NEUTRAL), `cues_summary`.

**Note:** this job informs, it does not gate. Gap *veto* is `O03`, which uses the actual open, not the estimate.

---

## P05 — Volatility Regime Classification 🟡 P1

**Trigger:** 08:45

**Why it matters:** this is the single highest-value filter identified in the strategy research. The Zerodha 45-DTE study found VIX-percentile filtering raised win rate from ~70% to ~86% (KB `04` §B1).

**Logic:**
```
1. Fetch India VIX (Lane A) / ATR-based realised vol (Lane B)
2. Compute VIX percentile over trailing 252 sessions
3. Compute IV Rank  = (IV - IV_52w_low) / (IV_52w_high - IV_52w_low) * 100
   Compute IV Pctl  = % of last 252 days IV closed below today
   IF IVR and IVP disagree by > 20 points → trust IVP, log the divergence
4. Band classification:
       < 11     VERY_LOW
       11 - 14  LOW
       14 - 20  NORMAL
       20 - 30  HIGH
       > 30     EXTREME
5. Compute realised vol (ATR-derived) and IV-RV spread
       IF IV < RV → flag SELLER_UNDERPAID   ← important warning
6. VRP proxy: rolling 20d mean of (IV - subsequent RV)
       IF negative → flag VRP_INVERTED       ← see KB 02 §A3
```

**Outputs:** `vix_level`, `vix_percentile`, `iv_rank`, `iv_percentile`, `regime_band`, `iv_rv_spread`, `vrp_state`.

**Consumed by:** `P08` strategy arming — this is the primary arming input.

---

## P06 — Instrument & Expiry Resolver 🔴 P0

**Trigger:** 08:50

**Why P0:** every downstream calculation depends on lot size and the correct expiry symbol. A wrong lot size silently mis-sizes every position — the most dangerous class of bug in this system, because it does not error, it just loses more money than intended.

**Logic:**
```
1. Resolve active contract:
       LANE A: nearest weekly expiry (Nifty Tue / Sensex Thu), honouring holiday shift from P02
       LANE B2: nearest liquid MCX GOLD/GOLDM contract (avoid delivery month)
2. Fetch CURRENT lot size FROM BROKER API — never from a constant
       Nifty 65 | BankNifty 30 | FinNifty 60 | MidCpNifty 120 | Sensex 20   (as of Jan 2026)
3. IF fetched lot size != config lot size:
       → P0 ALERT, halt trading, require manual confirmation
       (this is how you catch an exchange revision on the morning it lands)
4. Fetch tick size, freeze quantity, market lot, circuit limits
5. Build tradeable symbol strings for the adapter
6. Fetch full option chain, cache to DuckDB
7. Compute ATM strike, ATM straddle price (= market's expected move)
```

**Outputs:** `active_expiry`, `lot_size`, `tick_size`, `atm_strike`, `atm_straddle_price`, `expected_move_pts`, cached chain.

**Failure:** lot size mismatch or chain fetch failure → block trading, P0 alert.

---

## P07 — Capital & Margin Readiness 🔴 P0

**Trigger:** 08:55

**Logic:**
```
LANE A:
    1. broker.balance() → available cash, used margin, free margin
    2. Compare vs config.expected_capital; drift > 5% → alert (unexpected debit?)
    3. Compute today's risk budget = capital * config.daily_risk_pct
    4. Verify free margin >= margin needed for max_concurrent_positions
    5. Check for pending settlement / payin obligations

LANE B (prop firm) — DIFFERENT AND CRITICAL:
    1. mt5.account_info() → balance, equity, peak_equity
    2. Compute:
           daily_dd_used = (day_start_equity - equity) / day_start_equity
           max_dd_used   = (peak_equity - equity) / peak_equity      ← TRAILING model
    3. Compare against INTERNAL limits (80% of firm's — see 01 §1.3):
           internal_daily_dd = 4.0%   (firm ~5%)
           internal_max_dd   = 8.0%   (firm ~10%)
    4. IF either > 75% consumed → reduce size to 50%, alert
       IF either > 90% consumed → BLOCK NEW ENTRIES for the day
    5. IF live account terms cannot be read → DO NOT ARM. Refuse to trade blind.
```

**Outputs:** `available_capital`, `risk_budget_today`, `max_positions_allowed`, `dd_headroom_pct`.

**Failure:** insufficient margin or DD headroom → `trading_enabled = false`, alert.

---

## P08 — Strategy Arming / Selection 🟡 P1

**Trigger:** 09:00

**Why it exists:** an unarmed strategy cannot generate an order. This is where the decision engine from KB `08` executes — it turns market state into "which strategies may fire today."

**Logic:**
```
FOR each strategy in registry:
    armed = True; reasons = []

    # Gate 1 — event veto (P03)
    IF high_impact_event_today AND strategy.risk_class == UNDEFINED:
        armed = False; reasons += "event_veto_undefined_risk"
    IF high_impact_event_today AND strategy.risk_class == DEFINED:
        size_multiplier *= 0.5; reasons += "event_size_reduction"

    # Gate 2 — volatility regime (P05)
    IF regime_band NOT IN strategy.allowed_regimes:
        armed = False; reasons += f"regime_mismatch:{regime_band}"
    IF vrp_state == VRP_INVERTED AND strategy.is_short_premium:
        size_multiplier *= 0.5; reasons += "vrp_inverted_size_reduction"

    # Gate 3 — cycle stage (P02/P06)   [Lane A]
    IF cycle_stage NOT IN strategy.allowed_stages:
        armed = False; reasons += f"stage_mismatch:{cycle_stage}"
    IF cycle_stage == "S5" AND strategy.risk_class == UNDEFINED:
        armed = False; reasons += "no_naked_shorts_on_expiry"   # hard rule

    # Gate 4 — capital (P07)
    IF risk_budget_today < strategy.min_capital_required:
        armed = False; reasons += "insufficient_capital"

    # Gate 5 — strategy health (R02)
    IF strategy.decay_status == "DEGRADED":
        size_multiplier *= 0.5; reasons += "decay_warning"
    IF strategy.decay_status == "DISABLED":
        armed = False; reasons += "decay_disabled"

    WRITE strategy_arming(strategy, armed, size_multiplier, reasons)
```

**Outputs:** `strategy_arming` rows. **`E01` will not generate a signal for an unarmed strategy.**

**Design note:** every arming decision records *why*. When you ask "why did nothing trade on Tuesday", the answer is a database query, not a guess.

---

## P09 — Watchlist & Strike Shortlist Build 🟡 P1

**Trigger:** 09:05

**Logic (Lane A):**
```
1. Load cached chain from P06
2. FOR each armed strategy, compute candidate strikes per its rules:
       - delta-based:  find strikes nearest target delta (e.g. 20Δ)
       - distance-based: ATM ± N * expected_move
       - OI-based: highest Call OI (resistance), highest Put OI (support)
3. Liquidity filter — REJECT any strike where:
       bid_ask_spread > 0.1% of spot        (KB 02 §F1)
       OR OI < config.min_oi
       OR volume < config.min_volume
       OR bid == 0 or ask == 0
4. Compute for each candidate: mid, spread, IV, delta, gamma, theta, vega
5. Rank and store top N per strategy
```

**Logic (Lane B):** single instrument; compute ATR, session levels (Asian range high/low), prior day H/L/C, pivots.

**Outputs:** `watchlist` rows with pre-computed Greeks and liquidity metrics.

**Value:** at signal time `E02` does a table lookup rather than a chain scan. Latency at entry matters.

---

## P10 — Pre-Market Brief Generation 🟢 P2

**Trigger:** 09:10

**Output:** a Telegram message — the human-readable summary of everything P01–P09 decided.

```
📊 PRE-MARKET BRIEF — Tue 26 Aug 2026

LANE A — NIFTY
  Spot ~24,200 | Expiry TODAY (S5, 0 DTE)
  VIX 11.7 (pctl 18 — LOW) | IVR 22
  ⚠️ VRP INVERTED — short premium size halved
  Expected move (ATM straddle): ±118 pts
  Gap estimate (GIFT): +0.15%
  Events: none high-impact

  ARMED (2):
    ✅ butterfly_expiry      1 lot  max loss ₹1,625
    ✅ credit_spread_0dte    1 lot  max loss ₹4,550  [size x0.5: vrp]
  BLOCKED (3):
    ❌ iron_condor       stage_mismatch:S5
    ❌ short_straddle    no_naked_shorts_on_expiry
    ❌ orb_directional   decay_warning → below threshold

  Capital ₹3,00,000 | Risk budget today ₹3,000 | Max positions 2

LANE B — GOLD
  MCX GOLDM ~₹85,400 | ATR(14) 620
  Asian range: 85,100–85,650
  Session: London opens 13:30 IST
  Events: US CPI 19:00 IST ⚠️ → blackout 18:30–19:15
  DD headroom: daily 4.0% unused | max 6.2% remaining
  ARMED (1): ✅ london_breakout  0.5 lot

System: ✅ all healthy | Recon: ✅ clean | Kill switch: ARMED
```

**This brief is the product.** If you read only one thing each morning, it is this. It should be complete enough that you could trade the day manually from it.
