# Xillion — Product Roadmap & Completion

> High-level "how far along is this, really" snapshot, saved 2026-09-22 per
> Rakesh's request. This is a summary — the living, detailed sources are
> [task-tracker.md](../status/task-tracker.md) (day-to-day source of truth),
> [roadmap-quantman-parity.md](roadmap-quantman-parity.md) (the original
> QP-numbered checklist this summary is drawn from), and
> [deferred-backlog.md](../status/deferred-backlog.md) (what's deliberately
> not being built). If this file and one of those disagree later, trust the
> living doc and treat this one as due for a refresh.

## 🔴 2026-09-22 decision: Track B is now the main roadmap

Rakesh's call this session: with Track A's platform work substantially done
(see below), day-to-day priority shifts to **finishing Track B end-to-end and
making it fully usable from the UI/Telegram — not just runnable by someone
reading the code** — with a target of being usable "from next week." Track A
work continues only where it's genuinely blocking Track B (e.g. a platform
bug surfaces while building an asset lane), not as its own parallel stream.

---

## The two tracks

- **Track A — Platform.** Shared infrastructure every asset class needs:
  correctness, data warehouse, signal/journal lifecycle, AI assistant, risk
  engine, multi-broker execution, automation/hardening. Built once, 15
  checkpoints (CP1–CP15).
- **Track B — Asset pipelines.** The same repeatable 6-stage pipeline
  (Build → Backtest → Paper → Live → Automate → Document, see
  [asset-pipeline.md](../process/asset-pipeline.md)) applied per asset class
  / strategy.

## Track A — Platform: ~90% done

| Checkpoint | Status | What's left |
|---|---|---|
| CP1 Safety net + correctness | ✅ Done | — |
| CP2 Data warehouse | ✅ Done | — |
| CP3 Backfill + run history | ✅ Done | — |
| CP4 Signal lifecycle | 🟡 Engineering done | Telegram proof only needs a real alert to fire and be confirmed — happening naturally via Gold's live instance |
| CP5 Strategy builder | 🟡 Mostly done | Multi-leg options complexity carried forward into Track B strategy work, not a platform gap |
| CP6 Strategy journal + feedback loop | ✅ Done | — |
| CP7 MCP server | ✅ Done | — |
| CP8 AI assistant + RAG | 🟡 Mostly done | Verified end-to-end on local Ollama; an optional cloud LLM key would speed responses up but isn't required — deferred, Rakesh's call |
| CP9 Automation + hardening | ✅ Done | — |
| CP10 Maintenance mode | ✅ Done | — |
| CP11 Multi-leg execution + protective orders | ✅ Done | Dhan-side gap documented, not blocking |
| CP12 Trailing-stop engine | ✅ Done | A watchdog gap narrowed, not fully closed (see tracker) |
| CP13 Expanded risk engine | ✅ Done | — |
| CP14 Scheduled EOD reconciliation | ✅ Done | — |
| CP15 Dhan as a full second broker | 🟡 Code done | Blocked on Dhan live credentials for final verification (manual-tasks.md) |

**Bottom line:** the platform itself is not the bottleneck anymore. Every
open item above is either a user-side confirmation/credential, or something
that naturally resolves as Track B work runs (e.g. CP4's Telegram proof).

## Track B — Asset pipelines: ~25–30% done overall

| Lane | Stage 1 Build | Stage 2 Backtest | Stage 3 Paper | Stage 4 Live | Stage 5 Automate | Stage 6 Document |
|---|---|---|---|---|---|---|
| **Options (Lane A, NSE F&O)** | ✅ | ✅ | 🟡 unblocked, not run | 🟡 code ready, not activated | ⬜ | 🟡 ongoing |
| **Gold XAUUSD (Lane B1, Funding Pips/MT5)** | ✅ | ✅ (net-negative result, see below) | 🔴 blocked on a decision | ⬜ | ⬜ | 🟡 ongoing |
| Gold MCX (Lane B2) | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Forex (non-Gold pairs) | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Stock options / Stocks | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Crypto | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ — **deliberately deferred**, see deferred-backlog.md (India's 1% TDS makes active crypto trading structurally unprofitable) |

**Gold Lane B1 detail (the current focus):** the alert engine is genuinely
live (real Supabase, real Twelve Data feed, verified alive 2026-09-21). The
first real 6-month backtest (201 trades) came back **net-negative**
(-$12,705.76 on a $5,000 account) despite a 47.8% win rate — the real R:R
(~0.46:1) is far worse than the strategy card's assumed 2.5:1. Two follow-up
parameter sweeps (57 combos total) couldn't fix it via SL/TP sizing alone.
**This is a real, open, Rakesh-only decision** (manual-tasks.md's 🔴 item):
whether to push further into session-window/level-richness analysis before
concluding the signal itself lacks edge in this window, or treat it as dead
and reconsider. Nothing else in Lane B1 (paper trading, going live) proceeds
until this is resolved — that's Stage 3's gate working as designed, not a
stall.

**Bottom line:** Track B has one lane (Options) close to a real paper soak,
and one lane (Gold) with a live alert engine but an open strategy-viability
question blocking further progress. No lane has completed Stage 3 (paper)
or beyond yet — that's the honest state of "how close to real automated
trading" this project is.

---

## What else is on the roadmap, beyond Track A and B?

Short answer: **not much that isn't already folded into A/B, or explicitly
out of scope.** The two things worth naming:

1. **The v2 "Options Automation Platform" goals (G7–G13, added 2026-08-25)**
   — these predate the Track A/B naming but map directly onto it, and are
   **mostly already done**:
   - G7 Multi-leg options structures — ✅ done (CP11)
   - G8 Protective orders live at the broker — ✅ done (CP11)
   - G9 Trailing-stop engine — ✅ done (CP12)
   - G10 Two live trading brokers — ✅ done (CP11/CP15, Dhan pending live-cred verification)
   - G11 A second instrument lane (gold) — 🟡 in progress, this **is** Track B Lane B1
   - G12 An honestly-costed multi-leg backtest engine — 🟡 partial; Gold's backtest is real-priced, the original Options per-leg cost/fill model per the knowledge-base protocol hasn't been independently re-audited recently
   - G13 An MCP layer the AI assistant can drive — ✅ done (CP7 + CP8's prosper-engine extension)
2. **The AI/MCP layer (QP-6/QP-7 in the older roadmap doc)** — arguably a
   third pillar that sits *across* both tracks rather than inside either
   (it's asset-class-agnostic). **Already done**: MCP server (CP7),
   prosper-engine as an MCP client with a real tool loop, and the pre-trade
   AI-confidence hook wired into the alert pipeline (CP8).

Everything else that could be "roadmap" is an **explicit non-goal** for this
personal, single-user system — not planned, not forgotten:
- Multi-user auth / per-tenant isolation / subscription billing / a strategy
  marketplace — this becomes relevant only if it ever became a product with
  other users, which isn't the goal.
- A native mobile app — the responsive web UI works on a phone; not worth
  months of work for marginal gain unless that genuinely fails in practice.
- SEBI vendor empanelment — only relevant for a commercial data/advisory
  offering, not personal algo use (already permitted under the current
  retail framework).
- Tick-level backtesting, an options-greeks engine, portfolio-level sizing
  (Kelly/risk-parity) — all deferred until a specific strategy actually
  needs them; see deferred-backlog.md's "Engine features" table.
- Agent/workflow-driven signal generation ("JEV") — Rakesh's own idea,
  explicitly deferred until Gold Sweep-Reversal's current code-level
  economics are settled first (see deferred-backlog.md).

## Known gaps toward "usable from next week"

Found while syncing this roadmap, 2026-09-22 — not yet fixed:

- **Gold's alert mode never sends an exit alert.** `_fire_entry()` in
  `strategies/gold_sweep_reversal.py` sends the entry (with target/SL) via
  `ctx.alert_entry()`, but nothing tells you via Telegram when that target or
  SL is actually hit — you have to watch price yourself or wait for the
  weekly digest. Paper/live modes already handle this correctly via
  `on_tick()`; alert mode doesn't call it. Real gap, not yet fixed.
- **Twelve Data / Finnhub credentials are `.env`-only**, not yet a
  Settings-page card like every other broker/provider — already logged in
  deferred-backlog.md, not urgent for a single-user local setup but worth
  revisiting if "easy to update from the UI" matters for next week's target.
- **The Gold strategy-viability decision itself** (see Track B table above)
  is the actual gate — no amount of UI/Telegram polish makes it "usable" in
  the sense of real capital at risk until that's resolved.
