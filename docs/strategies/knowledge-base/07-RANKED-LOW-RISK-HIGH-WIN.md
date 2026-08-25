---
doc_id: 07-RANKED
title: "MASTER RANKING — Filtered for Low Risk + High Win Probability"
topic: the single ranked list answering "what should I trade, safest first"
compiled: 2026-08-24
use_when: User asks what to trade, what is safest, or what to start with
priority: HIGHEST — this is the file that answers the user's actual question
---

# 07 — MASTER RANKING: LOW RISK + HIGH WIN PROBABILITY

## The filter applied

Ranked top-to-bottom by this ordered set of criteria:

1. **Is max loss capped and known at entry?** (hard gate — undefined risk drops to the bottom regardless of win rate)
2. **Evidence quality of the win rate** (T1 > T2 > T3 > T5)
3. **Win probability**
4. **Win/loss size ratio** (does the win rate survive contact with expectancy?)
5. **Capital and margin efficiency**
6. **Execution simplicity** (fewer legs = lower cost, fewer things to get wrong)
7. **Fit with the current regime** (low VIX ~11.7, VRP inverted — see `01` §1.8, `02` §A3)

---

## ⚠️ FIRST: THE ARITHMETIC THAT GOVERNS EVERYTHING

Before the ranking, the maths that determines whether any of it works. **This section is more valuable than the ranking itself.**

### Break-even win rate formula `[T4-STRUCTURAL]`

For a credit strategy managed with a profit target and a stop:

```
Break-even win rate  =  Stop size / (Stop size + Profit target)
```

Both expressed as multiples of the credit received.

| Profit target | Stop loss | **Break-even win rate** |
|---|---|---|
| 50% of credit | 100% of credit | **66.7%** |
| 50% of credit | 150% of credit | **75.0%** |
| **50% of credit** | **200% of credit** | **80.0%** |
| 50% of credit | 300% of credit | 85.7% |
| Hold to expiry (100%) | Full max loss | see below |

### Worked example — a 20-delta bull put spread

```
Nifty ~24,200 · SELL 23,900 PE / BUY 23,700 PE
Width 200 · Credit 30 · Max loss 170 · Lot 65
```

**Case 1 — held to expiry, no management:**
- Break-even win rate = 170 / (170 + 30) = **85.0%**
- A 20-delta short strike implies ~**80%** probability of expiring OTM
- **80% < 85% ⇒ structurally NEGATIVE expectancy, before costs.**

**Case 2 — managed at 50% profit / 200% stop:**
- Win = +15 pts, Loss = −60 pts
- Break-even win rate = 60 / (60 + 15) = **80.0%**
- Vendor-claimed realised win rate for this management: ~75%
- **75% < 80% ⇒ still NEGATIVE, before costs.**

### What this means — read it twice

**The commonly published "sell 20-delta spreads, take 50%, stop at 200%" recipe does not have positive expectancy from the delta arithmetic alone.** A 65–75% win rate sounds excellent and is mathematically insufficient for the loss sizes involved.

**So where could an edge come from?** Only one place: the **Variance Risk Premium** — implied volatility being systematically higher than subsequently realised volatility, which makes short strikes get breached *less often* than their delta implies.

The evidence on that `[T2-RESEARCH]` (Nifty 50, 43M one-minute bars, Aug 2022 – Mar 2026):
- VRP positive on **74.9%** of days, mean **+1.208 vol points** ✅ the edge has existed
- Transaction costs consume **27.6%** of it ⚠️
- Left-tail asymmetry **1.975×** — losses are nearly twice as fat as a normal distribution predicts ⚠️
- **Early 2026: structural inversion, mean VRP −4.63 vol points** 🚨

**Bottom line: the theoretical edge behind every premium-selling strategy in this knowledge base was measured as positive over 2022–2025 and as inverted in early 2026.** Anyone starting premium selling today is starting into a regime where the underlying edge is, on the most recent evidence available, not present.

This does not mean "don't trade." It means: **backtest on recent data, not just the favourable years, and size for the possibility that the edge is currently absent.**

---

## THE RANKING

### 🥇 RANK 1 — BULL PUT / BEAR CALL CREDIT SPREAD (`03` §A2)

| Attribute | Value |
|---|---|
| **Max loss** | ✅ **Capped** — (width − credit) × lot, known in rupees at entry |
| **Win rate** | 60–75% `[T3-VENDOR]` |
| **Legs** | 2 (lowest cost of any credit structure) |
| **Margin** | Low (hedged) |
| **Cycle stage** | S1–S4 |
| **Break-even WR needed** | 75–80% depending on management ⚠️ |

**Why #1:** best combination of capped risk, decent win probability, minimum transaction cost, low margin, and — critically — **it is the easiest strategy in this knowledge base to backtest correctly.** Two legs, mechanical rules, no adjustment logic. You can validate or kill it quickly.

**The honest caveat:** per the arithmetic above, the standard parameters are marginal. The backtest must find parameters (delta, width, target, stop) where realised win rate clears the break-even line **after costs**. If it can't, that is a real and valuable answer.

→ **Full specification: `10-FIRST-STRATEGY-SPEC.md`**

---

### 🥈 RANK 2 — IRON CONDOR (`03` §A1)

| Attribute | Value |
|---|---|
| **Max loss** | ✅ **Capped**, one side only |
| **Win rate** | 65–80% `[T3-VENDOR]` |
| **Legs** | 4 (2× the cost of Rank 1) |
| **Margin** | Low (hedged both sides) |
| **Cycle stage** | S1–S3 |

**Why #2:** highest claimed win rate among defined-risk structures and market-neutral, so no directional call is required. Ranked below the credit spread purely on **cost and complexity** — four legs means eight chargeable events per round trip (`01` §1.4), which materially raises the break-even bar.

**Regime note:** needs ADX < 20 and IVR > 30. At the current VIX of ~11.7, the credit available is thin relative to the wing width. **Marginal fit right now.**

---

### 🥉 RANK 3 — LONG BUTTERFLY (`06` §D1)

| Attribute | Value |
|---|---|
| **Max loss** | ✅ **The debit paid — ₹1,625 in the worked example** |
| **Win rate** | 55–65% `[T3-VENDOR]`, generic not Nifty-specific |
| **Reward : Risk** | **3 : 1** |
| **Margin** | None — debit only |
| **Cycle stage** | S4–S5 |

**Why #3:** the **lowest absolute rupee risk of anything in this knowledge base**, and the only structure whose reward-to-risk ratio (3:1) means a moderate win rate is genuinely sufficient. Break-even win rate at 3:1 is just **25%**.

Ranked below the credit spreads only because the win rate is lower and the profit zone is narrow. **But for a trader who explicitly wants to limit downside while learning, this is arguably the best instrument on the entire list** — see the recommendation note at the end of this file.

---

### RANK 4 — CALENDAR SPREAD (`06` §D3)

| Attribute | Value |
|---|---|
| **Max loss** | ✅ Net debit |
| **Win rate** | `[T5-UNQUANTIFIED]` — none found |
| **Greeks** | **+theta AND +vega** (rare combination) |
| **Cycle stage** | Spans two cycles |

**Why #4 and why it's flagged:** the only theta-positive structure here that **benefits from a rise in IV**. With VIX at ~11.7 near the low end of its band, mean reversion upward is the more likely move, and that would help a calendar while hurting every condor and straddle on this list.

**Held at rank 4 solely because no win-rate evidence exists.** If backtesting confirms it, it arguably belongs higher in the current regime. **Worth testing second, after Rank 1.**

---

### RANK 5 — 0DTE DEFINED-RISK CREDIT SPREAD (`03` §A4)

| Attribute | Value |
|---|---|
| **Max loss** | ✅ Capped |
| **Win rate** | `[T5-UNQUANTIFIED]` |
| **Window** | 11:00–13:30, flat by 14:00 |
| **Cycle stage** | S5 only |

Fast theta and a defined loss, but expiry-day gamma means the transition from "winning" to "max loss" can happen in minutes. **Only after Ranks 1–3 are proven.** Remember the SEBI +2% expiry ELM.

---

### RANK 6 — IRON FLY (`03` §A3)

Capped risk ✅, richer credit than a condor, but a narrow profit zone and no verified win rate `[T5]`. Deployed on S4–S5, it inherits expiry gamma risk. **Middle of the pack.**

---

### RANK 7 — ORB / DIRECTIONAL OPTION BUYING (`05` §C1)

| Attribute | Value |
|---|---|
| **Max loss** | ✅ **Premium paid — cannot exceed it, ever** |
| **Win rate** | **48.7%** `[T1-BACKTEST]` — 2,122 trades, 8+ years |
| **Profit factor** | 1.23 · Sharpe 1.16 · Max DD −11.2% |

**Why it's here despite a sub-50% win rate:** this is the **best-evidenced strategy in the entire knowledge base by a wide margin** — 2,122 trades over 8+ years, profitable in 8 of 9 years, with full metrics disclosed. Everything ranked above it rests on vendor claims with no sample size.

It fails the user's *win rate* criterion but passes the *low risk* criterion emphatically: **a bought option cannot lose more than its premium under any circumstance.** No gap, no margin call, no tail.

**Also note: with VIX at ~11.7, options are historically cheap to buy.** The current regime is more favourable to buying than to selling — the opposite of what most retail commentary suggests.

**If the user's real priority is capital preservation while learning, this ranks higher than its win rate implies.**

---

### RANK 8 — PULLBACK + BREAKOUT COMBO (`05` §C5)

65% win rate, 1:2 R:R, `[T2-RESEARCH]`, defined risk ✅. **Only 53 trades** — sample too small to size against. Strong *filter design* (time windows, volume thresholds, spread limits) worth borrowing even if the strategy itself isn't traded.

---

### RANK 9 — 9/21 EMA CROSSOVER (`05` §C4)

Defined risk ✅. Honest baseline win rate **45–50%** `[T3]`; the advertised 60–68% requires unquantified filters. Fine as a directional entry *trigger* inside a larger framework; weak as a standalone system.

---

### RANK 10 — VWAP FAMILY, BOLLINGER, RSI DIVERGENCE, PRICE-ACTION, SUPERTREND (`05` §C2, C3, C7)

Defined risk ✅ but **zero verified win rates** `[T5]`. Additionally, several quote 10–20 point targets against a ₹40–60/lot round-trip cost base — the cost-to-target ratio is unfavourable before any edge is considered.

---

### RANK 11 — BROKEN WING BUTTERFLY (`06` §D2)

Elegant, defined risk, sometimes zero-risk on one side. Demoted purely on **complexity** — strike selection errors silently invert the risk profile. Revisit after Rank 1 is live and profitable.

---

## ❌ BELOW THE LINE — EXCLUDED BY THE RISK GATE

These fail criterion #1 (capped max loss). **They are excluded regardless of win rate.**

| Strategy | Win rate | Why excluded |
|---|---|---|
| **45-DTE ATM Short Straddle** | **~70%, or 86% VIX-filtered** `[T1]` | **Unbounded loss.** One backtested trade lost >1,000 points *despite a stop*. Highest-quality evidence + worst risk shape. |
| Short Strangle | 68% `[T1]` | Unbounded. 60-cycle study: −24% DD from a 5-loss cluster; modelled 12% index fall = 7.7× max profit. |
| 9:20 Short Straddle | 55–78% `[T3]` | Unbounded. Win rate *rises* as stop widens — the deception in plain sight. Documented edge decay since 2023. |
| Jade Lizard | Not stated | Hedged on the upside; naked on the downside, which is the tail that actually bites in Indian indices. |
| Front Ratio Spread | Not stated | Naked beyond the short strikes despite looking like a spread. |
| Naked single-leg selling | 30–40% `[T3]` | Unbounded + lowest win rate. No redeeming feature. |

**The single most important line in this document:** the highest credible win rate found anywhere in this research (**86%**) belongs to an **unhedged short straddle**. That is not a coincidence — it is the mechanical signature of a strategy that wins small, often, and loses catastrophically, rarely.

---

## Regime overlay — current fit (Aug 2026, VIX ~11.7, VRP inverted)

| Rank | Strategy | Current-regime fit |
|---|---|---|
| 1 | Credit Spread | ⚠️ Thin credit at low VIX. Test with a VIX/IVR entry filter. |
| 2 | Iron Condor | ⚠️ Credit thin relative to width. Marginal. |
| 3 | Long Butterfly | ✅ Debit structures are **cheap** when IV is low. Good fit. |
| 4 | Calendar | ✅✅ **Best structural fit** — +vega into a likely vol mean-reversion. |
| 7 | ORB / buying | ✅ Options cheap to buy at VIX 11.7. Favourable. |
| — | Any short premium | 🚨 VRP inversion + low VIX = the least favourable seller configuration. |

**Uncomfortable but honest conclusion:** the current regime favours **buying cheap options and debit structures** more than it favours the premium-selling strategies that dominate the "high win rate" lists. The user's instinct toward high-win-rate selling and the market's current state are pointing in opposite directions.

---

## The recommendation, stated plainly

**For backtesting first: Rank 1, the bull put / bear call credit spread.** It is capped-risk, cheap to execute, and — most importantly — the fastest strategy here to *prove or disprove*. Full spec in `10`.

**For live trading first, once backtested: consider starting with Rank 3, the long butterfly, at one lot.** Max loss of roughly ₹1,600 per lot means the tuition cost of learning expiry dynamics is bounded at an amount that cannot hurt. The 3:1 reward-to-risk means a 25% win rate breaks even — a far more forgiving bar than the 80% the credit spread needs.

**What not to do:** do not start with the 86% win-rate straddle. That number is real, it is the best-evidenced number in this research, and it is attached to the structure most capable of ending a trading account.

---

## Reality anchor `[T2-RESEARCH]` — SEBI FY22

- **91.1%** of individual F&O traders had net losses after costs
- Average loss per losing trader: **₹1.1 lakh**
- **71%** of aggregate retail losses (₹36,528cr of ₹51,689cr) was **transaction cost**, not bad directional calls
- Only **1–2%** cleared >₹1 lakh profit after costs
- **Profitable traders traded LESS frequently** — the opposite of a scalping cadence

The last point deserves weight. The data says selectivity beat activity. Every strategy in this knowledge base that fires 10–20 times a day is fighting that finding.
