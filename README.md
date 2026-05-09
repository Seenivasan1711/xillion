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
| `http://localhost:5173` | React UI (Vite dev server) |
| `http://localhost:8000` | FastAPI backend |
| `http://localhost:8000/api/docs` | Interactive API docs (Swagger) |

> The database (SQLite) is created automatically on first start inside `data/`. No separate DB process needed for local dev.

---

## With Docker Compose (alternative — requires Docker)

```bash
cp .env.example .env
docker compose up        # starts backend + frontend in one command
```

Backend at `localhost:8000`, Vite dev server at `localhost:5173`.

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

See `docs/09-progress-tracker.md` for task-level detail.

### First-run flow

1. `make dev` (or `docker compose up`) → open http://localhost:5173
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

This platform is for **personal use** on your own trading account. Read `docs/07-risk-and-compliance.md` before going live. In particular:
- Never go live before completing a paper-trade soak (Phase 4 exit criterion)
- Keep your SEBI OPS rate under 10/second (configured via `OPS_LIMIT_PER_SECOND`)
- Keep your `.env` file **out of git** — it contains broker API secrets
