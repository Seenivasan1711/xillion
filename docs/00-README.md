# AlgoTrader — Personal Algorithmic Trading Platform

A small, opinionated, self-hosted algo trading bot that lets you **drop a Python file to add a strategy** and **drop a Python file to add a broker**. Backtest, paper-trade, and go live from a clean dashboard. Personal-use first; cleanly extensible for commercial use later.

> **Internal codename:** AlgoTrader (placeholder — pick your own later)
> **Status:** Spec & design phase
> **Owner:** You (solo developer)

---

## What this folder contains

| # | Document | Purpose |
|---|---|---|
| 01 | [Product Spec (PRD)](./01-PRD.md) | Vision, goals, users, scope, success metrics |
| 02 | [Functional Requirements](./02-functional-requirements.md) | Every feature, prioritised (MVP / v1 / future) |
| 03 | [System Architecture](./03-architecture.md) | Components, data flow, technology choices |
| 04 | [Plugin Contracts](./04-plugin-contracts.md) | The exact interfaces for strategies and brokers |
| 05 | [Data Model](./05-data-model.md) | Database schema, env config |
| 06 | [UI/UX Design](./06-ui-ux.md) | Screens, wireframes, interaction patterns |
| 07 | [Risk & Compliance](./07-risk-and-compliance.md) | Risk controls, SEBI 2025 rules, kill switches |
| 08 | [Testing Strategy](./08-testing-strategy.md) | How we avoid blowing up the account |
| 09 | [Progress Tracker](./09-progress-tracker.md) | Phased build plan with checkboxes |
| 10 | [Decisions & Open Questions](./10-decisions-and-open-questions.md) | What's decided, what's not |

Read in order on the first pass. After that, jump to whatever's relevant.

---

## The 30-second pitch

**Problem.** You want to automate your trading. Existing tools force you into either (a) closed no-code platforms that you outgrow, or (b) raw scripts that have no UI, no risk controls, and no way to safely add new strategies or brokers.

**Solution.** A modular, self-hosted bot with two simple plugin contracts:

```
strategies/
  my_strategy.py       ← drop this file, configure in UI/DB, it runs
  another_one.py

brokers/
  zerodha.py           ← drop this, you get Zerodha
  upstox.py            ← drop this later, you get Upstox
  paper.py             ← built-in paper broker for testing
```

A FastAPI backend orchestrates everything. A simple React dashboard shows you what's running, P&L, and a big red **Kill Switch**. SQLite/Postgres stores config, trades, audit logs.

**Why now.** SEBI's 2025/2026 framework explicitly permits retail traders to run their own algos for personal and immediate-family accounts, with clear thresholds and rules. The architecture below is designed to stay compliant by default.

---

## Top-level architectural commitments

1. **Plugin-first.** Strategies and brokers are loaded dynamically from folders. No code changes needed to add either.
2. **Three execution modes, one strategy.** Same strategy code runs in **backtest**, **paper**, and **live** mode. The mode is set in config; the strategy doesn't care.
3. **Safety before features.** Kill switch, position limits, daily loss caps, and audit logs are not "v2 features" — they ship in v1.
4. **Boring stack.** Python + FastAPI + SQLite (upgradable to Postgres) + React. No Kafka, no Kubernetes. You can run this on a Raspberry Pi or a small VPS.
5. **Personal-use sized.** Single-user auth in v1. Multi-tenant features stubbed but not built. Don't pay the complexity tax until you need to.

---

## What this is NOT

- **Not HFT.** Latency target is "fast enough for retail strategies" (sub-second), not microseconds.
- **Not a strategy marketplace.** You write your own strategies. (For commercial pivot, that changes — see doc 10.)
- **Not financial advice.** It's infrastructure. The strategies you write are your responsibility.
- **Not a substitute for understanding what you're trading.** Backtests lie, slippage hurts, and your account is real money. Read doc 07 before you go live.

---

## Quick path through the docs

If you just want to **start coding tomorrow**:

1. Skim [01 PRD](./01-PRD.md) (10 min)
2. Read [03 Architecture](./03-architecture.md) (15 min)
3. Read [04 Plugin Contracts](./04-plugin-contracts.md) (15 min)
4. Open [09 Progress Tracker](./09-progress-tracker.md) and start at Phase 0

If you want to **understand the full thinking** first, read 01 → 10 in order. ~90 minutes total.
