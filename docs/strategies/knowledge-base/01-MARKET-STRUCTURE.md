---
doc_id: 01-MARKET-STRUCTURE
title: Indian Index Options Market Structure
topic: instruments, expiry calendar, lot sizes, transaction costs, margin, SEBI rules
compiled: 2026-08-24
use_when: Always. Every strike, size and cost calculation depends on these facts.
---

# 01 — MARKET STRUCTURE (as of 24 Aug 2026)

> **Verification note:** These are the facts as reported by public sources in Aug 2026. Lot sizes, STT and margin rules have changed four times in under two years. **Verify against the NSE/BSE circular and your broker's margin calculator before sizing any live trade.**

## 1.1 Expiry calendar — CURRENT REGIME

This changed on **1 Sep 2025**. Any source describing Nifty as a Thursday expiry is stale.

| Instrument | Exchange | Weekly? | Expiry day |
|---|---|---|---|
| **NIFTY 50** | NSE | ✅ Yes | **Every Tuesday** |
| **SENSEX** | BSE | ✅ Yes | **Every Thursday** |
| BANKNIFTY | NSE | ❌ Monthly only | Last Tuesday |
| FINNIFTY | NSE | ❌ Monthly only | Last Tuesday |
| MIDCPNIFTY | NSE | ❌ Monthly only | Last Tuesday |
| Single stocks | NSE | ❌ Monthly only | Last Tuesday (physically settled) |

- SEBI limited each exchange to **one weekly index expiry** (Nov 2024). Bank Nifty / FinNifty / MidCpNifty **lost weekly contracts entirely**.
- If an expiry day is a trading holiday, expiry moves to the **previous** trading day.
- Settlement time: 3:30 PM IST.

**Implication for strategy design:** There are now exactly **two weekly 0DTE sessions per week** available to a retail trader — Nifty on Tuesday (NSE) and Sensex on Thursday (BSE). Everything else is monthly. Strategies built around 4–5 weekly expiries a week no longer exist.

## 1.2 The weekly expiry cycle — the "bagging" spine

For **Nifty weekly (Tuesday expiry)**, one contract's life is 5 trading sessions. This cycle stage is the primary axis this knowledge base uses to organise strategies.

| Stage | Day | DTE | Dominant Greek | Character |
|---|---|---|---|---|
| **S1 — Birth** | Wednesday | 6 | Vega | New weekly opens. Widest premium, lowest gamma. Theta slow. |
| **S2 — Early** | Thursday | 5 | Vega / Theta | Positioning builds. IV still meaningful. |
| **S3 — Mid** | Friday | 4 | Theta | Theta becomes primary. Weekend decay priced in Friday. |
| **S4 — Late** | Monday | 1 | Theta / Gamma | Weekend decay realised. Gamma starting to bite. |
| **S5 — Expiry** | Tuesday | 0 | **Gamma** | 0DTE. Theta violent, gamma extreme. Highest risk session of the cycle. |

**Key structural fact `[T4-STRUCTURAL]`:** Theta and gamma both accelerate toward expiry, but they work against each other for opposite sides of a trade. A seller is paid theta and punished by gamma; a buyer pays theta and is rewarded by gamma. The seller's edge is largest in S3–S4 where theta is high but gamma has not yet exploded. S5 is where sellers earn the most premium per hour *and* face the highest chance of a catastrophic single move.

**Sensex (Thursday expiry)** runs the same 5-stage cycle shifted two days: S1 Friday, S2 Monday, S3 Tuesday, S4 Wednesday, S5 Thursday.

## 1.3 Lot sizes — CURRENT (effective Jan 2026)

Reduced from previous levels; two independent sources agree.

| Index | Symbol | Lot size (units) | Previous |
|---|---|---|---|
| Nifty 50 | NIFTY | **65** | 75 |
| Bank Nifty | BANKNIFTY | **30** | 35 |
| Nifty Financial Services | FINNIFTY | **60** | 65 |
| Nifty Midcap Select | MIDCPNIFTY | **120** | 140 |
| Nifty Next 50 | NXTYFIFTY | **25** | — |
| Sensex | SENSEX | **20** | — |

**Rupee conversion rule `[T4-STRUCTURAL]`:** ₹ P&L = (premium points) × (lot size) × (number of lots).
A 10-point move on one Nifty lot = ₹650. A 10-point move on one Sensex lot = ₹200.

**Side effect flagged by sources:** smaller lots mean less premium collected per contract, so sellers targeting the same income must trade more contracts — which multiplies transaction costs. This is a real drag on scalping and premium-selling economics.

## 1.4 Transaction costs — THE DOMINANT VARIABLE

**Sources disagree on exact current rates. Treat the table below as approximate and confirm with your broker's contract note.**

| Charge | Rate (options) | Applies to |
|---|---|---|
| **STT** | **0.15% of premium** (raised from 0.10%, eff. 1 Apr 2026) | **Sell side only** |
| STT on exercise | 0.15% of intrinsic value (raised from 0.125%) | ITM options left to expire |
| Brokerage | ₹20/order or lower (discount brokers) | Both sides |
| Exchange transaction charge | ~0.05% of premium (varies by exchange) | Both sides |
| SEBI turnover fee | ~0.0001% of turnover | Both sides |
| GST | 18% on (brokerage + transaction charges) | Both sides |
| Stamp duty | ~0.003% of premium | Buy side |

### Why this matters more than any strategy choice

- **SEBI FY22 study `[T2-RESEARCH]`:** 91.1% of individual F&O traders had net losses after costs. Aggregate losses ₹51,689 crore, of which **₹36,528 crore (~71%) was transaction cost**, not directional error.
- **STT is charged on the sell side of the premium.** Option *sellers* pay STT on entry (they sell to open). The Apr 2026 hike raised that cost 50%.
- Multi-leg structures multiply cost: an iron condor is **4 legs × 2 (entry+exit) = 8 chargeable events**. A short straddle is 4. A single option buy is 2.

**Hard rule for the AI:** Any strategy targeting less than ~₹100 per lot of gross profit is fighting a cost base that can consume most of it. When the user proposes a target of "10–20 points", compute the cost in the same breath.

## 1.5 Margin and capital

| Position type | Margin character |
|---|---|
| **Option buying** | Full premium, upfront. No SPAN margin. Max loss = premium paid. |
| **Naked option selling** | SPAN + Exposure margin. Runs to ~₹1–2 lakh+ per Nifty lot, varies daily with volatility. |
| **Hedged / spread selling** | Materially lower — the long leg caps worst-case loss, so SPAN drops sharply. Often a fraction of naked margin. |
| **Expiry day short** | **+2% additional Extreme Loss Margin (ELM)** on short option positions, SEBI-mandated. |

Other current SEBI rules:
- **Upfront premium collection**: brokers must collect full premium from buyers before execution.
- **Intraday position limit monitoring**: real-time, not end-of-day. Breaches penalised intraday.
- **Delta-based OI measurement**: position limits now measured on delta exposure, not raw contract count.

**Practical consequence and a core argument of this knowledge base:** hedged (defined-risk) selling is not only safer, it is dramatically more **capital efficient** in the current margin regime. For a trader with limited capital wanting high win probability, this is the structurally correct place to be — you get a comparable win rate for a fraction of the margin and a known worst case.

## 1.6 Liquidity map

| Instrument | Liquidity | Notes |
|---|---|---|
| Nifty weekly ATM ±3 strikes | Excellent | Tightest spreads in the market. Default choice. |
| Nifty weekly far OTM | Moderate → poor | Spreads widen sharply beyond ~5% OTM |
| Sensex weekly ATM | Good | Second-best weekly venue |
| Bank Nifty monthly ATM | Good | But no weekly — different trade horizon |
| FinNifty / MidCpNifty | Thin | Avoid for scalping; spreads punish |

**Rule:** slippage is a function of spread. Scalping strategies with 10–20 point targets are only viable on Nifty weekly ATM strikes. Anywhere else the spread eats the target.

## 1.7 Session timing map (IST)

| Window | Character | Typical use |
|---|---|---|
| 09:15–09:20 | Auction noise, widest spreads | **Avoid.** Most sources explicitly exclude this. |
| 09:20–09:45 | Opening range forms, high volatility | ORB setups; time-based straddle entries |
| 09:45–11:30 | Cleanest directional structure | Momentum/breakout scalps; research paper's preferred window |
| 11:30–13:30 | Liquidity lull, range compression | Theta strategies; squeeze setups. Directional scalps degrade here. |
| 13:30–14:45 | Volatility returns | Second directional window |
| 14:45–15:15 | Expiry-day gamma danger zone | Sellers exit. Spreads widen. |
| 15:15–15:30 | Closing auction pressure | Flat by here for intraday |

## 1.8 Current market context (24 Aug 2026) — SNAPSHOT, GOES STALE IMMEDIATELY

| Variable | Value | Read |
|---|---|---|
| Nifty 50 | ~24,200 | — |
| **India VIX** | **~11.7** (day range 10.32–11.76) | **LOW volatility regime** |
| Brent crude | ~$93/bbl | Geopolitical risk premium present |
| USD/INR | ~95.67 | RBI-supported |
| US 30Y yield | ~5.25% | Elevated — global risk factor |
| Macro overhang | US–Iran sanctions uncertainty | Event/gap risk elevated despite low VIX |

**Critical interpretation for strategy selection:** India VIX near 11–12 is in the **low band**. For premium sellers this means thin premiums for the same tail risk — the worst combination. Combined with the finding in `02` §VRP that the Nifty variance risk premium **inverted in early 2026**, the current environment is *not* a favourable starting environment for naive option selling. See `08` §Regime Gate.

The tension to hold: low VIX with an unresolved geopolitical overhang is precisely the configuration where a seller collects little and a gap can still happen.

**The AI must re-derive all of §1.8 from live data at query time. Do not quote these values as current.**
