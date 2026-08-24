# 15 — Task Tracker (LIVING DOCUMENT)

> **🔴 THIS IS THE SINGLE SOURCE OF TRUTH FOR "WHERE ARE WE".**
> Any session — human or AI — starts here. If you complete work, you update
> this file **in the same session**. See [Update protocol](#update-protocol).

**Last updated:** 2026-08-24
**Current position:** Track A · CP1 ✅ + CP2 ✅ + CP3 🟡 + CP4 🟡 + CP5 🟡 + CP6 ✅
+ CP7 ✅ + CP8 🟡 → **CP9 is next** (Automation + hardening — order state
machine, position reconciliation on restart, the live/paper real-time bar
gap found while building CP5, auto start/stop, risk-limit hot-reload
verification). CP3/CP4/CP5/CP8 are each "engineering done, one item needs
something only you can supply" (real backfill run, real Telegram bot, a
real options strategy to design multi-leg support against, a cloud LLM key
— see Blocked on you). None of that blocks CP9. **Note:** CP8's code lives
mostly in the separate `prosper-engine` repo and is uncommitted there —
xillion's commit standing-authorization doesn't extend to it.
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

### 🟡 CP5 — Strategy builder `MOSTLY DONE 2026-08-24 — multi-leg options carried to Track B`
- [x] Condition-builder UI (metric / operator / threshold rows) on top of the
      existing `params_schema` form — new `condition_list` param type,
      `ConditionListEditor` renders rows (metric+period, operator, value-or-
      another-metric), writes straight into the same JSON params blob every
      other strategy already uses
- [x] Generic `ConditionStrategy` (`strategies/condition_strategy.py`) that
      interprets builder output — a new setup is a JSON blob, not a new
      Python file. Long or short, entry/exit each an AND of conditions
- [x] Indicator library (`xillion/engine/indicators.py`): SMA, EMA, RSI, ATR,
      VWAP (rolling, not session-anchored — see its docstring), Bollinger,
      MACD, Supertrend. `rsi_threshold_alert.py` refactored to import the
      shared `rsi()` instead of its own private copy — one RSI formula in
      the codebase, not two that could silently drift apart
- [ ] **Multi-leg option structures (straddle/strangle/spreads) — NOT done,
      carried to Track B.** This needs a real options strategy to design
      against (multi-leg P&L combination, margin, which legs move together)
      — building it generically first, with no real strategy driving the
      requirements, risks guessing wrong. Better triggered by Blocked on
      you #2 (your trading-course rules) when Options reaches Stage 1
- [x] **Parameter optimisation: grid search + walk-forward**
      (`xillion/engine/optimization.py`) — walk-forward's overfit heuristic
      verified against a deliberately-constructed regime-change scenario
      (steady uptrend in-sample, hard reversal out-of-sample): correctly
      flags `is_likely_overfit=True` there and `False` when the same trend
      continues through both windows
- [x] `POST /backtest/optimize` + `POST /backtest/walk-forward` (reuse
      `_resolve_strategy_and_bars`, the same warehouse-backed fetch
      `/run-provider` already used) + sweep results UI on the Backtest page

**🐛 Real bug caught only by loading the app, not by tests:** the plugin
loader's `ParamSpec.type` allowlist didn't include `"condition_list"`, so
`condition_strategy.py` failed discovery and **silently vanished from the
strategy dropdown** — logged as a discovery error, but nothing surfaced it
anywhere a person would see. Fixed in `xillion/core/plugin_loader.py`
+ a regression test asserting `"Condition Strategy"` actually discovers.

**Verified, both end-to-end in a real browser against real data** (this
sandbox's disposable-SQLite workaround, per the CP2/CP3 note on Supabase
being unreachable here):
1. **Zero-code setup:** built "close crosses above SMA(3)" entry / "close <
   10" exit entirely by clicking, uploaded a CSV, ran it — P&L **−₹11.01**,
   matching the hand-verified unit test's −11.00 (the 1-paisa gap is real
   brokerage/STT the unit test zeroed out via `FeeConfig.zero()`).
2. **Parameter sweep against real NSE data:** grid search over RSI
   Threshold's `period` (10/14/20) via the free NSE Bhavcopy provider for
   real January 2024 data — persisted **124K+ real bars** in the process
   (the whole-file-bulk lever from CP2, proven again at a full month's
   scale, not just the 2-day CP3 sample), returned a correctly ranked
   3-row results table. (The specific symbol tried didn't match any real
   contract, so all three came back 0 trades — an honest result, not a
   failure: the fetch, the warehouse persistence, and the ranking all ran
   for real.) Walk-forward's own UI (folds/train-ratio fields, toggle) was
   checked structurally rather than re-run live, since its logic already has
   a dedicated, harder unit proof (the regime-change scenario above) than a
   second live run would add.

---

### ✅ CP6 — Strategy journal + feedback loop `DONE 2026-08-24` → *Goal #8*
- [x] `StrategyJournal` (`xillion/engine/journal.py`) — combines both places
      an outcome actually lives: `signal_log` ENTER/EXIT pairs (alert mode,
      has real target/stop-loss on record) and `backtest_trade` (has real
      P&L, but never had target/stop-loss — `ctx.buy()`/`ctx.sell()` never
      carried those fields, only `ctx.alert_entry()` does)
- [x] **Auto-tag failure modes — honestly scoped, not the full taxonomy.**
      `stopped_out` / `target_hit` are only claimed when the exit price
      *actually crossed* the recorded level; `win`/`loss` from real P&L.
      The rest of the template's taxonomy (`late_entry`, `slippage`,
      `no_fill`, `gap`, `regime_change`, `data_gap`, `system_error`) needs
      tick-level timing or broker fill/rejection data this system doesn't
      capture yet — auto-classifying those would be inventing certainty the
      data doesn't support, so they're `unclassified` until a human tags
      them via the new manual override (`journal_note` table)
- [x] Journal UI (`/journal`) — entries/wins/failures/win-rate, filter by
      strategy, click a failure/loss/unclassified row to set a manual
      failure mode + "what changed" note
- [x] **Strategy versioning** — `strategy_version_history`, append-only.
      `strategy_class` is upserted in place on every plugin sync (unchanged
      behaviour), which would silently lose prior versions the moment a
      strategy's code changes — `plugin_sync.py` now logs the old
      `(version, code_hash)` before overwriting, only when it actually changed
- [x] **Markdown export → `docs/strategies/<name>.md`** — writes only
      sections 5 (Failure log) and 6 (Version history); sections 1-4 (rules,
      backtest/paper/live results) are human-authored and survive re-export
      untouched, verified by round-tripping real template content

**🐛 Real bug caught only by inspecting real export output, not by the unit
tests that were passing:** the section-replace regex used `\s` in its
separator-row character class, which matches `\n` — so it silently
swallowed the template's empty placeholder row (`| | | | |`) into the
"header" group instead of the "replaceable data rows" group. Real journal
rows got appended *after* the stale placeholder instead of replacing it. The
existing tests all checked new content was present but never checked the
placeholder was gone — fixed the regex (`[ \t\-|]` instead of `[-\s|]`) and
added that missing assertion.

**Verified end-to-end in a real browser**, both journal sources exercised
through their real code paths (not hand-inserted rows): an alert-mode
ENTER/EXIT pair via `StrategyEngine.spawn()` (correctly auto-tagged
`stopped_out` — exit price genuinely crossed the recorded stop-loss) and a
`backtest_trade` via `persist_backtest_run()`. Manually tagged the backtest
loss as `late_entry` with a note, confirmed it persisted and re-rendered.
Exported to `docs/strategies/sma-cross.md`, inspected the real file on disk,
confirmed clean output, then deleted that verification artifact — it's
synthetic test data, not real strategy documentation, and doesn't belong in
the repo's actual docs.

---

### ✅ CP7 — MCP server `DONE 2026-08-24` → *Goal #6*
- [x] Read-only tools: `list_strategies`, `get_positions`, `get_trades_today`,
      `get_portfolio`, `run_backtest`, `get_journal` — every tool is a thin
      translation layer over the real REST API (`xillion/mcp_server/client.py`),
      so each one inherits the app's real auth instead of a second path
- [x] Guarded control tools: `start_instance`, `stop_instance`, `kill_switch`
      — `kill_switch` forwards straight to the existing TOTP-gated
      `/risk/kill-switch/activate`, same gate as the web UI, never bypassed
- [x] **No freeform order construction by an LLM** — structural, not just a
      rule: there is no order-placement tool at all, and
      `test_no_order_placement_tool_exists` in `test_mcp_server.py` asserts
      the exact tool-name set so a future addition can't slip one in unnoticed
- [x] **`GET /api/positions`** (`xillion/api/positions.py`) — pulled forward
      from CP9's "Logs DB persistence + GET /api/positions" bullet since
      `get_positions` needed it now. CP9's DB-persistence half of that
      bullet is separate and still pending

**Verified for real, not just unit-tested against a mock:** installed the
official `mcp` SDK (resolved to v2.0.0 — its high-level API moved from
`FastMCP` to `mcp.server.MCPServer`, a rename this session had to discover
by inspecting the installed package rather than assuming prior knowledge of
the SDK still applied), started the real backend, created a real user via
`/api/auth/setup`, then ran an actual MCP client (`mcp.client.stdio`) doing
a real protocol handshake against the real server subprocess: `initialize()`
succeeded, `list_tools()` returned all 9 real tools, `list_strategies` and
`get_portfolio` returned real data from the real running app (including CP5's
"Condition Strategy"), and calling `start_instance` on a nonexistent id
correctly surfaced the REST API's 404 as a clean MCP tool error rather than
crashing the server.

---

### 🟡 CP8 — AI assistant + RAG `MOSTLY DONE 2026-08-24 — cloud LLM key needs YOU`
**Cross-repo:** most of this checkpoint's work is in `prosper-engine`
(`~/Documents/personal/Projects/Learnings/prosper-engine`), a separate repo.
**Its changes are uncommitted** — xillion's commit standing-authorization
doesn't extend there; review and commit them yourself.

- [x] MCP **client** + tool loop in prosper-engine's `TradingAgent`
      (`agents/trading/agent.py::_chat_with_tool_loop`, new
      `agents/trading/xillion_mcp.py`) — `chat_full()` had tool support
      since 22 days before this session but nothing ever called it with
      `tools=`; now it loops (capped at 5 rounds) executing xillion's real
      MCP tools until the model stops calling them
- [x] **Real local tool-calling, not just a mock:** `core/llm_client.py`'s
      `_ollama()` silently dropped `tools` entirely before this — verified
      live that Ollama's `/api/chat` genuinely supports tool-calling for
      qwen3:8b (its `/api/tags` capabilities include `"tools"`) and wired
      it through properly (Ollama returns already-parsed dict arguments,
      not a JSON string like the OpenAI-compatible backends — this needed
      its own code path, not reuse of the existing parsing)
- [x] Ingest `docs/strategies/*.md` + journal exports into Chroma RAG
      (`prosper-engine/scripts/ingest_xillion.py`) — CP6's markdown export
      already writes real failure-log/version-history data into these
      files, so ingesting them covers "journal exports" too, not a second
      pipeline. Idempotent (stable ids from strategy slug + section/row)
- [ ] **Hosted LLM (Gemini/Groq free tier) — NOT done, needs you.** The
      swappable backend code already existed (built 22 days before this
      session) and still works; no cloud API key has ever been configured
      (`prosper-engine/.env` has only Ollama settings). Not a blocker for
      anything above — Ollama's real tool-calling made full verification
      possible without one. Get a free-tier key (Gemini via Google AI
      Studio is the earlier recommendation) and set it in `prosper-engine/.env`
      whenever you want a faster/hosted option instead of local Ollama
- [x] Pre-trade hook: AI reviews signal → confidence % → **prediction logged
      against actual outcome**. `signal_log.ai_confidence` (migration 008)
      + prosper-engine's new `POST /confidence` endpoint. **Runs as a
      background task** (`_fetch_and_store_confidence` in
      `strategy_engine.py`), strictly after the alert has already fired and
      the signal_log row already persisted — real qwen3:8b calls measured
      at 30-60s+, far too slow to sit in a live alert's critical path.
      Journal (CP6) surfaces `ai_confidence` next to the real outcome

**🐛 Two real bugs found only by running this for real, not by unit tests:**
1. `mcp>=1.2.0` resolved to `mcp==2.0.0`, which needs `starlette>=1.x` —
   breaking prosper-engine's pinned `fastapi==0.115.0` (`APIRouter()` itself
   raised `TypeError: unexpected keyword argument 'on_startup'`) for **every
   route in the app**, not just the new one. None of the test suite caught
   it because no test imported `api.routes.*` or `api.main`. Fixed by
   pinning `mcp==1.9.4` (needs only `starlette>=0.27`) +
   `starlette==0.38.6` + `sse-starlette==1.6.5`, verified with `pip check`
   and a real `uvicorn api.main:app` boot.
2. The confidence-endpoint's regex parser didn't accept a leading `-` sign,
   so `CONFIDENCE: -10` silently fell through to the neutral-50 fallback
   instead of parsing and clamping to 0 — caught by
   `test_clamps_out_of_range_confidence`, one of this checkpoint's own new
   tests, not by manual inspection.

**Verified for real, twice, against live local Ollama (no cloud key
needed):**
1. Asked the real `TradingAgent.chat()` "what strategies are available" —
   it correctly chose to call `list_strategies` (not guess), got the real
   tool result over a real MCP stdio connection to xillion's real running
   server, and synthesized an accurate, complete answer naming all 4 real
   strategies.
2. Spawned a real alert-mode instance, fired a real ENTER signal: the alert
   sent and the signal_log row persisted in **0.06s**, then ~46s later the
   background task filled in `ai_confidence=90.0` with real reasoning about
   the setup's 3:1 risk/reward — confirmed via the journal that the
   prediction and the (still-open) outcome sit side by side, exactly the
   "prediction logged against actual outcome" this bullet asked for.

All real Chroma/prosper-engine data touched during verification (one test
chat turn, one test strategy's RAG chunks) was deleted afterward — confirmed
the collections only contain the user's genuine pre-existing forex-scalping
data.

---

### ⬜ CP9 — Automation + hardening (~17 hrs) → *Goal #7*
- [ ] Order state machine — `Strategy.on_order_update` is **never called**
- [ ] **Position reconciliation on startup** — a restart currently loses all
      in-memory positions. Hard gate before real money
- [ ] **Live/paper real-time bar aggregation into `ctx.history()` — found
      2026-08-24 while building CP5.** `HistoryManager.add_bar()` exists but
      is **never called anywhere** in `strategy_engine.py` — nothing turns
      live ticks into bars and pushes them into the in-memory cache. CP2's
      DB-repository fallback (`xillion/data/history.py`) means an `on_bar`
      strategy still gets real historical bars via the warehouse, so this
      isn't a total blank — but it means **today's still-forming candles
      never show up**, only whatever was last backfilled. Any `on_bar`
      strategy (RSI Threshold, Condition Strategy, anything from CP5's
      builder) checking an intraday condition mid-session is working off
      stale data until this is built. Tick-only strategies (`on_tick`, e.g.
      Nifty Spot Alert) are unaffected
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
| 7 | A real multi-leg options strategy (straddle/strangle/spread) to design CP5's multi-leg support against — same trading-course source as #2 | CP5 close-out, Options S1 |
| 8 | A free-tier cloud LLM key (Gemini/Groq) in `prosper-engine/.env` — not blocking (Ollama's real tool-calling covered full verification), just faster/hosted than local Ollama when you want it | CP8 close-out |

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
