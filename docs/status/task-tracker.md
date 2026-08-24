# 15 — Task Tracker (LIVING DOCUMENT)

> **🔴 THIS IS THE SINGLE SOURCE OF TRUTH FOR "WHERE ARE WE".**
> Any session — human or AI — starts here. If you complete work, you update
> this file **in the same session**. See [Update protocol](#update-protocol).

**Last updated:** 2026-08-24
**Current position:** Track A · CP1 ✅ + CP2 ✅ → **CP3 is next**
**Active branch:** `feat/options-alert-engine`

> 2026-08-24 infra note: docs restructured from flat numbering into
> `status/ process/ architecture/ product/ strategies/ archive/` folders (all
> 35 cross-links rewritten and verified). Claude wiring added: 4 skills
> (`xillion-status`, `xillion-checkpoint`, `xillion-verify`,
> `xillion-new-strategy`) + 3 hooks (SessionStart orientation, Bash guard for
> the alembic/DATABASE_URL trap and >5MB staged files, Stop-hook tracker
> enforcement). Checkpoint commits are now standing-authorized (no
> Co-Authored-By, ever).

---

## How this project is structured

Two tracks run in parallel:

- **Track A — Platform**: shared infrastructure every asset class needs
  (correctness, data warehouse, journal, AI, automation). Built once.
- **Track B — Asset pipelines**: the *same repeatable 6-stage pipeline*
  applied per asset class. See [14-asset-pipeline.md](../process/asset-pipeline.md)
  for the stage definitions.

Track A must reach CP3 before any Track B pipeline can complete Stage 2
(backtesting needs the data warehouse).

---

## Timeline target

| Month | Goal |
|---|---|
| **Month 1** | Platform CP1–CP6 + **Options pipeline complete** + **Gold XAUUSD pipeline started** |
| **Month 2** | Gold XAUUSD complete + Forex + platform CP7–CP10 |
| **Month 3** | Stock options + Stocks + automation (CP11–CP14) + crypto if time |

Engineering ≈ 155 hrs. Paper-soak windows are **calendar-bound and cannot be
compressed** — they overlap later engineering, so nothing sits idle.

---

## TRACK A — Platform

### ✅ CP1 — Safety net + correctness `DONE 2026-08-24`
Fixed bugs that made every backtest number untrustworthy.

- [x] `.gitignore` the 32MB `data/*.csv` instrument masters (was about to be committed)
- [x] `xillion/engine/position_math.py` — signed-position arithmetic shared by
      live + backtest engines. Fixes shorting (previously a sell with no
      position credited cash and tracked nothing) **and** a latent live bug
      where a reversal kept the old side's `avg_price`
- [x] Mark-to-market equity — `equity()` was returning cash only, so the curve
      was flat mid-trade and **max drawdown / Sharpe / Sortino were all wrong**
- [x] `xillion/core/contracts.py` — contract multiplier. NIFTY lot size is 65,
      so options P&L was understated **65×**
- [x] Fee model: STT charged sell-side only; `FeeConfig.zero()` for exact tests
- [x] `_sortino` / `profit_factor` return `None` not `float("inf")` (invalid JSON)
- [x] **Bonus fix found during testing:** `compute_metrics` early-returned all
      zeros when no trade had *closed*, so a strategy still holding a winning
      position reported 0% return and 0 drawdown. Portfolio metrics now derive
      from the equity curve; trade stats from closed trades
- [x] 18 regression tests (`test_position_math.py`, `test_backtest_equity.py`)

**Verified:** `pytest tests/` → **96 passed** (78 pre-existing + 18 new).

---

### ✅ CP2 — Data warehouse `DONE 2026-08-24`
Stop re-fetching. Own the data. → *Goal: no third-party historical fees.*

- [x] Fixed `BarRepository.get_bars` — it **ignored its `exchange` argument**,
      so NSE/NFO rows could cross-contaminate. Now filters on it.
- [x] Replaced per-row `session.merge` with a single bulk
      `INSERT .. ON CONFLICT DO UPDATE` (dialect-aware: `pg_insert` on
      Postgres, `sqlite_insert` in tests) — the old per-row loop would have
      made a years-long backfill take one DB round-trip per bar
- [x] Migration `005`: `bar_coverage` + `market_holiday` tables. No new bar
      index needed — `bar`'s existing PK is `(symbol, exchange, timeframe, ts)`
      in exactly the order `get_bars` filters on, so it already serves as the
      range index
- [x] `xillion/data/warehouse.py::BarWarehouse` + `xillion/data/coverage.py`
      — check cache → fetch only the missing date range → persist → re-read
      from DB. A gap that comes back empty (holiday) is still marked
      covered, so it isn't re-requested forever
- [x] **Whole-file bhavcopy persistence** 💡 — `nse_bhavcopy.py` now exposes
      `fetch_all_bars_for_day` (parses every instrument in that day's ZIP,
      not just the one requested) behind a `supports_whole_file_bulk`
      capability flag. `BarWarehouse` uses a wildcard coverage key for such
      providers, so **one fetch covers every symbol on that exchange/day** —
      a second symbol on an already-fetched day costs zero network calls
- [x] Wired `POST /backtest/run-provider` through `BarWarehouse` instead of
      calling `provider.fetch_bars` directly
- [x] Wired `HistoryManager(repository=...)` in `StrategyEngine.spawn` — it
      accepted a `repository` arg since it was written but never read it, so
      a live/paper strategy needing e.g. a 200-bar SMA got nothing for its
      first 200 ticks even with years of DB history sitting right there.
      **Known gap, not fixed here:** the DB fallback defaults to
      `exchange="NSE"` — an NFO/BFO options instance won't get backfilled
      until the exchange-hardcoding audit lands in CP10. Falls back to
      in-memory-only (today's behaviour) for those, no regression either way
- [x] 11 new regression tests (`test_bar_repository.py`, `test_bar_warehouse.py`,
      `test_history_manager.py`) — includes the exact "second run, zero
      provider calls" check and a whole-file-bulk cross-symbol check

**Verified:** `pytest tests/` → **107 passed** (96 prior + 11 new). Ran the
counting-fake-provider scenario from the Verify line directly: first
`BarWarehouse.get_bars()` call makes 1 provider call, an identical second
call makes 0.

---

### ⬜ CP3 — Backfill + run history (~9 hrs)
- [ ] Backfill CLI + `POST /api/data/backfill` + `GET /api/data/coverage` + UI
- [ ] **Run the real 2–5 year backfill** (unattended)
- [ ] Persist `BacktestRun`/`BacktestTrade` — tables exist but **nothing ever
      writes to them**, so no backtest history is queryable
- [ ] `GET /api/backtest/runs` + runs history UI

**Verify:** 2+ years of NIFTY/BANKNIFTY option history queryable locally; a
6-month backtest completes in seconds with no network.

---

### ⬜ CP4 — Signal lifecycle (~9 hrs)
- [ ] **[YOU]** Buy Kite Connect (₹500/mo) + create Telegram bot (@BotFather)
      — `ZERODHA_*` and `TELEGRAM_*` env vars are currently **empty**
- [ ] Entry + **target + stop-loss + EXIT** signals with parent-child linkage.
      Today `signal_log` is entry-only and **never writes an EXIT row**
- [ ] Signals read API + Alerts page + Telegram formatting

**Verify:** paper alert fires BUY with target+SL, then a correctly-timed SELL.

---

### ⬜ CP5 — Strategy builder (~14 hrs)
- [ ] Condition-builder UI (metric / operator / threshold rows) on top of the
      existing `params_schema` form
- [ ] Generic `ConditionStrategy` that interprets builder output — so new
      setups need no new Python file
- [ ] Indicator library: SMA, EMA, RSI, ATR, VWAP, Bollinger, MACD, supertrend
- [ ] Multi-leg option structure support (straddle/strangle/spreads)
- [ ] **Parameter optimisation: grid search + walk-forward** (was in the old
      `09-progress-tracker.md` "Future" list). Needed for Stage 2's
      robustness check — a strategy whose results collapse on a ±10%
      parameter move is curve-fit, and this is what detects that

**Verify:** build a working setup end-to-end in the UI with zero code, and run
a parameter sweep that surfaces an over-fit configuration.

---

### ⬜ CP6 — Strategy journal + feedback loop (~14 hrs) → *Goal #8*
- [ ] `StrategyJournal` — every signal linked to its outcome
- [ ] Auto-tag failure modes: stopped out / target missed / late entry /
      slippage / no-fill / gap
- [ ] Journal UI — performance over time, failure patterns grouped
- [ ] **Strategy versioning** — param changes tracked as versions, compared
- [ ] **Markdown export per strategy → `docs/strategies/<name>.md`** so the
      RAG layer (CP8) ingests real trade history, not just code

---

### ⬜ CP7 — MCP server (~8 hrs) → *Goal #6*
- [ ] Read-only tools: `list_strategies`, `get_positions`, `get_trades_today`,
      `get_portfolio`, `run_backtest`, `get_journal`
- [ ] Guarded control tools: `start_instance`, `stop_instance`, `kill_switch`
- [ ] **No freeform order construction by an LLM** — query/control only

---

### ⬜ CP8 — AI assistant + RAG (~11 hrs) → *Goal #6*
- [ ] MCP **client** + tool loop in prosper-engine's `TradingAgent` (it has
      `chat_full()` with tool support but **never passes tools**)
- [ ] Ingest `docs/strategies/*.md` + journal exports into Chroma RAG
- [ ] Hosted LLM (Gemini/Groq free tier)
- [ ] Pre-trade hook: AI reviews signal → confidence % on alert → **prediction
      logged against actual outcome** so you can tell signal from noise

---

### ⬜ CP9 — Automation + hardening (~17 hrs) → *Goal #7*
- [ ] Order state machine — `Strategy.on_order_update` is **never called**
- [ ] **Position reconciliation on startup** — a restart currently loses all
      in-memory positions. Hard gate before real money
- [ ] Auto start/stop instances at market open/close
- [ ] Logs DB persistence + `GET /api/positions`
- [ ] Self-failure alerting — if the *system* breaks, you get told
- [ ] **Verify risk-limit hot-reload** — `PUT /api/settings/risk-limits`
      persists to DB, but it's unconfirmed whether it updates the in-memory
      `RiskManager` at runtime. If it doesn't, changing a limit in the UI
      silently does nothing until restart (carried over from
      `09-progress-tracker.md` P1)

**Verify:** kill the process mid-position, restart, positions rebuild correctly.

---

### ⬜ CP10 — Maintenance mode (~9 hrs) → *Goal #10*
- [ ] Daily/weekly digest — the thing that makes 3–6 hrs/week real
- [ ] Self-healing / auto-recovery
- [ ] Runbook: what to check, what to ignore, when to intervene

---

## TRACK B — Asset pipelines

Each asset runs the same 6 stages — see
[14-asset-pipeline.md](../process/asset-pipeline.md). Mark stages as they complete.

| Asset | S1 Build | S2 Backtest | S3 Paper | S4 Live | S5 Auto | S6 Docs |
|---|---|---|---|---|---|---|
| **Options** (NIFTY/BANKNIFTY/SENSEX) · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Gold XAUUSD** · Funding Pips MT5 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Forex** · Funding Pips MT5 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Stock options** · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Stocks** · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Crypto** · TBD exchange | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

### Per-asset enablement work
Infrastructure each asset needs before its pipeline can start:

- **Options** — ✅ ready (Zerodha + NSE bhavcopy + instrument resolver all exist)
- **Gold XAUUSD / Forex** — ⬜ needs: MT5 broker plugin, 24×5 session calendar,
  currency field, FX lot math, **Funding Pips drawdown rules as hard risk
  limits** (breaching one instantly fails the account), XAUUSD data provider
- **Stock options** — ⬜ needs: stock-option chain resolution (reuses index logic)
- **Stocks** — ⬜ needs: equity instrument type (cheapest — multiplier is 1)
- **Crypto** — ⬜ needs: exchange integration, **1% TDS in the fee engine**
  (this alone makes most active crypto strategies unprofitable — model it
  before trading, not after)

---

## Blocked on you

| # | Item | Blocks |
|---|---|---|
| 1 | Kite Connect plan + Telegram bot (~1 hr) | CP4 onward |
| 2 | Real strategy rules from trading-course videos | Options S1 |
| 3 | CA opinion on Funding Pips prop-firm income | Gold/Forex S4 |
| 4 | Funding Pips account + challenge | Gold S3 onward |
| 5 | Confirm ₹50k starting capital, ₹1,000/mo first milestone | Options S4 |

---

## Explicitly deferred / out of scope

**See [16-deferred-backlog.md](deferred-backlog.md)** — every consciously-
deferred item with its reason and the trigger that would justify revisiting.
Check it before treating anything as a missing feature.

---

## Update protocol

**Whenever a checkpoint or pipeline stage completes:**

1. Tick the boxes and change ⬜ → ✅ (or 🟡 for in-progress)
2. Update **Last updated** and **Current position** at the top
3. Add a one-line note on anything surprising found along the way — the
   surprises are what a cold session most needs to know
4. If the work produced a strategy insight, also write it to
   `docs/strategies/<name>.md` (RAG ingests these)

**Status legend:** ✅ done · 🟡 in progress · ⬜ not started · 🔴 blocked
