# Xillion — Personal Algorithmic Trading Platform

> Self-hosted algo trading bot: drop a Python file to add a strategy, drop a Python file to add a broker.

See `docs/` for full specifications.

---

## Quick start — single command

**Prerequisites:** Python 3.11+, Node 20+, a virtual environment activated.

```bash
# First time only — installs everything and creates .env + data/
make setup

# Every time after that — starts backend + frontend together
make dev
```

That's it. Both processes start in one terminal. **Ctrl+C** stops everything cleanly.

| URL | What |
|-----|------|
| `http://localhost:5174` | React UI (Vite dev server) |
| `http://localhost:8001` | FastAPI backend |
| `http://localhost:8001/api/docs` | Interactive API docs (Swagger) |

> The database (SQLite) is created automatically on first start inside `data/`. No separate DB process needed for local dev.

---

## Local backtest quick start

Backtest history (`bar`, `bar_coverage`, `option_chain_snapshot` — NIFTY +
BANKNIFTY, 2021-01-01 → present) lives in a **local-only** SQLite warehouse
at `data/backtest_warehouse.db`, separate from the main app DB. This keeps
Supabase's free tier from filling up with regenerable historical cache — see
`CLAUDE.md`'s Deploy workflow section for the full story. It means real
backtests only work **locally** for now; Render doesn't carry this file.

```bash
# 1. Start the app (creates the warehouse DB on first boot if missing)
make dev

# 2. Open http://localhost:5174, complete Setup (first run only) → log in
```

Then, in the UI:

3. **Settings → Data Providers** — confirm coverage shows a NIFTY/BANKNIFTY
   range (already backfilled if you've pulled this repo's `data/` folder;
   otherwise trigger a backfill from this same panel — it fetches free NSE
   Bhavcopy data day by day).
4. **Backtest page** — pick a strategy (e.g. `Credit Spread Weekly` or `SMA
   Cross`), pick the `NSE Bhavcopy` provider, set symbol (`NIFTY` /
   `BANKNIFTY`) and a date range inside the covered window, click **Run
   Backtest**. Equity curve, metrics, and the trade list render in place;
   every run is also saved to **Run history** on the same page.

Prefer the API directly (e.g. for scripting a sweep)? The same thing is
`POST /api/backtest/run-provider` — see `http://localhost:8001/api/docs`
for the full request shape, or `POST /api/backtest/optimize` /
`/walk-forward` for parameter sweeps over the same warehouse-backed bars.

**Once a strategy is proven out here**, promote it the normal way: commit
the strategy file, open a PR, merge to `main`. The strategy code itself has
no dependency on the local warehouse — live/paper trading on Render (or
Zerodha/Dhan paper mode) uses real-time broker ticks, not this cache; the
warehouse only matters for *backtesting* history.

**Back up the warehouse before anything risky** (wiping `data/`, a fresh
machine) — it took hours to build from NSE Bhavcopy. **Yes, this dump
already exists and is ready to reuse** — the NIFTY+BANKNIFTY 2021-2026
backfill (1.5GB raw) compresses to **~241MB gzipped**, small enough to sit
in Google Drive (or wherever) comfortably:
```bash
make backup-warehouse                       # → data/backups/warehouse/warehouse_<ts>.db.gz
```
Upload that `.gz` to Drive — there's no cloud copy of this file by design,
and it's 100% free to regenerate from NSE Bhavcopy if you ever lose it, so
this is purely a time-saver, not irreplaceable data. On any new setup
(fresh machine, a new git worktree/branch checkout — **`data/` is
gitignored and NOT shared between worktrees**, so every worktree needs its
own restore), skip the hours-long backfill entirely:
```bash
make restore-warehouse FILE=path/to/warehouse_<ts>.db.gz
```
Whole-file snapshot, so it automatically covers any table added later —
nothing to update here as the schema grows.

**Note on encrypted credentials across setups:** if `ENCRYPTION_KEY` is
left empty in `.env`, the app auto-generates and persists one to
`data/.encryption_key` **per machine**. That file isn't part of this
backup and isn't shared between worktrees either — if you're pointed at a
shared Postgres DB (see below) that already has encrypted broker/Telegram
credentials from another machine, a fresh auto-generated key here won't
decrypt them. Set a real `ENCRYPTION_KEY` in `.env` once
(`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
and reuse it everywhere you want those credentials to keep working.

See [docs/product/user-guide.md](docs/product/user-guide.md) for the full
walkthrough of every page in the app (Journal, Alerts, MCP server, going
live, etc.), not just the backtest flow.

---

## Gold Sweep-Reversal (XAUUSD alert engine) quick start

An alert-only strategy — Telegram notification with full reasoning per
signal, plus taken/skipped + win/loss tracking on the Alerts page — not
live trading. Full rules, design rationale, and honest gaps:
[docs/strategies/gold-xauusd-sweep-reversal.md](docs/strategies/gold-xauusd-sweep-reversal.md).
Deliberately **doesn't need the Funding Pips MT5 broker/bridge** (no Wine,
no MT5 terminal) — it runs on a separate free live-data feed instead.

**1. Two free API keys, no card required:**
- [Twelve Data](https://twelvedata.com) → live XAUUSD M5 candles. Required.
- [Finnhub](https://finnhub.io) → news/econ-calendar ritual check. Optional
  — the strategy's rules run fine without it, this check is currently a
  stub either way (see the strategy doc §7).

Add both to `.env`:
```bash
TWELVE_DATA_API_KEY=...
FINNHUB_API_KEY=...
```

**2. Apply the DB migration** (adds taken/skipped/outcome columns to
`signal_log`; additive-only, no data touched):
```bash
alembic upgrade head       # or: make db-upgrade
```
> If your `DATABASE_URL` points at a shared/production database (see
> "Deploy workflow" in `CLAUDE.md` — this repo's own local setup does, by
> design, to stay in sync with what's deployed), treat this as a real
> production migration: confirm before running, even though it's additive.

**3. Start the app** (`make dev`) and confirm the feed connected — Dev
page / logs should show `twelve_data: connected successfully`. If it
errors instead, the key is wrong (`TwelveDataBroker.connect()` makes a
real `/quote` call and raises on any API error).

**4. Create the instance.** There's no broker-picker in the
instance-creation UI yet, so create it directly via the API — paste this
in the browser console on a tab where you're already logged into the app:
```js
await fetch('/api/instances', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'Gold Sweep-Reversal (XAUUSD)',
    strategy_class_name: 'Gold Sweep-Reversal',
    mode: 'alert',
    instruments: ['XAUUSD'],
    timeframe: '5m',
    broker_connection_name: 'Twelve Data Gold Feed',
    capital_allocation: 5000,     // matches the FundingPips $5K card
    params: {},                   // defaults match the card exactly
  }),
}).then(r => r.json()).then(console.log)
```
Then start it from the Strategies page (or `POST /api/instances/{id}/start`).

**5. Verify it's actually alive.** During 07:00–13:00 UTC
(12:30–18:30 IST), watch Dev logs for a `daily levels marked` line, then
wait for a real ENTER signal to confirm the whole path end to end
(Twelve Data → strategy → Telegram → Alerts page take/skip buttons).
Fewer than 4 daily levels on the first day or two is expected — see the
strategy doc §7, not a bug.

---

## With Docker Compose (alternative — requires Docker)

```bash
cp .env.example .env
docker compose up        # starts backend + frontend in one command
```

Backend at `localhost:8001`, Vite dev server at `localhost:5174`.

---

## CLI

```bash
# List discovered plugins
xillion plugins list

# Run a backtest
xillion backtest run "SMA Cross" data/nifty_15m.csv \
  --capital 100000 --slippage 5 --params '{"fast":10,"slow":30,"qty":1}'

# Database management
xillion db upgrade    # run pending Alembic migrations
```

CSV format for `backtest run`:
```
symbol,ts,open,high,low,close,volume[,timeframe,exchange]
NIFTY,2024-01-15T09:15:00,21000,21050,20990,21030,1000
```

---

## Adding a strategy

```bash
cp strategies/_template.py strategies/my_strategy.py
# Edit the file, implement on_bar()
# Click "Reload" in the dashboard — strategy appears instantly
```

## Adding a broker

```bash
# Read brokers/_base.py for the contract
cp brokers/paper.py brokers/my_broker.py
# Implement all abstract methods
# Add credentials to .env
# Restart backend — broker appears in dashboard
```

---

## Deploy on Render

1. Push repo to GitHub
2. Create a new Render **Web Service** — connect the repo
3. Render auto-detects `render.yml` and creates the service + Postgres DB
4. Set secret env vars in Render dashboard:
   - `ZERODHA_PRIMARY_*` (when you reach Phase 3)
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
5. Deploy

The build command (`make render-build`) installs Node, builds React, then installs Python deps.
The start command runs `alembic upgrade head` then starts uvicorn.

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 async |
| Database | SQLite (dev), Postgres (prod) |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| Charts | lightweight-charts |
| Auth | Session cookie + TOTP (Phase 3+) |
| Notifications | Telegram (Phase 5+) |
| CI | GitHub Actions |
| Deploy | Render |

---

## Build phases

| Phase | Status | Description |
|---|---|---|
| 0 | ✅ | Repo scaffolding, CI, docker-compose, React shell |
| 1 | ✅ | Plugin core (Strategy/Broker ABCs, loader, SMA example) |
| 2 | ✅ | Backtest engine + metrics + CLI |
| 3 | ✅ | Zerodha broker + auth + minimal UI |
| 4 | ✅ | Strategy instances + paper trading |
| 5 | ✅ | Risk manager + live trading + kill switch |
| 6 | ✅ | Dashboard polish + mobile (Trades, Logs, Settings pages) |
| 7 | ✅ | Hardening (Docker, systemd, HTTPS, backup, tests) |

See `docs/archive/progress-tracker-phases-0-10.md` for task-level detail.

### First-run flow

1. `make dev` (or `docker compose up`) → open http://localhost:5174
2. **Setup page** — create your first user (this becomes your login).
3. **Settings → Zerodha Credentials** — enter your API key, secret, user ID, login password, and TOTP secret. Click *Save & Connect*. Credentials are encrypted at rest.
4. **Backtest** — choose a strategy, upload a CSV of historical bars, click *Run Backtest*. Equity curve and metrics render in the same view.
5. **Strategies → New Instance** — pick a strategy (e.g. SMA Cross), choose paper mode, set instruments (e.g. `NIFTY`), start it. Paper mode requires Zerodha to be connected for live ticks; otherwise the strategy idles. Validate strategy logic with Backtest before running paper.

---

## Project structure

```
xillion/
├── xillion/          Python package (core, api, db, engine, data, notifications)
├── strategies/       Drop .py files here to add strategies
├── brokers/          Drop .py files here to add brokers
├── frontend/         React + Vite app
├── tests/            pytest test suite
├── scripts/          Utility scripts (init_db, import_csv)
├── docs/             Spec documents
├── render.yml        Render deployment config
├── docker-compose.yml Local dev
└── Makefile          All commands
```

---

## Risk & compliance

This platform is for **personal use** on your own trading account. Read `docs/architecture/risk-and-compliance.md` before going live. In particular:
- Never go live before completing a paper-trade soak (Phase 4 exit criterion)
- Keep your SEBI OPS rate under 10/second (configured via `OPS_LIMIT_PER_SECOND`)
- Keep your `.env` file **out of git** — it contains broker API secrets
