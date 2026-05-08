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
