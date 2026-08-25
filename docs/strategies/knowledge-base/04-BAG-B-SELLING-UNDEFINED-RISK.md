---
doc_id: 04-BAG-B
title: "BAG B — Premium Selling, UNDEFINED RISK"
topic: naked credit strategies; highest win rates in the knowledge base, unbounded loss
risk_class: UNDEFINED (no maximum loss)
compiled: 2026-08-24
use_when: Reference and comparison. NOT recommended for the stated low-risk objective.
warning: Every strategy in this bag can lose more than the account holds.
---

# BAG B — PREMIUM SELLING WITH UNDEFINED RISK

## ⚠️ Read this before anything else on this page

**This bag contains the highest win rates in the entire knowledge base — 65% to 86%. It is also the bag that bankrupts people.**

These two facts are the same fact. A naked short option wins often *because* it collects a small premium against a large, rare, unbounded loss. The high win rate is not evidence of safety; it is the *mechanical consequence* of the risk shape.

**The user's stated objective is "very low risk with high winning probability." Bag B satisfies the second half and violates the first half completely.** These strategies are documented here so the AI can (a) recognise them when the user encounters them online, (b) explain why the attractive win rates are misleading, and (c) point to the Bag A equivalent that achieves a comparable win rate with a capped loss.

**Default position: do not recommend anything in this bag.** If the user explicitly asks for it, lead with the tail-risk data below.

---

## B1. SHORT STRADDLE (naked)

**Cycle stage:** S3–S5 most common; also traded as a monthly 45-DTE position.
**Market view:** Index stays near current level.
**Risk class:** UNDEFINED ❌

### Structure
Sell ATM Call + Sell ATM Put, same strike, same expiry. No wings.

### Time-based variant — the "9:20 straddle"
The most widely traded systematic options strategy in India.

**Rules:** at 9:20 AM sell the ATM call and ATM put on the current weekly, exit 3:10–3:20 PM or on stop.

**Entry-time comparison `[T3-VENDOR]`:**

| Entry | Character |
|---|---|
| **9:20 AM** | The canonical entry. Highest premium, highest gap exposure. |
| 9:30 AM | 5–10% lower premium, marginally better win rate (+2–3%) |
| 10:00–10:30 AM | 10–20% less premium, smoother equity curve, higher win rate |
| 1:00 PM (expiry day) | Thin premium (30–50 pts), quoted 75–80% win rate |

**Stop-loss sensitivity `[T3-VENDOR]` — the key table:**

| Stop loss | Win rate | Loss character |
|---|---|---|
| 25% of premium | 65–70% | Avg loss 2–3× avg win |
| 30% of premium | 60–65% | Improved R:R |
| 50% of premium | 72–78% | Larger individual losses |
| **No stop** | **55–60%** | **Catastrophic tail losses** |

**Read this table carefully:** widening the stop *raises* the win rate and *worsens* the loss size. This is the central deception of high-win-rate selling. A 78% win rate here is worse than a 65% win rate, not better.

### 45-DTE monthly variant — ⭐ THE BEST EVIDENCE IN THIS KNOWLEDGE BASE `[T1-BACKTEST]`

Zerodha study, Jan 2019 – Jun 2026, ~86 monthly cycles, **net of brokerage, STT and statutory charges**:

**Rules:** enter 45 calendar days before monthly expiry at 3:15 PM; sell ATM straddle; exit at 50% of credit (profit), 200% of credit (stop), or 21 DTE (time stop); hourly close checks.

| Variant | Win rate | Note |
|---|---|---|
| **ATM straddle** | **~70%** | Best avg P&L — highest premium collected |
| 30-delta strangle | ~62% | ~50% lower avg P&L |
| 16-delta strangle | ~57% | 7.3 points avg |

**Findings that matter more than the win rate:**
- Profitable in **5 of 7 full years**
- **One trade lost over 1,000 points despite the stop loss** — gap risk defeats stops
- **VIX filter: entries above the 75th percentile of VIX → ~86% win rate** (vs ~70% unfiltered) with reduced drawdown
- Author's own emphasis: *"position sizing matters most"*; recommends max 1.5× leverage against **notional** exposure, not against margin

**The 86% figure is the highest credible win rate in this knowledge base. It belongs to an unhedged short straddle. Every time the user is tempted by it, the 1,000-point single-trade loss belongs in the same sentence.**

### Strategy decay `[T3-VENDOR]`
The 9:20 straddle's edge visibly degraded in 2023, attributed to (a) crowding as the strategy became popular, and (b) a persistent low-volatility regime. One source suggests shifting entry to 10:30 AM as a partial remedy.

**Generalisable lesson: a published, popular, mechanical options strategy decays.** Any backtest of a widely-known setup is measuring a period when it was less crowded than it is now.

---

## B2. SHORT STRANGLE (naked)

**Cycle stage:** S1–S4.
**Market view:** Index stays inside a range, wider than a straddle's.
**Risk class:** UNDEFINED ❌

### Structure
Sell OTM Call + Sell OTM Put at different strikes. Lower credit than a straddle, wider profit zone.

### Tail-risk evidence `[T1-BACKTEST]` — 60-cycle study (US SPY data; mechanism transfers, magnitudes do not)

**Rules:** sell 16-delta put and call, 30–45 DTE, enter when IV rank > 35, close at 50% max profit, hard stop at 2× credit.

| Metric | Value |
|---|---|
| Win rate | **68%** (41 of 60) |
| Average credit | $520 |
| Net per cycle | +$62 |
| 60-cycle total | +$3,725 |
| **Max drawdown** | **−24%** |
| Worst single loss | −$1,040 (full stop) = two winning cycles erased in 9 days |

**The decisive finding:** the study computed that a 12% index decline would produce approximately **−$3,980 — about 7.7× the maximum possible profit of $520.**

> "The best case is known and small, the worst case is unknown and large."

**Loss clustering:** the entire −24% drawdown came from **five consecutive losses**, not from evenly distributed bad luck. Position sizing must survive the streak, not the average.

Author's explicit warning: **never scale up after a winning streak** — the conditions that produce easy wins are the conditions that precede drawdowns.

### Indian variant `[T5-UNQUANTIFIED]`
"Sell OTM+2 CE and PE on the Nifty weekly" is a commonly described retail setup. A backtest was published but the results section was not retrievable. **No verified Indian win rate exists for this in my research.**

---

## B3. NAKED SINGLE-LEG SELLING

**Risk class:** UNDEFINED ❌❌ (worst in the knowledge base)

Selling a bare call or bare put with no hedge.
- `[T3-VENDOR]` One ranking listed naked options **last of 10 strategies**, win rate 30–40%, marked "advanced traders only"
- A naked short call has **theoretically unlimited** loss
- Margin is the highest of any structure here

**No circumstance in this knowledge base recommends this for the user's stated objective.**

---

## B4. JADE LIZARD

**Risk class:** PARTIALLY DEFINED ⚠️ (no upside risk, undefined downside)

### Structure `[T3-VENDOR]`
Sell 1 OTM Put + Sell 1 OTM Call + Buy 1 further-OTM Call.

- The long call caps **upside** risk entirely — if total credit exceeds the call spread width, there is *no* upside risk at all
- **Downside remains naked below the short put** — theoretically large loss
- Use case: neutral-to-mildly-bullish, high IV

**Why it sits in Bag B despite the hedge:** the hedge is on the wrong side. Indian index crashes are downside events, and the put skew (`02` §A4) exists precisely because that is where the risk is. A jade lizard hedges the tail that rarely bites and leaves open the one that does.

---

## BAG B SUMMARY TABLE

| # | Strategy | Win rate | Tier | Max loss | Verdict for this user |
|---|---|---|---|---|---|
| B1a | 9:20 Short Straddle | 55–78% | T3 | **Unbounded** | ❌ Reject |
| B1b | 45-DTE ATM Straddle | ~70% (86% VIX-filtered) | **T1** | **Unbounded** | ❌ Reject — best evidence, worst risk shape |
| B2 | Short Strangle | 68% | T1 | **Unbounded** | ❌ Reject |
| B3 | Naked single leg | 30–40% | T3 | **Unbounded** | ❌❌ Reject |
| B4 | Jade Lizard | Not stated | T5 | Unbounded downside | ❌ Reject |

---

## The Bag A ↔ Bag B translation table

Every Bag B strategy has a defined-risk cousin. **When the user is drawn to a Bag B win rate, redirect here:**

| Bag B (undefined) | → | Bag A equivalent (defined) | Cost of the hedge |
|---|---|---|---|
| Short Straddle | → | **Iron Fly** (A3) | Some credit given up for wings |
| Short Strangle | → | **Iron Condor** (A1) | Some credit given up for wings |
| Naked short put | → | **Bull Put Spread** (A2) | Some credit given up for the long put |
| Naked short call | → | **Bear Call Spread** (A2) | Some credit given up for the long call |
| Expiry-day naked sell | → | **0DTE Credit Spread** (A4) | Some credit given up for the wing |

**The hedge always costs credit. That cost is the price of knowing your worst case. For a trader who explicitly wants low risk, it is the correct trade to make — and it is also what makes the position affordable, because hedged margin is dramatically lower (`01` §1.5).**
