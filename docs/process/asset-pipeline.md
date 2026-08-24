# 14 — The Asset Pipeline (repeat this per asset class)

> Every asset class — options, gold, forex, stock options, stocks, crypto —
> goes through the **same six stages**. The platform work (Track A in
> [15-task-tracker.md](../status/task-tracker.md)) exists to make this pipeline
> cheap to repeat. Doing it once for options should make doing it for gold
> mostly configuration, not new engineering.

**The rule: no stage starts until the previous one's exit criterion is met.**
That rule is the whole point — it's what stops an unvalidated strategy from
reaching real money.

---

## Stage 1 — Build the strategy

**Goal:** the setup exists in the system and reads the right data.

- Define rules explicitly: entry condition, exit condition, target, stop-loss,
  position sizing, filters (time-of-day, volatility, trend regime)
- Build it via the **condition builder UI** (CP5) if it's expressible there;
  drop to a Python plugin in `strategies/` only for genuinely complex logic
  (multi-leg structures, custom greeks)
- Confirm the strategy reads the instruments it expects — resolution,
  timeframe, and data availability

**Exit:** the strategy appears in the UI, an instance can be created, and a
dry run shows it evaluating against real data without errors.

**Write down:** the rules, in plain language, in `docs/strategies/<name>.md`.
Do this *before* backtesting — a strategy you can't state plainly is a
strategy you can't debug later.

---

## Stage 2 — Backtest on 2–5 years of history

**Goal:** know whether the edge exists at all, before spending time or money.

- Requires Track A **CP2 + CP3** (data warehouse + backfill) — that's what
  makes multi-year backtesting free and fast
- Run across **multiple market regimes**: trending, choppy, high-vol, crash.
  A strategy that only works in one regime will fail the moment the regime
  changes, and you want to learn that here
- **Hand-verify a sample.** Pick 5 trades, compute P&L manually, compare. If
  they don't match, the bug is in the engine, not the strategy — stop and fix
- Vary parameters to check robustness. If results collapse when a parameter
  moves 10%, it's curve-fit, not an edge

**Exit:** positive expectancy across ≥2 years and ≥2 regimes, **and** a manual
spot-check that matches the engine.

**⚠️ Reality check:** most strategies fail here. That's the stage doing its
job — a failed backtest costs hours; a failed live strategy costs money.

**Write down:** metrics per regime, parameter-sensitivity findings, and *why
you believe the edge exists* (what market behaviour is it exploiting?).

---

## Stage 3 — White/paper testing in real time

**Goal:** prove the strategy behaves live the way the backtest said it would.

- Run in **paper mode against live market data** in our own system
- 📅 **CALENDAR-BOUND: 2–4 weeks minimum.** Cannot be compressed. This is real
  market days, not simulated ones
- Watch specifically for the things backtests can't show:
  - signal *timing* (does it fire when you'd expect, or a bar late?)
  - missed/duplicate signals
  - slippage vs. the backtest's assumption
  - data gaps, feed disconnects, reconnect behaviour
- Compare paper results against the backtest over the *same* period. Large
  divergence means the backtest is lying — go back to Stage 2

**Exit:** 2+ weeks with no missed/duplicate/mistimed signals, and paper results
broadly consistent with backtest expectations.

**Write down:** every divergence between backtest and paper, and its cause.
This is the highest-value documentation in the whole pipeline — it's what
teaches the AI layer (CP8) where models break.

---

## Stage 4 — Live, small

**Goal:** real money, smallest possible size, fully monitored.

- Requires Track A **CP9** (position reconciliation) — going live without it
  means a process restart loses track of open positions
- Start at the **minimum viable size** (1 lot). The goal is not profit here,
  it's confirming fills, fees, and slippage match expectations
- Risk limits tight: daily loss cap, max positions, kill switch tested
- Monitor daily. Real fills differ from paper fills — note by how much

**Exit:** ≥20 real trades with fills, fees and slippage matching paper within
tolerance, and the kill switch verified on a live position.

**Write down:** real vs. paper slippage and fee reality. Feed this back into
the backtest's fee/slippage config so future backtests are honest.

---

## Stage 5 — Automate

**Goal:** it runs without you.

- Auto start/stop at session open/close
- Auto position reconciliation on restart
- Failure alerting — you're told when the *system* breaks, not just when a
  trade loses
- Scale size only on a **proven track record**, never on a good week

**Exit:** a full week of unattended operation with no manual intervention.

---

## Stage 6 — Document for AI

**Goal:** the accumulated learning becomes machine-usable.

- Consolidate Stages 1–5 notes into `docs/strategies/<name>.md`
- Export journal data (CP6) — every signal, outcome, and tagged failure mode
- Ingest into the RAG layer (CP8) so the assistant can answer *"why did this
  strategy fail last October?"* from real history rather than guesswork
- **This is what makes later assets faster** — the AI has prior context on
  what worked, what broke, and why

**Exit:** the assistant can answer questions about this strategy's real
history, citing actual trades.

---

## Per-asset notes

### Options (NIFTY / BANKNIFTY / SENSEX) — Zerodha
Infrastructure ready today. Free NSE bhavcopy covers daily-bar backtesting.
**Lot size 65 for NIFTY** — the multiplier fix (CP1) matters most here.
Intraday backtesting needs paid Kite historical data.

### Gold XAUUSD — Funding Pips (MT5)
Needs the MT5 broker plugin, a 24×5 session calendar, and FX lot math.
**Funding Pips drawdown rules must be encoded as hard risk limits** —
breaching daily or max drawdown instantly fails the account and burns the
challenge fee, so treat it as a safety system, not a formality.
⚠️ Get a CA opinion on prop-firm income treatment before Stage 4.

### Forex — Funding Pips (MT5)
Nearly free once gold is done — same broker, same calendar, same lot math.
This is why gold and forex are adjacent in the plan.

### Stock options — Zerodha
Reuses the index-option resolver. Main new work is universe selection
(which stocks) and much wider liquidity variation than index options.

### Stocks — Zerodha
Cheapest asset class: multiplier is 1, no expiry, no strike resolution.

### Crypto — exchange TBD
**Model the 1% TDS in the fee engine before backtesting anything.** TDS
applies per transaction, so a strategy trading 100×/month pays 100% of one
position's value in TDS annually. Most active crypto strategies are
structurally unprofitable in India — better to prove that in a backtest.
