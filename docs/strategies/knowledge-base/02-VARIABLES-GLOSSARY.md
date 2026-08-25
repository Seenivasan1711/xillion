---
doc_id: 02-VARIABLES
title: Decision Variables Glossary
topic: every input a trader evaluates before entering an options trade, with thresholds
compiled: 2026-08-24
use_when: Classifying current market state; answering "what should I look at right now"
---

# 02 — DECISION VARIABLES GLOSSARY

This is the complete checklist of inputs. `08-DAILY-DECISION-ENGINE.md` consumes these to produce a strategy recommendation.

Variables are grouped by family. Each carries: what it is, how to read it, thresholds, and confidence tier on those thresholds.

---

## FAMILY A — VOLATILITY (decides SELL vs BUY)

This family answers the first and most important question: **are options currently expensive or cheap?**

### A1. India VIX
- **What:** 30-day forward implied volatility of Nifty, annualised, published by NSE.
- **Read:** VIX 12 ⇒ market pricing ~12% annualised vol ⇒ ~0.75% daily expected move (12 ÷ √252).
- **Thresholds `[T3-VENDOR]`:**

| Band | Value | Regime | Bias |
|---|---|---|---|
| Very low | < 11 | Complacent | Selling pays poorly. Buying is cheap. |
| Low | 11–14 | Calm range | Weak seller edge. Prefer defined risk. |
| Normal | 14–20 | Healthy | Best general seller band |
| High | 20–30 | Stressed | Rich premium, but real movement risk |
| Extreme | > 30 | Panic | Highest premium, highest gap risk. Defined risk mandatory. |

- **Directional quirk:** India VIX is negatively correlated with Nifty. Sharp Nifty falls spike VIX; grinding rallies bleed it.
- **Current context:** ~11.7 on 24 Aug 2026 → **low band**.

### A2. IV Rank (IVR) and IV Percentile (IVP)
- **IV Rank** = (current IV − 52w low) ÷ (52w high − 52w low) × 100. Where IV sits in its own annual range.
- **IV Percentile** = % of days in the last year IV closed below today's. More robust to single outlier spikes.
- **Why both:** one extreme spike distorts IVR but barely moves IVP. When they disagree, trust IVP.
- **Thresholds `[T3-VENDOR]`:**
  - IVR > 50 → premium selling favoured
  - IVR 30–50 → neutral, defined risk only
  - IVR < 30 → selling poorly compensated; consider buying or standing aside
- **The single most evidence-backed filter in this knowledge base `[T1-BACKTEST]`:** in the Zerodha 45-DTE Nifty study, restricting entries to **VIX above its 75th percentile** raised win rate from ~70% to **~86%** and reduced drawdown. High-IV entry filtering is the closest thing to a free improvement that appears in the data.

### A3. Variance / Volatility Risk Premium (VRP)
- **What:** implied volatility minus subsequently realised volatility. Positive VRP = options overpriced = sellers structurally advantaged.
- **Evidence `[T2-RESEARCH]`** (Nifty 50 study, 43M one-minute option bars, Aug 2022–Mar 2026):
  - VRP positive on **74.9%** of trading days, mean **+1.208 vol points**
  - After transaction costs, median net edge **+1.131 vol points** — costs erase **27.6%** of gross
  - Distribution is **not normal**: left-tail asymmetry **1.975×**, inversion rate 25.1%
  - **⚠️ Early 2026 structural inversion: mean VRP −4.63 vol points**, statistically robust
- **How to use:** VRP is the theoretical justification for option selling. The 2026 inversion means that justification has weakened or reversed in the current regime. **This is the most important single finding for anyone starting premium selling right now.**

### A4. IV Skew
- **What:** difference in IV across strikes. Indian index puts habitually carry higher IV than equidistant calls (crash insurance demand).
- **Read:** steepening put skew = rising fear = hedging demand. Flat skew = complacency.
- **Use:** informs which side of a strangle is better compensated, and warns when a "neutral" structure is actually being paid asymmetrically.

### A5. Realised Volatility (RV) / ATR
- **What:** actual observed movement. ATR(14) on the index in points is the practical form.
- **Use:** compare to implied. IV >> RV = sellers paid well. IV < RV = sellers underpaid — a warning sign that is easy to miss when only watching VIX.
- **Also sets stop distance:** a stop tighter than 1×ATR on the relevant timeframe will be hit by noise.

---

## FAMILY B — EXPIRY CYCLE POSITION (decides WHICH structure)

### B1. DTE (Days To Expiry)
The organising axis of this knowledge base. See `01` §1.2.
- DTE 6–4 → vega-dominant → structures that benefit from IV drop
- DTE 3–1 → theta-dominant → **best risk-adjusted window for sellers**
- DTE 0 → gamma-dominant → highest reward and highest ruin probability

### B2. Theta (per day, in points)
- **What:** premium decay per day. Accelerates non-linearly into expiry.
- **Magnitude `[T3-VENDOR]`:** ATM Nifty option decays ~₹3–5/hour on a normal day vs **₹20–40+/hour on expiry afternoon**.
- **Expiry-day decay curve `[T3-VENDOR]`:** an ATM option can lose **70–80% of remaining value between 1:00 PM and 3:00 PM**.

### B3. Gamma
- **What:** rate of change of delta. Explodes near expiry near ATM.
- **Magnitude `[T3-VENDOR]`:** on expiry day a **50-point Nifty move can swing ATM premium 35–45 points**.
- **This is the number that kills expiry-day sellers.** A position that looks 90% safe at 2:00 PM can be destroyed by 2:20 PM.

### B4. Vega
- **What:** sensitivity to a 1-point IV change. Highest at ATM and at longer DTE.
- **Use:** at DTE 5–6, an IV spike hurts a seller more than the underlying's movement does. At DTE 0, vega is near irrelevant.

### B5. Delta
- **What:** rate of change vs underlying; also a rough proxy for probability of finishing ITM.
- **Standard strike-selection tool `[T3-VENDOR]`:**

| Short strike delta | Approx. probability OTM at expiry | Character |
|---|---|---|
| 10Δ | ~90% | Very conservative, thin credit |
| 16Δ | ~84% | Common institutional default |
| 20–30Δ | ~70–80% | "Sweet spot" per multiple sources |
| 35–40Δ | ~60–65% | Aggressive |
| 50Δ (ATM) | ~50% | Max premium, max risk |

⚠️ **Delta is NOT probability of profit.** It approximates probability of expiring ITM. A position can be stopped out for a full loss without ever finishing ITM. Real-world win rate is lower than 1−delta once stops are applied.

---

## FAMILY C — MARKET STRUCTURE / DIRECTION (decides SIDE)

### C1. Trend state
- Higher highs + higher lows = uptrend; inverse = downtrend; neither = range.
- Practical test: price vs VWAP on the day; price vs 20/50 EMA on 15-min.
- **Gate:** range-bound → neutral structures (condor, straddle). Trending → directional or one-sided credit spreads. **Do not sell a neutral structure into a trend day.**

### C2. VWAP
- **What:** volume-weighted average price. The intraday "fair value" reference; institutional benchmark.
- **Uses:** above VWAP = intraday bullish control; pullbacks to VWAP in a trend = entry zone; repeated rejection = fade signal; price pinned to VWAP = range regime confirmation.

### C3. ADX
- **What:** trend strength (not direction).
- **Thresholds `[T3-VENDOR]`:** ADX < 20 = no trend (favours range/neutral strategies); 20–25 = emerging; > 25 = trending (favours directional, penalises condors).
- **Use as the range-vs-trend gate** before deploying any neutral structure.

### C4. Opening Range (OR)
- First 15 or 30 minutes' high/low. Defines the day's initial balance.
- **Evidence `[T1-BACKTEST]`:** wider opening ranges outperformed narrow ones in the 8-year Nifty ORB study (+30.3% for ~144-pt ranges vs +18.6% for ~35-pt ranges). Ranges under 40 points were filtered out entirely.

### C5. Previous day levels / gap
- PDH, PDL, previous close, overnight gap size.
- **Gap rule:** a gap beyond the prior day's range changes the regime. Time-based entries (e.g. fixed 9:20 straddle) are most vulnerable on gap days — the strategy enters blind into a regime it did not anticipate.

### C6. Support / resistance and round numbers
- Nifty gravitates to 50 and 100-point round levels, especially near expiry, because those carry the largest OI.

---

## FAMILY D — POSITIONING / FLOW (confirms or vetoes)

### D1. Open Interest (OI)
- **What:** total open contracts. Not volume.
- **Read `[T3-VENDOR]`:** highest Call OI strike ≈ resistance; highest Put OI strike ≈ support; the band between them is the market's implied expected range.

### D2. Change in OI + price (buildup table)
`[T3-VENDOR]` — the standard four-quadrant read:

| Price | OI rising | OI falling |
|---|---|---|
| **Up** | Long buildup (bullish, strong) | Short covering (bullish, weaker) |
| **Down** | Short buildup (bearish, strong) | Long unwinding (bearish, weaker) |

### D3. Put-Call Ratio (PCR)
- PCR = total Put OI ÷ total Call OI.
- **Thresholds `[T3-VENDOR]`:** > 1.2 = heavy put positioning (contrarian bullish); 0.8–1.2 = neutral/range; < 0.7 = heavy call positioning (contrarian bearish).
- ⚠️ Sources are explicit: **use as a sentiment filter, never as a standalone entry signal.**

### D4. Max Pain
- Strike at which option buyers collectively lose most / writers pay least.
- **Reliability `[T3-VENDOR]`:** meaningful only in the **last 1–2 sessions** before expiry. Noise earlier in the cycle.

### D5. ATM straddle price
- Sum of ATM call + ATM put premium. The market's own quoted expected move for the remaining life of the contract.
- **This is the cleanest single "expected move" number available** and requires no model. If ATM straddle = 150 points, the market prices roughly ±150 points by expiry. Any strategy whose breakevens sit inside that band is fighting the market's own estimate.

### D6. FII / DII cash and F&O data
- End-of-day institutional flows; FII index-futures long/short ratio.
- Slow-moving context, not an intraday trigger.

### D7. GIFT Nifty
- Overnight/pre-market proxy for Nifty's likely open. Primary gap-risk input before the session.

---

## FAMILY E — EVENT RISK (veto layer)

### E1. Scheduled events
RBI policy, CPI/inflation prints, Union Budget, US Fed decisions, US CPI, monthly F&O expiry, quarterly results season, election events.

### E2. Unscheduled / geopolitical
Currently live per `01` §1.8: US–Iran sanctions, crude oil at ~$93, elevated US yields.

**Veto rule:** short-premium strategies with undefined risk should not be held across a scheduled binary event. Defined-risk structures may be — the max loss is known and already sized.

### E3. Liquidity events
Holiday-shortened weeks, expiry-day-adjacent holidays (shifts expiry a day earlier — see `01` §1.1).

---

## FAMILY F — EXECUTION QUALITY (feasibility gate)

### F1. Bid-ask spread
- **Research-paper threshold `[T2-RESEARCH]`:** require spread **< 0.1% of spot** before entering. Below that, skip the trade.
- At Nifty ~24,200 this is roughly a 24-point equivalent constraint on the underlying; on the option itself, ATM weekly spreads should be ~₹0.5–2.

### F2. Slippage budget
- Must be modelled in every backtest. See `09`.
- On a 10–20 point target, 2 points of slippage is 10–20% of gross P&L. On a 4-leg structure it applies **four times on entry and four on exit**.

### F3. Volume confirmation
- Common filter: require breakout-candle volume ≥ 1.4–2.0× the recent average.

---

## FAMILY G — RISK / MONEY MANAGEMENT (mandatory, non-optional)

### G1. Risk per trade
- Consensus across nearly every source: **1–2% of capital maximum**, some say 0.5%.

### G2. Max loss in rupees, computed BEFORE entry
- For defined-risk structures `[T4-STRUCTURAL]`: `Max loss = (spread width − net credit) × lot size × lots`
- For undefined-risk structures: **there is no max loss**. This is not a rhetorical point.

### G3. Daily loss limit
- Research-paper rule `[T2-RESEARCH]`: stop for the day after **3 consecutive losses** or **5% capital drawdown**.

### G4. Position count
- 3–5 trades/day for discretionary scalping; sources describing 20 trades/day are describing a cost structure that is very hard to overcome.

### G5. Win/loss size ratio — the variable most often ignored
- **Expectancy = (Win% × Avg Win) − (Loss% × Avg Loss)**
- A 70% win rate with average loss 3× average win is **negative expectancy**. See `07` §Expectancy Math for worked numbers.
- **Track this from trade one.** It is more informative than win rate.

### G6. Adverse-streak survivability
- `[T1-BACKTEST]` finding from a 60-cycle strangle study: losses **cluster**, they do not arrive evenly spaced. A five-loss streak produced the entire −24% drawdown. Position size must assume the streak, not the average.

---

## Quick-reference: minimum viable input set

For the AI to give any live-market opinion, it needs at minimum:

1. Instrument + current spot
2. DTE / cycle stage (S1–S5)
3. India VIX + IV rank if available
4. Trend state (trending vs range) — from chart or ADX
5. ATM straddle price (expected move)
6. Any scheduled event today/tomorrow
7. User's capital and risk-per-trade limit

**If any of items 1–4 are missing, ask for them rather than guessing.**
