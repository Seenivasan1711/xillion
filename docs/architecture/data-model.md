# 05 — Data Model

This document defines the persistent data model. Schema is shown in SQLite-flavoured DDL but maps cleanly to Postgres.

## 1. Storage strategy

| Data category | Storage |
|---|---|
| Strategy code | Files on disk (`strategies/`, `brokers/`) |
| Strategy & broker config | DB tables |
| Orders, fills, positions | DB tables (source of truth) |
| Audit log | DB append-only table |
| Historical bars | DB time-series table (Postgres + TimescaleDB later, plain SQLite for v1) |
| Live ticks | In-memory (recent N), DB for sampled records |
| Backtest runs | DB tables |
| Secrets (API keys, TOTP) | `.env` file, never in DB, never in git |
| Static settings | `.env` |
| Sessions | DB (or Redis later) |

## 2. Schema

### 2.1 Plugin registry (cached metadata)

```sql
CREATE TABLE strategy_class (
  -- Discovered strategy classes; a row here doesn't mean it's running.
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT UNIQUE NOT NULL,           -- Strategy.name
  module_path     TEXT NOT NULL,                  -- e.g. "strategies.example_sma_cross"
  class_name      TEXT NOT NULL,                  -- e.g. "SMACrossStrategy"
  version         TEXT NOT NULL,
  description     TEXT,
  author          TEXT,
  default_timeframe TEXT,
  params_schema_json TEXT NOT NULL,               -- JSON of params_schema
  code_hash       TEXT NOT NULL,                  -- sha256 of the file
  discovered_at   TEXT NOT NULL,                  -- ISO datetime
  last_seen_at    TEXT NOT NULL
);

CREATE TABLE broker_class (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT UNIQUE NOT NULL,           -- Broker.name
  module_path     TEXT NOT NULL,
  class_name      TEXT NOT NULL,
  version         TEXT NOT NULL,
  capabilities_json TEXT NOT NULL,
  discovered_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL
);
```

### 2.2 Broker connections (configured + auth state)

```sql
CREATE TABLE broker_connection (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  broker_class_id INTEGER NOT NULL REFERENCES broker_class(id),
  name            TEXT NOT NULL,                  -- e.g. "My Zerodha"
  credentials_ref TEXT NOT NULL,                  -- env-var prefix, NOT the secret itself
                                                  -- e.g. "ZERODHA_PRIMARY"
  is_active       BOOLEAN NOT NULL DEFAULT 1,
  last_connected_at TEXT,
  last_error      TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  UNIQUE(broker_class_id, name)
);
```

The actual API keys live in `.env` (or a vault). The DB only references them by name. This keeps secrets out of backups.

### 2.3 Strategy instances

```sql
CREATE TABLE strategy_instance (
  id              TEXT PRIMARY KEY,               -- uuid
  strategy_class_id INTEGER NOT NULL REFERENCES strategy_class(id),
  strategy_class_version TEXT NOT NULL,           -- pinned at instance creation
  name            TEXT NOT NULL,                  -- user-given, e.g. "ORB on NIFTY"
  mode            TEXT NOT NULL CHECK(mode IN ('backtest','paper','live')),
  status          TEXT NOT NULL CHECK(status IN ('idle','running','paused','error','killed')),
  broker_connection_id INTEGER NOT NULL REFERENCES broker_connection(id),
  instruments_json TEXT NOT NULL,                 -- list of symbols
  timeframe       TEXT NOT NULL,
  params_json     TEXT NOT NULL,
  capital_allocation NUMERIC NOT NULL,
  risk_limits_json TEXT NOT NULL,                 -- daily_loss, max_positions, etc.
  state_blob      BLOB,                           -- pickled ctx.state
  last_started_at TEXT,
  last_stopped_at TEXT,
  last_error      TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE INDEX idx_strategy_instance_status ON strategy_instance(status);
CREATE INDEX idx_strategy_instance_mode ON strategy_instance(mode);
```

### 2.4 Orders & fills

```sql
CREATE TABLE order_record (
  id              TEXT PRIMARY KEY,               -- uuid (= client_order_id)
  broker_order_id TEXT,                           -- nullable until broker assigns
  broker_connection_id INTEGER NOT NULL REFERENCES broker_connection(id),
  strategy_instance_id TEXT REFERENCES strategy_instance(id),  -- NULL for manual orders
  symbol          TEXT NOT NULL,
  exchange        TEXT NOT NULL,
  side            TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  quantity        INTEGER NOT NULL,
  filled_quantity INTEGER NOT NULL DEFAULT 0,
  order_type      TEXT NOT NULL,
  price           NUMERIC,
  stop_price      NUMERIC,
  status          TEXT NOT NULL,
  avg_fill_price  NUMERIC,
  rejection_reason TEXT,
  tag             TEXT,
  submitted_at    TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE INDEX idx_order_strategy ON order_record(strategy_instance_id);
CREATE INDEX idx_order_status   ON order_record(status);
CREATE INDEX idx_order_symbol_date ON order_record(symbol, submitted_at);

CREATE TABLE fill (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id        TEXT NOT NULL REFERENCES order_record(id),
  broker_fill_id  TEXT,
  symbol          TEXT NOT NULL,
  side            TEXT NOT NULL,
  quantity        INTEGER NOT NULL,
  price           NUMERIC NOT NULL,
  fees            NUMERIC NOT NULL DEFAULT 0,
  ts              TEXT NOT NULL
);

CREATE INDEX idx_fill_order ON fill(order_id);
```

### 2.5 Positions

```sql
CREATE TABLE position (
  -- One row per (strategy_instance_id, symbol). Recomputed from fills + reconciled with broker.
  strategy_instance_id TEXT NOT NULL REFERENCES strategy_instance(id),
  symbol          TEXT NOT NULL,
  quantity        INTEGER NOT NULL,               -- signed: + long, - short
  avg_price       NUMERIC NOT NULL,
  realised_pnl    NUMERIC NOT NULL DEFAULT 0,
  last_price      NUMERIC,
  updated_at      TEXT NOT NULL,
  PRIMARY KEY(strategy_instance_id, symbol)
);
```

### 2.6 Audit log (immutable)

```sql
CREATE TABLE audit_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  actor_type      TEXT NOT NULL CHECK(actor_type IN ('user','system','strategy','broker')),
  actor_id        TEXT,                           -- user_id, strategy_instance_id, etc.
  event_type      TEXT NOT NULL,                  -- e.g. "order.submitted", "kill_switch.fired"
  payload_json    TEXT NOT NULL,
  prev_hash       TEXT,                           -- chains to previous record
  hash            TEXT NOT NULL                   -- sha256(prev_hash + payload)
);

CREATE INDEX idx_audit_ts        ON audit_log(ts);
CREATE INDEX idx_audit_event     ON audit_log(event_type);
CREATE INDEX idx_audit_actor     ON audit_log(actor_type, actor_id);
```

The hash chain is paranoia, but cheap. Detects DB tampering.

### 2.7 Risk state (current day)

```sql
CREATE TABLE daily_risk_state (
  trading_date    TEXT PRIMARY KEY,               -- YYYY-MM-DD
  account_realised_pnl NUMERIC NOT NULL DEFAULT 0,
  account_unrealised_pnl NUMERIC NOT NULL DEFAULT 0,
  total_orders_placed INTEGER NOT NULL DEFAULT 0,
  kill_switch_active BOOLEAN NOT NULL DEFAULT 0,
  kill_switch_at  TEXT,
  notes           TEXT
);

CREATE TABLE daily_strategy_pnl (
  trading_date    TEXT NOT NULL,
  strategy_instance_id TEXT NOT NULL REFERENCES strategy_instance(id),
  realised_pnl    NUMERIC NOT NULL DEFAULT 0,
  unrealised_pnl  NUMERIC NOT NULL DEFAULT 0,
  trade_count     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(trading_date, strategy_instance_id)
);
```

### 2.8 Historical bars

```sql
CREATE TABLE bar (
  symbol          TEXT NOT NULL,
  exchange        TEXT NOT NULL,
  timeframe       TEXT NOT NULL,
  ts              TEXT NOT NULL,                  -- bar open
  open            NUMERIC NOT NULL,
  high            NUMERIC NOT NULL,
  low             NUMERIC NOT NULL,
  close           NUMERIC NOT NULL,
  volume          INTEGER NOT NULL,
  PRIMARY KEY(symbol, timeframe, ts)
);

CREATE INDEX idx_bar_symbol_tf ON bar(symbol, timeframe);
```

For Postgres + Timescale: convert this to a hypertable on `ts`.

### 2.9 Backtest runs

```sql
CREATE TABLE backtest_run (
  id              TEXT PRIMARY KEY,
  strategy_class_id INTEGER NOT NULL REFERENCES strategy_class(id),
  strategy_class_version TEXT NOT NULL,
  params_json     TEXT NOT NULL,
  instruments_json TEXT NOT NULL,
  timeframe       TEXT NOT NULL,
  from_ts         TEXT NOT NULL,
  to_ts           TEXT NOT NULL,
  initial_capital NUMERIC NOT NULL,
  slippage_bps    INTEGER NOT NULL DEFAULT 0,
  fee_config_json TEXT,
  metrics_json    TEXT,                           -- Sharpe, max DD, etc.
  equity_curve_json TEXT,                         -- compressed list
  status          TEXT NOT NULL CHECK(status IN ('queued','running','done','failed')),
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  error           TEXT
);

CREATE TABLE backtest_trade (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id          TEXT NOT NULL REFERENCES backtest_run(id),
  symbol          TEXT NOT NULL,
  side            TEXT NOT NULL,
  quantity        INTEGER NOT NULL,
  entry_ts        TEXT NOT NULL,
  entry_price     NUMERIC NOT NULL,
  exit_ts         TEXT,
  exit_price      NUMERIC,
  pnl             NUMERIC,
  tag             TEXT
);

CREATE INDEX idx_backtest_trade_run ON backtest_trade(run_id);
```

### 2.10 Auth & sessions

```sql
CREATE TABLE app_user (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  username        TEXT UNIQUE NOT NULL,
  password_hash   TEXT NOT NULL,                  -- argon2
  totp_secret     TEXT,                           -- encrypted
  is_active       BOOLEAN NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL,
  last_login_at   TEXT
);

CREATE TABLE session (
  id              TEXT PRIMARY KEY,               -- session token
  user_id         INTEGER NOT NULL REFERENCES app_user(id),
  created_at      TEXT NOT NULL,
  expires_at      TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  ip              TEXT,
  user_agent      TEXT
);
```

### 2.11 Notifications

```sql
CREATE TABLE notification_channel (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  type            TEXT NOT NULL CHECK(type IN ('telegram','email','webhook')),
  config_json     TEXT NOT NULL,                  -- bot token ref, chat id, etc.
  is_active       BOOLEAN NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL
);

CREATE TABLE notification_rule (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id      INTEGER NOT NULL REFERENCES notification_channel(id),
  event_type      TEXT NOT NULL,                  -- e.g. "order.filled", "risk.daily_loss_limit_hit"
  min_severity    TEXT NOT NULL CHECK(min_severity IN ('debug','info','warn','error','critical')),
  is_active       BOOLEAN NOT NULL DEFAULT 1
);
```

## 3. Environment configuration

```ini
# .env  — copied from .env.example, never committed

# --- Application ---
APP_ENV=production              # development | production
APP_PORT=8000
APP_BASE_URL=https://my-bot.example.com

# --- Database ---
DATABASE_URL=sqlite:///./data/algotrader.db
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/algotrader

# --- Auth ---
APP_SECRET_KEY=<long random hex>
SESSION_LIFETIME_HOURS=8
ENCRYPTION_KEY=<fernet key, used to encrypt totp secrets in DB>

# --- Brokers ---
ZERODHA_PRIMARY_API_KEY=xxx
ZERODHA_PRIMARY_API_SECRET=xxx
ZERODHA_PRIMARY_USER_ID=AB1234
ZERODHA_PRIMARY_PASSWORD=xxx
ZERODHA_PRIMARY_TOTP_SECRET=xxx       # for auto-login flow

# Future: UPSTOX_PRIMARY_API_KEY=...

# --- Notifications ---
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_FROM=

# --- Compliance ---
APP_BIND_IP=203.0.113.42       # the static IP this app runs on; warns on mismatch
OPS_LIMIT_PER_SECOND=9         # stay strictly under SEBI's 10/s retail threshold

# --- Risk defaults (used when a strategy doesn't override) ---
DEFAULT_ACCOUNT_DAILY_LOSS_PCT=3
DEFAULT_PER_STRATEGY_DAILY_LOSS_PCT=2
DEFAULT_MAX_OPEN_POSITIONS=10
```

## 4. Migrations

Use Alembic. Initial migration creates all tables above. Subsequent migrations:

- Add columns rather than rename when possible
- Never delete audit-related tables
- Test each migration against a prod-sized seed DB before applying

## 5. Backups

- Nightly dump of full DB → encrypted blob → object storage (B2 / S3 / Wasabi)
- Retain 30 daily, 12 monthly, 5 yearly
- Restore drill: at least once before going live

## 6. SQLite → Postgres path

Plan from day one to be Postgres-compatible. Concrete steps:

1. Use SQLAlchemy types portable across both (`Numeric`, `Text`, `Integer`, `Boolean`, `DateTime`).
2. Avoid SQLite-specific features (`AUTOINCREMENT` is portable; `WITHOUT ROWID` is not — don't use it).
3. JSON columns: use `JSON` type (works in both, with different storage internals).
4. Provide a migration script: SQLite dump → pg_load with type coercion.
5. CI: run the test suite against both SQLite and Postgres weekly.

## 7. Data retention

| Table | Retention |
|---|---|
| `audit_log` | Forever (or ≥ 5 years per SEBI) |
| `order_record`, `fill` | ≥ 5 years |
| `position` | Current state only; history reconstructable from fills |
| `bar` (historical) | Forever (or until storage cost hurts) |
| `daily_risk_state` | ≥ 5 years |
| `session` | Until expiry, then deleted |
| `backtest_run` | Configurable; default keep last 100 per strategy |
