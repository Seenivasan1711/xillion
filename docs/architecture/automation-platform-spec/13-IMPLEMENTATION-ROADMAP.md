---
doc_id: 13-ROADMAP
title: Implementation Roadmap — Phase 0 to 6
audience: PM, engineering
version: 1.0
---

# 13 — IMPLEMENTATION ROADMAP

**Sequencing principle: build the things that protect capital before the things that make it.** A system that can enter but not exit safely is worse than no system. Each phase ends with a **hard gate** — measurable criteria that must pass before the next phase starts.

**Estimates assume one competent backend engineer working full-time.** Halve the throughput for part-time.

---

## PHASE 0 — FOUNDATION & DATA CAPTURE
**Duration: 1 week · Gate: data flowing and stored**

> ⭐ **Start recording market data on day one, before anything else is built.** Option chain history cannot be bought cheaply and cannot be reconstructed later. Every day you delay is a day permanently missing from your future backtests.

### Deliverables
```
□ Repo, CI (GitHub Actions), pre-commit, project structure
□ Docker Compose: postgres, redis, app skeleton
□ Config system (Pydantic Settings + YAML) — 12-CONFIG-SCHEMA.md
□ Secrets management (never in git — use env/vault)
□ Structured JSON logging
□ India-region VPS provisioned WITH STATIC IP        ← SEBI requirement, 01 §1.1
□ Broker account + API keys (Dhan primary, Zerodha secondary)
□ BrokerAdapter interface defined (02 §2.4)
□ Dhan adapter: auth, quote, candles, option_chain, balance  (READ ONLY)
□ ⭐ DATA RECORDER: 1-min option chain snapshots → Parquet/DuckDB
□ ⭐ DATA RECORDER: underlying 1-min OHLCV, India VIX, ATM straddle price
□ Basic Telegram bot (send only)
```

### Gate 0 ✅
- [ ] Option chain recording for 5 consecutive sessions with zero gaps
- [ ] Data integrity check passes (no missing minutes, no null LTPs on liquid strikes)
- [ ] Config loads and validates
- [ ] Can query a historical chain from DuckDB in <1s
- [ ] Static IP confirmed whitelisted with broker

---

## PHASE 1 — SAFE MANUAL EXECUTION (all 18 P0 jobs)
**Duration: 3–4 weeks · Gate: can safely place, protect and exit ONE manually-triggered trade**

**Goal: no strategy logic at all. A human decides the trade; the system executes it correctly and cannot hurt you.**

### Deliverables
```
RISK ENGINE (build first — everything else depends on it)
□ 10-RISK-ENGINE.md §10.2 order validation, all checks
□ OPS token bucket (7/sec cap)
□ Circuit breakers (daily loss, consecutive losses, drawdown)
□ K01 kill switch: Telegram /kill, file sentinel, API endpoint
□ K03 heartbeat + SEPARATE watchdog process
□ K04 audit log writer
□ 100% branch coverage on the risk engine     ← non-negotiable gate item

JOBS — P0 ONLY
□ P01 health & auth refresh (incl. daily 2FA prompt flow)
□ P06 instrument & expiry resolver (lot size FROM API, mismatch → halt)
□ P07 capital & margin readiness
□ E02 pre-entry gate (all ~24 checks)
□ E03 position sizing (incl. the lots==0 path with suggestions)
□ E04 order construction (leg ordering: LONGS FIRST)
□ E05 order execution + ⭐ ROLLBACK PROTOCOL
□ E06 fill verification & reconcile
□ E07 protective order placement (+ broker-side disaster stop)
□ T01 position & P&L monitor (MTM at bid/ask, MAE/MFE)
□ X01 exit execution (SHORTS FIRST on exit)
□ X02 square-off enforcer (independent of everything else)
□ X03 exit fill verification
□ M01 broker reconciliation
□ K02 alert router
□ K05 config validator

RUNTIME
□ Paper-trading mode via full pipeline (Dhan sandbox or OpenAlgo sandbox)
□ Manual trade trigger: Telegram command or CLI
```

### Gate 1 ✅ — the most important gate in the project
- [ ] 20 paper trades executed end-to-end, zero state divergence
- [ ] **E05 rollback tested: naked-short scenario force-unwinds within 5s**
- [ ] **X02 flattens positions with the entire app stopped except scheduler + adapter**
- [ ] **Watchdog flattens when main process is killed with a position open**
- [ ] Kill switch fires from phone in <5s
- [ ] Risk engine: 100% branch coverage, 20-orders-in-1s halts the system
- [ ] M01 reconciles clean for 5 consecutive days
- [ ] Protective order rejection → position auto-closes
- [ ] **1 live trade, 1 lot, minimum size, fully manual trigger, reconciles clean**

> **Do not proceed past Gate 1 with any item unchecked.** Everything after this phase increases trade frequency. Frequency multiplies whatever defects remain here.

---

## PHASE 2 — AUTOMATED SINGLE STRATEGY (Lane A)
**Duration: 3–4 weeks · Gate: one strategy trades itself, profitably in paper**

### Deliverables
```
□ P02 calendar (incl. holiday-shifted expiry)
□ P05 volatility regime classification
□ P08 strategy arming
□ P09 watchlist / strike shortlist
□ O01 opening range · O02 regime confirm · O03 gap veto
□ E01 signal generation + Strategy plugin contract
□ T03 ⭐ TRAILING STOP ENGINE (all 6 algorithms, ratchet property-tested)
□ T05 breakeven shift
□ T06 time stop
□ M02 journal · M03 P&L & cost attribution · M08 archival
□ R06 config vs exchange audit
□ ⭐ BACKTEST ENGINE v1 (DuckDB + Polars, full Indian cost model)
□ STRATEGY #1: defined-risk credit spread (KB 10-FIRST-STRATEGY-SPEC)
□ Grafana dashboard: positions, P&L, system health
```

### Gate 2 ✅
- [ ] Backtest engine reproduces 10 manually-verified historical trades exactly
- [ ] Backtest includes full costs; **cost line is non-zero and itemised**
- [ ] Strategy #1 backtested per KB `09` protocol, pass/fail criteria applied
- [ ] **T03 ratchet: property test proves the stop never loosens, across restarts**
- [ ] 30 paper trades: live results within 10pp of backtest win rate
- [ ] Full day runs unattended with no manual intervention
- [ ] `wr_margin` computed and displayed

---

## PHASE 3 — HARDENING & LANE B FOUNDATION
**Duration: 3–4 weeks · Gate: robust under failure; gold lane executing in paper**

### Deliverables
```
LANE A HARDENING
□ P03 economic calendar · P04 global cues · P10 pre-market brief
□ T04 partial exit / scale-out (with protective-order resize!)
□ T08 spread degradation monitor
□ T09 event proximity guard
□ M04 slippage · M05 strategy metrics · M06 regime log · M07 post-market brief
□ Chaos testing: kill redis/postgres/broker mid-trade
□ Broker failover: Dhan → Zerodha

LANE B
□ Windows VPS + MT5 terminal + local watchdog
□ MT5 BrokerAdapter implementation (mt5-bridge service)
□ Prop-firm DD tracking (trailing peak equity) in P07
□ Prop DD circuit breakers in risk engine
□ Session model + session-aware arming (11 §11.3)
□ Rollover window handling (widen stops, block entries)
□ Chandelier/ATR trail tuned for gold
□ ⭐ MCX (Lane B2) adapter — reuses the Lane A broker adapter
```

### Gate 3 ✅
- [ ] Chaos tests pass: every dependency failure results in fail-closed
- [ ] Broker failover works mid-session
- [ ] MT5 bridge stable for 5 continuous trading days
- [ ] MT5 terminal crash → watchdog restarts, positions still protected
- [ ] Prop DD tracking matches Funding Pips' own dashboard to within 0.1%
- [ ] Lane B: 20 paper trades, session filters verified (no overnight-window entries)
- [ ] Lane B2 (MCX) places and exits a paper trade through the same adapter

---

## PHASE 4 — MULTI-STRATEGY & INTELLIGENCE
**Duration: 4–5 weeks · Gate: portfolio-level operation**

```
□ T02 Greeks drift monitor · T10 correlation & exposure aggregator
□ R02 ⭐ strategy decay monitor (auto-downgrade / auto-disable)
□ R04 risk budget rebalance (anti-martingale hard-coded)
□ R05 monthly performance review
□ Strategy registry: 3–5 strategies across both lanes
□ Cross-lane risk budgeting
□ Backtest engine v2: regime splits, walk-forward, parameter sweeps
□ Full Grafana suite: equity curve, per-strategy, cost trend, wr_margin
```

### Gate 4 ✅
- [ ] 3+ strategies running concurrently without interference
- [ ] Decay monitor correctly auto-disables a deliberately broken strategy
- [ ] Portfolio heat calculation verified against manual computation
- [ ] Correlated-exposure detection fires on a constructed correlated pair
- [ ] 60 days of paper trading with positive net expectancy

---

## PHASE 5 — OPTIMISATION & ADVANCED
**Duration: 4+ weeks · ongoing**

```
□ T07 adjustment trigger (with all guardrails from 07 §T07)
□ R01 walk-forward revalidation · R03 parameter drift detection
□ Advanced structures: calendar, butterfly, BWB
□ Execution improvements: smart limit pricing from slippage data (M04 feedback loop)
□ Backtest slippage replaced with MEASURED slippage
□ Consider NautilusTrader for Lane B backtesting
```

---

## PHASE 6 — SCALE & REFINE
**Ongoing**

```
□ Prefect migration (from APScheduler) if job complexity demands it
□ QuestDB migration if tick volume demands it (probably never, for one trader)
□ Additional instruments (Sensex weekly, Bank Nifty monthly)
□ Automated strategy research pipeline
□ Latency optimisation (only if measurement shows it matters)
```

---

## Capital deployment schedule — tied to gates, not to dates

| Stage | Capital | Precondition |
|---|---|---|
| Phase 0–1 | ₹0 (paper) | — |
| End Phase 1 | **1 lot, minimum size** | Gate 1 fully passed |
| Phase 2 | 1 lot | 30 paper trades matching backtest |
| End Phase 2 | 1 lot live, 30 trades | Gate 2 passed |
| Phase 3 | 1–2 lots | 30 live trades, positive expectancy, clean recon throughout |
| Phase 4 | Scale to plan | 100 live trades, `wr_margin` > 0, max DD < backtest DD |
| Phase 5+ | Per R04 | Sustained positive expectancy over 6 months |

**Hard rule: never increase size within 30 trades of a size increase.** Let each size level produce enough data to be evaluated before changing it.

---

## Critical path

```
Phase 0 data recording ──┐
                          ├──▶ Phase 2 backtest engine ──▶ strategy validation
Phase 1 risk engine ──────┤
                          └──▶ Phase 1 execution ──▶ Phase 2 automation ──▶ Phase 3+
```

**The two things that gate everything: the data recorder (Phase 0) and the risk engine (Phase 1).** Start both immediately and in parallel if you have two engineers.

---

## Effort summary

| Phase | Weeks | Focus |
|---|---|---|
| 0 | 1 | Foundation + data capture |
| 1 | 3–4 | Risk engine + safe execution (18 P0 jobs) |
| 2 | 3–4 | First automated strategy + backtest engine |
| 3 | 3–4 | Hardening + Lane B |
| 4 | 4–5 | Multi-strategy + intelligence |
| 5 | 4+ | Advanced + optimisation |
| **Total to production-ready** | **~15–18 weeks** | (one full-time engineer) |

**Fastest path to first live trade: end of Phase 1, ~4–5 weeks.** That trade will be 1 lot, manually triggered, and fully protected — which is exactly the right first live trade.

---

## Anti-patterns to avoid

| ❌ Don't | ✅ Do |
|---|---|
| Build strategies before the risk engine | Risk engine first, always |
| Skip paper trading because backtest looked good | Paper is where execution reality appears |
| Start data recording "once the system is ready" | Record from day one — history is unrecoverable |
| Hard-code lot size, expiry day, or cost rates | Config + R06 audit |
| Trust submit acks as truth | Always verify against broker state (E06) |
| Build adjustments early | Phase 5, with guardrails, or never |
| Increase size after a winning streak | Anti-martingale, hard-coded (R04) |
| Optimise latency before measuring | Measure first; you are not competing on speed |
| Auto-apply R03 parameter recommendations | Human approves, then re-run R01 |
