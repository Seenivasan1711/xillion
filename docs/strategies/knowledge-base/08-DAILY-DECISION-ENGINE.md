---
doc_id: 08-DECISION-ENGINE
title: Daily Decision Engine
topic: deterministic IF/THEN rules mapping live market state to a strategy shortlist
compiled: 2026-08-24
use_when: EVERY live-market query. This is the executable core of the knowledge base.
---

# 08 — DAILY DECISION ENGINE

This file turns live observations into a strategy shortlist. It is written as a sequence of gates. **Run them in order.** A failed gate stops the process — it does not get overridden by a later signal.

---

## STEP 0 — INPUT COLLECTION

Required before any recommendation. If any of these is missing, **ask for it — do not assume**.

```yaml
instrument:        # NIFTY (Tue expiry) | SENSEX (Thu expiry) | BANKNIFTY (monthly)
spot:              # current index level
dte:               # days to expiry → maps to cycle stage S1-S5
india_vix:         # current level
iv_rank:           # if available (else use VIX band as proxy)
atm_straddle_price:# market's own expected-move estimate
trend_state:       # TRENDING_UP | TRENDING_DOWN | RANGE  (from chart or ADX)
adx:               # if available
day_open_vs_prev:  # gap size in points
events_today:      # RBI / CPI / Fed / Budget / results / none
time_now:          # IST
capital:           # total trading capital
risk_per_trade:    # % — default 1%
```

**Chart inputs the user should supply** (they mentioned having charts from the start of the options cycle):
- Index chart: 5-min and 15-min, from the cycle's S1 (Wednesday for Nifty) to now
- VWAP, opening range high/low, prior-day high/low/close
- Option chain snapshot: OI by strike, change in OI, PCR, IV per strike

---

## GATE 1 — EVENT VETO 🚫

```
IF a scheduled binary event (RBI policy, CPI, Fed, Budget, major results) 
   lands today or before this position's exit:
     → BLOCK all undefined-risk strategies (Bag B) unconditionally
     → ALLOW defined-risk only, at reduced size (halve normal size)
     → PREFER debit structures (Bag D) or standing aside
```

Unscheduled/geopolitical overhang (currently: US–Iran sanctions, crude ~$93, elevated US yields per `01` §1.8) is not a full veto but is a **size reducer** and an argument for capped-risk structures.

---

## GATE 2 — REGIME CLASSIFICATION (volatility)

```
IF india_vix < 11:              regime = VERY_LOW
ELIF india_vix 11-14:           regime = LOW          ← current (~11.7)
ELIF india_vix 14-20:           regime = NORMAL
ELIF india_vix 20-30:           regime = HIGH
ELSE:                           regime = EXTREME
```

**Action by regime:**

| Regime | Selling premium | Buying premium | Preferred bags |
|---|---|---|---|
| VERY_LOW | ❌ Poorly compensated | ✅ Cheap | C, D |
| **LOW** | ⚠️ **Weak edge — defined risk only** | ✅ **Reasonably cheap** | **C, D, A (small)** |
| NORMAL | ✅ Best general band | Neutral | A |
| HIGH | ✅ Rich premium, real risk | ❌ Expensive | A (defined risk mandatory) |
| EXTREME | ⚠️ Rich but dangerous | ❌ Very expensive | A only, reduced size, or stand aside |

**🚨 VRP OVERRIDE — check this before any selling recommendation:**
```
The Nifty variance risk premium was measured as INVERTED in early 2026
(mean -4.63 vol points) [T2-RESEARCH].

IF the user has no live evidence that VRP has returned to positive:
   → State explicitly that the structural edge behind premium selling
     may currently be absent
   → Recommend reduced size for ALL short-premium strategies
   → Do not present historical selling win rates as current expectations
```

---

## GATE 3 — CYCLE STAGE (which structures are eligible)

```
Nifty:  S1=Wed(6DTE) S2=Thu(5) S3=Fri(4) S4=Mon(1) S5=Tue(0)
Sensex: S1=Fri       S2=Mon    S3=Tue    S4=Wed    S5=Thu
```

| Stage | Dominant Greek | Eligible structures | Blocked |
|---|---|---|---|
| **S1** (6 DTE) | Vega | Iron Condor, Credit Spread, Calendar | Iron Fly (too much time value) |
| **S2** (5 DTE) | Vega/Theta | Iron Condor, Credit Spread, Calendar | — |
| **S3** (4 DTE) | Theta | **Credit Spread ⭐, Iron Condor** | — |
| **S4** (1 DTE) | Theta/Gamma | Credit Spread, Iron Fly, Butterfly | New condors (too little time) |
| **S5** (0 DTE) | **Gamma** | Butterfly, 0DTE credit spread, directional buying | **ALL naked selling — absolute block** |

**S3–S4 is the theta sweet spot:** decay is fast, gamma has not yet exploded. This is where a defined-risk seller has the best risk-adjusted window of the cycle.

---

## GATE 4 — DIRECTION / TREND STATE

```
IF adx > 25 OR (clear HH-HL or LH-LL structure on 15-min):
     trend = TRENDING
     → BLOCK neutral structures (Iron Condor, Iron Fly, Butterfly)
     → ALLOW one-sided credit spreads AGAINST the trend's opposite side
         (uptrend → Bull Put Spread; downtrend → Bear Call Spread)
     → ALLOW directional buying (Bag C)

ELIF adx < 20 AND price oscillating around VWAP:
     trend = RANGE
     → ALLOW neutral structures (Iron Condor ⭐, Butterfly, Iron Fly)
     → BLOCK breakout strategies (they fail in chop — see the 2023 ORB loss year)

ELSE:
     trend = TRANSITIONAL
     → Reduce size or stand aside. Ambiguity is not a setup.
```

**Note on directional credit spreads:** in an uptrend, a **bull put spread** is the aligned trade — you are selling downside insurance in a market that is rising. You win if the market goes up, sideways, *or* down slightly. This "three ways to win" property is why Rank 1 tolerates being directionally wrong.

---

## GATE 5 — TIME-OF-DAY

| Time (IST) | Allowed | Blocked |
|---|---|---|
| 09:15–09:20 | Nothing | Everything — auction noise, widest spreads |
| 09:20–09:45 | ORB formation; time-based entries | New neutral positions |
| **09:45–11:30** | **Directional scalps ⭐ (best window)** | — |
| 11:30–13:30 | Theta structures, squeeze setups | Directional scalps degrade |
| 13:30–14:45 | Second directional window | New S5 short premium |
| 14:45–15:15 | Exits only | **All new expiry-day shorts** |
| 15:15–15:30 | Flat | Everything |

**Expiry day (S5) hard rule:** be flat by **14:00**. Multiple sources converge on this. One phrases it as "the final 90 minutes destroy accounts."

---

## GATE 6 — EXECUTION FEASIBILITY

```
IF bid_ask_spread > 0.1% of spot:            → SKIP the trade
IF strike is beyond ATM ±5 strikes on weekly: → SKIP (liquidity)
IF instrument is FINNIFTY or MIDCPNIFTY 
   and intent is scalping:                    → SKIP (too thin)
IF expected_gross_profit < 3× round_trip_cost: → SKIP (cost dominates)
```

That last check is the one most often skipped and most often fatal. See `01` §1.4.

---

## GATE 7 — POSITION SIZING (mandatory, never optional)

```
max_loss_rupees = risk_per_trade% × capital

FOR DEFINED-RISK STRUCTURES:
    max_loss_per_lot = (width - credit) × lot_size
    lots = floor(max_loss_rupees / max_loss_per_lot)
    IF lots < 1 → the trade is too large for this account. SKIP IT.

FOR UNDEFINED-RISK STRUCTURES:
    → There is no max_loss. Sizing cannot be computed. 
    → This is a reason to not take the trade, not a detail to skip past.
```

**Worked example:** capital ₹3,00,000, risk 1% = ₹3,000 max loss.
Bull put spread, width 200, credit 30 → max loss/lot = 170 × 65 = **₹11,050**.
₹3,000 / ₹11,050 = 0.27 lots → **less than 1 lot. This trade cannot be taken at 1% risk on ₹3 lakh.**

Options to make it fit:
- Narrow the width to 100 → max loss ≈ (100−18) × 65 = ₹5,330 (still >1% of ₹3L)
- Narrow to 50 → max loss ≈ (50−10) × 65 = ₹2,600 ✅ fits
- Or trade **Sensex** (lot 20 instead of 65) → a 200-wide spread = 170 × 20 = ₹3,400, close to fitting
- Or accept 2% risk
- Or use a **butterfly** (`06` §D1), max loss ~₹1,625/lot — still the smallest risk on the list, though it needs ~2% risk tolerance on ₹3L

**This calculation is why `07` recommends starting with the butterfly for live trading. Lot size 65 on Nifty makes most defined-risk spreads too large for a small account at honest risk limits. Sensex's lot of 20 is materially friendlier to small capital — a point almost no strategy guide mentions.**

---

## STEP 8 — OUTPUT FORMAT

The AI must produce exactly this structure:

```
MARKET STATE
  Instrument / Spot / Cycle stage (S_) / DTE
  VIX ___ → regime ___    | VRP caveat if selling is under consideration
  Trend ___ (ADX ___)     | Expected move (ATM straddle) ± ___ pts
  Events: ___             | Time: ___

GATES
  G1 Event    : PASS / VETO — reason
  G2 Regime   : ___
  G3 Stage    : eligible = [...]
  G4 Trend    : ___ → blocked = [...]
  G5 Time     : ___
  G6 Feasible : PASS / SKIP

SHORTLIST (max 3, ranked, each with:)
  Strategy name + KB reference (e.g. "03-BAG-A §A2")
  Exact strikes
  Credit/debit expected
  MAX LOSS IN RUPEES ← always state this first
  Lots (from Gate 7)
  Profit target / stop / time stop
  Win rate + CONFIDENCE TIER
  Primary failure mode

IF NO STRATEGY PASSES ALL GATES:
  Say so. "No setup today" is a valid and frequently correct output.
  Do not manufacture a trade to fill the response.

MANDATORY FOOTER
  - Which inputs were missing/assumed
  - Reminder: analysis support, not financial advice; user decides
```

---

## Worked example — running the engine on today's snapshot

```
INPUT: NIFTY, spot ~24,200, VIX ~11.7, Aug 24 2026 (Monday), 
       geopolitical overhang, no scheduled event today

G1 Event    : PASS (no scheduled binary event) but geopolitical overhang → size down
G2 Regime   : VIX 11.7 → LOW. Selling weakly compensated.
              🚨 VRP inversion flag active → short premium edge questionable
G3 Stage    : Monday, Nifty expires Tuesday → S4, 1 DTE. Theta/gamma.
              Eligible: Credit Spread, Iron Fly, Butterfly. Blocked: new condors.
G4 Trend    : REQUIRES USER'S CHART — cannot classify without it
G5 Time     : depends on query time
G6 Feasible : Nifty weekly ATM ±3 → liquidity fine

SHORTLIST (pending trend input):
  IF RANGE  → Long Butterfly at the high-OI round strike 
              (lowest capital, 3:1 R:R, fits small accounts)
  IF TREND  → Aligned credit spread, narrow width to fit sizing
  ALWAYS    → flag that low VIX + inverted VRP is a poor selling backdrop,
              and that debit structures are relatively favoured right now
```

**Note what the engine does here: it refuses to name a trade without the trend input, and it leads with the regime warning rather than the win rate.** That is the correct behaviour.
