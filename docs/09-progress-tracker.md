# 09 — Progress Tracker

A phased plan with task-level checkboxes. Each phase ends with an **exit criterion** — a working artefact you'd be willing to demo. Don't move on until the exit criterion is met.

Estimates are evenings-and-weekends pace. Aggressive but not unrealistic.

Update this file as you go: change `[ ]` to `[x]`, add notes inline.

## Phase 0 — Foundations (1 week)

Goal: a clean repo you can develop in for 12 weeks without reorganising it.

- [x] Create monorepo structure as in [doc 03 §8](./03-architecture.md)
- [x] Set up `pyproject.toml` with ruff, black, mypy, pytest, pytest-asyncio
- [x] Set up `.env.example` with all required variables (see doc 05)
- [x] Initial GitHub Actions: lint, type-check, unit-test on PR
- [x] `docker-compose.yml` for local dev (backend + sqlite volume)
- [x] Bootstrap React + Vite + Tailwind frontend (single "Hello" page)
- [x] Wire frontend dev server to backend in dev mode
- [x] Choose & wire structured logger (`structlog` recommended)
- [x] Initial Alembic migration (empty schema, just establishes the framework)
- [x] README with setup steps that an external reader could follow
- [x] Decide & document Python version, frontend Node version

**Exit:** `docker compose up`, browse to `localhost:8000`, see "Hello" page; `pytest` runs and passes (zero tests is fine).

---

## Phase 1 — Plugin core (2 weeks)

Goal: prove the plugin model works end-to-end with a fake strategy and a fake broker.

### Core types & contracts

- [x] Implement `algotrader/core/events.py` with `Tick`, `Bar`, `Order`, `OrderRequest`, `Position`, etc.
- [x] Implement `algotrader/core/strategy_base.py` (`Strategy` ABC, `StrategyContext`)
- [x] Implement `algotrader/core/broker_base.py` (`Broker` ABC, `BrokerCapabilities`)

### Plugin discovery

- [x] Implement `algotrader/core/plugin_loader.py`: scan folders, import, validate
- [x] Validation: required fields, well-formed `params_schema`
- [x] CLI command: `algotrader plugins list`
- [x] Unit tests: malformed plugin → graceful skip + error event

### Sample plugins

- [x] `strategies/_template.py` with full skeleton + comments
- [x] `strategies/example_sma_cross.py` (a working canonical example)
- [x] `brokers/backtest.py` — built-in deterministic broker
- [x] `brokers/paper.py` — built-in paper broker (uses live ticks, simulates fills)
- [x] `brokers/_dummy.py` — broker that records calls (for tests)

### Wire-up

- [x] In-memory `StrategyContext` implementation
- [x] Strategy Engine: instantiate, drive `on_start` / `on_bar` / `on_stop`
- [x] Market data bus (publish/subscribe in-memory)
- [x] Tick aggregator: ticks → bars at multiple timeframes

### Tests

- [x] Unit: plugin loader
- [x] Unit: aggregator with edge cases (gaps, holidays)
- [x] Integration: SMA Cross strategy on canned tick stream produces expected orders

**Exit:** Drop a strategy file, drop a fake broker, run a script that pipes a recorded tick stream → see strategy place orders against the fake broker. No DB or UI yet.

---

## Phase 2 — Backtest engine (2 weeks)

Goal: backtest a real strategy on real historical data with real metrics.

### Storage

- [x] Implement persistence layer (SQLAlchemy models for tables in doc 05)
- [x] First migration creates tables: `strategy_class`, `broker_class`, `bar`, `backtest_run`, `backtest_trade`, `audit_log`
- [x] CSV importer for historical OHLCV data

### Backtest engine

- [x] `BacktestBroker.fill_simulator` with configurable slippage, fees
- [x] Backtest orchestrator: load history → drive strategy → record trades
- [x] Metrics: total return, CAGR, Sharpe, Sortino, max DD, drawdown duration, win rate, profit factor, expectancy, trade count
- [x] Equity curve generation
- [x] Determinism test: same inputs + seed → identical outputs

### CLI

- [x] `algotrader backtest run <strategy> <params> <data> --from --to`
- [x] Output: metrics table + equity curve PNG

### Audit log

- [x] `AuditLog` writer, hash chain
- [x] Audit log records strategy lifecycle and order events in backtest

**Exit:** From the CLI, run a backtest of `example_sma_cross` on a year of NIFTY 1-min data; see metrics in the terminal; row recorded in `backtest_run`.

---

## Phase 3 — Zerodha integration + minimal UI (2 weeks)

Goal: real broker connectivity in paper mode, with a UI you can actually look at.

### Zerodha broker plugin

- [x] `brokers/zerodha.py` — connect (manual login flow first)
- [x] Historical data fetch
- [x] Live tick subscription via `KiteTicker`
- [x] Place / cancel / modify order
- [x] Get positions, holdings, margins
- [x] Order event stream (postbacks → our `Order` updates)
- [x] Encrypted token cache to disk

### Auth automation

- [x] Auto-login flow with TOTP (use `pyotp`); investigate broker T&Cs first
- [x] Daily token refresh job (scheduled around 6 AM IST)
- [x] Healthcheck reports auth state

### FastAPI backend skeleton

- [x] App startup wires plugin loader, DB, broker connections
- [x] `/api/health` endpoint
- [x] `/api/strategies` list, get
- [x] `/api/brokers` list, status
- [x] WebSocket endpoint streaming basic events (ticks, orders)
- [x] CORS for local dev

### Frontend MVP

- [x] Login screen (single user) + 2FA (TOTP)
- [x] Layout with top bar + nav
- [x] Dashboard skeleton: fetch & display strategies, broker status
- [x] WebSocket client; show live ticks for one symbol on dashboard

**Exit:** Open the UI, log in with 2FA, see "Zerodha: Connected" status, see a live tick stream for NIFTY. No live orders yet.

---

## Phase 4 — Strategy instances + paper trading (2 weeks)

Goal: run a strategy in paper mode against live Zerodha data.

### Strategy instances

- [x] DB-backed `strategy_instance` records (config, status, state)
- [x] CRUD API: create, list, update params, start, stop
- [x] UI: Strategies page, "New Instance" wizard, parameter form auto-rendered from `params_schema`
- [x] Strategy runner: spawns asyncio tasks per running instance
- [x] Crash isolation: exception in one strategy → mark errored, alert, don't crash others

### Paper broker on live data

- [x] Wire `PaperBroker` to consume live Zerodha ticks
- [x] Simulated fills with realistic latency + slippage
- [x] Paper positions tracked in DB

### UI: dashboard becomes useful

- [x] Per-strategy P&L (live)
- [x] Position table (live)
- [x] Recent activity feed (live via WS)

### Tests

- [x] Integration: create instance via API, start, simulate ticks, see orders flow

**Exit:** Create a strategy instance for `example_sma_cross` on a real symbol in paper mode, start it during market hours, watch it place simulated trades on the dashboard.

---

## Phase 5 — Risk manager + live trading (2 weeks)

Goal: real-money trading, with the risk system that justifies trusting it.

### Risk Manager

- [x] Implement gates: per-strategy / account daily loss, max position, max open positions, capital allocation, OPS limiter, margin pre-check, sanity checks
- [x] All risk decisions logged to audit
- [x] Unit tests for every gate

### Live mode

- [x] Switch instance mode: paper → live (with 2FA confirmation in UI)
- [x] Live mode routes through Zerodha broker
- [x] Order state machine fully wired: pending → submitted → accepted → filled / rejected
- [x] Reconciliation job: every 60s compare DB vs broker

### Kill switch

- [x] Backend endpoint with 2FA gate
- [x] Cascade: pause all strategies → cancel all open orders → optionally exit positions
- [x] Durable kill switch flag in DB
- [x] UI banner + Telegram alert
- [x] Manual reset flow

### Notifications

- [x] Telegram bot integration
- [x] Configurable alert rules (event types × min severity)

**Exit:** Place a real ₹0-risk order (smallest possible quantity, far OTM option, after-market), see it execute, see audit log clean. Run the kill switch on a real open order, see it cancel within 5 seconds.

---

## Phase 6 — Polish & dashboard depth (2 weeks)

Goal: a UI you'd actually use on your phone during a stressful day.

### UI

- [x] Strategy detail page (Overview / Parameters / Trades / Logs / History tabs)
- [x] Backtest UI: form, run, results page with equity curve + metrics + trades
- [x] Compare backtests side-by-side
- [x] Trades page with filters and drill-down drawer
- [x] Logs page with structured search
- [x] Settings: brokers, risk limits, notifications, compliance dashboard
- [x] Mobile responsive QA pass on real phone

### UX details

- [x] Empty states for every screen
- [x] Loading skeletons (no spinners)
- [x] Error boundaries
- [x] Confirmation modals where required (see doc 06 §7)
- [x] Dark mode polish

### Charts

- [x] Equity curve component (re-used in dashboard, strategy detail, backtest)
- [x] Price chart with trade markers (using `lightweight-charts`)

### Compliance dashboard

- [x] Show: bound IP, configured OPS limit, last token refresh, audit log stats, retention status

**Exit:** A new user (you) can complete every Journey from doc 01 §6 without dipping into terminal or DB.

---

## Phase 7 — Hardening (1 week)

Goal: deployable. Backups, alerts, drills.

- [x] Deployment guide for the chosen target (single VPS recommended)
- [x] systemd unit files or docker compose production config
- [x] HTTPS via Caddy or Nginx + Let's Encrypt
- [x] Daily DB backup script + restore drill
- [x] Crash recovery testing (kill -9 with open positions)
- [x] Reconciliation drift drill (manufacture mismatch, watch alerts fire)
- [x] OPS limiter stress test
- [x] Memory leak soak test (4 hours paper mode)
- [x] Manual go-live drill checklist (doc 08 §8) executed and signed off

**Exit:** v1.0.0 tag. You feel comfortable letting it run unattended for an hour.

---

## Phase 8 — UI Redesign (new designs, May 2026)

Goal: implement the new Xillion design system across all screens. Reference: `Xillion.html` design file.

### Shared components (prerequisite for all screens)

- [x] `Sparkline` component — SVG line chart with gradient fill (used on Dashboard + Backtest)
- [x] `Gauge` component — circular arc gauge showing % value with label/sub (used on Dashboard risk budget)
- [x] `SegmentedControl` component — inline pill button group (used on Strategies modal, Trades filter, Logs filter, Backtest time range)
- [x] `Badge` with animated dot variant for live/streaming indicators

### Layout

- [x] Replace horizontal topbar nav with collapsible left sidebar (Workspace + System sections, user chip at bottom)
- [x] Redesign topbar: breadcrumbs, global search (⌘K), live status dots (broker + feed latency), theme toggle, notifications bell
- [x] Replace kill switch button with skull-icon dropdown menu (pause all strategies, cancel all orders, flatten positions, trigger kill switch with 2-step confirm)

### Dashboard

- [x] Hero P&L card: today's P&L (₹ + % vs yesterday), equity total, intraday sparkline, 4-stat footer (open trades, closed, win rate, avg trade)
- [x] Equity curve card with 1W/1M/3M/1Y segmented time selector
- [x] Stat strip: Strategies running/total, Broker status, Drawdown (% + progress bar), Today's order count
- [x] Risk budget card: two Gauges (capital used %, loss budget %), plus risk metrics table (daily loss cap, per-trade risk, max positions, OPS)
- [x] Live ticks redesign: 4-column grid per symbol with LTP, % change (▲/▼), volume, streaming badge
- [x] Active strategies table: full columns — name, mode, status, capital, trades, P&L, started, stop/start action
- [x] Backend: new `GET /api/portfolio/summary` endpoint for P&L today, equity history, intraday curve, drawdown

### Strategies

- [x] Add "Archived" tab with count pill (Instances | Classes | Archived)
- [x] Add count pills to all tab labels
- [x] Convert instance list from 1-column stack to 2-column grid
- [x] Add Capital / Trades / P&L 3-stat row to instance cards (requires `trade_count` + `pnl` in instance API response)
- [x] Add "Configure" ghost button to instance cards
- [x] Replace mode `<select>` with segmented control (Paper | Live) in New Instance modal

### Trades

- [x] Add Win rate stat card (4th card) with progress bar
- [x] Embed filter input (with search icon) inside table card header
- [x] Add All/BUY/SELL segmented side filter
- [x] Add "streaming" animated badge to table card header
- [x] Add Order ID as last column in trades table

### Backtest

- [x] Add trade log table to results section ("last 6 trades": Date, Side, Entry, Exit, Bars, P&L)
- [x] Add "Avg holding" as 10th metric in metrics grid
- [x] Add run-time badge to results header (e.g. "done · 4.2s")
- [x] Show date range + session count in results header

### Logs

- [x] Move filter input + level selector inside card header bar (currently floats above the card)
- [x] Replace level `<select>` dropdown with segmented control (all / info / warn / err / debug)
- [x] Add "tailing" animated badge + filtered line count to card header

### Settings

- [x] Convert flat sections to 5-tab layout: Brokers | Risk | Notifications | Account | Danger zone
- [x] Brokers tab: always-visible credential fields, "Test connection" button, Paper engine info card, Add broker placeholder
- [x] Risk tab: editable per-instance caps (daily loss %, per-trade %, max positions, position size ₹) + OPS throttle with live progress bar (currently read-only)
- [x] Notifications tab: Telegram bot token + chat ID, toggle switches per alert type (entirely new — no existing UI)
- [x] Account tab: username, email, timezone, theme selector, TOTP re-enroll (consolidates current 2FA section)
- [x] Danger zone tab: "Reset all data" + "Wipe everything" with confirmation dialogs

**Exit:** Every screen matches the new Xillion design. All existing functionality is preserved.

---

## Phase 9 — Backend data + housekeeping (May 2026)

### Uncommitted changes

- [x] Commit port changes: `docker-compose.yml` (8000→8001) and `frontend/vite.config.ts` (5173→5174)

### Dashboard backend endpoint

- [x] Implement `GET /api/portfolio/summary` — returns: `pnl_today` (₹ + %), `equity_total`, `intraday_curve` (array of {ts, value}), `drawdown_pct`, `open_trades`, `closed_trades_today`, `win_rate`, `avg_trade_pnl`
- [x] Wire Dashboard hero P&L card to `/api/portfolio/summary` (remove placeholder fallbacks)
- [x] Wire equity curve card to the `historical_equity` / `intraday_curve` from the same endpoint
- [x] Wire risk budget Gauges to real `capital_used_pct` + `loss_budget_pct` from the endpoint
- [x] Wire stat strip "Drawdown" card to live `drawdown_pct` from the endpoint

### Phase 0–7 tracker cleanup

- [x] Sweep Phases 0–7 checkboxes and mark completed items `[x]` to reflect actual committed state

---

## Phase 10 — DB persistence pipeline + Trades page (May 2026)

Goal: every order, fill, and closed trade round-trip is persisted to DB; the Trades page loads from DB on mount and receives real-time updates via WebSocket.

### A — Execution layer DB persistence

- [x] `ExecutionRouter._persist_order()` — upserts `OrderRecord` + writes `FillRecord` on fill; increments `DailyRiskState.total_orders_placed`
- [x] `_StrategyContextImpl._persist_trade_close()` — upserts `PositionRecord`, `DailyStrategyPnl`, `DailyRiskState.account_realised_pnl` when a position fully closes
- [x] `_StrategyContextImpl._update_position_from_order()` wired into `place_order()` (was dead code)
- [x] Thread `db_factory`, `broker_connection_id`, `instance_name`, `on_trade_close` through `StrategyEngine.spawn()` and `instances.py start_instance`

### B — In-session trade counters

- [x] `_StrategyContextImpl` tracks `_trade_count` and `_win_count` per running instance
- [x] `StrategyRunner` exposes `trade_count` and `win_count` properties
- [x] `_inst_to_dict` in `instances.py` includes `trade_count` and `win_count`

### C — Trades API + page

- [x] `GET /api/trades` — FIFO-matched entry/exit pairs from `FillRecord`; supports `symbol`, `instance_id`, `date_from` filters and pagination
- [x] Register trades router in `main.py`
- [x] `MatchedTrade` interface + `api.trades.list()` in `frontend/src/lib/api.ts`
- [x] `Trades.tsx` rewritten — loads history from DB on mount, WS listener for real-time `trade_closed` events, entry/exit column layout, direction filter (LONG/SHORT)

### D — Win rate in portfolio endpoint

- [x] `GET /api/portfolio/summary` computes `win_rate` from today's FIFO-matched fills (replaces the hardcoded `0.0`)

**Exit:** start a paper strategy, place a BUY+SELL pair; `/api/trades` returns the matched trade; Trades page shows it; Dashboard win rate is non-zero.

---

## Future / commercial — Phase 8+

- [ ] Second broker plugin (Upstox / Fyers)
- [ ] Strategy parameter optimisation UI (grid search, walk-forward)
- [ ] Multi-user authentication and RBAC
- [ ] Postgres production deployment
- [ ] Per-user broker connections
- [ ] Per-tenant data isolation
- [ ] SEBI vendor empanelment (legal track, in parallel)
- [ ] Subscription billing
- [ ] Mobile native app (only if responsive web isn't enough)

---

## Cross-cutting workstreams

These run alongside every phase, not as separate phases:

### Tests
- Add unit tests as you build (don't defer)
- Integration tests on each phase boundary
- Manual drills before each release tag

### Docs
- Inline docstrings on every public API
- Update `04-plugin-contracts.md` if contracts change (treat as a versioned API)
- Update this tracker as you go (PR template should include "tracker updated")

### Audit log
- Every new feature should ask: "is this audited?" If yes, add the event type

### Compliance
- Re-read [doc 07](./07-risk-and-compliance.md) at each phase boundary
- Watch for SEBI rule updates (subscribe to NSE/SEBI circulars)

---

## Rough schedule

| Phase | Calendar weeks (cumulative) |
|---|---|
| 0 | Week 1 |
| 1 | Weeks 2–3 |
| 2 | Weeks 4–5 |
| 3 | Weeks 6–7 |
| 4 | Weeks 8–9 |
| 5 | Weeks 10–11 |
| 6 | Weeks 12–13 |
| 7 | Week 14 |

**v1.0.0 target: ~14 calendar weeks** of evenings + weekends. Under-promise: assume slippage, give yourself slack.

## Anti-goals (what slows the project down)

- Premature optimisation: SQLite is fine for v1. Don't migrate to Postgres unless something is actually slow.
- Premature abstraction: don't add a fourth mode beyond backtest/paper/live "just in case."
- Bikeshedding: pick boring defaults, ship them, change later if needed.
- Adding features in the "future" list before P0 is done.
- Going live before paper-mode soak passes.

## Definition of "done" for a task

A checked box means:
1. Code is merged to main
2. Tests added and passing
3. Documentation updated where relevant
4. Manually verified end-to-end (or paper soak passed if it's a behavioural change)
