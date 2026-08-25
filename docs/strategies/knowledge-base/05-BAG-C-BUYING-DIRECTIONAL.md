---
doc_id: 05-BAG-C
title: "BAG C — Option Buying and Directional Scalping"
topic: long premium strategies; defined risk, low capital, LOW win rate
risk_class: DEFINED (max loss = premium paid)
compiled: 2026-08-24
use_when: A directional edge is present; user has small capital; user accepts low win rate
---

# BAG C — OPTION BUYING / DIRECTIONAL SCALPING

## The risk-shape inversion

Bag C is the mirror image of Bags A and B:

| | Bag A/B (selling) | **Bag C (buying)** |
|---|---|---|
| Win rate | High (60–86%) | **Low (35–50%)** |
| Average win | Small | **Large** |
| Average loss | Large | **Small (capped at premium)** |
| Max loss | Capped / unbounded | **Always capped at premium paid** |
| Capital per trade | Margin (large) | **Premium only (small)** |
| Time works | For you | **Against you** |

**For the user's objective this is the wrong bag on win rate but the right bag on risk and capital.** A ₹5,000 option purchase can lose at most ₹5,000, no gap can change that, and no margin call can arrive. That is genuinely low risk in the absolute sense — the problem is that most of these trades lose.

**Do not dismiss Bag C entirely.** It is the correct bag when: capital is small, the user cannot meet selling margins, an event is expected, or IV is very low (as it is now — see `01` §1.8, VIX ~11.7, which makes options *cheap to buy*).

---

## C1. OPENING RANGE BREAKOUT (ORB) — best-evidenced directional strategy

**Cycle stage:** Any. **Window:** 09:15–09:45 formation, entry on break.
**Risk class:** DEFINED ✅

### The 8-year Nifty study `[T1-BACKTEST]` — the single most complete backtest found

**Rules:** opening range = first two 15-min candles (09:15–09:45). Buy break above range high / sell break below range low. Stop at opposite end of range. Target 2R. **Hard exit 2:30 PM.** One trade per day. Skip days where the range is narrower than 40 Nifty points.

**Results, Jul 2017 – Mar 2026:**

| Metric | Value |
|---|---|
| Total return | **+91.6%** |
| **Win rate** | **48.7%** |
| Profit factor | 1.23 |
| Sharpe | 1.16 |
| Max drawdown | −11.2% |
| Total trades | 2,122 (~236/yr) |
| Avg win / avg loss | +0.48% / −0.37% |

**Why a 48.7% win rate is profitable:** average win (+0.48%) exceeds average loss (−0.37%). This is the cleanest demonstration in the knowledge base that **win rate alone is not the objective**. A sub-50% strategy beat several 70% strategies on risk-adjusted terms.

**Sub-findings:**
- Profitable in **8 of 9 full years**. Only 2023 lost (−1.1%) — a choppy sideways year, the regime that kills breakouts.
- **Short trades produced ~75% of total profit**
- **Friday alone produced 40%+ of annual profit**
- Wider opening ranges (~144 pts) returned +30.3% vs narrow ranges (~35 pts) at +18.6%
- Only **13% of trades reached the full 2:1 target**; **51% were time-stopped at 2:30 PM**

### Shorter-window variants `[T1-BACKTEST]`
5-min opening range (first six bars), long only, one entry/session, Nifty futures, 42 signals, Jul–Oct 2025:

| Variant | Win rate | Avg R | Return | Max DD |
|---|---|---|---|---|
| Fixed 1.5R cap | 57.1% | 0.28 | 2.88% | −1.02% |
| RSI ≥70 exit | **71.4%** | **0.18** | 1.54% | −0.62% |

**Note the inversion again:** the 71.4% win-rate variant delivered a *lower* average R and *lower* return than the 57.1% variant. The source's own conclusion: *"average R per trade matters more than win rate."*

### Applying ORB to options
The backtests above are on the **index/futures**, not on option premiums. To trade it via options:
- Buy ATM or slightly-ITM (delta 0.40–0.60) weekly option in the breakout direction
- ⚠️ **The index backtest's results do not transfer directly.** Theta, IV changes and bid-ask spread all sit between the index move and your P&L. Re-backtest on actual option premium data — see `09`.

### Failure mode
Choppy sideways markets producing false breaks. 2023 is the documented example.

---

## C2. VWAP PULLBACK

**Cycle stage:** Any. **Window:** 09:50–11:30, 13:30–14:45.
**Risk class:** DEFINED ✅ | **Win rate:** `[T5-UNQUANTIFIED]` not stated by any source

### Rules `[T3-VENDOR]`
- Price holding one side of VWAP; on a pullback into VWAP with a confirming candle, buy CE (uptrend) or PE (downtrend)
- Strike: ATM / slightly ITM, delta 0.40–0.60, current weekly
- Stop: ₹10–15/lot, or VWAP itself
- Target: ₹10–20/lot (≈15–25 Nifty pts). Book 70%, trail rest at entry
- Timeframe: 1-min or 3-min

⚠️ **Cost warning:** a ₹10–20 target against a cost base that can run ₹40–60 per lot per round trip (`01` §1.4) is not obviously viable. Model costs before believing this setup.

---

## C3. VWAP RECLAIM / REJECTION / SQUEEZE

`[T3-VENDOR]` — three related setups, none with a stated win rate. R:R quoted as **1:2 to 1:3**.

| Setup | Trigger | Stop | Window |
|---|---|---|---|
| **Reclaim** | Above VWAP 45+ min, dips 1–3 candles (RSI-9 40–58), closes back above VWAP on rising volume | Below dip low, capped 0.5% | 09:50–11:30, 13:30–14:45 |
| **Rejection** | Below VWAP, rallies to test, fails; enter PE on rejection candle close | Above rejection wick, capped 0.3% | Same |
| **Squeeze breakout** | 4+ consecutive 5-min candles within 0.15% of VWAP on falling volume, then break outside ±1SD on 2× volume | Back inside VWAP | 11:30–13:30 (the lull) |

The squeeze variant is notable for deliberately targeting the midday lull when other setups go quiet.

---

## C4. 9/21 EMA CROSSOVER

**Cycle stage:** Any. **Timeframe:** 3-min entry, 15-min trend filter.
**Risk class:** DEFINED ✅

### Rules `[T3-VENDOR]`
- 15-min chart confirms trend (price vs VWAP / HH-HL structure)
- 9 EMA crosses 21 EMA on 3-min, crossover candle in trend direction, volume above prior 3–4 candles, price near VWAP
- Stop: low (long) / high (short) of the crossover candle; if the candle range is >60–70 Bank Nifty points, use the previous candle instead
- T1 = 1.5R (book 50%), T2 = 2–3R trailing the rest to breakeven
- Position risk 0.3–0.5% of account

### Win rate `[T3-VENDOR]`
- **Unfiltered baseline: 45–50%**
- **With five additional filters: 60–68%**
- Target R:R 2:1

⚠️ The 60–68% figure requires filters the source describes but does not fully quantify, and no sample size is given. The **45–50% baseline is the more honest planning number.**

---

## C5. PULLBACK + BREAKOUT COMBO (published research) `[T2-RESEARCH]`

Academic paper on Bank Nifty. **65% win rate, 1:2 R:R, 53 trades.**

### Pullback leg
- Trend defined by 2+ higher highs/lows
- Wait for pullback within **0.1% of VWAP**
- Enter on break of the last 15-second high/low with volume ≥ **1.4× average**
- Exit 50% at 0.5% profit, remainder at 0.75%

### Breakout leg
- Mark prior-day and current-day S/R on 5-min
- Identify tight consolidation (±0.1% range, volume <0.8× average)
- Enter on a close outside the range with volume ≥ **1.5× average** and **OI rise >5%**
- Retest entry within 3 candles; target 0.5%

### Filters (the valuable part)
- **Trade window 09:45–11:30 only** — "cleanest breakouts"
- Skip 09:15–09:30 (false breakouts), 12:30–13:30 (thin liquidity), 15:15–15:30
- Skip news events and sideways markets (±0.2% band held >15 min)
- **Require bid-ask spread < 0.1% of spot**

### Risk rules
Max 1% capital risk/trade · stop 0.3% against entry · move to breakeven after 0.3% profit · **halt after 3 consecutive losses or 5% capital loss**

⚠️ **53 trades is a small sample.** Tested on TradingView paper accounts across low/medium/high IV regimes. Needs independent replication before sizing real capital.

---

## C6. EXPIRY-DAY DIRECTIONAL SCALP (0DTE buying)

**Cycle stage:** S5. **Risk class:** DEFINED ✅ (premium only) but **extremely high variance**

### The three windows `[T3-VENDOR]`

| Window | Character | Use |
|---|---|---|
| **09:30–10:30** | Gamma elevated, directional moves produce outsized premium swings | **Best window for buying ATM** |
| 10:30–13:30 | Volatility compresses, theta accelerates | Bad for buying. Sell (hedged) instead. |
| 14:00–15:30 | Sharpest moves, but spreads widen dramatically | Highest risk both ways |

### Expiry ORB scalp `[T3-VENDOR]`
- 09:15–10:00, break of opening range with volume spike + VWAP confirmation
- **ATM strikes only** — never OTM on expiry day
- Stop: **30% of premium paid** (tight, because theta is working against you every minute)
- Target: 20–30 points premium gain
- **Time stop: exit within 30 minutes if target not hit**
- Max 2–3 trades per session

### Max pain convergence `[T3-VENDOR]`
- Between 12:00–14:00, if Nifty is 100+ points from max pain: buy ATM PE if above max pain, ATM CE if below
- Confirm with OI unwinding at extreme strikes
- Exit by 13:30; target max pain level or 50% of the distance
- ⚠️ Max pain is only considered meaningful in the last 1–2 sessions (`02` §D4). This is a **low-confidence, T5 setup.**

### Why buying beats selling on expiry morning
Gamma is the buyer's friend and the seller's enemy. In the 09:30–10:30 window, a buyer's small defined risk is paired with the largest gamma of the entire cycle. This is the one place in the knowledge base where a low-win-rate buying strategy has a coherent structural argument in its favour.

---

## C7. SECONDARY / UNQUANTIFIED DIRECTIONAL SETUPS

All `[T5-UNQUANTIFIED]` — rules exist, no performance data found in any source.

| Setup | Trigger | Note |
|---|---|---|
| **Bollinger mean reversion** | Buy lower band / sell upper band, target 20-SMA midline | Needs a range filter (ADX<20) or it fades real breakouts |
| **RSI divergence** | Price new high/low, RSI fails to confirm | Notoriously early in strong trends |
| **Price action BOS / liquidity sweep** | Structure break or sweep past an obvious high/low then reversal | Qualitative by design — hardest thing here to backtest mechanically |
| **Volume-confirmed breakout** | Level break on ≥2× average volume | A filter, not a standalone system |
| **Delta / footprint divergence** | Price new high, cumulative delta fails to confirm | Needs order-flow data most Indian retail terminals lack — factor the data cost in |
| **Supertrend** | Trend-following flip signal | Widely used; no India-specific options backtest with disclosed metrics found |
| **Gap-up / gap-down fade or follow** | First 30 min after a gap | Gap days are exactly when time-based systems fail — see `04` §B1 |

---

## BAG C SUMMARY TABLE

| # | Strategy | Win rate | Tier | R:R | Max loss | Regime |
|---|---|---|---|---|---|---|
| **C1** | **ORB (8-yr Nifty)** | **48.7%** | **T1** | 2:1 nominal | Premium | Trending |
| C1b | ORB 5-min variants | 57.1% / 71.4% | T1 | 1.5R cap | Premium | Trending |
| C2 | VWAP Pullback | Not stated | T3 | ~1.3:1 | Premium | Trending |
| C3 | VWAP Reclaim/Reject/Squeeze | Not stated | T3 | 1:2–1:3 | Premium | Mixed |
| C4 | 9/21 EMA Crossover | 45–50% base | T3 | 2:1 | Premium | Trending |
| **C5** | **Pullback+Breakout Combo** | **65%** | **T2** | **1:2** | Premium | Trending, 09:45–11:30 |
| C6 | Expiry-day scalp | Not stated | T3/T5 | Varies | Premium | S5 morning |
| C7 | Seven secondary setups | Not stated | T5 | — | Premium | Varies |

**Best-evidenced in this bag: C1 (2,122 trades, 8+ years) and C5 (peer-reviewed, but only 53 trades).**
