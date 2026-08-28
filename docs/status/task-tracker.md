# 15 — Task Tracker (LIVING DOCUMENT)

> **🔴 THIS IS THE SINGLE SOURCE OF TRUTH FOR "WHERE ARE WE".**
> Any session — human or AI — starts here. If you complete work, you update
> this file **in the same session**. See [Update protocol](#update-protocol).

**Last updated:** 2026-08-28
**Current position:** **2026-08-28: Gold Lane B1's broker+bridge plumbing
built (see the Track B section below) — code-complete but unverified, no
real MT5 account/Wine environment in this sandbox.** Before that,
`feat/options-alert-engine` was merged to `main`
2026-08-26 (fast-forward, 259 files, all of Track A + Track A extension +
CP15 + a full frontend UX overhaul) and pushed.** `main` is now the current
baseline; a new branch will be created off it for the next phase (Track B
asset pipelines + remaining deferred Track A items). This session (2026-08-25
into 2026-08-26) also did a large frontend UX pass not itemized as its own
checkpoint: new SVG logo/favicon, sidebar collapse, command palette,
skeleton loaders, a redesigned login page, light-theme contrast/glassy
rebalance, Settings split into Settings + Configuration, Logs merged into a
single Dev page with a real WS-connection-status badge, and a Telegram
"send test message" / Dhan "check connection" flow. Both Dhan and Telegram
are now genuinely connected and verified live on Render (manual-tasks.md
items #10/#11 resolved).

**Real production bug found and fixed 2026-08-26, while diagnosing why a
Dhan paper instance kept showing "No live tick source":** the `dhanhq` SDK's
`MarketFeed.__init__` calls `asyncio.set_event_loop(self.loop)` on whatever
thread constructs it — since `brokers/dhan.py`'s `_start_feed()` runs on the
main thread (the same one FastAPI/uvicorn's server loop runs on), this
silently overwrote the process's default event loop. Manifested in
production as `dhan_tick_broadcaster` crash-looping with `cannot reuse
already awaited coroutine` until `task_supervisor.py`'s restart budget (5
restarts/10min) was exhausted, after which the feed just silently stayed
dead — no further alert, nothing to notice short of checking Dev logs.
Fixed by restoring the correct event loop immediately after constructing
`MarketFeed`. Two related bugs found in the same pass: (1) every
`_try_connect_dhan()`/`_try_connect_zerodha()` call (daily refresh, manual
reconnect, settings save) leaked a supervised broadcaster task, since the
previous one's handle was never stored or cancelled — now tracked on
`app.state` and cancelled before starting a new one; (2) the SDK's own WS
reconnect loop retries every ~1s forever uncapped, so a bad connection
flooded the Dev-page logs at roughly 1 line/sec indefinitely — now gives up
after 10 consecutive failures and alerts once via Telegram instead. Also
added full-traceback capture to `task_supervisor.py`'s crash logging (it
previously only logged `str(exc)`, making a crash like this one very hard to
diagnose from Telegram/Dev-log output alone).

**Previous position (2026-08-25), preserved for history:** **The entire Track A extension (CP11-CP15) is now
code-complete.** Track A original (CP1-CP10) was already done. In this
session: CP11 (multi-leg execution + protective orders) done, plus its own
follow-up (Options Stage 2 backtest genuinely unblocked, with a real
open→close trade through `BacktestEngine`). CP12 (trailing-stop engine)
done, including the arguably more load-bearing fix that `ctx.state` now
actually survives a restart (it never did before, despite the class's own
docstring claiming it). CP13 (expanded risk engine) done — 18 checks, 100%
branch coverage, and the previously-dead `AuditLog` finally wired in. CP14
(EOD reconciliation + square-off) done — X02 and M01 as independent
scheduled jobs, verified against the exact "crash mid-position, restart
after close" scenario the checkpoint asked for. CP15 (Dhan as a second full
broker) is **code-complete but not live-verified** — `brokers/dhan.py`
built against DhanHQ's real docs/SDK (fetched and read directly this
session, not assumed), multi-broker selection now genuinely wired
end-to-end (a real pre-existing bug found and fixed: `_resolve_broker` was
hardcoded to Zerodha only), but running an actual order through it needs a
real Dhan account — logged as the literal next thing to do in
[manual-tasks.md](manual-tasks.md), not silently skipped.

**What's left to trade real money, in order:** (1) **a free Dhan account +
token (#10) is still the fastest path to seeing the app run for real** —
paper mode no longer needs Zerodha at all, so this goes first and costs
nothing; (2) the real 2-5yr NSE backfill (#6) — **🔵 no longer blocked on
you, Claude is running it now** (NIFTY+BANKNIFTY-scoped, see CP3); (3) a
Telegram bot (#11) for alerts, DB-configurable via Settings → Notifications
as of 2026-08-25 — Kite Connect (#1) itself stays deferred, low priority,
Rakesh's explicit call; (4) a real broker-side bracket/GTT order path
(CP11's own honest gap — protective orders are software-stop only today);
(5) the static-IP whitelisting SEBI requires for live order placement.
**2026-08-25: five other Blocked-on-you items resolved by Rakesh's
decisions in one pass** — ₹50k/₹1,000-mo milestone confirmed, CA opinion
decided not needed (foreign income on ITR instead), Funding Pips account
already held, Redis choice decided (Upstash), LLM key + static-IP research
explicitly deferred for later. See `manual-tasks.md` for the live
checklist. CP3/CP4/CP5/CP8 remain "engineering done, one item needs
something only you can supply" (CP3's item is now in progress, not
waiting on you). **Note:** CP8's code lives mostly in the separate
`prosper-engine` repo and
is uncommitted there — xillion's commit standing-authorization doesn't
extend to it.

**Found while checking for other gaps, 2026-08-25:** Settings → Risk and →
Danger zone tabs have called `/settings/risk-limits`, `/settings/reset-data`,
`/settings/wipe` since they were built, but none of those routes existed on
the backend — both tabs 404'd, unrelated to anything else this session.
Added `reset-data` (clears trade/log/run data, preserves credentials +
config) and `wipe` (clears everything, `/auth/setup-status` naturally
takes over) in full. **`risk-limits` persists but is deliberately NOT
wired into live enforcement** — its field shape doesn't map cleanly onto
how risk actually works today (account-wide `default_*` config +
per-instance `risk_limits_json`), and guessing at that mapping risks
getting real risk enforcement wrong, not just a cosmetic bug. Left as an
open design gap rather than faked. 404/404 tests passing.

**Active branch:** `feat/track-b-pipelines` (created 2026-08-26 off `main`
at `0273cf3`, worktree at `.claude/worktrees/track-b-pipelines`). Covers the
next phase broadly: the deferred Track A validation items (real pass/fail
backtest run, paper-soak monitoring, Zerodha/Dhan product-type decision,
static-IP research) first, then Track B asset pipelines (Gold/MT5, MCX,
stocks, crypto) as they come up. `main` itself stays the stable baseline —
`feat/options-alert-engine` is fully merged into it and can be deleted.

> **2026-08-26 — Supabase free-tier overage, root-caused and fixed.**
> Supabase emailed that the DB hit 1611MB against the 500MB free limit.
> `bar` (1056MB) + `option_chain_snapshot` (519MB) turned out to be 98% of
> that — both 100% regenerable backtest/historical cache, never live app
> state, and never needed to share a cloud DB with the ~1MB of actual live
> state (users, sessions, instances, credentials, journal) at all. Split
> them onto a separate local-only SQLite warehouse DB (`Settings.
> backtest_database_url`, defaults to `./data/backtest_warehouse.db`,
> `get_warehouse_session_factory()` in `xillion/db/session.py`) — see
> `CLAUDE.md`'s Deploy workflow section for the full picture, including the
> Render-ephemeral-disk implication. Existing data was copied across via
> `scripts/migrate_warehouse_to_local.py` (keyset-paginated, not OFFSET —
> `bar` alone is 4.5M+ rows) rather than re-fetched from scratch, then
> reclaimed from Supabase via `scripts/truncate_supabase_warehouse.py`.
> Also found in passing: a genuine correctness gap where
> `xillion/api/backtest.py`'s in-progress option-chain backfill for the
> real credit-spread pass/fail run (see the 2026-08-26 crash-loop entry
> above) was about to make the Supabase overage significantly worse —
> stopped mid-run once the email surfaced this.
>
> **2026-08-27 — truncation completed, confirmed via direct query.**
> Supabase auto-flips a project into DB-level read-only mode once it
> exceeds its free-tier disk quota — this blocks even the `TRUNCATE`
> that would free the space, a genuine chicken-and-egg the project was
> stuck in. Supabase's documented fix
> (`SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE`) only affects
> *subsequent* transactions in the same session, not the one already open
> — and the SQL Editor's "Run" wraps a pasted multi-statement block in one
> implicit transaction, so the naive combined-script version still hit
> `cannot execute TRUNCATE TABLE in a read-only transaction`. Fixed by
> adding an explicit `commit;` between the `SET` and the `TRUNCATE`s in
> one single Editor run, forcing a new transaction that picks up the
> just-changed session default:
> ```sql
> set session characteristics as transaction read write;
> commit;
> TRUNCATE TABLE "bar";
> TRUNCATE TABLE "bar_coverage";
> TRUNCATE TABLE "option_chain_snapshot";
> commit;
> set default_transaction_read_only = 'off';
> ```
> Confirmed via `pg_database_size(current_database())`: **1611MB → 40MB.**
> Local warehouse (`data/backtest_warehouse.db`, 1.1GB) holds the full
> migrated dataset — 4,498,851 `bar` rows, 2,208,349
> `option_chain_snapshot` rows, verified matching source counts before
> truncation.

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

### ✅ CP3 — Backfill + run history `DONE 2026-08-26 — 2021-2026 NIFTY+BANKNIFTY backfilled`
- [x] Backfill CLI (`scripts/backfill.py`, resumable year-by-year) +
      `POST /api/data/backfill` + `GET /api/data/backfill` (job status) +
      `GET /api/data/coverage`, plus a Coverage & backfill panel under
      Settings → Data Providers
- [x] **Run the real 2–5 year backfill — DONE 2026-08-26.**
      Was blocked on this sandbox not reaching Supabase; turned out the
      project was paused (Rakesh resumed it 2026-08-25), and the
      direct-connection hostname is IPv6-only anyway — switched `.env` to
      the Session pooler (IPv4). **Scoped to NIFTY + BANKNIFTY only**, not
      the whole NFO market: an unfiltered 2021→today run would be ~85M
      rows / ~25-30GB, well past free-tier Postgres storage. Added a real
      `underlying_filter` parameter threaded through
      `xillion/core/data_provider_base.py` →
      `data_providers/nse_bhavcopy.py` → `xillion/data/warehouse.py` →
      `scripts/backfill.py --underlying-filter`, keeping the whole-file
      bulk-fetch lever (still one download per day) but only persisting
      matching underlyings. **Real subtlety handled, not glossed over:** a
      filtered bulk fetch must NOT share the unfiltered `WILDCARD_SYMBOL`
      coverage key, or a later full-market request for the same dates
      would wrongly think it's already covered and skip the excluded
      contracts — uses a distinct coverage key (`*:NIFTY,BANKNIFTY`)
      instead.

      **First run "completed" but was silently wrong for 2021-2023 —
      caught by checking the actual data, not by trusting the log
      output.** NSE's current bhavcopy URL (the "UDiFF" format this
      provider used exclusively) genuinely 404s for any date before
      2024-01-01 — confirmed by directly probing the URL across several
      dates, not assumed. `_fetch_and_parse_day` treats a 404 as "holiday,
      no trading" (correct for a real holiday) and marks that date range
      as covered — so 2021-2023 got marked fully covered in
      `bar_coverage` while genuinely containing zero real bars for
      2,646+ days straight. Caught by querying the actual `bar` table
      after the "successful" run and finding the earliest row was
      2024-01-01, not 2021-01-01.

      **Fixed for real, not patched around:** found (via WebSearch, then
      verified by downloading and parsing an actual 2021-06-15 file, not
      trusting the search result) that NSE's older archive format still
      exists at a different URL with different columns
      (`archives.nseindia.com/content/historical/DERIVATIVES/...`,
      `INSTRUMENT`/`SYMBOL`/`EXPIRY_DT`/`STRIKE_PR` instead of the new
      format's `TckrSymb`/`FinInstrmNm`/`XpryDt`/`StrkPric`, and no
      ready-made tradingsymbol column at all). Both
      `_fetch_and_parse_day` (bars) and `fetch_option_chain_for_day`
      (strike/premium resolution — separately verified as the thing a
      real backtest actually depends on for options, not the `bar` table)
      now try the new-format URL first and fall back to this legacy one
      on a 404 — no hardcoded cutover date needed, correct regardless of
      exactly which day NSE switched formats.

      **Two honestly-documented approximations the legacy path carries
      that the new format doesn't need** (see
      `data_providers/nse_bhavcopy.py`'s module docstring for the full
      reasoning): (1) `underlying_price` — the legacy file has no
      equivalent to the new format's `UndrlygPric` (NSE's own recorded
      spot), approximated from the same-day nearest-expiry index future's
      own close (index futures trade close to spot, but this is a proxy,
      not an exact recorded value); (2) `lot_size` — no equivalent to
      `NewBrdLotQty` exists pre-2024 either, and NIFTY/BANKNIFTY's real
      lot size changed multiple times across 2021-2023 with no verified
      free source for the exact value on an arbitrary date — rather than
      guess, this returns `lot_size=0`, which `size_defined_risk_position`
      already turns into a loud `ValueError` instead of a silently
      mis-sized trade. **A pre-2024 backtest cannot size positions yet**
      until a real historical lot-size table replaces this — flagged
      here, not hidden.

      Tradingsymbols for legacy dates are a synthetic, internal-only
      convention (`_legacy_tradingsymbol_from_row`), not NSE's or
      Zerodha's real naming — safe only because this data never leaves
      the backtest engine (never placed as a live order, never
      reconciled against a live broker). 6 new unit tests
      (`test_nse_bhavcopy_legacy_format.py`), verified end-to-end against
      the real 2021-06-15 file before trusting it (4,384 bars, 50,734
      option-chain rows, spot-proxy and symbol-consistency between the
      bar and option-chain paths both confirmed by hand). Corrected the
      first run's bad `bar_coverage` row (`from_date` moved from
      2021-01-01 to 2024-01-01, the genuinely-verified boundary) and
      re-ran the backfill for just 2021-2023 through the fixed code.
      **Completed 2026-08-26** — 2,680,368 real bars persisted for
      2021-01-01 → 2023-12-29 (spot-checked directly against the live
      Supabase DB, not trusted from the run's own log line, which
      misleadingly printed "0 bars" — a known cosmetic quirk: it counts
      rows matching the literal `--symbol NIFTY` argument, not the many
      distinct per-contract tradingsymbols the whole-file-bulk fetch
      actually persists). Combined with the earlier 2024-2026 run,
      `bar_coverage` now shows one continuous row
      (`*:BANKNIFTY,NIFTY`/NFO) spanning **2021-01-01 → 2026-08-25**.
- [x] Persist `BacktestRun`/`BacktestTrade` — tables existed since migration
      001/002 but nothing ever wrote to them; wired into all three
      `/backtest/run*` endpoints
- [x] `GET /api/backtest/runs` + `GET /api/backtest/runs/{id}` + Run history
      panel on the Backtest page

**Verify:** Browser-verified end-to-end against a disposable local SQLite DB
(same Supabase-unreachable reason above) — real login, real click-through,
real NSE network fetch. **2+ years of NIFTY/BANKNIFTY option history
queryable locally is now true for the real Supabase DB too** — 5+ years,
2021-2026, confirmed by direct query, not just the run's own log output.

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
- [ ] **[YOU]** Create a Telegram bot (@BotFather) — Kite Connect deferred
      by your own call, no longer bundled with this item (2026-08-25).
      **As of 2026-08-25, enter the bot token + chat ID via Settings →
      Notifications, not `.env`** — new `GET`/`PUT /settings/notifications`
      (`xillion/api/settings.py`), same encrypted DB pattern as
      Dhan/Zerodha, applies to the running `TelegramNotifier` immediately
      via a new `.configure()` method, no restart needed. Blocks only the
      *real* Telegram proof below, not anything already built
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
chat turn, one test strategy's RAG chunks) was meant to be deleted
afterward — but that claim was premature: closing out CP8 on 2026-08-24
(re-checking the background verification task's output, `bvpc15kg3`, which
had finished with exit 0 and the exact `0.06s`/`~46.3s`/`ai_confidence=90.0`
numbers already written above) found one leftover entry in
`tenant_0__trading__strategies` — id `39b7ebb2-ef00-49c5-a98a-831968cef511`,
title "Test strategy", tag `['test']`, almost certainly left by
`scripts/ingest_xillion.py` during testing. Deleted it directly via
`chromadb.PersistentClient`. Re-verified all three collections after:
`strategies` now holds only the user's genuine "Bearish engulfing scalp";
`journal` holds one genuine EURUSD trade; `chat_history` holds two genuine
turns from 2026-03-15, predating this session. The confidence endpoint
itself (`api/routes/confidence.py`) never touches Chroma/RAG at all — "no
tools, no RAG lookup here on purpose" is in its own docstring — so this
leftover predated CP8's confidence-hook work specifically and came from
the earlier MCP/RAG ingestion verification.

The manually-started prosper-engine `uvicorn` (port 8010) and any xillion
backend from this checkpoint's verification were already stopped by the
time this close-out ran (`lsof -i :8010 -i :8799` returned nothing); no
disposable DB files were left behind either. Full xillion suite: **241
passed** (this pass also found and fixed an unrelated flaky test in CP10's
`test_digest.py` — `id(db)` used as a "unique" suffix across sessions can
collide once an earlier session object is garbage-collected; switched to
`uuid4()`, separate commit `1cb6a29`).

---

### ✅ CP9 — Automation + hardening (~17 hrs) → *Goal #7* `DONE 2026-08-24`
- [x] Order state machine — `Strategy.on_order_update` is now called as a
      fire-and-forget task right after `place_order()`'s own order-state
      transition, same pattern as `on_trade_close`
- [x] **Position reconciliation on startup** — a `live`-mode instance now
      queries the broker's real open positions before `on_start` runs, so a
      restart with real money in an open position no longer looks flat.
      Symbols outside the instance's configured instruments are ignored;
      paper mode is untouched (its own simulated positions correctly start
      flat); a broker fetch failure doesn't crash startup, it just restores
      nothing
- [x] **Live/paper real-time bar aggregation into `ctx.history()`** — found
      2026-08-24 while building CP5, fixed same day. New
      `xillion/data/bar_aggregator.py::BarAggregator` turns the live tick
      stream into bars (bucket-aligned OHLC, cumulative-volume-delta
      handling for Zerodha-shaped ticks) and publishes them onto
      `MarketDataBus`; `_tick_broadcaster` in `main.py` feeds it every tick
      alongside the existing WS broadcast. `StrategyRunner._handle_bar` now
      also pushes the bar into `ctx.history()`'s in-memory cache before
      dispatch, so `on_bar` strategies see the candle that just closed
      immediately, not just on the next DB backfill
- [x] **Risk limits were silently never enforced at all** (found while
      building this checkpoint, more severe than anything on the original
      list) — `ExecutionRouter.submit()` never passed `strategy_config`/
      `current_positions` to `risk.check()`, so every real order skipped
      the daily-loss and max-open-positions gates regardless of what was
      configured. `RiskManager.check()`'s own tests were correct and always
      had been — the bug was purely in the wiring layer between the router
      and the risk manager, which had zero test coverage before this.
      Separately, `StrategyEngine.spawn()` didn't read `risk_limits` from
      the DB at all, so even a fresh instance start ignored configured
      limits. Both fixed; `ExecutionRouter` now carries a `risk_config` +
      `set_risk_config()` for hot-reload
- [x] Auto start/stop instances at market open/close — opt-in per instance
      via a new `auto_start` column (migration `009`), toggled from the
      Strategies page. `xillion/engine/market_scheduler.py` polls
      `is_market_open()` and reacts only to open↔closed *transitions*
      (never on the first observation after process start, which would
      fire a start/stop based on an assumed prior state never actually
      observed) — chosen over hardcoding 9:15/15:30 IST like the existing
      daily-refresh tasks because `is_market_open()` already encodes the
      NSE holiday calendar, so no separate holiday awareness is needed here
- [x] Logs DB persistence + `GET /api/positions` — `GET /api/positions` was
      already done in CP7. The DB-persistence half turned out to be a
      bigger gap than expected: the Logs page was built to render a live
      `"log"` WebSocket event and claimed "scrollback retained for 24h",
      but **nothing in the backend had ever emitted that event type at
      all** — the page was live-tailing nothing and had nothing to load on
      reload either way. New `xillion/observability/log_capture.py` wires
      a structlog processor into `main.py`'s `structlog.configure()` that
      captures every `logger.*()` call app-wide (via
      `CallsiteParameterAdder` for the source module) into a bounded
      queue, drained by a background task that persists to a new
      `system_log` table (migration `010`) and broadcasts the same event
      live, with a 24h retention prune. New `GET /api/logs` for history on
      mount. Hand-verified end-to-end in a real browser: history loads on
      page load, then the line count updated live in real time after
      triggering a real backend action. **Found and fixed while wiring
      this in:** the console output's timestamp briefly regressed to a raw
      unix-epoch float — structlog's actual built-in default `TimeStamper`
      uses `fmt="%Y-%m-%d %H:%M:%S", utc=False`, not the bare
      `TimeStamper()` constructor's own default (`fmt=None` → epoch
      float); had to match the built-in default explicitly since
      overriding `processors=` replaces it silently
- [x] Self-failure alerting — if the *system* breaks, you get told. Two
      halves: (1) `xillion/observability/task_supervisor.py::supervise()`
      wraps the long-running background loops (tick broadcaster, daily
      refreshes, market-hours scheduler, log persistence) and Telegram-
      alerts on any exit that isn't a clean shutdown cancellation —
      **deliberately alerts on a clean `return` too, not just an
      exception**, because `_tick_broadcaster`'s own try/except already
      swallows its own errors and just returns, so exception-only
      detection would miss the most likely real failure (the broker's tick
      stream ending on a disconnect); (2) a strategy crashing in
      `on_start`/`on_bar`/`on_tick` now fires a Telegram alert in addition
      to the logging that already existed. Found in passing: `on_tick`'s
      exception handler never set `status="error"`/`last_error` the way
      `on_bar` and `on_start` already did — a crashed tick-only strategy
      (e.g. Nifty Spot Alert) looked identical to one running fine. Fixed
      to match. Also added a Telegram alert on a failed Zerodha connect
      attempt at startup/daily-refresh (previously logged only)
- [x] **Verify risk-limit hot-reload** — already covered by
      `test_hot_reload_tightens_limit_on_a_running_instance_without_restart`
      as a side effect of the "risk limits never enforced" fix above: an
      order approved under a limit of 5, then rejected after
      `engine.update_risk_config()` tightens it to 1 — no restart, same
      running instance. The `PUT /api/settings/risk-limits` endpoint this
      bullet originally named (from `09-progress-tracker.md`) doesn't
      exist in the current codebase; the real mechanism is
      `PATCH /instances/{id}` with `risk_limits` in the body, which was
      already wired to `engine.update_risk_config()` before this session

**Verify:** kill the process mid-position, restart, positions rebuild
correctly — confirmed via `test_live_instance_restores_a_real_open_position_on_start`
and friends. 234 tests passing (up from 175 at the start of this checkpoint).

---

### ✅ CP10 — Maintenance mode (~9 hrs) → *Goal #10* `DONE 2026-08-24`
- [x] Daily/weekly digest — the thing that makes 3–6 hrs/week real.
      `xillion/engine/digest.py::build_digest` reuses the exact same FIFO
      fill-matching `GET /api/trades` already does
      (`xillion/api/trades.py::_match_fills`), since that's the only place
      real live/paper P&L actually lives — CP6's journal (`build_journal`)
      was deliberately *not* reused here: it mixes in backtest-only data
      and alert-mode signals never carry a real fill. Sent via Telegram at
      ~4pm IST daily (after market close) and Sunday ~6pm IST weekly
      (`xillion/engine/digest_scheduler.py`), same fixed-clock-time pattern
      as the existing daily token/instrument refreshes — deliberately not
      the market-hours scheduler's transition-detection style, since a
      digest is a calendar event, not a reaction to market state
- [x] Self-healing / auto-recovery — `task_supervisor.py`'s CP9 alerting
      now actually restarts the crashed background task (tick broadcaster,
      daily refreshes, market-hours scheduler, log persistence, both
      digest schedulers), bounded to 5 restarts per 10 minutes so a
      crash-looping task doesn't spin forever; alerts on every restart
      *and* gives up with a distinct "gave up" alert once the budget is
      exceeded, explicitly telling you it won't retry again. Required
      changing `supervise()`'s signature from a bare coroutine to a
      zero-arg factory (`lambda: _daily_token_refresh(app)`), since a
      coroutine object can only be awaited once and restarting needs a
      fresh one each time — updated all 6 call sites in `main.py`
- [x] Runbook (`docs/process/runbook.md`) — every alert title quoted in it
      is copy-pasted from the actual code that sends it (cross-checked
      against `risk.py`, `zerodha.py`, `strategy_engine.py`,
      `task_supervisor.py`), not written from memory of what the alerts
      were *supposed* to say. Documents one real gap found while writing
      it: a daily-loss-limit rejection (`RiskRejected`) does **not** fire a
      Telegram alert today — it only shows up as a `REJECTED` order in
      Trades/Journal, so "strategy stopped trading, no alert fired" is a
      real, expected (if not ideal) state, not a bug to chase
- [x] 6 new tests (`test_digest.py`) + rewrote `test_task_supervisor.py`'s
      6 tests for the factory-based restart behavior (raises-and-restarts,
      clean-return-and-restarts, cancel-means-no-restart, no-notifier
      doesn't crash, crash-loop gives up after budget, gave-up alert body
      explicitly says it won't retry)

**Verified:** 241 tests passing (234 at the start of this checkpoint). Real
boot against a disposable local SQLite DB with the full supervised-task +
digest-scheduler stack wired in, zero startup errors. `build_digest` +
`format_digest_message` hand-run against that same live DB, correctly
reported "No closed trades" / "Nothing currently running" for the empty
state.

---

## TRACK A EXTENSION — Automation Platform Retrofit (added 2026-08-25)

Gap-mapped from `docs/architecture/automation-platform-spec/`'s 52-job
catalog onto what CP1-CP10 already built — see
[architecture/overview.md](../architecture/overview.md) §12.1 for the full
per-job-series mapping table this sequencing is drawn from. **Sequenced by
what blocks the first real strategy (the credit spread,
`docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md`) going live**, not
by the spec's own phase numbers — Options S1/S2 (build + backtest) can start
in parallel with CP11-CP13 since the strategy itself is single-leg-testable
before multi-leg execution is finished, but CP11 (multi-leg + protective
orders) is a hard gate before Options S4 (live).

### ✅ CP11 — Multi-leg execution + protective orders `DONE 2026-08-25 — bracket/GTT gap closed for Zerodha, verified-blocked for Dhan`
- [x] Multi-leg position model — [xillion/core/multileg.py](../../xillion/core/multileg.py):
      `MultiLegSpec`/`Leg`/`LegRole` group 2-4 broker orders into one logical
      structure. Deliberately does NOT add a parallel position-tracking
      table — each leg still flows through the existing per-symbol
      `Position`/`PositionRecord` machinery (`ctx.place_order` per leg), so
      there's one source of truth per symbol and the coordination layer
      (ordering + rollback) sits on top rather than duplicating state
- [x] Leg-ordering discipline on entry/exit — **longs first on entry, shorts
      first on exit** — `order_entry_sequence`/`order_exit_sequence` in
      `multileg.py`, enforced regardless of the caller's list order
- [x] **Leg-failure protocol (E05)** — [xillion/core/multileg_execution.py](../../xillion/core/multileg_execution.py)
      `MultiLegExecutor`. Naked-short detection is per-leg (`protects_leg_index`
      pairing, not a hardcoded 2-leg assumption — generalises to condor/
      butterfly). Force-unwinds at market on a naked short, retries once and
      unwinds cleanly on a defined-risk partial, halts for human review on
      an unclassifiable partial. 12 unit tests cover the spec's own E05
      acceptance-test list (long fills/short rejected → retry→unwind; short
      held without its protecting long → force-unwind; partial fill above/
      below the 50% ratio; a leg stuck open past the fill timeout)
- [x] **Protective order placement (E07)** — [xillion/core/protective_orders.py](../../xillion/core/protective_orders.py)
      computes stop/target/time-stop levels from the real fill price; the
      credit-spread strategy monitors them every tick and fires a real
      market exit order (shorts-first) through the same leg-failure
      protocol when triggered. The spec's own caveat applies: a software
      stop needs the process alive to fire; an always-on watchdog independent of the
      strategy's own tick loop is CP12's job, not this one's
- [x] Position sizing for multi-leg — `size_defined_risk_position()` in
      `multileg.py`, `lots < 1 → skip, don't round up`, unit-tested against
      the exact KB `10-FIRST-STRATEGY-SPEC.md` §7 worked-example numbers
      (Nifty 200-wide → 0 lots, Nifty 50-wide → 1 lot, Sensex 100-wide →
      1 lot)
- [x] First real consumer built end-to-end: `strategies/credit_spread_weekly.py`
      (Options Stage 1) — see [docs/strategies/credit-spread-weekly.md](../strategies/credit-spread-weekly.md)
- [x] **Follow-up, 2026-08-25: Options Stage 2 (backtest) unblocked.**
      [xillion/data/option_chain.py](../../xillion/data/option_chain.py) —
      `HistoricalOptionRow` + `OptionChainWarehouse`, same cache-on-fetch/
      whole-file-bulk pattern as CP2's `BarWarehouse`, sourced from NSE
      Bhavcopy's own `StrkPric`/`XpryDt`/`OptnTp`/`UndrlygPric` columns
      (confirmed against a real live file fetched 2026-08-24, not assumed —
      `UndrlygPric` in particular is the exchange's own recorded underlying
      close, used as the backtest's spot proxy with no separate index feed
      needed). New `option_chain_snapshot` table (migration 011) — a
      DATE-SCOPED snapshot, deliberately separate from the live `instrument`
      table (a truncate-and-reload cache of TODAY only, useless for "what
      did NIFTY's chain look like on 2026-03-06"). `_BacktestContext` in
      `backtest_engine.py` now implements `get_spot`/`resolve_strike`/
      `get_option_price`/`subscribe_instrument`, reusing the SAME
      `resolve_option()` the live path uses — no second resolver. Wired
      into all three `/backtest/run*` API endpoints.
      **A deeper bug this surfaced and fixed, not assumed away:**
      `StrategyContext` had no environment-aware "what time is it" — the
      credit-spread strategy's entry-window/DTE gates called a bare
      `datetime.now()`, which only works for live/paper (bars arrive in
      real time); a real multi-year backtest replaying history would only
      ever check against *today's* real date regardless of which period
      was being simulated, so the DTE gate would pass by coincidence at
      best. Fixed by adding `StrategyContext.now()` (live: real wall-clock;
      backtest: the currently-simulated bar's own timestamp) — the
      strategy now calls `ctx.now()`, not `datetime.now()`.
      **Also found and fixed:** a MARKET order for a freshly-resolved
      option leg filled at price 0 in backtest mode, because
      `_last_price` (what `place_order`'s MARKET fallback reads) was only
      ever populated by the bar-driven symbol, never by a dynamically
      resolved leg — fixed by caching the fetched close in `get_option_price`
      itself, the same place the strategy already fetches it to compute
      credit.
      BacktestEngine's main loop now also synthesizes a daily Tick for
      every dynamically-subscribed option leg after each `on_bar` (bhavcopy
      is EOD-only, so this is honestly daily granularity, not a claim of
      intraday accuracy) — without this, `on_tick`-driven exit logic
      (CP11's protective-order monitoring) would never fire in a backtest
      at all, since `BacktestEngine.run()` only ever called `on_bar`.
- [x] **Follow-up, 2026-08-25: the real-broker bracket/GTT gap, narrowed —
      Zerodha done, Dhan verified-blocked, not guessed at either way.**
      First verified the old `supports_bracket_orders=True` flag against
      Kite Connect's *current* API docs, not assumed from the flag's own
      value: Zerodha discontinued bracket orders entirely (`"bo"` isn't a
      valid `variety` any more) — the flag now correctly reads `False`.
      GTT triggers are still real and supported, so that's what got built:
      `Broker.place_protective_gtt()`/`cancel_gtt()`
      (`xillion/core/broker_base.py`) + a real `ZerodhaBroker`
      implementation verified against the actual installed `kiteconnect`
      SDK source (`place_gtt`/`_get_gtt_payload`), not the docs alone.
      **A genuine, honestly-documented approximation, not an exact
      mirror:** Kite's GTT triggers on ONE instrument's own LTP, but the
      software stop triggers on `spread_value` (short leg LTP minus long
      leg LTP) — no single-instrument trigger can express a two-leg net
      condition. `short_leg_gtt_levels()` converts the spread-value
      threshold to an approximate short-leg-only price by holding the long
      leg's entry-fill price fixed — a real circuit-breaker for the worst
      case (process down, software stop can't fire), not a precision
      replacement for the tick-driven check that's still primary.
      `credit_spread_weekly.py` places this GTT right after entry fills
      and cancels it on any genuine exit — but deliberately **not** on
      `HALTED_FOR_HUMAN` (an unclassifiable partial fill), since the
      broker-side position is unclear exactly then and cancelling would
      remove the protection that window most needs.
      **Dhan verified-blocked, not silently skipped:** Dhan's own
      equivalent ("Forever Orders") is real and documented
      (dhanhq.co/docs/v2/forever/), but its `productType` field only
      accepts `CNC`/`MTF` — `brokers/dhan.py` hardcodes every regular
      order's product to `INTRADAY` (a known, already-documented
      simplification from CP15, not new). Building Forever-Order support
      today would either silently fail against the real API or require
      changing what product type Dhan positions trade under — a bigger,
      separate decision, not guessed at here.
      **Also found and fixed in the same broker-capability area:**
      `POST /brokers/connections/{name}/reconnect` was hardcoded to
      `"Zerodha Primary"` only — Dhan's own Reconnect button in Settings →
      Active connections would have 400'd. Now dispatches by connection
      name generically.

**Verify:** 33 unit tests (`test_multileg.py`, `test_multileg_execution.py`,
`test_protective_orders.py`) + 6 integration tests
(`test_credit_spread_strategy.py`) for the original CP11 scope, PLUS 7 unit
tests (`test_option_chain.py`, including the real-column-name parser check)
and 2 integration tests (`test_credit_spread_backtest.py`) for the
backtest follow-up, PLUS the 2026-08-25 GTT follow-up: 5 unit tests
(`test_zerodha_protective_gtt.py`, against the real installed SDK's method
signature) + 2 unit tests (`short_leg_gtt_levels` in
`test_protective_orders.py`) + 3 integration tests (GTT placed on entry,
cancelled on genuine exit, preserved on `HALTED_FOR_HUMAN`, in
`test_credit_spread_strategy.py`) + 4 unit tests
(`test_broker_reconnect.py`) for the reconnect fix. **A real,
pre-existing test-isolation bug found and fixed along the way:**
`test_credit_spread_strategy.py`'s `FakeContext.OPTION_PRICE` was a shared
*class-level* dict — one test's `ctx.OPTION_PRICE[...] = X` silently
leaked into every later test's fresh instance, since Python attribute
lookup falls through to the class for an unshadowed mutable default. Now
copied per-instance in `__init__`. 418/418 tests passing, no regressions.
**Not yet done:** NSE-listed underlyings only for backtest options
(NIFTY/BANKNIFTY; Sensex is BSE-listed, NSE Bhavcopy doesn't cover it),
and Dhan's Forever-Order path (blocked on the product-type decision
above).

---

### ✅ CP12 — Trailing-stop engine `DONE 2026-08-25 — watchdog gap narrowed, not fully closed`
- [x] Three trailing algorithms + the ratchet enforcement point —
      [xillion/core/trailing_stop.py](../../xillion/core/trailing_stop.py):
      `fixed_trail` (spec §3.2.1, generic baseline), `r_ladder_trail` (spec's
      own "recommended default"), `credit_trail` (spec §3.2.6 — the
      credit-spread-specific one, trails on captured credit %, never on
      underlying spot per the spec's explicit "category error" warning).
      ATR/chandelier and swing-structure trails (need bar history +
      indicators) not implemented — a natural next addition, not required
      by this checkpoint's own "at least one algorithm" bar
- [x] **Ratchet property-tested**: `ratchet()` is the single point every
      algorithm routes through (`max` for LONG, `min` for SHORT); a
      dedicated property test runs 1000 independent random price paths ×
      2 directions × 30 steps each (30,000 checks total) asserting the
      stop is monotonic at EVERY step, not just start-vs-end. Stdlib
      `random` with a fixed seed rather than adding a `hypothesis`
      dependency for one property
- [x] Breakeven-shift trigger (T05) — `breakeven_shift()`/`apply_breakeven_shift()`,
      fires once at the configured R-multiple, sets a flag so it can't
      re-fire, still routes through the ratchet
- [x] Time-stop enforcement — already existed from CP11
      (`protective_orders.py`'s `check_exit_trigger` TIME_STOP branch); not
      duplicated here
- [x] **"Survives a process restart" — the real watchdog-gap work.**
      `ctx.state` now genuinely persists to `StrategyInstance.state_blob`
      and restores on the next `spawn()` — that column has existed in the
      schema since migration 001 and `StrategyContext`'s own docstring
      claimed this happened ("persisted to DB on on_stop, restored on
      on_start"), but nothing ever wrote or read it; `ctx.state` silently
      reset to `{}` on every single spawn. This is what actually would let
      a real trailing-stop's state (or CP11's credit-spread protective
      levels) survive a deliberate restart. Persisted two ways: awaited on
      a clean `StrategyRunner.stop()` (guarantees the FINAL state lands),
      and fire-and-forget after every `on_bar` (crash resilience for the
      common case — a process killed between bars still has the last
      bar's state on disk). Pickle, not JSON, matching the column's
      `LargeBinary` type and the state's potential non-JSON contents
      (Decimal, etc)

**Honest gap, narrowed but not closed:** this makes a *deliberate* restart
(redeploy, manual stop/start) safe — state is genuinely there when the
process comes back. It does **not** add an independent watchdog that
detects an *ungraceful crash* and restarts the instance itself (the
automation spec's K03 heartbeat/watchdog job) — if the process dies without
calling `stop()`, only the last on_bar's fire-and-forget snapshot exists,
and nothing currently notices the crash and acts on it. That remains open.

**Verify:** `test_trailing_stop.py` (20 tests, including the 30,000-check
ratchet property test) + `test_strategy_state_persistence.py` (3 integration
tests: state survives a clean stop+respawn with a brand-new engine/bus,
`on_start`'s `setdefault` doesn't clobber restored values, and fire-and-
forget persistence after `on_bar` doesn't require waiting for a clean
stop). 312/312 tests passing, no regressions.

---

### ✅ CP13 — Expanded risk engine `DONE 2026-08-25`
- [x] Brought `RiskManager.check()` from 6 checks to **18** —
      [xillion/core/risk.py](../../xillion/core/risk.py), table-driven
      (`checks: list[tuple[name, ok]]`, matching the spec's own
      `validate_order()` shape) rather than nested early-returns, both for
      readability and because it made 100% branch coverage tractable.
      Priority order followed exactly as `risk-and-compliance.md` Part C.1
      specified:
      1. **Price collar** (`price_collar` — order price within 0.5x-1.5x
         LTP) + **OPS cap tightened to 7/sec** with a genuine 9/sec hard
         ceiling — hitting the hard ceiling now fires the kill switch
         (runaway-loop signal per spec §10.3: "a loop that generates 9
         orders/second will generate 9,000"), tracked on a SEPARATE
         attempt-window from the soft-throttle accepted-window, since the
         runaway signature is attempt rate, not accepted-order rate
      2. **Idempotency-key dedup** (`not_duplicate` — a client_order_id
         re-submitted within 5 minutes is rejected)
      3. Prop-firm DD gates — still deferred to Lane B, unchanged
      Also added, all from the spec's same check groups: `qty_lot_multiple`,
      `qty_within_freeze`, `qty_sane`, `price_tick_multiple`,
      `price_within_circuit`, `notional_sane`, `trading_enabled` (a softer,
      manually-reversible pause distinct from the kill switch), `order_count_sane`
      (per-strategy daily order cap), `not_self_trade` (opposite-side open
      order on the same symbol — `ExecutionRouter.submit()` now supplies
      this from its own `get_open_orders()` automatically). Every new
      market-data-dependent check (`price_collar`, `price_tick_multiple`,
      `price_within_circuit`, `notional_sane`, `qty_lot_multiple`,
      `qty_within_freeze`) is **skipped, not failed,** when the caller's
      `MarketContext` doesn't supply that field — honestly documented as
      not yet wired to a live broker quote (no code path constructs one
      pre-trade today), not silently treated as passed.
      **Deliberately NOT implemented, and why:** `margin_sufficient` (would
      need a synchronous pre-trade broker RPC — a real latency tradeoff not
      decided yet), `market_open`/`symbol_tradeable` (risk of regressing
      paper/alert-mode testing outside market hours without deciding what
      "mode-aware" means for this check first), `modify_rate_ok`
      (`modify_order` itself isn't implemented anywhere in the codebase yet
      — nothing to rate-limit).
- [x] **100% branch coverage on `xillion/core/risk.py`** — verified with
      `pytest --cov=xillion.core.risk --cov-branch`, not just "tests pass."
- [x] **Audit log wiring** — `xillion/core/audit.py`'s `AuditLog`/
      `AuditLogRecord` (hash-chained, append-only) existed in the schema
      and as working code since early in the project, but nothing ever
      called `.record()` — risk decisions were only ever visible in
      structlog output. `ExecutionRouter.submit()` now writes every
      decision (approved or rejected, with the specific failed check
      names) here, **awaited, not fire-and-forget** — matching the spec's
      own K04 requirement that order-event audit writes are synchronous on
      the critical path.
      **A real bug this caught, not a hypothetical:** the first version of
      this used `asyncio.create_task()` (fire-and-forget, matching this
      file's OWN precedent for `_persist_order`/`_persist_trade_close`) and
      it reliably **hung the entire integration test suite** partway
      through — orphaned audit-write tasks from earlier tests, still
      holding the shared SQLite connection when their test's event loop
      tore down, blocked a later test's DB access indefinitely. Switching
      to awaited (which the spec asked for anyway) fixed it outright.

**Verify:** a deliberately fat-fingered order (10x the LTP) is rejected
before it reaches the broker adapter (`test_risk_audit_log.py`'s
`test_fat_fingered_price_is_rejected_before_reaching_the_broker` — asserts
`broker.placed_orders == []`), with the specific failed check
(`price_collar`) named in a real `audit_log` row, not just a log line.
343/343 tests passing (53 in `test_risk_manager.py` alone), no regressions.

---

### ✅ CP14 — Scheduled EOD reconciliation + flatten-at-close `DONE 2026-08-25`
- [x] **X02 — square-off enforcer** — [xillion/engine/square_off.py](../../xillion/engine/square_off.py).
      Deliberately driven by a `Broker` only, nothing from `StrategyEngine`/
      `StrategyContext` — per the spec, this job "must work when everything
      else is broken" and "does not check whether strategies are armed…
      it queries the broker for open positions and closes them." Queries
      `broker.get_positions()`, closes anything nonzero at MARKET, then
      **re-queries to verify** rather than trusting the close order's ack —
      an unverified close is exactly the kind of assumption CP11's E06 also
      refused to make. Scope note: implements the safety property (nothing
      open past close) immediately at MARKET rather than the spec's full
      13-minute price-improvement ladder (warn → soft LIMIT → aggressive →
      MARKET → verify) — strictly safer, not price-optimal; the staged
      ladder is a natural next refinement, honestly deferred, not silently
      dropped.
- [x] **M01 — broker reconciliation** — [xillion/engine/reconciliation.py](../../xillion/engine/reconciliation.py),
      independent of X02 (runs 30 min later, its own scheduled trigger) so
      it's a genuine second check, not just X02 grading its own homework.
      Compares broker positions against `PositionRecord` three ways
      (broker-only, internal-only, quantity-mismatch) and additionally
      flags **any** open position at EOD as a discrepancy even when both
      sides agree — matching the spec's "must be FLAT at EOD for intraday
      strategies" rule. Persisted to a new `reconciliation_report` table
      (migration 012) — not just logged, so a `DISCREPANCY`/`FAILED` day is
      a durable, queryable fact per the spec's own "block tomorrow's
      trading if not CLEAN" design (that blocking behaviour itself isn't
      wired to anything yet — the report exists and is queryable, nothing
      reads it to gate a new trading day). **Scope note:** positions only —
      orders/fills reconciliation and funds (broker P&L vs computed P&L)
      reconciliation are NOT implemented; funds specifically needs a
      "today's realised P&L" broker capability the `Broker` ABC doesn't
      expose today, honestly left as a gap rather than faked.
- [x] Both wired as their own supervised background tasks in
      [xillion/main.py](../../xillion/main.py) — X02 at 15:15 IST, M01 at
      15:45 IST, same sleep-until-next-fixed-clock-time pattern as CP10's
      digest scheduler, deliberately two separate loops (not one combined
      job) so a bug in one can't silently take out the other.

**Verify:** the crash scenario simulated directly — a real open position at
the broker with nothing in xillion's memory aware of it (no StrategyEngine
involved at all) — then X02 and M01 run in sequence exactly as the
scheduler would: good path (`test_x02_flattens_then_m01_confirms_clean`)
X02 flattens it and M01 independently confirms CLEAN; bad path
(`test_x02_fails_to_flatten_and_m01_catches_it_loudly`) X02's close order
is rejected, and M01 still shows the position as an EOD `DISCREPANCY` with
a critical alert fired — never silently carried forward. 367/367 tests
passing, no regressions.

---

### 🟡 CP15 — Dhan as a full trading broker, parallel with Zerodha `CODE DONE 2026-08-25 — blocked on credentials for live verification`
- [x] **`brokers/dhan.py`** — auth, positions/funds, order placement
      (place/modify/cancel/get/list), live ticks, historical data — matching
      the `brokers/zerodha.py` pattern (reconnect hardening, real
      socket-state tracking distinct from the REST session state) rather
      than adopting OpenAlgo (open question Q11 — a second hand-written
      adapter didn't make the case for a dependency yet). Built against
      **real, verified sources**, not assumed: fetched DhanHQ's own docs
      (dhanhq.co/docs/v2/orders/, /live-market-feed/, /market-quote/) and
      the official `dhanhq` PyPI SDK's source (github.com/dhan-oss/DhanHQ-py)
      directly during this session — order request/response shapes, the
      TRANSIT/PENDING/PART_TRADED/TRADED/REJECTED/CANCELLED/EXPIRED status
      enum, and the WebSocket feed's binary tick protocol are all confirmed
      against real docs and source, not guessed. The WebSocket feed's
      binary parsing is delegated to the SDK's own `MarketFeed` class
      rather than hand-rolled — a custom binary protocol (not JSON) is real
      complexity worth reusing a maintained implementation for, same
      reasoning `zerodha.py` already applied to `KiteTicker`.
      Extracted the scrip-master (symbol → securityId) resolution shared by
      this and `data_providers/dhanhq.py` into
      [xillion/core/dhan_instruments.py](../../xillion/core/dhan_instruments.py)
      rather than duplicating it a second time.
      **A real bug the real CSV caught, not assumed away:** `LOT_SIZE` in
      Dhan's actual scrip master is float-formatted (`"1.0"`, not `"1"`) —
      `int()` on that string raises `ValueError`. Fixed to `int(float(...))`.
      **Genuine unknown, inherited from the SDK itself, not hidden:** the
      SDK's own `DhanLogin.generate_token()` docstring admits it doesn't
      know the PIN+TOTP endpoint's exact success response shape ("usually
      it returns accessToken") — handled defensively (tries a few plausible
      keys, raises a clear error otherwise) rather than assumed correct.
- [x] **Multi-broker selection actually wired** — `xillion/api/instances.py`'s
      `_resolve_broker` was **hardcoded to "Zerodha Primary"** for every
      live/alert-mode instance regardless of what it was configured with;
      Dhan would have been unreachable from live trading even fully
      connected. Now resolves via the instance's own
      `broker_connection_id` → `BrokerConnection.name` →
      `app.state.broker_instances`, so an instance genuinely trades through
      whichever broker it's configured for.
      **A second real bug found while fixing the first:** `start_instance_core`
      unconditionally called `await broker.connect({})` even when
      `_resolve_broker` returned an ALREADY-connected broker — for
      `ZerodhaBroker`, whose `connect()` immediately does
      `credentials["api_key"]`, that empty-dict second call would raise
      `KeyError`. Never caught before because live mode has been blocked on
      real Kite Connect credentials (Blocked-on-you #1) for this project's
      entire history. `_resolve_broker` now returns `(broker,
      already_connected)` and the caller only connects when it's actually needed.
- [x] Wired into `xillion/main.py` — `_try_connect_dhan` (same DB-first/
      env-fallback credential loading as Zerodha's), called at startup
      alongside Zerodha, non-fatal if unconfigured or failing (Zerodha stays
      the primary broker either way). Daily token re-validation at 6:30 IST
      (15 min after Zerodha's, avoiding both brokers hitting their auth
      endpoints at the exact same moment) — doesn't force-delete the cached
      token first like Zerodha's does, since `DhanBroker.connect()` already
      validates the cached/provided token itself and only falls through to
      PIN+TOTP auto-refresh if it's genuinely invalid.
- [ ] Failover semantics — if Zerodha is down, does Dhan take over
      automatically or does that require a manual switch? **Still not
      decided** — the spec's Phase 3 treats this as a hardening-phase
      feature, not P0. Both brokers connect independently today; nothing
      automatically fails over between them.

**Verify:** `test_dhan_instruments.py` (10 tests, real scrip-master CSV
columns) + `test_dhan_broker.py` (9 tests, real order request/response
shapes, every documented Dhan order status mapped) + `test_resolve_broker.py`
(5 tests, proves Dhan is genuinely selectable and the connect({}) bug is
fixed) all pass — but **the checkpoint's own literal Verify line ("a real
Dhan order placed and filled in paper mode, live ticks flowing, auth
refresh working on Dhan's own daily-token cadence") requires a real Dhan
account and is not yet done** — logged in
[docs/status/manual-tasks.md](../status/manual-tasks.md) as the actual
blocker, not silently skipped. 391/391 tests passing overall, no
regressions.

**Follow-up, 2026-08-25: paper mode is now genuinely free-to-verify on Dhan
alone, no Zerodha subscription required.** Prompted by the user asking
whether Kite Connect's ₹500/mo was actually necessary before seeing the app
work, or could be deferred. It could — but three separate bugs stood
between "Dhan is code-complete" and "paper mode actually shows a live price
sourced from Dhan":
1. `start_instance_core`'s live-tick subscription (a *second*, separate
   spot from `_resolve_broker`, which this checkpoint's own fix above
   didn't cover) was still hardcoded to the literal string `"Zerodha
   Primary"` — a Dhan-only instance got no ticks even with Dhan connected.
   Now resolves via `broker_connection_id` → `BrokerConnection.name`, same
   pattern as `_resolve_broker`.
2. **Dead code, real bug:** `PaperBroker.on_tick` was never actually
   subscribed to `MarketDataBus` — the wiring sketched in `_resolve_broker`
   was written but never connected (the comment there admitted as much:
   "not implemented in bus"). `PaperBroker._last_prices` — used for both
   fills and `get_quote` — silently never updated from live ticks in
   production, for *any* broker, Zerodha included, this whole time. Now
   `start_instance_core` subscribes a handler per instrument for paper-mode
   instances, tracked in `app.state.paper_tick_handlers` and unsubscribed
   in `stop_instance_core` (otherwise every restart leaks a handler holding
   a reference to the discarded `PaperBroker`).
3. `_try_connect_dhan` connected the broker but never started a
   `_tick_broadcaster` task for it the way `_try_connect_zerodha` does —
   `DhanBroker.tick_stream()` was never drained, so its ticks never reached
   `app.state.bus` regardless of (1) and (2). Now wired identically to
   Zerodha's (`_tick_broadcaster` is broker-agnostic, just needed the
   `supervise(...)` call).

New `test_paper_tick_wiring.py` (4 tests) proves paper mode subscribes
through whichever broker the instance is configured for (not hardcoded),
that `PaperBroker._last_prices` genuinely updates from a published bus
tick, and that stopping an instance unsubscribes its handler. 395/395
tests passing. **Net effect: a paper instance configured for "Dhan
Primary" now works end-to-end once a free Dhan account + token exists —
Kite Connect's ₹500/mo is no longer required to see the app trade for
real** (still needed eventually for the Zerodha-specific path, but not to
validate the system today).

**Follow-up, 2026-08-25: Dhan credentials moved off `.env`, onto the same
encrypted-DB path Zerodha already used.** The user asked directly: with
multiple broker providers, isn't `.env` the wrong place to store
credentials — shouldn't they live in the DB so they're easy to update or
add a new provider? Correct instinct, and the architecture already half
agreed — `xillion/auth/credstore.py`'s `BrokerCredential` table
(Fernet-encrypted payload) plus a full `GET`/`PUT`/`DELETE
/settings/zerodha` API and Settings UI form already existed, but were only
ever wired up for Zerodha; Dhan's loader (`_load_dhan_credentials`) checked
the DB first but nothing ever wrote to it, so it silently always fell back
to `.env`. Added the mirror: `GET`/`PUT`/`DELETE /settings/dhan`
(`xillion/api/settings.py`) and a matching Dhan card in
`frontend/src/pages/Settings.tsx` → Brokers tab. Credentials now go in
through the app itself, encrypted at rest, no `.env` editing, and this
pattern generalizes cleanly to any future broker (MT5 for Gold Lane B1,
etc.) — same shape, new router functions. New `test_dhan_settings.py` (2
tests) proves the round-trip and that saving/deleting one broker's
credentials never touches another's row. 397/397 tests passing.

---

## TRACK B — Asset pipelines

Each asset runs the same 6 stages — see
[14-asset-pipeline.md](../process/asset-pipeline.md). Mark stages as they complete.

| Asset | S1 Build | S2 Backtest | S3 Paper | S4 Live | S5 Auto | S6 Docs |
|---|---|---|---|---|---|---|
| **Options — credit spread** (Nifty/Sensex weekly) · Zerodha+Dhan | ✅ `strategies/credit_spread_weekly.py` | ✅ real backtest (open+close, real trade) | ⬜ | ⬜ blocked on real-broker bracket/GTT (CP11 gap) | ⬜ | 🟡 Stage 1 documented |
| **Gold — Lane B1** (XAUUSD) · Funding Pips MT5 | 🟡 broker+bridge built, unverified | ⬜ | ⬜ | ⬜ | ⬜ | 🟡 |
| **Gold — Lane B2** (MCX futures/options) · Zerodha/Dhan | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Stock options** · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Stocks** · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Crypto** · TBD exchange | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

**2026-08-25: Options S1 + S2 built.** `strategies/credit_spread_weekly.py`
implements the Nifty/Sensex weekly Bull Put / Bear Call credit spread from
`docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md` — entry timing,
trend-aligned direction, strike-count strike selection (a coarser proxy for
the KB's delta arms — no greeks engine exists), credit-adequacy filter,
KB §7 position sizing, multi-leg entry/exit via CP11, and software
protective-order monitoring. Full rules + honest gaps written up in
`docs/strategies/credit-spread-weekly.md`. S2 (Backtest) is now real, not
just wired: `xillion/data/option_chain.py` + `_BacktestContext` resolve
actual historical strikes from NSE Bhavcopy, and the strategy has run a
genuine open→close cycle through `BacktestEngine` with a real recorded
trade (see CP11 section above for the full writeup, including two real
bugs this surfaced and fixed). **What Stage 2 still can't do:** run the
real, multi-year, pass/fail-criteria backtest KB `10-FIRST-STRATEGY-SPEC.md`
§10 calls for — that needs the actual 2-5yr NSE backfill (Blocked-on-you
#6) and is NSE-listed underlyings only (NIFTY/BANKNIFTY; Sensex is
BSE-listed, out of reach of this provider). S4 (Live) is blocked on the
CP11 bracket/GTT gap (software stops now survive a restart via CP12, but
that's not the same as a fully independent crash-watchdog — see CP12).

### Per-asset enablement work
Infrastructure each asset needs before its pipeline can start:

- **Options** — 🟡 Stage 1+2 done (engine-level). **Blocked on:** the real
  multi-year backfill for a genuine pass/fail backtest run (#6 below),
  real-broker bracket/GTT for Stage 4. Stage 3 (paper) is unblocked today —
  CP11's leg-failure protocol and software protective orders are both real,
  tested, and now restart-safe (CP12), just not yet run against live market
  data for the required 2+ weeks
- **Gold Lane B1 (XAUUSD/Funding Pips)** — 🟡 **2026-08-28: MT5 broker
  plugin + bridge built, structurally correct but unverified end-to-end**
  (same position CP15/Dhan started from before real credentials existed).
  `brokers/mt5_funding_pips.py` (migration 014: `mt5_pending_order` /
  `mt5_bridge_tick` / `mt5_bridge_state`) + `xillion/api/mt5_bridge.py` +
  `mt5_bridge/bridge.py`. Architecturally different from Zerodha/Dhan on
  purpose: the official `MetaTrader5` Python package only talks to a real
  MT5 terminal on the SAME machine, which Render (this backend's host) can
  never be — so this broker queues orders/reads prices via DB tables a
  separate local process (the bridge, run on Rakesh's own Mac under Wine
  per his no-VPS-cost choice) polls against, rather than calling a broker
  API directly like every other plugin here does. `OrderRequest.quantity`
  (int, project-wide) is repurposed as MICRO-LOTS (hundredths of a lot) for
  this broker only, documented in the file rather than changing the shared
  type. 12 new unit tests (`test_mt5_broker.py`) cover the queue/poll/
  report mechanics with a real in-memory DB, no real MT5 needed for that
  part. **Still needed, and genuinely open:** 24×5 session calendar,
  currency field, real FX lot-size math beyond the micro-lot convention,
  **Funding Pips drawdown rules as hard risk limits** (breaching one
  instantly fails the account — see `architecture/risk-and-compliance.md`
  Part C.3), a historical Gold data source (Stage 2 needs it, this file
  doesn't provide it), and the actual Wine/Mac bridge setup + a real MT5
  account to verify any of this against — none of that exists in this
  sandbox. `mt5_bridge/README.md` has the setup steps but they're
  unverified against a real Mac+Wine environment.
- **Gold Lane B2 (MCX)** — ⬜ needs: MCX instrument/expiry resolution
  (monthly, 5th), reuses the Lane A broker adapter (Dhan/Zerodha both
  support MCX) — cheaper to build than B1 since no new broker is needed,
  only a new instrument type
- **Stock options** — ⬜ needs: stock-option chain resolution (reuses index logic)
- **Stocks** — ⬜ needs: equity instrument type (cheapest — multiplier is 1)
- **Crypto** — ⬜ needs: exchange integration, **1% TDS in the fee engine**
  (this alone makes most active crypto strategies unprofitable — model it
  before trading, not after)

---

## Blocked on you

> **Full actionable checklist, kept live across sessions:**
> [`docs/status/manual-tasks.md`](manual-tasks.md) — this table is the
> per-checkpoint summary; that file is what Rakesh actually works through
> and checks off. Keep both in sync (see `.claude/skills/xillion-manual-tasks/`).

| # | Item | Blocks | Status |
|---|---|---|---|
| 1 | Kite Connect plan (~1 hr) | CP4 onward (Zerodha-specific path only) | Open — **low priority, deferred by Rakesh 2026-08-25**, do #10 first |
| ~~2~~ | ~~Real strategy rules from trading-course videos~~ | ~~Options S1~~ | ✅ **Resolved 2026-08-25** — `docs/strategies/knowledge-base/` |
| ~~3~~ | ~~CA opinion on Funding Pips prop-firm income~~ | ~~Gold Lane B1 S4~~ | ✅ **Resolved 2026-08-25** — decided not needed, will declare as foreign income on ITR directly |
| ~~4~~ | ~~Funding Pips account + challenge~~ | ~~Gold Lane B1 S3 onward~~ | ✅ **Resolved 2026-08-25** — already had this |
| ~~5~~ | ~~Confirm ₹50k starting capital, ₹1,000/mo first milestone~~ | ~~Options S4~~ | ✅ **Resolved 2026-08-25** — confirmed yes |
| ~~6~~ | ~~Run `python scripts/backfill.py` for real (2-5yr)~~ | ~~CP3 close-out, Options S2~~ | ✅ **Done 2026-08-26** — 2021-2026 NIFTY+BANKNIFTY, one continuous `bar_coverage` span, confirmed via direct DB query |
| ~~7~~ | ~~A real multi-leg options strategy to design multi-leg support against~~ | ~~CP5 close-out, Options S1~~ | ✅ **Resolved 2026-08-25** — the credit spread (2-leg) + condor (4-leg) + butterfly (3-leg, 1:2:1) are all fully specced |
| ~~8~~ | ~~Confirm free-tier Redis provider choice~~ | ~~CP13 (only if in-memory state turns out insufficient)~~ | ✅ **Resolved 2026-08-25** — decided: Upstash. Not wired in yet, only needed if CP13's in-memory state turns out insufficient |
| 9 | A free-tier cloud LLM key (Gemini/Groq) in `prosper-engine/.env` — not blocking (Ollama's real tool-calling covered full verification), just faster/hosted than local Ollama when you want it | CP8 close-out | Open, not blocking — **explicitly deferred by Rakesh 2026-08-25** |
| ~~10~~ | ~~**Dhan API access token + client ID**~~ | ~~CP15 live verification~~ | ✅ **Resolved 2026-08-26** — connected live on Render; see the crash-loop bug found+fixed same day, above |
| ~~11~~ | ~~Telegram bot~~ | ~~Alerts, kill-switch notifications~~ | ✅ **Resolved 2026-08-26** — connected live on Render, "Send test message" verified working |

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
