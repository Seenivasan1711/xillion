# 15 — Task Tracker (LIVING DOCUMENT)

> **🔴 THIS IS THE SINGLE SOURCE OF TRUTH FOR "WHERE ARE WE".**
> Any session — human or AI — starts here. If you complete work, you update
> this file **in the same session**. See [Update protocol](#update-protocol).

**Last updated:** 2026-08-24
**Current position:** Track A · CP1 ✅ + CP2 ✅ + CP3 🟡 + CP4 🟡 (both only missing a real-credentials proof, not code — see Blocked on you #1 and #6) → **CP5 is next.** CP5 (strategy builder: condition-builder UI, generic `ConditionStrategy`, indicator library, parameter optimisation) is pure platform engineering — not blocked on anything. Your trading-course strategy rules (Blocked on you #2) are needed later, to actually *use* the builder for Options Stage 1 in Track B, not to build it
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

### 🟡 CP3 — Backfill + run history `MOSTLY DONE 2026-08-24 — one item needs YOU`
- [x] Backfill CLI (`scripts/backfill.py`, resumable year-by-year) +
      `POST /api/data/backfill` + `GET /api/data/backfill` (job status) +
      `GET /api/data/coverage`, plus a Coverage & backfill panel under
      Settings → Data Providers
- [ ] **Run the real 2–5 year backfill — NOT DONE, needs you.** This sandbox
      can't reach Supabase directly (`db.<project>.supabase.co` doesn't
      resolve from here — general internet works fine, just not that host;
      see note below). Run it from your own machine once CP3 is pulled:
      `python scripts/backfill.py --provider "NSE Bhavcopy (Free)" --symbol <full tradingsymbol> --exchange NFO --instrument-type option --from-date 2021-01-01 --to-date 2026-08-24`
      — safe to re-run, already-covered years are skipped
- [x] Persist `BacktestRun`/`BacktestTrade` — tables existed since migration
      001/002 but nothing ever wrote to them; wired into all three
      `/backtest/run*` endpoints
- [x] `GET /api/backtest/runs` + `GET /api/backtest/runs/{id}` + Run history
      panel on the Backtest page

**Verify:** Browser-verified end-to-end against a disposable local SQLite DB
(same Supabase-unreachable reason above) — real login, real click-through,
real NSE network fetch. **2+ years of NIFTY/BANKNIFTY option history
queryable locally** is not yet true for the real Supabase DB — that's
exactly the one unchecked item above.

**🐛 Real bug caught by the browser check, not the unit tests:** the CP2
bulk `upsert_bars` blew past SQLite's default 999-bound-parameter limit
("too many SQL variables") the moment a real whole-file bhavcopy fetch tried
to persist hundreds of contracts in one statement — every unit test used 1-2
bars, so this never surfaced there. Fixed by batching at 100 rows/statement
(dialect-agnostic, so Postgres gets the same safety margin even though its
own limit is far higher). Confirmed fixed against real NSE data: one
two-day backfill request persisted **124,012 bars across 62,402 distinct
F&O contracts** from 2 real bhavcopy files — this is the CP2 "big lever"
actually proven, not just unit-tested.

---

### 🟡 CP4 — Signal lifecycle `ENGINEERING DONE 2026-08-24 — Telegram proof needs YOU`
- [ ] **[YOU]** Buy Kite Connect (₹500/mo) + create Telegram bot (@BotFather)
      — `ZERODHA_*` and `TELEGRAM_*` env vars are currently **empty**. Blocks
      only the *real* Telegram proof below, not anything already built
- [x] Entry + **target + stop-loss + EXIT** signals with parent-child linkage.
      `signal_log` was entry-only with no ENTER/EXIT distinction at all — its
      `signal_type` column actually held the free-text tag, not a lifecycle
      stage (migration `006`). New `ctx.alert_entry()`/`ctx.alert_exit()` on
      `StrategyContext`; an EXIT auto-links to the most recent **still-open**
      ENTER sharing its `(instance, symbol, tag)` — verified a same-tag
      entry/exit/entry/exit sequence links each exit to *its own* entry, not
      the earlier closed one
- [x] `GET /signals` (+ instance filter) + Alerts page + Telegram-body
      formatting (target/stop-loss lines, "closing entry #N")

**Verified two ways:**
1. `pytest` — 6 new tests (`test_signal_lifecycle.py`,
   `test_signals_api.py`), incl. the repeated-tag-doesn't-cross-link case.
2. **Browser, real engine code path, not a mocked UI:** drove
   `StrategyEngine.spawn()` + `ctx.alert_entry`/`alert_exit` for real against
   a disposable local DB (same Supabase-unreachable reason as CP2/CP3),
   confirmed the Alerts page renders exactly what was expected — an open
   ENTER with target/SL, an EXIT correctly linked to entry #1, a second
   ENTER still open. Notifier used was a fake (`_FakeNotifier`) since no
   real Telegram bot token exists yet — **that's the one thing not proven
   end-to-end**: real Telegram delivery, blocked on item #1 above.

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
| 6 | Run `python scripts/backfill.py` for real (2-5yr) from a machine that can reach Supabase — this sandbox can't resolve `db.<project>.supabase.co` | CP3 close-out, Options S2 |

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
