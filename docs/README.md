# AlgoTrader — Personal Algorithmic Trading Platform

A small, opinionated, self-hosted algo trading bot that lets you **drop a Python file to add a strategy** and **drop a Python file to add a broker**. Backtest, paper-trade, and go live from a clean dashboard. Personal-use first; cleanly extensible for commercial use later.

> **Internal codename:** AlgoTrader (placeholder — pick your own later)
> **Status:** Spec & design phase
> **Owner:** You (solo developer)

---

## 🔴 Cold start — read these two

| Document | Purpose |
|---|---|
| **[status/task-tracker.md](status/task-tracker.md)** | **THE living status.** Where we are, what's next, what's blocked. Start here, always |
| [process/asset-pipeline.md](process/asset-pipeline.md) | The repeatable 6-stage process every asset class runs through |

Everything below is reference — read on demand, not up front.

---

## Structure

```
docs/
├── status/         ← changes constantly; read every session
├── process/        ← how we work
├── architecture/   ← how it's built
├── product/        ← what & why
├── strategies/     ← one file per strategy (RAG-ingested)
└── archive/        ← superseded, kept for history
```

### `status/` — living state
| Document | Purpose |
|---|---|
| [task-tracker.md](status/task-tracker.md) | Current position, checkpoints, per-asset pipeline progress, blockers |
| [deferred-backlog.md](status/deferred-backlog.md) | Consciously **not** building, with reasons + revisit triggers |
| [decisions-and-open-questions.md](status/decisions-and-open-questions.md) | What's decided, what's still open |

### `process/` — how we work
| Document | Purpose |
|---|---|
| [asset-pipeline.md](process/asset-pipeline.md) | The 6 stages: build → backtest → paper → live → automate → document |
| [testing-strategy.md](process/testing-strategy.md) | How we avoid blowing up the account |
| [go-live-checklist.md](process/go-live-checklist.md) | Pre-flight before real money |
| [automation-registry.md](process/automation-registry.md) | Every skill/hook/CLAUDE.md rule, why it exists, and the candidate watchlist for what to build next |

### `architecture/` — how it's built
| Document | Purpose |
|---|---|
| [overview.md](architecture/overview.md) | Components, data flow, technology choices |
| [plugin-contracts.md](architecture/plugin-contracts.md) | Exact interfaces for strategies, brokers, data providers |
| [data-model.md](architecture/data-model.md) | Database schema, env config |
| [risk-and-compliance.md](architecture/risk-and-compliance.md) | Risk controls, SEBI rules, kill switches |

### `product/` — what & why
| Document | Purpose |
|---|---|
| [prd.md](product/prd.md) | Vision, goals, scope, success metrics |
| [functional-requirements.md](product/functional-requirements.md) | Every feature, prioritised |
| [ui-ux.md](product/ui-ux.md) | Screens, wireframes, interaction patterns |
| [user-guide.md](product/user-guide.md) | How to actually use the app |
| [roadmap-quantman-parity.md](product/roadmap-quantman-parity.md) | Original vision + data-provider tier comparison |

### `strategies/` — per-strategy records
One file per strategy, from [_TEMPLATE.md](strategies/_TEMPLATE.md). Rules,
backtest results, paper divergences, and a **failure log**. These are ingested
into the RAG layer so the assistant can answer questions about real history.

### `archive/`
[progress-tracker-phases-0-10.md](archive/progress-tracker-phases-0-10.md) —
the original Phase 0–10 build record. **Superseded by `status/task-tracker.md`
for status**; kept because it accurately documents what was built when.

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

1. Skim [PRD](product/prd.md) (10 min)
2. Read [Architecture overview](architecture/overview.md) (15 min)
3. Read [Plugin contracts](architecture/plugin-contracts.md) (15 min)
4. Open [task-tracker.md](status/task-tracker.md) and start at the current checkpoint

If you want to **understand the full thinking** first, read everything under
`product/` and `architecture/` in order. ~90 minutes total.
