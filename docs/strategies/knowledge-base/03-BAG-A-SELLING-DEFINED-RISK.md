---
doc_id: 03-BAG-A
title: "BAG A — Premium Selling, DEFINED RISK"
topic: credit strategies with a capped max loss, organised by expiry-cycle stage
risk_class: DEFINED (max loss known and capped at entry)
compiled: 2026-08-24
use_when: Market state favours premium selling AND user prioritises capped risk
---

# BAG A — PREMIUM SELLING WITH DEFINED RISK

**This is the bag that best matches the objective "low risk + high win probability."** Every structure here has a max loss that is known in rupees at the moment of entry and cannot exceed that number regardless of what the market does — including gaps, circuit moves, and overnight events.

**Universal schema for every entry below:**
`Structure · Cycle stage · Market view · Entry rules · Strike selection · Max loss (T4) · Win rate (tiered) · Management · Failure mode`

---

## A1. IRON CONDOR

**Cycle stage:** S1–S3 (DTE 6–3). Needs time for theta to work.
**Market view:** Range-bound, low-to-moderate directional conviction.
**Risk class:** DEFINED ✅

### Structure
Four legs, one net credit:
- Sell 1 OTM Call · Buy 1 further-OTM Call (call credit spread)
- Sell 1 OTM Put · Buy 1 further-OTM Put (put credit spread)

### Nifty worked example (illustrative, Nifty ~24,200, lot 65)
```
SELL 24,500 CE   |  BUY 24,700 CE   → call spread, width 200
SELL 23,900 PE   |  BUY 23,700 PE   → put spread, width 200
Net credit: say 55 points
```
- **Max profit** = 55 pts × 65 = **₹3,575** (if Nifty finishes between 23,900 and 24,500)
- **Max loss** `[T4-STRUCTURAL]` = (200 − 55) × 65 = **₹9,425**
- Loss can only occur on **one side**, never both.

### Strike selection `[T3-VENDOR]`
- Short strikes at **15–20 delta** = balanced (cited 65–70% win rate at entry)
- 10 delta = conservative (~84–90% probability OTM, thin credit)
- 30+ delta = aggressive (~65–70% probability OTM, fat credit)
- Target credit ≈ **25–33% of spread width**
- Wing width: wider wings = more credit but larger max loss; narrower = cheaper insurance, less credit

### Win rate
- `[T3-VENDOR]` **65–70% at entry**; rises to **~80% realised** when managed by closing at 50% of max profit
- `[T3-VENDOR]` A separate ranking placed iron condor **#1 of 10 strategies at 70–80%** win rate
- ⚠️ Both figures are vendor-stated with no disclosed methodology or sample. Treat as hypotheses.

### Management (this is what makes or breaks it) `[T3-VENDOR]`
- **Take profit at 50% of max credit.** Do not hold to expiry for the last rupee — this is the single most cited rule.
- **Stop loss at 200% of credit received** (i.e. loss = 2× credit).
- **Close at 7 DTE** to avoid gamma escalation.
- Close both spreads together; avoid legging out of the winning side.

### Failure mode
A sustained trend that runs through one short strike and keeps going. The condor caps the loss, but you take the full capped loss and the collected credit does not come close to offsetting it. Multiple trend months in a row is how condor traders bleed.

### Regime fit
- ✅ ADX < 20, price ranging, IVR > 30
- ❌ Trending market, ADX > 25, pre-event, IVR < 25 (credit too thin to justify the width)

---

## A2. CREDIT SPREAD (Bull Put / Bear Call) — ⭐ THE CORE RECOMMENDATION

**Cycle stage:** S1–S4 (DTE 6–1). Most flexible structure in this knowledge base.
**Market view:** Mildly directional — "I think it won't go below X" or "won't go above Y".
**Risk class:** DEFINED ✅

### Structure
Two legs, one side only:
- **Bull Put Spread** (mildly bullish): Sell higher-strike Put, Buy lower-strike Put
- **Bear Call Spread** (mildly bearish): Sell lower-strike Call, Buy higher-strike Call

### Nifty worked example (Nifty ~24,200, mildly bullish, lot 65)
```
SELL 23,900 PE  @ 70
BUY  23,700 PE  @ 40
Net credit: 30 points · Width: 200
```
- **Max profit** = 30 × 65 = **₹1,950**
- **Max loss** `[T4-STRUCTURAL]` = (200 − 30) × 65 = **₹11,050**
- **Profit if** Nifty stays above 23,900 at expiry (2.8% cushion below spot at entry)

### Strike selection `[T3-VENDOR]`
| Short delta | Approx POP | Use |
|---|---|---|
| 16Δ | ~84% | Conservative |
| 20–30Δ | 70–80% | **Recommended band** |
| 35–40Δ | 60–65% | Aggressive |
| 45–50Δ | 50–55% | Not recommended |

### Win rate `[T3-VENDOR]`
- **60–70%** at standard parameters
- **~75% realised** when closed at 50% max profit
- Expected return quoted as 10–30% of capital at risk per trade

### Management `[T3-VENDOR]`
- Close at **50–75% of max profit**
- Exit if ≤7 DTE and the spread still holds meaningful value
- Risk 2–5% of capital per trade (this KB recommends 1–2%)
- Never let it run to expiry hoping for the final few rupees — that is where gamma converts a small win into the full max loss

### Why this is the recommended starting structure
1. **Only 2 legs** — half the transaction cost of a condor, half the execution risk
2. **Max loss known in rupees before entry**, cannot be exceeded
3. **Directionally forgiving** — you can be wrong about direction and still win, as long as you are not badly wrong
4. **Low margin** vs naked selling
5. **Easiest structure in this KB to backtest correctly** — two legs, mechanical rules, no adjustment logic needed

→ Full specification in `10-FIRST-STRATEGY-SPEC.md`

### Failure mode
A fast directional move through the short strike, especially a gap. You take the capped loss. With a 30-credit / 200-width spread, one max loss wipes out roughly 5.7 winning trades. **This ratio is the entire ballgame — see `07` §Expectancy Math.**

---

## A3. IRON FLY (Iron Butterfly)

**Cycle stage:** S4–S5 (DTE 1–0). Designed for pinning.
**Market view:** Strong conviction the index finishes very close to a specific level.
**Risk class:** DEFINED ✅

### Structure
- Sell ATM Call + Sell ATM Put (the short straddle core)
- Buy OTM Call + Buy OTM Put (the wings that define the risk)

Effectively a **short straddle with insurance**. The wings convert an unbounded-risk position into a capped one, at the cost of some credit.

### Characteristics
- Collects **more credit than an iron condor** (ATM shorts)
- **Narrower profit zone** than a condor
- Max profit only if the index finishes exactly at the short strike
- `[T4-STRUCTURAL]` Max loss = (wing distance − net credit) × lot size

### Common Indian variant `[T5-UNQUANTIFIED]`
Intraday Nifty iron fly with **500–700 point wings**, entered in the morning and exited before close, is a widely-discussed setup. Backtest sources for it exist but were not retrievable with disclosed metrics — **treat as unvalidated**.

### Management
- Same discipline as condor: profit-take at 25–50% of credit, hard stop at a multiple of credit
- On expiry day, the position must be actively managed — gamma near the short strike is extreme

### Failure mode
Any decisive directional move. The iron fly's profit zone is narrow by construction; it wins on pinning and loses on trend. On expiry day the transition from "winning" to "max loss" can take minutes.

---

## A4. DEFINED-RISK EXPIRY-DAY CREDIT SPREAD (0DTE)

**Cycle stage:** S5 only (DTE 0 — Nifty Tuesday, Sensex Thursday).
**Market view:** Index will not travel a specific distance in the remaining hours.
**Risk class:** DEFINED ✅

### The setup `[T3-VENDOR]`
- **Window: 11:00 AM – 1:30 PM.** Theta is aggressive, gamma has not yet peaked.
- Sell OTM CE ~150–200 points above spot; buy CE ~50 points further out as the wing (or the put-side mirror)
- Conditions required: range-bound tape, flat VWAP, horizontal Bollinger Bands
- **Exit at 50% of max profit, or by 1:30 PM — whichever comes first**

### 0DTE worked example `[T3-VENDOR]`
```
Nifty 24,500 · SELL 24,600 CE, BUY 24,700 CE
Net credit ~30 pts → Max risk = 100 − 30 = 70 pts = ₹4,550 (lot 65)
```

### Supporting theta data `[T3-VENDOR]`
| Time | ATM premium | Theta pressure |
|---|---|---|
| 09:15 | ₹80–120 | Moderate |
| 11:00 | ₹50–80 | Increasing |
| 13:00 | ₹25–40 | Aggressive |
| 14:30 | ₹5–15 | Severe |
| 15:15 | ₹0–5 | Terminal |

An ATM option can lose **70–80% of remaining value between 1:00 PM and 3:00 PM**.

### Hard rules from sources — near-universal agreement
- **NEVER sell naked on expiry day.** Every source that discusses 0DTE says this explicitly.
- **Be flat by 2:00 PM.** One source: "the final 90 minutes destroy accounts."
- Remember the SEBI **+2% ELM** on expiry-day shorts (`01` §1.5).

### Failure mode
Gamma. A 50-point Nifty move can swing ATM premium 35–45 points on expiry day. The wing caps the damage, which is exactly why the naked version of this trade is excluded from Bag A.

---

## A5. COVERED CALL

**Cycle stage:** Monthly cycle, not weekly.
**Market view:** Own the underlying, expect sideways-to-mildly-up.
**Risk class:** DEFINED on the option leg ✅ (but you carry full equity/ETF downside)

- Own the underlying (stock, or an index ETF as a proxy), sell an OTM call against it
- `[T3-VENDOR]` win rate quoted **60–70%**
- Caps upside in exchange for premium income
- **Not applicable to pure index-options intraday trading** — included for completeness because it appears in every "high win rate" list. Requires holding capital in the underlying, which is a different business from scalping.

---

## BAG A SUMMARY TABLE

| # | Strategy | Stage | Legs | Max loss | Win rate | Tier | Best regime |
|---|---|---|---|---|---|---|---|
| A1 | Iron Condor | S1–S3 | 4 | Capped | 65–80% | T3 | Range, IVR>30 |
| **A2** | **Credit Spread** | **S1–S4** | **2** | **Capped** | **60–75%** | **T3** | **Mild directional** |
| A3 | Iron Fly | S4–S5 | 4 | Capped | Not stated | T5 | Pinning expectation |
| A4 | 0DTE Credit Spread | S5 | 2 | Capped | Not stated | T5 | Range, midday |
| A5 | Covered Call | Monthly | 1 + stock | Capped* | 60–70% | T3 | Sideways, holding stock |

*Option leg capped; underlying exposure is not.

## Cross-cutting warning for Bag A

Every win rate in this bag is **T3 — vendor-claimed, no disclosed methodology or sample size**. None of them has been verified on Indian weekly options with realistic costs. They are starting hypotheses for backtesting, not expectations. The **T4 structural facts** (max loss formulas) are the only fully reliable content on this page — and they are also the most important, because they are what makes this bag "low risk."
