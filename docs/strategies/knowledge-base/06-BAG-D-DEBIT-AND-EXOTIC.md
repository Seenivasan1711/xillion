---
doc_id: 06-BAG-D
title: "BAG D — Debit Structures and Multi-Leg Exotics"
topic: butterflies, calendars, ratio spreads, BWB, ZEBRA — low capital, defined risk, specific views
risk_class: MOSTLY DEFINED
compiled: 2026-08-24
use_when: User has a precise view (a pinning level, an IV-differential view) or very small capital
---

# BAG D — DEBIT STRUCTURES AND EXOTICS

These structures trade a **lower win rate for an outstanding reward-to-risk ratio and very low capital**. They are the specialist tools: each expresses a narrower view than a condor or a credit spread, and pays much better when that view is right.

**Relevance to the user's objective:** mixed. Risk is defined and capital is tiny (a Nifty butterfly can risk ~₹1,625 total), which is excellent. But win rates are lower, because these need the index to land in a specific place. Best treated as **occasional high-conviction additions**, not the core strategy.

---

## D1. LONG BUTTERFLY SPREAD

**Cycle stage:** S4–S5 (needs low time value to be cheap).
**Market view:** Index pins at a specific level at expiry.
**Risk class:** DEFINED ✅ | **Capital: lowest in this knowledge base**

### Structure
1:2:1 ratio, equidistant strikes:
- Buy 1 lower strike · Sell 2 middle strike · Buy 1 upper strike (all calls, or all puts)

### Worked Nifty example `[T3-VENDOR]` (spot 22,500, 1 DTE)
```
BUY  22,400 CE @ 115
SELL 2× 22,500 CE @ 55 each  (= 110 credit)
BUY  22,600 CE @ 20
Net debit: 25 points
```
| Metric | Value (at current Nifty lot of 65) |
|---|---|
| Max profit | (100 − 25) × 65 = **₹4,875** |
| **Max loss** | **₹1,625** (the net debit — that's all) |
| Breakevens | 22,375 / 22,625 |
| **Reward : Risk** | **3 : 1** |

> ⚠️ **Correction to source:** the original source quoted ₹625 max loss / ₹1,875 max profit, which implies a lot size of 25. **Current Nifty lot size is 65** (`01` §1.3), so the rupee figures are 2.6× larger. The **3:1 ratio is unaffected** by lot size. This is a live example of the stale-source problem in `11`.

### Why this matters for a low-capital, risk-averse trader
**Max loss is the debit paid — ₹1,625 in this example.** No margin, no gap risk beyond that number, no possibility of a larger loss under any market outcome. For someone who wants to *learn expiry-day dynamics without risking real damage*, the butterfly is arguably the safest instrument in this entire knowledge base.

The trade-off: it needs the index to finish inside a ~250-point window. Win rate `[T3-VENDOR]` quoted at **55–65%** in one ranking, but that figure is generic, not Nifty-specific — treat as T3/T5.

### Best use
- Expiry-day pinning plays around high-OI round numbers (`02` §D1, §C6)
- Gamma effects near the centre strike maximise profit at expiry
- Extremely cheap way to express "I think it closes near 24,200"

---

## D2. BROKEN WING BUTTERFLY (BWB)

**Cycle stage:** S2–S4.
**Market view:** Mild directional bias with a pinning expectation.
**Risk class:** DEFINED on one side, reduced or eliminated on the other ✅

### Structure `[T3-VENDOR]`
Like a butterfly but with **unequal wing spacing** — the gap between the lower and middle strike ≠ the gap between middle and upper.

**Bullish BWB (calls), Nifty ~23,000 example:**
```
BUY  22,800 CE
SELL 2× 23,000 CE
BUY  23,250 CE      ← wider wing = the "broken" side
```

### The key property
Because the wings are unequal, the structure **can often be entered for a net credit**. When the credit exceeds the max loss on the broken wing, **one side of the trade has effectively zero risk** — you either profit or scratch on that side.

### When to use `[T3-VENDOR]`
- Moderately directional view (small-to-moderate expected move)
- Sideways-to-slightly-trending markets
- Put-based bearish BWBs benefit most when IV is elevated (richer credit)

### Win rate
`[T5-UNQUANTIFIED]` — not provided by any source found.

### Honest assessment
BWB is genuinely elegant and is a favourite of experienced defined-risk traders. **It is not a beginner structure** — the credit/risk relationship depends on precise strike selection and can silently invert if the strikes are chosen carelessly. Recommend only after the user is comfortable with A2 credit spreads.

---

## D3. CALENDAR SPREAD (Horizontal Spread)

**Cycle stage:** Spans two cycles by definition.
**Market view:** Index stays near a strike short-term; also a view on the IV term structure.
**Risk class:** DEFINED ✅ (max loss = net debit)

### Structure
- Sell a near-dated option (e.g. current weekly)
- Buy a later-dated option at the **same strike** (e.g. next weekly or monthly)

### Mechanism
The near leg decays faster than the far leg (theta accelerates into expiry). The spread profits from that differential.

**Positive theta, positive vega** — an unusual combination. Most theta-positive structures are vega-negative. That makes the calendar the natural choice when you want theta income *without* being hurt by an IV rise.

### Current-regime relevance ⭐
With India VIX at ~11.7 (`01` §1.8) — a **low** reading — a rise in IV is more likely than a further collapse. A calendar's positive vega means an IV increase *helps* it, whereas it would hurt an iron condor or short straddle.

**This makes calendars one of the more structurally coherent selling-adjacent strategies in the current low-VIX environment.** Flagged for backtesting attention.

### Constraint under the current expiry regime
Post-Sep-2025, Nifty has weekly Tuesday expiries, so weekly-vs-weekly calendars are available. But **Bank Nifty / FinNifty / MidCpNifty are monthly-only** (`01` §1.1) — calendar spreads on those now require month-to-month legs, a very different (and slower) trade.

### Win rate
`[T5-UNQUANTIFIED]` — no backtest with disclosed metrics found for Nifty weeklies.

### Failure mode
A large directional move away from the strike. Both legs lose value, and the spread collapses toward zero. Also vulnerable if IV in the near leg rises faster than the far leg (rare but possible around events).

---

## D4. RATIO SPREADS

**Risk class:** ⚠️ **VARIABLE — often UNDEFINED. Read carefully.**

### Structure
Buy 1 option and sell 2 (or more) further-OTM options of the same type.

- **Front ratio spread** (sell more than you buy): collects credit, **carries naked risk** beyond the short strikes
- **Back ratio spread** (buy more than you sell): pays debit, defined risk, profits from a large move

**Critical distinction:** a front ratio spread is essentially a partially-hedged naked position. Despite looking like a "spread", it belongs risk-wise in **Bag B**, not Bag D. The extra short leg is unhedged.

**Recommendation:** do not use front ratio spreads for the stated low-risk objective. Back ratios are defined-risk but have low win rates (they need a big move).

---

## D5. ZEBRA / OTHER MULTI-LEG STRUCTURES

`[T5-UNQUANTIFIED]` — noted for completeness.

Sources describe ZEBRA (Zero Extrinsic Back Ratio) and related four-leg constructions as ways to build synthetic stock-like exposure with defined risk. Descriptions found in research were inconsistent and partly conflated with iron condor mechanics.

**Recommendation: skip.** Execution complexity, wider spreads across four legs, and higher cumulative transaction cost (`01` §1.4) outweigh the theoretical benefit for a retail trader on Indian index options. Revisit only after A2 and A1 are proven profitable in live trading.

---

## D6. PROTECTIVE PUT / COLLAR

**Risk class:** DEFINED ✅

- **Protective put:** own the underlying, buy a put as insurance. `[T3-VENDOR]` win rate quoted 50–60%.
- **Collar:** protective put financed by selling a covered call.

Portfolio-hedging tools rather than income strategies. Relevant only if the user holds an equity/ETF portfolio alongside. **Not applicable to index-options intraday trading.**

---

## BAG D SUMMARY TABLE

| # | Structure | Capital | Max loss | Win rate | Tier | Best for |
|---|---|---|---|---|---|---|
| **D1** | **Long Butterfly** | **Lowest (₹1,625 ex.)** | **Debit only** | 55–65% | T3/T5 | Expiry pinning; safest learning tool |
| D2 | Broken Wing Butterfly | Low | Defined (one side ~0) | Not stated | T5 | Directional + pinning, experienced only |
| **D3** | **Calendar Spread** | Low–moderate | **Debit only** | Not stated | T5 | **Low-VIX regime (now); +theta +vega** |
| D4 | Front ratio spread | Moderate | ⚠️ **Undefined** | Not stated | T5 | ❌ Not for this objective |
| D4b | Back ratio spread | Low | Debit only | Not stated | T5 | Big-move expectation |
| D5 | ZEBRA / 4-leg exotics | Moderate | Varies | Not stated | T5 | ❌ Skip — cost and complexity |
| D6 | Protective put / Collar | High (needs stock) | Defined | 50–60% | T3 | Portfolio hedging only |

---

## Two flags for the current regime (Aug 2026)

1. **D3 Calendar Spread** deserves backtesting attention because it is **positive vega in a low-VIX environment** — it benefits if volatility mean-reverts upward from ~11.7, whereas most premium-selling structures are hurt by exactly that.

2. **D1 Long Butterfly** deserves attention as the **lowest-capital, lowest-absolute-risk way to trade expiry day**. If the user wants to learn S5 (expiry) dynamics — which is where the biggest premium and biggest danger both live — doing it with a ~₹1,625 max loss is a far better education than doing it with an unhedged short position.
