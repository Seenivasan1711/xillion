# 09 — Progress Tracker

A phased plan with task-level checkboxes. Each phase ends with an **exit criterion** — a working artefact you'd be willing to demo. Don't move on until the exit criterion is met.

Estimates are evenings-and-weekends pace. Aggressive but not unrealistic.

Update this file as you go: change `[ ]` to `[x]`, add notes inline.

## Phase 0 — Foundations (1 week)

Goal: a clean repo you can develop in for 12 weeks without reorganising it.

- [ ] Create monorepo structure as in [doc 03 §8](./03-architecture.md)
- [ ] Set up `pyproject.toml` with ruff, black, mypy, pytest, pytest-asyncio
- [ ] Set up `.env.example` with all required variables (see doc 05)
- [ ] Initial GitHub Actions: lint, type-check, unit-test on PR
- [ ] `docker-compose.yml` for local dev (backend + sqlite volume)
- [ ] Bootstrap React + Vite + Tailwind frontend (single "Hello" page)
- [ ] Wire frontend dev server to backend in dev mode
- [ ] Choose & wire structured logger (`structlog` recommended)
- [ ] Initial Alembic migration (empty schema, just establishes the framework)
- [ ] README with setup steps that an external reader could follow
- [ ] Decide & document Python version, frontend Node version

**Exit:** `docker compose up`, browse to `localhost:8000`, see "Hello" page; `pytest` runs and passes (zero tests is fine).

---

## Phase 1 — Plugin core (2 weeks)

Goal: prove the plugin model works end-to-end with a fake strategy and a fake broker.

### Core types & contracts

- [ ] Implement `algotrader/core/events.py` with `Tick`, `Bar`, `Order`, `OrderRequest`, `Position`, etc.
- [ ] Implement `algotrader/core/strategy_base.py` (`Strategy` ABC, `StrategyContext`)
- [ ] Implement `algotrader/core/broker_base.py` (`Broker` ABC, `BrokerCapabilities`)

### Plugin discovery

- [ ] Implement `algotrader/core/plugin_loader.py`: scan folders, import, validate
- [ ] Validation: required fields, well-formed `params_schema`
- [ ] CLI command: `algotrader plugins list`
- [ ] Unit tests: malformed plugin → graceful skip + error event

### Sample plugins

- [ ] `strategies/_template.py` with full skeleton + comments
- [ ] `strategies/example_sma_cross.py` (a working canonical example)
- [ ] `brokers/backtest.py` — built-in deterministic broker
- [ ] `brokers/paper.py` — built-in paper broker (uses live ticks, simulates fills)
- [ ] `brokers/_dummy.py` — broker that records calls (for tests)

### Wire-up

- [ ] In-memory `StrategyContext` implementation
- [ ] Strategy Engine: instantiate, drive `on_start` / `on_bar` / `on_stop`
- [ ] Market data bus (publish/subscribe in-memory)
- [ ] Tick aggregator: ticks → bars at multiple timeframes

### Tests

- [ ] Unit: plugin loader
- [ ] Unit: aggregator with edge cases (gaps, holidays)
- [ ] Integration: SMA Cross strategy on canned tick stream produces expected orders

**Exit:** Drop a strategy file, drop a fake broker, run a script that pipes a recorded tick stream → see strategy place orders against the fake broker. No DB or UI yet.

---

## Phase 2 — Backtest engine (2 weeks)

Goal: backtest a real strategy on real historical data with real metrics.

### Storage

- [ ] Implement persistence layer (SQLAlchemy models for tables in doc 05)
- [ ] First migration creates tables: `strategy_class`, `broker_class`, `bar`, `backtest_run`, `backtest_trade`, `audit_log`
- [ ] CSV importer for historical OHLCV data

### Backtest engine

- [ ] `BacktestBroker.fill_simulator` with configurable slippage, fees
- [ ] Backtest orchestrator: load history → drive strategy → record trades
- [ ] Metrics: total return, CAGR, Sharpe, Sortino, max DD, drawdown duration, win rate, profit factor, expectancy, trade count
- [ ] Equity curve generation
- [ ] Determinism test: same inputs + seed → identical outputs

### CLI

- [ ] `algotrader backtest run <strategy> <params> <data> --from --to`
- [ ] Output: metrics table + equity curve PNG

### Audit log

- [ ] `AuditLog` writer, hash chain
- [ ] Audit log records strategy lifecycle and order events in backtest

**Exit:** From the CLI, run a backtest of `example_sma_cross` on a year of NIFTY 1-min data; see metrics in the terminal; row recorded in `backtest_run`.

---

## Phase 3 — Zerodha integration + minimal UI (2 weeks)

Goal: real broker connectivity in paper mode, with a UI you can actually look at.

### Zerodha broker plugin

- [ ] `brokers/zerodha.py` — connect (manual login flow first)
- [ ] Historical data fetch
- [ ] Live tick subscription via `KiteTicker`
- [ ] Place / cancel / modify order
- [ ] Get positions, holdings, margins
- [ ] Order event stream (postbacks → our `Order` updates)
- [ ] Encrypted token cache to disk

### Auth automation

- [ ] Auto-login flow with TOTP (use `pyotp`); investigate broker T&Cs first
- [ ] Daily token refresh job (scheduled around 6 AM IST)
- [ ] Healthcheck reports auth state

### FastAPI backend skeleton

- [ ] App startup wires plugin loader, DB, broker connections
- [ ] `/api/health` endpoint
- [ ] `/api/strategies` list, get
- [ ] `/api/brokers` list, status
- [ ] WebSocket endpoint streaming basic events (ticks, orders)
- [ ] CORS for local dev

### Frontend MVP

- [ ] Login screen (single user) + 2FA (TOTP)
- [ ] Layout with top bar + nav
- [ ] Dashboard skeleton: fetch & display strategies, broker status
- [ ] WebSocket client; show live ticks for one symbol on dashboard

**Exit:** Open the UI, log in with 2FA, see "Zerodha: Connected" status, see a live tick stream for NIFTY. No live orders yet.

---

## Phase 4 — Strategy instances + paper trading (2 weeks)

Goal: run a strategy in paper mode against live Zerodha data.

### Strategy instances

- [ ] DB-backed `strategy_instance` records (config, status, state)
- [ ] CRUD API: create, list, update params, start, stop
- [ ] UI: Strategies page, "New Instance" wizard, parameter form auto-rendered from `params_schema`
- [ ] Strategy runner: spawns asyncio tasks per running instance
- [ ] Crash isolation: exception in one strategy → mark errored, alert, don't crash others

### Paper broker on live data

- [ ] Wire `PaperBroker` to consume live Zerodha ticks
- [ ] Simulated fills with realistic latency + slippage
- [ ] Paper positions tracked in DB

### UI: dashboard becomes useful

- [ ] Per-strategy P&L (live)
- [ ] Position table (live)
- [ ] Recent activity feed (live via WS)

### Tests

- [ ] Integration: create instance via API, start, simulate ticks, see orders flow

**Exit:** Create a strategy instance for `example_sma_cross` on a real symbol in paper mode, start it during market hours, watch it place simulated trades on the dashboard.

---

## Phase 5 — Risk manager + live trading (2 weeks)

Goal: real-money trading, with the risk system that justifies trusting it.

### Risk Manager

- [ ] Implement gates: per-strategy / account daily loss, max position, max open positions, capital allocation, OPS limiter, margin pre-check, sanity checks
- [ ] All risk decisions logged to audit
- [ ] Unit tests for every gate

### Live mode

- [ ] Switch instance mode: paper → live (with 2FA confirmation in UI)
- [ ] Live mode routes through Zerodha broker
- [ ] Order state machine fully wired: pending → submitted → accepted → filled / rejected
- [ ] Reconciliation job: every 60s compare DB vs broker

### Kill switch

- [ ] Backend endpoint with 2FA gate
- [ ] Cascade: pause all strategies → cancel all open orders → optionally exit positions
- [ ] Durable kill switch flag in DB
- [ ] UI banner + Telegram alert
- [ ] Manual reset flow

### Notifications

- [ ] Telegram bot integration
- [ ] Configurable alert rules (event types × min severity)

**Exit:** Place a real ₹0-risk order (smallest possible quantity, far OTM option, after-market), see it execute, see audit log clean. Run the kill switch on a real open order, see it cancel within 5 seconds.

---

## Phase 6 — Polish & dashboard depth (2 weeks)

Goal: a UI you'd actually use on your phone during a stressful day.

### UI

- [ ] Strategy detail page (Overview / Parameters / Trades / Logs / History tabs)
- [ ] Backtest UI: form, run, results page with equity curve + metrics + trades
- [ ] Compare backtests side-by-side
- [ ] Trades page with filters and drill-down drawer
- [ ] Logs page with structured search
- [ ] Settings: brokers, risk limits, notifications, compliance dashboard
- [ ] Mobile responsive QA pass on real phone

### UX details

- [ ] Empty states for every screen
- [ ] Loading skeletons (no spinners)
- [ ] Error boundaries
- [ ] Confirmation modals where required (see doc 06 §7)
- [ ] Dark mode polish

### Charts

- [ ] Equity curve component (re-used in dashboard, strategy detail, backtest)
- [ ] Price chart with trade markers (using `lightweight-charts`)

### Compliance dashboard

- [ ] Show: bound IP, configured OPS limit, last token refresh, audit log stats, retention status

**Exit:** A new user (you) can complete every Journey from doc 01 §6 without dipping into terminal or DB.

---

## Phase 7 — Hardening (1 week)

Goal: deployable. Backups, alerts, drills.

- [ ] Deployment guide for the chosen target (single VPS recommended)
- [ ] systemd unit files or docker compose production config
- [ ] HTTPS via Caddy or Nginx + Let's Encrypt
- [ ] Daily DB backup script + restore drill
- [ ] Crash recovery testing (kill -9 with open positions)
- [ ] Reconciliation drift drill (manufacture mismatch, watch alerts fire)
- [ ] OPS limiter stress test
- [ ] Memory leak soak test (4 hours paper mode)
- [ ] Manual go-live drill checklist (doc 08 §8) executed and signed off

**Exit:** v1.0.0 tag. You feel comfortable letting it run unattended for an hour.

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
