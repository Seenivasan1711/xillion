# Trading Automation Platform Spec

Source: `tradingautomationspec.zip`, supplied by Rakesh 2026-08-25. Stored
here verbatim (file names and content unchanged from the zip).

## What this is

A **job-based trading operations platform** spec: 52 discrete, independently
schedulable jobs (pre-market → open → entry → in-trade → exit → post-market →
periodic → cross-cutting) that automate the rituals a discretionary trader
performs manually every day. Written by/for an engineering team building from
an empty repo — see the note below on how it actually applies here.

**Two instrument lanes:**
- **Lane A** — Nifty/Sensex weekly index options, NSE/BSE, primary
- **Lane B** — Gold, split into **B1** (XAUUSD via Funding Pips/MT5, prop-firm
  account, "primary per your instruction") and **B2** (MCX Gold futures/options,
  domestic/SEBI-regulated, "fallback + hedge against rule change") — built in
  parallel since ~85% of the session logic, volatility drivers and trailing-stop
  engines are shared. See `01-REGULATORY-CONSTRAINTS.md` §1.2 for why spot
  XAUUSD via offshore retail forex is a FEMA problem but prop-firm evaluation
  trading is a materially different (and generally permissible) legal
  question — read that section before assuming either lane is off the table.

## ⚠️ How this spec actually applies to xillion — read this before the rest

This spec is written as if starting from Phase 0 on an empty repo, recommending
a stack (OpenAlgo, Redis, DuckDB+Parquet, Prometheus/Grafana, APScheduler→Prefect)
independent of what already exists. **xillion is not an empty repo** — CP1
through CP10 already built a real risk engine, kill switch, audit-log-adjacent
journal, Telegram alerting with self-healing background tasks, a daily/weekly
digest, position reconciliation on restart, and a battle-tested Zerodha broker
integration.

**Decision (2026-08-25, confirmed with Rakesh): retrofit this spec into
xillion.** Map the 52-job catalog onto what already exists; build only the
real gaps (protective broker-side orders, a trailing-stop engine, the
multi-leg leg-failure protocol, end-of-day broker reconciliation, the
expanded ~20-check risk engine, Dhan as a full trading broker alongside
Zerodha). See [`docs/status/decisions-and-open-questions.md`](../../status/decisions-and-open-questions.md)
D17-D20 for the full reasoning and infra-cost constraints (everything free/
minimal-cost until a VPS is actually provisioned), and
[`docs/status/task-tracker.md`](../../status/task-tracker.md) for the concrete
gap-mapped build plan.

## File map

| File | Contains |
|---|---|
| `00-README-AND-SCOPE.md` | Scope, design principles, job-ID convention, explicit non-goals |
| `01-REGULATORY-CONSTRAINTS.md` | SEBI algo framework, FEMA/Funding Pips analysis — read before coding |
| `02-SYSTEM-ARCHITECTURE.md` | Service topology, BrokerAdapter interface, broker comparison (Dhan/Zerodha/Groww), tech stack |
| `03-DATA-MODEL.md` | Postgres schema, DuckDB/Parquet analytical store, Redis key layout, event contracts |
| `04-JOB-CATALOG.md` | Master index of all 52 jobs, criticality, phase, dependency graph |
| `05-JOBS-PREMARKET.md` | P-series job specs (auth, calendar, regime, arming, brief) |
| `06-JOBS-ENTRY.md` | O/E-series specs (opening range, signal → gate → size → order → fill → protect) |
| `07-JOBS-INTRADE.md` | T-series specs (P&L monitor, trailing stop engine, breakeven, partial exit) |
| `08-JOBS-POSTMARKET.md` | X/M-series specs (exit, square-off, reconciliation, journal, slippage) |
| `09-JOBS-PERIODIC.md` | R-series specs (walk-forward revalidation, decay monitor, config audit) |
| `10-RISK-ENGINE.md` | The ~20-check mandatory order gate — no order bypasses this |
| `11-INSTRUMENT-LANES.md` | Full Lane A vs B1 vs B2 comparison; what's shared (~85%) vs lane-specific |
| `12-CONFIG-SCHEMA.md` | Complete YAML config contract (compliance/capital/risk/instruments/strategies/brokers) |
| `13-IMPLEMENTATION-ROADMAP.md` | Phase 0-6 plan with deliverables and hard gates |
| `14-TESTING-AND-ACCEPTANCE.md` | Test strategy, acceptance criteria per phase |
| `15-RUNBOOK-AND-OBSERVABILITY.md` | Alerts, dashboards, incident response — compare against xillion's own `docs/process/runbook.md` |

## Cross-reference

The strategy this harness runs first is specified in the companion knowledge
base: [`docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md`](../../strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md).
