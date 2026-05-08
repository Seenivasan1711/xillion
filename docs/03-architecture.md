# 03 — System Architecture

## 1. Architectural principles

These guide every design decision below. When in doubt, return here.

1. **Plugin boundaries are sacred.** Strategies don't know about brokers. Brokers don't know about strategies. The orchestrator knows about both.
2. **One strategy, three modes.** The strategy code is identical in backtest, paper, and live. Mode is decided by which broker the orchestrator hands the strategy.
3. **Event-driven over polling.** Market data and orders flow as events. Strategies react. This is also how every serious trading system is built.
4. **Fail closed on safety.** If the system is unsure, it does not place an order. Risk controls are pre-trade gates, not post-trade alarms.
5. **Boring beats fancy.** Python + FastAPI + SQLite + React. Everything else is a future problem.
6. **Single binary mindset.** Even if it's docker-composed, the system should feel like one thing you start and stop.

## 2. High-level component view

```
                    ┌──────────────────────────────────────────┐
                    │              Web UI (React)              │
                    │   Dashboard | Strategies | Backtest |    │
                    │   Trades | Settings | KILL SWITCH        │
                    └──────────────────┬───────────────────────┘
                            REST + WebSocket (FastAPI)
                                       │
   ┌───────────────────────────────────┴────────────────────────────────┐
   │                     ALGOTRADER CORE  (Python)                      │
   │                                                                    │
   │   ┌─────────────┐   ┌────────────────┐   ┌────────────────────┐    │
   │   │  Strategy   │   │     Risk       │   │     Execution      │    │
   │   │   Engine    │◄─►│    Manager     │◄─►│      Router        │    │
   │   │             │   │                │   │                    │    │
   │   └──────▲──────┘   └────────────────┘   └─────────┬──────────┘    │
   │          │                                         │               │
   │          │  events                       orders    │               │
   │          │                                         ▼               │
   │   ┌──────┴───────┐                       ┌──────────────────┐      │
   │   │   Market     │                       │   Broker Plugin  │      │
   │   │   Data Bus   │◄──────────────────────┤    Interface     │      │
   │   └──────▲───────┘                       └─────────┬────────┘      │
   │          │                                         │               │
   │          │                          ┌──────────────┼─────┐         │
   │          │                          ▼              ▼     ▼         │
   │          │                       Zerodha       Paper   Backtest    │
   │          │                                                         │
   │   ┌──────┴───────┐    ┌──────────────────┐    ┌────────────────┐   │
   │   │  Plugin      │    │    Audit Log     │    │   Persistence  │   │
   │   │  Loader      │    │   (immutable)    │    │   (SQL)        │   │
   │   └──────────────┘    └──────────────────┘    └────────────────┘   │
   │          ▲                                                         │
   │          │  scans folders                                          │
   │   ┌──────┴───────────┐    ┌─────────────────────┐                  │
   │   │   strategies/    │    │      brokers/       │                  │
   │   │   *.py files     │    │     *.py files      │                  │
   │   └──────────────────┘    └─────────────────────┘                  │
   └────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                              ┌────────────────────┐
                              │   Notifier         │
                              │  (Telegram, Email) │
                              └────────────────────┘
```

## 3. Components in detail

### 3.1 Strategy Engine

The strategy engine is the runtime that loads strategy plugins, subscribes them to market data, and routes their order requests to the execution router.

**Responsibilities:**
- Discover strategy classes via the Plugin Loader
- Instantiate strategy instances based on DB config
- Wire each instance to its market data subscriptions
- Invoke lifecycle hooks (`on_start`, `on_bar`, `on_tick`, `on_order_update`, `on_stop`)
- Catch exceptions in user strategy code and isolate failures
- Expose strategy state to the API layer

**Concurrency model:** Each strategy instance runs in its own asyncio task. Strategies do not share mutable state. (Multiprocessing later if a CPU-heavy strategy needs it, but asyncio is enough for retail latencies.)

### 3.2 Market Data Bus

A pub/sub layer that abstracts where data comes from. In live/paper mode, the broker plugin pushes ticks. In backtest mode, the backtest broker replays historical bars. Strategies subscribe to symbols & timeframes and receive normalised events.

**Event types:**
- `Tick(symbol, ltp, ltt, bid, ask, volume, oi)`
- `Bar(symbol, tf, ts, o, h, l, c, v)` (computed by aggregator)
- `OrderBookSnapshot(symbol, bids, asks)` (optional)

### 3.3 Risk Manager

A pre-trade gate every order must pass through. It knows:
- Current positions (per strategy and aggregate)
- Today's P&L (per strategy and aggregate)
- Configured limits (capital, position size, daily loss, max positions)
- OPS counter
- Kill switch state

**Decision API:** `risk.check(order_request) → Approved | Rejected(reason)`

The Risk Manager is the **only** thing that can say "yes, send this order." Strategies cannot bypass it. Even the manual "place test order" UI button goes through it.

### 3.4 Execution Router

Receives approved order requests from the Risk Manager. Looks up the strategy instance's mode (backtest / paper / live) and routes to the appropriate broker plugin. Tracks order state machine. Updates the Position store. Notifies the strategy via `on_order_update`.

### 3.5 Broker Plugin Interface

A defined Python ABC (see doc 04). Each broker implementation provides:
- Auth (login, refresh, logout)
- Market data (subscribe, unsubscribe, historical fetch)
- Orders (place, modify, cancel, get status)
- Account (positions, holdings, margins)
- Lifecycle (connect, disconnect, healthcheck)

**Built-in plugins:**
- `BacktestBroker` — for backtests; deterministic, fast
- `PaperBroker` — for paper trading; uses live market data, simulates fills
- `ZerodhaBroker` — for live trading on Kite Connect

### 3.6 Plugin Loader

On startup and on demand:
1. Walks `strategies/` and `brokers/` directories
2. Imports each `.py` file in a sandboxed module namespace
3. Inspects for classes inheriting `Strategy` or `Broker`
4. Validates the contract (required methods, parameter schema)
5. Registers them in an in-memory registry the rest of the app uses

Failed plugins log errors but don't prevent startup.

### 3.7 Audit Log

Append-only table. Every important event:
- Strategy lifecycle (start, pause, resume, stop, killed)
- Order lifecycle (submitted, accepted, filled, rejected)
- Config changes (params, capital, mode)
- Auth events (login, 2FA, kill switch fired)
- Compliance events (OPS limit hit, risk gate rejected an order)

Records carry: timestamp, actor (user / system / strategy), action, before/after snapshot if relevant, and a hash chain so tampering shows up.

### 3.8 Persistence layer

SQLite by default; Postgres as an env-config swap. Schema in [doc 05](./05-data-model.md).

### 3.9 API layer (FastAPI)

REST endpoints for CRUD-style operations. WebSocket endpoint for live updates to the UI (positions, P&L, log tail, market ticks). Auth via session cookie + 2FA-gated sensitive actions.

### 3.10 Web UI (React + Vite + Tailwind)

See [doc 06](./06-ui-ux.md) for screens. Single-page app, mobile-responsive. WebSocket for live data. No state management framework needed at this scale (Zustand is enough).

### 3.11 Notifier

Single class that fans out alerts to Telegram (primary), email (secondary), and in-app. Reads channel config from DB.

## 4. Data flow examples

### Live order flow (the critical path)

```
Strategy generates signal
     │
     ▼
strategy.place_order(OrderRequest)
     │
     ▼
RiskManager.check(order_request)
   ├─ rejected → audit_log + alert + return error to strategy
   └─ approved
     │
     ▼
ExecutionRouter.submit(order_request)
     │
     ▼
broker_plugin.place_order(order_request)  [Zerodha REST API]
     │
     ▼
broker returns order_id, status=PENDING
     │
     ▼
PositionStore.update_pending(order)
AuditLog.record(order_submitted)
     │
     ▼
broker WebSocket / postback delivers status updates
     │
     ▼
ExecutionRouter.on_order_update(order)
PositionStore.update(order)
strategy.on_order_update(order)
AuditLog.record(order_filled)
     │
     ▼
WebSocket pushes update to UI
Notifier sends Telegram if configured
```

### Backtest flow

```
User clicks "Run Backtest"
     │
     ▼
API loads strategy config + history (cached or from broker)
     │
     ▼
BacktestBroker initialised with history + slippage/fee config
StrategyEngine instantiates strategy with mode=backtest
     │
     ▼
Loop bars in chronological order:
  for bar in history:
    market_data_bus.publish(bar)         # strategy.on_bar fires
    backtest_broker.advance_clock(bar)   # process pending fills
     │
     ▼
At end: compute metrics, persist run, return to UI
```

### Strategy hot-reload

```
User clicks "Reload Strategies"
     │
     ▼
PluginLoader rescans strategies/
For each running strategy whose code hash changed:
  1. Pause new signal generation
  2. Snapshot state
  3. Replace class in registry
  4. Reattach instance to new class
  5. Resume

If reload fails: keep old class, log error, alert.
```

## 5. Concurrency and processes

For v1, **one process** is enough. Within that process:

- Main asyncio event loop drives the API + WebSocket
- A separate asyncio task per strategy instance
- A separate asyncio task per active broker WebSocket
- A worker pool (3–5 threads) for blocking calls (broker REST, DB writes that aren't async)
- A scheduler task for cron-like work (daily token refresh, EOD report, audit log archive)

If a heavy strategy is CPU-bound (rare for retail), move it to a multiprocessing worker. Don't pre-optimise.

## 6. State management

| State | Where it lives | Why |
|---|---|---|
| Strategy code | Files on disk | The whole point of the plugin design |
| Strategy config (params, mode, etc.) | DB | Survives restarts, editable from UI |
| Positions, orders, fills | DB (source of truth) + in-memory cache | Cache is convenience; DB is truth |
| Live market data | In-memory ring buffer | Recent bars; older lives in DB |
| Audit log | DB (append-only table) | Survives forever |
| Secrets (API keys, TOTP) | `.env` file (encrypted optional) | Never in DB, never in git |
| Session tokens | DB or Redis (later) | Short-lived |

**On crash recovery:** boot reads DB, reconciles with broker (positions, orders), emits a "reconciliation" audit event, and resumes. If reconciliation finds drift > tolerance, it pauses all strategies and alerts.

## 7. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Strategy authors expect Python; broker libraries are Python-native |
| API framework | FastAPI | Async-native, auto-generates docs, type hints |
| ORM | SQLAlchemy 2.0 (async) | Boring, well-supported |
| DB | SQLite default, Postgres prod | Zero-config dev, scalable later |
| Async | asyncio + httpx | Standard library + good async HTTP |
| Frontend | React + Vite + TypeScript + Tailwind | Fast iteration, good ecosystem |
| Charts | lightweight-charts (TradingView's OSS) | Best fit for OHLC + indicators |
| State (UI) | Zustand | Simpler than Redux for this scale |
| WebSocket | FastAPI's built-in | One less dependency |
| Auth | Custom (session cookie + TOTP) | OAuth overkill for single-user |
| Process supervisor | systemd or docker compose | Production-appropriate |
| Logging | structlog + loguru | Structured logs out of the box |
| Testing | pytest + pytest-asyncio + Playwright | Backend + frontend |
| CI | GitHub Actions | Free for personal repos |

**Things deliberately not in the stack (yet):**

- Kafka / Redis Streams — overkill for one user
- Kubernetes — overkill
- ML frameworks — strategies that need ML can import them themselves
- gRPC — REST + WebSocket is enough

## 8. Repository layout

```
algotrader/
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml
│
├── docs/                          ← these documents live here in the repo
│   └── ...
│
├── algotrader/                    ← main backend package
│   ├── __init__.py
│   ├── main.py                    ← FastAPI app entrypoint
│   │
│   ├── core/                      ← domain logic, no IO
│   │   ├── strategy_base.py       ← Strategy ABC (the plugin contract)
│   │   ├── broker_base.py         ← Broker ABC (the plugin contract)
│   │   ├── events.py              ← Tick, Bar, Order, OrderRequest, Position, Fill
│   │   ├── risk.py                ← RiskManager
│   │   ├── execution.py           ← ExecutionRouter
│   │   ├── audit.py               ← AuditLog
│   │   └── plugin_loader.py
│   │
│   ├── data/                      ← market data bus + storage
│   │   ├── bus.py
│   │   ├── aggregator.py          ← ticks → bars
│   │   ├── history.py             ← historical fetch + cache
│   │   └── repository.py          ← SQL access for bars
│   │
│   ├── api/                       ← FastAPI routes
│   │   ├── strategies.py
│   │   ├── brokers.py
│   │   ├── orders.py
│   │   ├── backtest.py
│   │   ├── auth.py
│   │   ├── ws.py                  ← WebSocket
│   │   └── kill_switch.py
│   │
│   ├── notifications/
│   │   ├── telegram.py
│   │   └── email.py
│   │
│   └── db/
│       ├── models.py              ← SQLAlchemy models
│       ├── migrations/            ← alembic migrations
│       └── session.py
│
├── strategies/                    ← USER STRATEGIES GO HERE
│   ├── _template.py               ← copy this to start a new strategy
│   ├── example_sma_cross.py
│   └── example_orb.py
│
├── brokers/                       ← USER BROKER PLUGINS GO HERE
│   ├── _base.py                   ← (re-exports core/broker_base.py)
│   ├── backtest.py                ← built-in
│   ├── paper.py                   ← built-in
│   └── zerodha.py
│
├── frontend/                      ← React app
│   ├── package.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   └── lib/
│   └── vite.config.ts
│
├── scripts/
│   ├── init_db.py
│   ├── seed_dev.py
│   └── backup.sh
│
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

## 9. Deployment topology

### v1 — Personal use

**Option A: Single VPS (recommended)**

- Small VPS (2 vCPU, 4 GB RAM, 40 GB SSD) — DigitalOcean / Hetzner / a Mumbai-based provider
- Static public IP (required for SEBI compliance — broker whitelisting)
- Docker Compose: backend + frontend + sqlite (or postgres)
- Caddy or Nginx for HTTPS
- systemd or docker for process supervision
- Daily DB backup to encrypted object storage

**Option B: Home machine**

- Same setup, but on a home PC
- ⚠ Requires a static IP from your ISP or a DDNS workaround
- ⚠ Power/network downtime is your problem
- ⚠ Use only if you're actively monitoring

### Future — Commercial

- Per-user containers (or per-user processes inside one app)
- Postgres as primary DB
- Redis for sessions and queues
- Per-user broker connections (with their own static IPs / proxies — significant ops complexity)

## 10. Performance targets (v1)

| Metric | Target |
|---|---|
| Order placement latency (signal → broker API) | < 500 ms median |
| WebSocket tick → strategy `on_tick` invoked | < 50 ms |
| Backtest of 1 year, 1-min bars, 1 instrument | < 60 seconds |
| API response time (P95) | < 200 ms |
| Memory footprint, idle | < 300 MB |
| Memory footprint, 5 strategies live | < 800 MB |
| Startup time | < 10 seconds |

## 11. What we explicitly accept

- We are not microsecond-fast. SEBI's 10 OPS retail threshold means we don't need to be.
- We support one user well. Multi-user is future work, not a v1 hidden feature.
- We trust our own strategies (it's a single-tenant system). No sandboxing of strategy code in v1.
- We rely on the broker for last-mile risk (e.g., margin checks). Our risk manager is in addition to, not instead of, the broker's.
- We accept some duplication between core code and broker plugins (e.g., normalising order types). It's the cost of clean abstractions.
