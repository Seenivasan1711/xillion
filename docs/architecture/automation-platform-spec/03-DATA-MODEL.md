---
doc_id: 03-DATA-MODEL
title: Data Model
audience: backend, data
version: 1.0
---

# 03 — DATA MODEL

Postgres for transactional/state. DuckDB+Parquet for time-series/analytical. Redis for live state.

---

## 3.1 Postgres — core tables

```sql
-- ============ STRATEGY & ARMING ============
CREATE TABLE strategies (
    name              TEXT PRIMARY KEY,
    lane              TEXT NOT NULL CHECK (lane IN ('A','B1','B2')),
    risk_class        TEXT NOT NULL CHECK (risk_class IN ('DEFINED','UNDEFINED')),
    structure_type    TEXT NOT NULL,
    enabled           BOOLEAN NOT NULL DEFAULT false,
    decay_status      TEXT NOT NULL DEFAULT 'HEALTHY'
                      CHECK (decay_status IN ('HEALTHY','WATCH','DEGRADED','DISABLED')),
    config            JSONB NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE strategy_arming (
    id                BIGSERIAL PRIMARY KEY,
    trade_date        DATE NOT NULL,
    strategy          TEXT NOT NULL REFERENCES strategies(name),
    armed             BOOLEAN NOT NULL,
    size_multiplier   NUMERIC(4,2) NOT NULL DEFAULT 1.0,
    reasons           TEXT[] NOT NULL,        -- why armed / why not
    regime_snapshot   JSONB NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (trade_date, strategy)
);

-- ============ SIGNALS & GATES ============
CREATE TABLE signals (
    id                UUID PRIMARY KEY,
    strategy          TEXT NOT NULL REFERENCES strategies(name),
    lane              TEXT NOT NULL,
    generated_at      TIMESTAMPTZ NOT NULL,
    direction         TEXT NOT NULL,
    structure         JSONB NOT NULL,          -- leg definitions
    confidence        NUMERIC(4,3),
    reason            TEXT NOT NULL,           -- MANDATORY human-readable
    market_snapshot   JSONB NOT NULL
);

-- Every gate evaluation. This table answers "why didn't it trade?"
CREATE TABLE gate_evaluations (
    id                BIGSERIAL PRIMARY KEY,
    signal_id         UUID NOT NULL REFERENCES signals(id),
    evaluated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    passed            BOOLEAN NOT NULL,
    failed_gates      TEXT[],
    all_gate_results  JSONB NOT NULL
);
CREATE INDEX ON gate_evaluations (evaluated_at, passed);

-- ============ ORDERS & FILLS ============
CREATE TABLE orders (
    id                UUID PRIMARY KEY,
    idempotency_key   TEXT UNIQUE NOT NULL,    -- prevents duplicate submission
    signal_id         UUID REFERENCES signals(id),
    position_id       UUID,
    broker            TEXT NOT NULL,
    broker_order_id   TEXT,
    lane              TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    leg_index         INT NOT NULL DEFAULT 0,
    order_type        TEXT NOT NULL,
    product           TEXT NOT NULL,
    qty               INT NOT NULL,
    price             NUMERIC(12,2),
    trigger_price     NUMERIC(12,2),
    purpose           TEXT NOT NULL            -- ENTRY | EXIT | STOP | TARGET | ADJUST
                      CHECK (purpose IN ('ENTRY','EXIT','STOP','TARGET','ADJUST')),
    status            TEXT NOT NULL,
    filled_qty        INT NOT NULL DEFAULT 0,
    avg_fill_price    NUMERIC(12,2),
    rejection_reason  TEXT,
    submitted_at      TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON orders (position_id);
CREATE INDEX ON orders (broker_order_id);

CREATE TABLE fills (
    id                BIGSERIAL PRIMARY KEY,
    order_id          UUID NOT NULL REFERENCES orders(id),
    broker_trade_id   TEXT,
    qty               INT NOT NULL,
    price             NUMERIC(12,2) NOT NULL,
    filled_at         TIMESTAMPTZ NOT NULL,
    intended_price    NUMERIC(12,2),
    slippage          NUMERIC(12,2) GENERATED ALWAYS AS (price - intended_price) STORED
);

-- ============ POSITIONS ============
CREATE TABLE positions (
    id                UUID PRIMARY KEY,
    signal_id         UUID REFERENCES signals(id),
    strategy          TEXT NOT NULL REFERENCES strategies(name),
    lane              TEXT NOT NULL,
    structure_type    TEXT NOT NULL,
    risk_class        TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('OPENING','OPEN','CLOSING','CLOSED','FAILED')),
    legs              JSONB NOT NULL,
    lots              INT NOT NULL,
    lot_size          INT NOT NULL,            -- snapshot; lot sizes change (01 §1.5)
    entry_time        TIMESTAMPTZ,
    entry_value       NUMERIC(14,2),
    entry_cost        NUMERIC(12,2),
    exit_time         TIMESTAMPTZ,
    exit_value        NUMERIC(14,2),
    exit_cost         NUMERIC(12,2),
    exit_reason       TEXT,
    max_loss_planned  NUMERIC(12,2) NOT NULL,
    max_loss_actual   NUMERIC(12,2),
    max_profit        NUMERIC(12,2),
    initial_risk      NUMERIC(12,2) NOT NULL,
    initial_stop      NUMERIC(12,2),
    current_stop      NUMERIC(12,2),
    realised_pnl      NUMERIC(14,2),
    mae               NUMERIC(14,2),           -- max adverse excursion
    mfe               NUMERIC(14,2),           -- max favourable excursion
    context           JSONB,                   -- VIX, regime, stage, gap at entry
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON positions (status) WHERE status IN ('OPENING','OPEN','CLOSING');
CREATE INDEX ON positions (strategy, entry_time);

-- Every stop movement — feeds R03 parameter analysis
CREATE TABLE stop_history (
    id                BIGSERIAL PRIMARY KEY,
    position_id       UUID NOT NULL REFERENCES positions(id),
    changed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_stop          NUMERIC(12,2),
    new_stop          NUMERIC(12,2) NOT NULL,
    algorithm         TEXT NOT NULL,           -- fixed | chandelier | r_ladder | ...
    trigger_reason    TEXT NOT NULL,
    underlying_price  NUMERIC(12,2),
    r_multiple        NUMERIC(6,3)
);

-- ============ RISK & COMPLIANCE ============
CREATE TABLE risk_decisions (
    id                BIGSERIAL PRIMARY KEY,
    order_id          UUID,
    decided_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved          BOOLEAN NOT NULL,
    failed_checks     TEXT[],
    context           JSONB NOT NULL
);

CREATE TABLE kill_switch_events (
    id                BIGSERIAL PRIMARY KEY,
    activated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            TEXT NOT NULL,           -- TELEGRAM | CIRCUIT_BREAKER | WATCHDOG | API | FILE
    reason            TEXT NOT NULL,
    flatten_requested BOOLEAN NOT NULL,
    state_snapshot    JSONB NOT NULL,
    rearmed_at        TIMESTAMPTZ,
    rearmed_by        TEXT
);

-- Append-only, 5-year retention (SEBI, 01 §1.1)
CREATE TABLE audit_log (
    id                BIGSERIAL PRIMARY KEY,
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor             TEXT NOT NULL,           -- job id, 'human', 'watchdog'
    action            TEXT NOT NULL,
    entity_type       TEXT,
    entity_id         TEXT,
    payload           JSONB NOT NULL
);
CREATE INDEX ON audit_log (occurred_at);
CREATE INDEX ON audit_log (entity_type, entity_id);

-- ============ REPORTING ============
CREATE TABLE reconciliation_reports (
    id                BIGSERIAL PRIMARY KEY,
    trade_date        DATE NOT NULL,
    lane              TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('CLEAN','DISCREPANCY','FAILED')),
    discrepancies     JSONB,
    broker_pnl        NUMERIC(14,2),
    internal_pnl      NUMERIC(14,2),
    signed_off_by     TEXT,
    signed_off_at     TIMESTAMPTZ,
    UNIQUE (trade_date, lane)
);

CREATE TABLE strategy_metrics (
    id                BIGSERIAL PRIMARY KEY,
    strategy          TEXT NOT NULL REFERENCES strategies(name),
    as_of             DATE NOT NULL,
    window_size       INT NOT NULL,            -- 20 | 50 | 100 | 0 for all-time
    trades            INT NOT NULL,
    win_rate          NUMERIC(5,4),
    avg_win           NUMERIC(12,2),
    avg_loss          NUMERIC(12,2),
    expectancy        NUMERIC(12,2),
    profit_factor     NUMERIC(8,4),
    break_even_wr     NUMERIC(5,4),            -- stop/(stop+target)
    wr_margin         NUMERIC(6,4),            -- ⭐ actual - required
    max_drawdown      NUMERIC(12,2),
    avg_r             NUMERIC(6,3),
    UNIQUE (strategy, as_of, window_size)
);

CREATE TABLE regime_log (
    trade_date        DATE PRIMARY KEY,
    vix_open          NUMERIC(6,2), vix_high NUMERIC(6,2),
    vix_low           NUMERIC(6,2), vix_close NUMERIC(6,2),
    vix_percentile    NUMERIC(5,2),
    iv_rank           NUMERIC(5,2),
    realised_vol      NUMERIC(6,2),
    iv_rv_spread      NUMERIC(6,2),
    vrp_estimate      NUMERIC(6,3),
    regime_band       TEXT,
    trend_state       TEXT,
    adx               NUMERIC(5,2),
    gap_pct           NUMERIC(6,3),
    expected_move     NUMERIC(8,2),
    realised_move     NUMERIC(8,2),
    cycle_stage       TEXT,
    events            JSONB
);

CREATE TABLE event_blackouts (
    id                BIGSERIAL PRIMARY KEY,
    lane              TEXT NOT NULL,
    event_name        TEXT NOT NULL,
    event_time        TIMESTAMPTZ NOT NULL,
    impact            TEXT NOT NULL CHECK (impact IN ('HIGH','MEDIUM','LOW')),
    blackout_start    TIMESTAMPTZ NOT NULL,
    blackout_end      TIMESTAMPTZ NOT NULL
);
```

---

## 3.2 DuckDB / Parquet — analytical store

```sql
-- Partitioned: data/chains/date=YYYY-MM-DD/underlying=NIFTY/*.parquet
CREATE TABLE option_chain_snapshots (
    ts               TIMESTAMP,
    underlying       VARCHAR,
    spot             DOUBLE,
    expiry           DATE,
    strike           INTEGER,
    option_type      VARCHAR,     -- CE | PE
    ltp              DOUBLE,
    bid              DOUBLE,
    ask              DOUBLE,
    bid_qty          INTEGER,
    ask_qty          INTEGER,
    volume           BIGINT,
    oi               BIGINT,
    oi_change        BIGINT,
    iv               DOUBLE,
    delta            DOUBLE, gamma DOUBLE, theta DOUBLE, vega DOUBLE
);

CREATE TABLE candles (
    ts               TIMESTAMP, symbol VARCHAR, timeframe VARCHAR,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume BIGINT, oi BIGINT
);

CREATE TABLE vix_history (ts TIMESTAMP, value DOUBLE);

CREATE TABLE derived_metrics (
    ts               TIMESTAMP, underlying VARCHAR,
    atm_strike       INTEGER,
    atm_straddle     DOUBLE,        -- market's expected move
    pcr_oi           DOUBLE,
    max_pain         INTEGER,
    iv_rank          DOUBLE,
    total_call_oi    BIGINT, total_put_oi BIGINT
);

CREATE TABLE equity_curve (ts TIMESTAMP, lane VARCHAR,
    balance DOUBLE, equity DOUBLE, peak_equity DOUBLE, drawdown_pct DOUBLE);
```

**Storage:** full Nifty chain at 1-min ≈ 2–5 MB/day compressed → **under 2 GB/year.** Never delete it.

---

## 3.3 Redis — live state

```
kill_switch:active              -> "1" | absent
trading_enabled                 -> "1" | "0"
health:{component}              -> JSON
position:{id}                   -> JSON (live P&L, stop, MAE/MFE)
positions:open                  -> SET of position ids
ops:{broker}                    -> ZSET (sliding-window OPS counter)
lock:{resource}                 -> distributed lock
heartbeat:{service}             -> unix ts
day:pnl                         -> current day net P&L
day:trades                      -> count
day:consecutive_losses          -> count
quote:{symbol}                  -> latest tick (short TTL)
```

---

## 3.4 Event contracts (internal pub/sub)

```python
@dataclass(frozen=True)
class SignalGenerated:   signal_id: UUID; strategy: str; lane: str; ts: datetime
@dataclass(frozen=True)
class GatePassed:        signal_id: UUID; ts: datetime
@dataclass(frozen=True)
class GateFailed:        signal_id: UUID; failed: list[str]; ts: datetime
@dataclass(frozen=True)
class OrderSubmitted:    order_id: UUID; broker_order_id: str; ts: datetime
@dataclass(frozen=True)
class OrderFilled:       order_id: UUID; qty: int; price: Decimal; ts: datetime
@dataclass(frozen=True)
class PositionOpened:    position_id: UUID; ts: datetime
@dataclass(frozen=True)
class StopMoved:         position_id: UUID; old: Decimal; new: Decimal; algo: str
@dataclass(frozen=True)
class PositionClosed:    position_id: UUID; pnl: Decimal; reason: str; ts: datetime
@dataclass(frozen=True)
class CircuitBreakerTripped: breaker: str; action: str; ts: datetime
@dataclass(frozen=True)
class KillSwitchActivated:   source: str; reason: str; ts: datetime
```

---

## 3.5 Retention

| Data | Retention | Rationale |
|---|---|---|
| `audit_log` | **5 years** | SEBI requirement |
| `orders`, `fills`, `positions` | 5 years | Compliance + analysis |
| Option chain snapshots | **Forever** | Irreplaceable research asset |
| Tick data | 1 yr raw → 1-min forever | Storage vs value |
| Redis live state | Ephemeral | Rebuilt from Postgres on restart |
| Backups | 90 days rolling + monthly forever | Recovery |
