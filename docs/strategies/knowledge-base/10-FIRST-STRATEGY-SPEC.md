---
doc_id: 10-FIRST-SPEC
title: "First Strategy — Full Backtest Specification"
topic: complete mechanical spec for the recommended starting strategy
strategy: Nifty/Sensex weekly Bull Put / Bear Call Credit Spread (defined risk)
compiled: 2026-08-24
use_when: User asks what to backtest first, or how to implement the recommendation
---

# 10 — FIRST STRATEGY: DEFINED-RISK WEEKLY CREDIT SPREAD

## Why this one

Selected from `07` Rank 1 against the user's stated priorities:

| Requirement | How this meets it |
|---|---|
| **Very low risk** | Max loss capped in rupees at entry. No gap, circuit move, or overnight event can exceed it. |
| **High win probability** | 60–75% claimed `[T3]`; the backtest exists to verify or refute this |
| **Don't need huge amounts** | Consistent small credits; hedged margin is a fraction of naked |
| **Will backtest first** | **2 legs, fully mechanical, no adjustment logic** — the fastest structure here to validate or kill |

**The critical thing this spec is designed to discover:** whether realised win rate clears the **break-even win rate** (`07` §Arithmetic) after full Indian transaction costs. The honest expectation is that at default parameters it may not — and finding that out on a spreadsheet is the entire point.

---

## 1. INSTRUMENT

**Primary: NIFTY weekly (Tuesday expiry), lot 65**
**Secondary — test in parallel: SENSEX weekly (Thursday expiry), lot 20**

⭐ **Sensex is materially better suited to small capital.** With a lot of 20 vs Nifty's 65, the same 200-point-wide spread carries roughly **one-third the rupee risk**. If the account is under ~₹5 lakh, Sensex may be the only instrument where honest 1% position sizing yields a tradeable lot count. Test both; do not assume Nifty is the default.

---

## 2. CYCLE STAGE AND ENTRY TIMING

- **Entry stage: S3 (Friday for Nifty / Tuesday for Sensex), 4 DTE**
  - Rationale: theta is meaningfully accelerated, gamma has not yet exploded (`01` §1.2). Best risk-adjusted seller window in the cycle.
- **Entry time: 09:45–10:30 IST**
  - After the opening auction distortion, before the midday liquidity lull
- **Variants to test:** S2 (5 DTE) and S4 (1 DTE) as separate arms

---

## 3. DIRECTION SELECTION

```
Determine trend on the 15-min chart at entry time:

IF price > VWAP AND 20EMA > 50EMA        → BULL PUT SPREAD (sell downside)
ELIF price < VWAP AND 20EMA < 50EMA      → BEAR CALL SPREAD (sell upside)
ELSE (no clear trend)                     → SKIP, or test an IRON CONDOR arm (both sides)
```

**Why the aligned side:** a bull put spread in an uptrend wins if the market rises, goes sideways, *or* falls modestly. Three outcomes out of four. This is the property that lets a directional call be wrong without being fatal.

---

## 4. STRIKE SELECTION — test all three arms

| Arm | Short strike | Approx POP | Expected character |
|---|---|---|---|
| **A — Conservative** | 10–15 delta | ~85–90% | High WR, thin credit |
| **B — Balanced ⭐** | 20 delta | ~80% | Primary arm |
| **C — Aggressive** | 30 delta | ~70% | Fat credit, lower WR |

**Long strike (the wing) — test three widths:**
- 100 points (Nifty) / 300 points (Sensex) — cheapest risk, smallest credit
- 200 points (Nifty) / 500 points (Sensex) — baseline
- 300 points (Nifty) / 700 points (Sensex) — most credit, largest max loss

**Fallback if delta data is unavailable:** select the short strike at approximately **1.0 × the ATM straddle price** away from spot (`02` §D5). The ATM straddle is the market's own expected-move estimate and requires no model.

---

## 5. ENTRY FILTERS — the arms that matter most

Test the strategy **with and without** each filter. Per the Zerodha 45-DTE study, the VIX filter was the single largest improvement found in any research reviewed (~70% → ~86% win rate).

```
FILTER 1 — VOLATILITY (highest priority to test)
  ENTER only if india_vix > 40th percentile of trailing 252 days
  Aggressive variant: > 75th percentile   ← the one that produced 86% in the 45-DTE study
  Rationale: selling into low IV is selling cheap insurance

FILTER 2 — TREND ALIGNMENT
  Only sell the side aligned with the 15-min trend (see §3)

FILTER 3 — EVENT VETO
  SKIP if RBI policy / CPI / Fed / Budget / major results fall before exit

FILTER 4 — CREDIT ADEQUACY
  REQUIRE credit >= 15% of spread width
  If the market won't pay 15% of the width, the risk/reward is not there

FILTER 5 — LIQUIDITY
  REQUIRE bid-ask spread < 0.1% of spot on both legs
```

---

## 6. MANAGEMENT — test all combinations

```
PROFIT TARGET   : 50% of credit  |  75% of credit  |  hold to expiry
STOP LOSS       : 100% of credit |  150%           |  200%  |  none
TIME STOP       : exit at 1 DTE (avoid expiry-day gamma entirely)
```

**Break-even win rate for each combination `[T4-STRUCTURAL]` — compute and print this next to every result:**

| Target | Stop | Break-even WR |
|---|---|---|
| 50% | 100% | **66.7%** |
| 50% | 150% | **75.0%** |
| 50% | 200% | **80.0%** |
| 75% | 150% | **66.7%** |
| 75% | 200% | **72.7%** |

**The backtest's single most important output is: realised WR vs break-even WR, after costs.** Everything else is secondary.

---

## 7. POSITION SIZING

```
max_loss_per_lot = (width − credit) × lot_size
lots = floor((risk_pct × capital) / max_loss_per_lot)
IF lots < 1 → narrow the width, switch to Sensex, or skip
```

**Worked, ₹3,00,000 capital at 1% risk (₹3,000):**

| Instrument | Width | Credit | Max loss/lot | Lots at 1% |
|---|---|---|---|---|
| Nifty | 200 | 30 | 170 × 65 = ₹11,050 | **0 — too big** |
| Nifty | 100 | 18 | 82 × 65 = ₹5,330 | **0 — too big** |
| Nifty | 50 | 10 | 40 × 65 = ₹2,600 | **1** ✅ |
| Sensex | 500 | 80 | 420 × 20 = ₹8,400 | **0 — too big** |
| Sensex | 200 | 35 | 165 × 20 = ₹3,300 | **0 — just misses** |
| **Sensex** | **100** | **18** | **82 × 20 = ₹1,640** | **1** ✅ |

**This table is the practical reason Sensex deserves a parallel test, and the reason `07` suggests the butterfly for live trading at small capital.**

---

## 8. COSTS TO MODEL (non-negotiable)

```
Per leg, per side:
  STT             : 0.15% of premium, SELL side only
  Brokerage       : ₹20 per order (or your broker's actual)
  Exchange charges: ~0.05% of premium
  GST             : 18% on (brokerage + exchange charges)
  Stamp duty      : ~0.003% of premium, buy side
  SEBI fees       : ~0.0001% of turnover

Credit spread = 2 legs × 2 (entry+exit) = 4 chargeable events
Slippage      : assume the unfavourable side of the spread on ALL 4
Stop fills    : assume NEXT OPEN, not the trigger price (gap modelling)
```

---

## 9. REPORTING — split every result by

- Cycle stage arm (S2 / S3 / S4)
- Delta arm (A / B / C)
- Width arm (narrow / base / wide)
- Management combination
- **VIX regime band** (<12, 12–15, 15–20, 20+)
- **Year — and 2019–2025 vs 2026-YTD separately** (the VRP inversion test, `09` Rule 11)
- Instrument (Nifty vs Sensex)

---

## 10. PASS / FAIL CRITERIA — decide these BEFORE running

**Deploy live only if ALL of:**

| # | Criterion | Threshold |
|---|---|---|
| 1 | Realised WR clears break-even WR, **after costs** | Margin ≥ 5 percentage points |
| 2 | Profit factor after costs | > 1.25 |
| 3 | Sample size | ≥ 100 trades |
| 4 | Walk-forward out-of-sample holds | Within 70% of in-sample |
| 5 | Max drawdown | < 15% of capital |
| 6 | Longest losing streak survivable at chosen size | Yes |
| 7 | Profitable in ≥ 60% of tested years **including 2026 YTD** | Yes |
| 8 | Costs as % of gross profit | < 40% |

**If criterion 1 or 7 fails, do not trade it.** Those two are the regime and arithmetic tests, and they are the ones most likely to fail.

---

## 11. IMPLEMENTATION PATH

1. **Screen fast on AlgoTest** — it supports multi-leg and delta-based strike selection natively. Run the arm matrix. Kill obviously dead combinations.
2. **Rebuild the survivors in Python** with your own cost and slippage model. Platform default cost assumptions are usually optimistic.
3. **Walk-forward** the survivors.
4. **Paper trade 20–30 trades** — this catches execution reality (fills, spreads, timing) that no backtest models.
5. **Go live at 1 lot minimum size**, and hold it there for at least 30 trades regardless of results.
6. **Track realised vs backtested win rate.** Divergence beyond ~10 percentage points means the backtest was wrong about something — stop and find out what.

---

## 12. WHAT SUCCESS AND FAILURE LOOK LIKE

**Success:** a parameter set where realised WR beats break-even WR by 5+ points after costs, holds out-of-sample, and stays positive in 2026 data.

**Failure — and the more likely outcome:** the strategy is marginal or negative after costs at every parameter set. **This is a good result.** It is obtained for the price of a few evenings rather than the ₹1.1 lakh SEBI records as the average losing F&O trader's year.

If it fails, the next things to test, in order:
1. **Calendar spread** (`06` §D3) — positive vega suits the current low-VIX regime
2. **Long butterfly** (`06` §D1) — 3:1 R:R means only a 25% win rate is needed to break even
3. **ORB directional** (`05` §C1) — the best-evidenced strategy in the knowledge base, though a buying strategy with a sub-50% win rate

---

## A closing note on the objective

The user wants high win probability and low risk. This spec is built to deliver exactly that **if the market is currently paying for it**. The research says the market paid for it from 2022 to 2025 and stopped paying in early 2026.

The purpose of this backtest is to find out which of those two worlds we are in — before capital is at risk, not after.
