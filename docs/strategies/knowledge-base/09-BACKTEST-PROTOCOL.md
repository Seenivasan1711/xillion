---
doc_id: 09-BACKTEST
title: Backtest Protocol
topic: how to validate a strategy honestly before risking capital
compiled: 2026-08-24
use_when: User asks about backtesting, validating, or whether a result can be trusted
---

# 09 — BACKTEST PROTOCOL

## Why this file exists

Nearly every win rate in this knowledge base is unverified. The point of backtesting is not to confirm them — it is to **find out whether they survive contact with Indian transaction costs, real spreads, and recent market regimes**. A backtest designed to confirm a hypothesis will always succeed. A backtest designed to kill it is the useful one.

---

## The 10 rules

### 1. Use real option premium data, not synthetic
Weekly Nifty premiums do not move like spot. Model the **actual strike's 1-min or tick OHLC**, with bid/ask where obtainable. A Black-Scholes approximation from spot will silently overstate every result, because it prices no spread and no liquidity gap.

> **This is why the ORB backtests in `05` §C1 cannot be taken at face value for options trading — they measure index/futures moves, not option P&L.**

### 2. Charge full round-trip costs on every leg
Per `01` §1.4: STT (sell side, 0.15% since Apr 2026), brokerage, exchange transaction charges, GST, SEBI fees, stamp duty.

```
Iron condor = 4 legs × 2 (entry + exit) = 8 chargeable events
Credit spread = 2 legs × 2 = 4
Long option  = 1 leg × 2  = 2
```

**Given SEBI's finding that 71% of aggregate retail losses were transaction costs, a backtest without full costs is measuring a strategy that does not exist.**

### 3. Model slippage worse than mid-price
Assume you get filled at the **unfavourable side of the spread**, both directions. On a 4-leg structure that is 8 unfavourable fills per round trip. At a 10–20 point target, 2 points of slippage is 10–20% of gross.

### 4. Segment by volatility regime
Report win rate and expectancy separately for VIX <12, 12–15, 15–20, 20+. An aggregate number hides a strategy that only works in one band. The Zerodha 45-DTE study is the model here: the VIX>75th-percentile subset behaved completely differently (86% vs 70%) from the whole.

### 5. Walk forward — never optimise and report in-sample
Optimise parameters on one window, then test **unchanged** on a later, unseen window. A single clean equity curve over one fixed historical period is usually an in-sample fit, not evidence.

### 6. Track expectancy, not win rate
```
Expectancy = (Win% × Avg Win) − (Loss% × Avg Loss)
```
Report: profit factor, average win, average loss, largest single loss, and the **break-even win rate** implied by the management rules (`07` §Arithmetic). If realised win rate does not clear that line after costs, the strategy is dead regardless of how good the win rate looks.

### 7. Separate expiry day from the rest of the cycle
S5 behaves nothing like S1–S4 — theta 5–10× faster, gamma extreme. Pooling them misrepresents both. Report per cycle stage.

### 8. Stress-test the daily loss limit
If the "stop after 3 consecutive losses / 5% drawdown" rule fires on a large share of days, the strategy's variance exceeds the tested position size. That is a **sizing** finding the backtest should surface, not a nuisance to disable.

### 9. Model gap risk explicitly for anything short
The 45-DTE study recorded **one trade losing over 1,000 points despite a stop loss** — because the gap opened past it. Any backtest where stops always fill at the stop price is fiction. Test with stops filling at the next open, not the trigger price.

### 10. Backtest margin, not just P&L, for premium selling
Margin requirements move daily with volatility. A strategy that is profitable but occasionally demands 3× the expected margin will force liquidation at the worst moment. Track peak margin, not just P&L.

---

## Rule 11 — test the current regime specifically

Given the `[T2-RESEARCH]` finding of a **VRP inversion in early 2026**, any premium-selling backtest must report:
- Performance **2019–2025** (the favourable VRP period), AND
- Performance **2026 year-to-date** (the inverted period), separately

If a strategy is only profitable in the first window, you are backtesting a regime, not a strategy.

---

## Sample-size guidance

| Trades | Interpretation |
|---|---|
| < 30 | Anecdote. No statistical meaning. |
| 30–100 | Directional hint. The 53-trade research paper (`05` §C5) sits here. |
| 100–500 | Usable, regime-dependent. The 42-signal ORB study is below this. |
| **500+** | **Reasonable confidence.** The 2,122-trade 8-year ORB study sits here. |

**Rule of thumb:** you need enough trades that a 5-loss cluster (documented as the real drawdown driver) is a small fraction of the sample.

---

## Tooling available in India

| Platform | Free tier | Data depth | Strategy support |
|---|---|---|---|
| **AlgoTest** | 25 backtests/week | 7.5+ yrs intraday + EOD | Multi-leg, delta-based strikes, time entries ⭐ |
| Opstra | Limited | EOD only | Straddles, condors, payoff analysis |
| Sensibull | Limited | Paid for full backtesting | Visual builder, educational |
| Streak | Free for Zerodha | Indicator-based | Limited options support |
| Stockmock | Limited | — | Multi-leg backtesting |
| **Python + own data** | Free (data costs) | Whatever you buy | **Fully customisable ⭐** |

**Recommendation given the user's background:** AlgoTest for fast hypothesis screening (it handles multi-leg and delta-based strike selection natively, which is exactly what Rank 1 needs), then a Python implementation for the strategy that survives — so costs, slippage and walk-forward are under your own control rather than the platform's assumptions.

The main constraint on any of these is **data**: intraday option-chain history is expensive, which is why free tools mostly offer EOD. For scalping validation, EOD data is useless.

---

## Backtest report template

Every strategy test should produce:

```
STRATEGY: ___                          PERIOD: ___ to ___
INSTRUMENT: ___                        CYCLE STAGE(S): ___

SAMPLE
  Total trades: ___     Trades/month: ___

RETURNS
  Total return %        CAGR %
  Profit factor         Sharpe
  Max drawdown %        Longest losing streak: ___ trades

TRADE STATS
  Win rate %            Break-even WR required: ___%   ← must compare these
  Avg win / Avg loss    Largest single loss
  Avg holding period

COSTS  ← if this section is empty the backtest is invalid
  Total costs paid      Costs as % of gross profit
  Slippage assumption   Fill assumption on stops

REGIME SPLIT
  By VIX band           By cycle stage       By year
  2019-2025 vs 2026 YTD (mandatory for short-premium)

VERDICT
  Does realised WR clear break-even WR after costs?   YES / NO
  Walk-forward result vs in-sample:  ___
  Max margin required: ___
```

**If the "COSTS" section is empty, the backtest is not evidence of anything.**

---

## The honest possible outcome

A properly-costed backtest of a popular strategy on recent Indian data may well show **no edge**. That is not a failed project — it is the most valuable result available, because it costs nothing but time, whereas discovering it live costs the ₹1.1 lakh that SEBI reports as the average losing trader's outcome.

Treat "this doesn't work after costs" as a successful experiment.
