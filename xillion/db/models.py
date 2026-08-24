"""
SQLAlchemy 2.0 ORM models — matches the schema in docs/05-data-model.md.
Uses portable types (Numeric, Text, Integer, Boolean) for SQLite/Postgres compat.
"""
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Plugin registry ────────────────────────────────────────────────────────────

class StrategyClass(Base):
    __tablename__ = "strategy_class"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    module_path: Mapped[str] = mapped_column(Text, nullable=False)
    class_name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    default_timeframe: Mapped[str | None] = mapped_column(Text)
    params_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False)

    instances: Mapped[list["StrategyInstance"]] = relationship(back_populates="strategy_class")
    backtest_runs: Mapped[list["BacktestRun"]] = relationship(back_populates="strategy_class")


class BrokerClass(Base):
    __tablename__ = "broker_class"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    module_path: Mapped[str] = mapped_column(Text, nullable=False)
    class_name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False)

    connections: Mapped[list["BrokerConnection"]] = relationship(back_populates="broker_class")


class DataProviderClass(Base):
    """Discovered historical-data-provider plugins from data_providers/ --
    same drop-a-file discovery pattern as StrategyClass/BrokerClass."""
    __tablename__ = "data_provider_class"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    module_path: Mapped[str] = mapped_column(Text, nullable=False)
    class_name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False)


class DataProviderCredential(Base):
    """Encrypted API credentials for a data provider that needs its own key
    (e.g. TrueData, DhanHQ). Providers that piggyback on a connected broker
    (e.g. Kite) or need no auth (e.g. free NSE bhavcopy) have no row here."""
    __tablename__ = "data_provider_credential"

    name: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "TrueData Primary"
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "TrueData"
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


# ── Broker connections ─────────────────────────────────────────────────────────

class BrokerConnection(Base):
    __tablename__ = "broker_connection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_class_id: Mapped[int] = mapped_column(ForeignKey("broker_class.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    credentials_ref: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_connected_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    broker_class: Mapped[BrokerClass] = relationship(back_populates="connections")
    instances: Mapped[list["StrategyInstance"]] = relationship(back_populates="broker_connection")
    orders: Mapped[list["OrderRecord"]] = relationship(back_populates="broker_connection")


# ── Strategy instances ─────────────────────────────────────────────────────────

class StrategyInstance(Base):
    __tablename__ = "strategy_instance"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # UUID
    strategy_class_id: Mapped[int] = mapped_column(ForeignKey("strategy_class.id"), nullable=False)
    strategy_class_version: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)   # backtest | paper | live
    status: Mapped[str] = mapped_column(Text, nullable=False) # idle|running|paused|error|killed
    broker_connection_id: Mapped[int] = mapped_column(ForeignKey("broker_connection.id"), nullable=False)
    instruments_json: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    capital_allocation: Mapped[float] = mapped_column(Numeric, nullable=False)
    risk_limits_json: Mapped[str] = mapped_column(Text, nullable=False)
    state_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_started_at: Mapped[str | None] = mapped_column(Text)
    last_stopped_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    strategy_class: Mapped[StrategyClass] = relationship(back_populates="instances")
    broker_connection: Mapped[BrokerConnection] = relationship(back_populates="instances")
    orders: Mapped[list["OrderRecord"]] = relationship(back_populates="strategy_instance")
    positions: Mapped[list["PositionRecord"]] = relationship(back_populates="strategy_instance")
    signal_logs: Mapped[list["SignalLog"]] = relationship(back_populates="strategy_instance")

    __table_args__ = (
        Index("idx_strategy_instance_status", "status"),
        Index("idx_strategy_instance_mode", "mode"),
    )


# ── Orders & fills ─────────────────────────────────────────────────────────────

class OrderRecord(Base):
    __tablename__ = "order_record"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # UUID = client_order_id
    broker_order_id: Mapped[str | None] = mapped_column(Text)
    broker_connection_id: Mapped[int] = mapped_column(ForeignKey("broker_connection.id"), nullable=False)
    strategy_instance_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_instance.id"))
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)      # BUY | SELL
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric)
    stop_price: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    avg_fill_price: Mapped[float | None] = mapped_column(Numeric)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    tag: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    broker_connection: Mapped[BrokerConnection] = relationship(back_populates="orders")
    strategy_instance: Mapped[StrategyInstance | None] = relationship(back_populates="orders")
    fills: Mapped[list["FillRecord"]] = relationship(back_populates="order")

    __table_args__ = (
        Index("idx_order_strategy", "strategy_instance_id"),
        Index("idx_order_status", "status"),
        Index("idx_order_symbol_date", "symbol", "submitted_at"),
    )


class FillRecord(Base):
    __tablename__ = "fill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("order_record.id"), nullable=False)
    broker_fill_id: Mapped[str | None] = mapped_column(Text)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric, nullable=False)
    fees: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    ts: Mapped[str] = mapped_column(Text, nullable=False)

    order: Mapped[OrderRecord] = relationship(back_populates="fills")

    __table_args__ = (Index("idx_fill_order", "order_id"),)


# ── Positions ──────────────────────────────────────────────────────────────────

class PositionRecord(Base):
    __tablename__ = "position"

    strategy_instance_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_instance.id"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    realised_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    last_price: Mapped[float | None] = mapped_column(Numeric)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    strategy_instance: Mapped[StrategyInstance] = relationship(back_populates="positions")


# ── Audit log (append-only) ────────────────────────────────────────────────────

class AuditLogRecord(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)  # user|system|strategy|broker
    actor_id: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_audit_ts", "ts"),
        Index("idx_audit_event", "event_type"),
        Index("idx_audit_actor", "actor_type", "actor_id"),
    )


# ── Daily risk state ───────────────────────────────────────────────────────────

class DailyRiskState(Base):
    __tablename__ = "daily_risk_state"

    trading_date: Mapped[str] = mapped_column(Text, primary_key=True)  # YYYY-MM-DD
    account_realised_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    account_unrealised_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    total_orders_placed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kill_switch_at: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class DailyStrategyPnl(Base):
    __tablename__ = "daily_strategy_pnl"

    trading_date: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_instance_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_instance.id"), primary_key=True
    )
    realised_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    unrealised_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ── Historical bars ────────────────────────────────────────────────────────────

class BarRecord(Base):
    __tablename__ = "bar"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    timeframe: Mapped[str] = mapped_column(Text, primary_key=True)
    ts: Mapped[str] = mapped_column(Text, primary_key=True)  # bar open ISO datetime
    open: Mapped[float] = mapped_column(Numeric, nullable=False)
    high: Mapped[float] = mapped_column(Numeric, nullable=False)
    low: Mapped[float] = mapped_column(Numeric, nullable=False)
    close: Mapped[float] = mapped_column(Numeric, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("idx_bar_symbol_tf", "symbol", "timeframe"),)


class BarCoverage(Base):
    """Tracks which contiguous date range is already fetched for a
    (symbol, exchange, timeframe, provider) combination, so BarWarehouse can
    fetch only the gap instead of re-requesting a range it already has --
    including holidays inside that range, which never produce a bar but are
    still "covered" once the range containing them has been fetched once.

    `symbol="*"` is a wildcard row used by whole-file-bulk providers (e.g.
    NSE bhavcopy): one fetch persists every instrument's bar for that day, so
    coverage is tracked per exchange/day rather than per symbol."""
    __tablename__ = "bar_coverage"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    timeframe: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_name: Mapped[str] = mapped_column(Text, primary_key=True)
    from_date: Mapped[str] = mapped_column(Text, nullable=False)  # ISO date
    to_date: Mapped[str] = mapped_column(Text, nullable=False)  # ISO date
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class MarketHoliday(Base):
    """Known non-trading days per exchange, so a backfill or paper-session
    scheduler can skip them without hitting the provider to find out."""
    __tablename__ = "market_holiday"

    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    holiday_date: Mapped[str] = mapped_column(Text, primary_key=True)  # ISO date
    description: Mapped[str | None] = mapped_column(Text)


# ── Journal (CP6) ──────────────────────────────────────────────────────────────

class JournalNote(Base):
    """Manual annotation on a journal entry -- the failure-mode taxonomy
    entries auto-classification (xillion/engine/journal.py) has no real
    evidence for (late_entry, slippage, no_fill, gap, regime_change,
    data_gap, system_error), plus the free-text "what did you change"
    narrative the docs/strategies/<name>.md failure log wants. Keyed by
    the same (source, source_id) journal.py uses, not a hard FK, since
    "source" spans two different tables (signal_log, backtest_trade)."""
    __tablename__ = "journal_note"

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    failure_mode: Mapped[str | None] = mapped_column(Text)
    change_made: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class StrategyVersionHistory(Base):
    """Append-only log of every (version, code_hash) a strategy class has
    ever had. strategy_class itself is upserted in place on every plugin
    sync (see plugin_sync.py), which would otherwise silently lose this."""
    __tablename__ = "strategy_version_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_class_id: Mapped[int] = mapped_column(ForeignKey("strategy_class.id"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_strategy_version_history_class", "strategy_class_id"),)


# ── Backtest runs ──────────────────────────────────────────────────────────────

class BacktestRun(Base):
    __tablename__ = "backtest_run"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # UUID
    strategy_class_id: Mapped[int] = mapped_column(ForeignKey("strategy_class.id"), nullable=False)
    strategy_class_version: Mapped[str] = mapped_column(Text, nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    instruments_json: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    from_ts: Mapped[str] = mapped_column(Text, nullable=False)
    to_ts: Mapped[str] = mapped_column(Text, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Numeric, nullable=False)
    slippage_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fee_config_json: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[str | None] = mapped_column(Text)
    equity_curve_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # queued|running|done|failed
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    strategy_class: Mapped[StrategyClass] = relationship(back_populates="backtest_runs")
    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="run")


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_run.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_ts: Mapped[str] = mapped_column(Text, nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    exit_ts: Mapped[str | None] = mapped_column(Text)
    exit_price: Mapped[float | None] = mapped_column(Numeric)
    pnl: Mapped[float | None] = mapped_column(Numeric)
    tag: Mapped[str | None] = mapped_column(Text)

    run: Mapped[BacktestRun] = relationship(back_populates="trades")

    __table_args__ = (Index("idx_backtest_trade_run", "run_id"),)


# ── Auth & sessions ────────────────────────────────────────────────────────────

class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(Text)  # encrypted
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_login_at: Mapped[str | None] = mapped_column(Text)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # session token
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)

    user: Mapped[AppUser] = relationship(back_populates="sessions")


# ── Broker credentials (encrypted) ────────────────────────────────────────────


class BrokerCredential(Base):
    __tablename__ = "broker_credential"

    name: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "Zerodha Primary"
    broker_name: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "Zerodha"
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted JSON
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


# ── Instrument master (options resolution) ────────────────────────────────────

class Instrument(Base):
    """Cached row from Kite's instrument dump. Refreshed daily. Nullable
    strike/option_type/expiry so non-derivative rows (indices, equities,
    futures, and any future asset class such as forex) fit the same table."""
    __tablename__ = "instrument"

    instrument_token: Mapped[int] = mapped_column(Integer, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    tradingsymbol: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)  # underlying, e.g. "NIFTY"
    expiry: Mapped[str | None] = mapped_column(Text)  # ISO date
    strike: Mapped[float | None] = mapped_column(Numeric)
    option_type: Mapped[str | None] = mapped_column(Text)  # CE | PE
    segment: Mapped[str] = mapped_column(Text, nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_size: Mapped[float] = mapped_column(Numeric, nullable=False)
    last_updated: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_instrument_resolve", "name", "expiry", "option_type", "strike"),
        Index("idx_instrument_symbol", "tradingsymbol", "exchange"),
    )


# ── Signal log (alert mode) ────────────────────────────────────────────────────

class SignalLog(Base):
    """Every signal emitted by an alert-mode strategy instance. No fill/price
    execution data — this is the forward-test dataset the build spec calls for.

    `signal_type` is the lifecycle stage (ENTER | EXIT | SIGNAL for a
    one-shot alert with no exit leg); `tag` is the setup identifier a
    strategy uses to pair an EXIT back to the ENTER it closes, via
    `parent_signal_id` (CP4 -- before this, `signal_type` held the tag
    string and there was no ENTER/EXIT distinction or linkage at all)."""
    __tablename__ = "signal_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_instance_id: Mapped[str] = mapped_column(ForeignKey("strategy_instance.id"), nullable=False)
    ts: Mapped[str] = mapped_column(Text, nullable=False)
    underlying_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_tradingsymbol: Mapped[str | None] = mapped_column(Text)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)  # ENTER | EXIT | SIGNAL
    tag: Mapped[str | None] = mapped_column(Text)  # setup identifier, pairs ENTER <-> EXIT
    parent_signal_id: Mapped[int | None] = mapped_column(ForeignKey("signal_log.id"))
    target_price: Mapped[float | None] = mapped_column(Numeric)
    stop_loss_price: Mapped[float | None] = mapped_column(Numeric)
    side: Mapped[str | None] = mapped_column(Text)  # BUY | SELL
    price: Mapped[float | None] = mapped_column(Numeric)
    message: Mapped[str] = mapped_column(Text, nullable=False)  # the "reason" text
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notified_at: Mapped[str | None] = mapped_column(Text)
    context_json: Mapped[str | None] = mapped_column(Text)

    strategy_instance: Mapped[StrategyInstance] = relationship(back_populates="signal_logs")

    __table_args__ = (
        Index("idx_signal_log_instance_ts", "strategy_instance_id", "ts"),
        Index("idx_signal_log_underlying_ts", "underlying_symbol", "ts"),
        Index("idx_signal_log_open_entry", "strategy_instance_id", "underlying_symbol", "tag", "signal_type"),
    )


# ── Notifications ──────────────────────────────────────────────────────────────

class NotificationChannel(Base):
    __tablename__ = "notification_channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # telegram|email|webhook
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    rules: Mapped[list["NotificationRule"]] = relationship(back_populates="channel")


class NotificationRule(Base):
    __tablename__ = "notification_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("notification_channel.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    min_severity: Mapped[str] = mapped_column(Text, nullable=False)  # debug|info|warn|error|critical
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    channel: Mapped[NotificationChannel] = relationship(back_populates="rules")
