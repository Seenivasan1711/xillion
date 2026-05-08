"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_class",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, unique=True, nullable=False),
        sa.Column("module_path", sa.Text, nullable=False),
        sa.Column("class_name", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("author", sa.Text),
        sa.Column("default_timeframe", sa.Text),
        sa.Column("params_schema_json", sa.Text, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("discovered_at", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.Text, nullable=False),
    )
    op.create_table(
        "broker_class",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, unique=True, nullable=False),
        sa.Column("module_path", sa.Text, nullable=False),
        sa.Column("class_name", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("capabilities_json", sa.Text, nullable=False),
        sa.Column("discovered_at", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.Text, nullable=False),
    )
    op.create_table(
        "broker_connection",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("broker_class_id", sa.Integer, sa.ForeignKey("broker_class.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("credentials_ref", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_connected_at", sa.Text),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("broker_class_id", "name"),
    )
    op.create_table(
        "strategy_instance",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("strategy_class_id", sa.Integer, sa.ForeignKey("strategy_class.id"), nullable=False),
        sa.Column("strategy_class_version", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("broker_connection_id", sa.Integer, sa.ForeignKey("broker_connection.id"), nullable=False),
        sa.Column("instruments_json", sa.Text, nullable=False),
        sa.Column("timeframe", sa.Text, nullable=False),
        sa.Column("params_json", sa.Text, nullable=False),
        sa.Column("capital_allocation", sa.Numeric, nullable=False),
        sa.Column("risk_limits_json", sa.Text, nullable=False),
        sa.Column("state_blob", sa.LargeBinary),
        sa.Column("last_started_at", sa.Text),
        sa.Column("last_stopped_at", sa.Text),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("idx_strategy_instance_status", "strategy_instance", ["status"])
    op.create_index("idx_strategy_instance_mode", "strategy_instance", ["mode"])

    op.create_table(
        "order_record",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("broker_order_id", sa.Text),
        sa.Column("broker_connection_id", sa.Integer, sa.ForeignKey("broker_connection.id"), nullable=False),
        sa.Column("strategy_instance_id", sa.Text, sa.ForeignKey("strategy_instance.id")),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("exchange", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("filled_quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("order_type", sa.Text, nullable=False),
        sa.Column("price", sa.Numeric),
        sa.Column("stop_price", sa.Numeric),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("avg_fill_price", sa.Numeric),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("tag", sa.Text),
        sa.Column("submitted_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("idx_order_strategy", "order_record", ["strategy_instance_id"])
    op.create_index("idx_order_status", "order_record", ["status"])
    op.create_index("idx_order_symbol_date", "order_record", ["symbol", "submitted_at"])

    op.create_table(
        "fill",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text, sa.ForeignKey("order_record.id"), nullable=False),
        sa.Column("broker_fill_id", sa.Text),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("price", sa.Numeric, nullable=False),
        sa.Column("fees", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("ts", sa.Text, nullable=False),
    )
    op.create_index("idx_fill_order", "fill", ["order_id"])

    op.create_table(
        "position",
        sa.Column("strategy_instance_id", sa.Text, sa.ForeignKey("strategy_instance.id"), primary_key=True),
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("avg_price", sa.Numeric, nullable=False),
        sa.Column("realised_pnl", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("last_price", sa.Numeric),
        sa.Column("updated_at", sa.Text, nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text, nullable=False),
        sa.Column("actor_type", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("prev_hash", sa.Text),
        sa.Column("hash", sa.Text, nullable=False),
    )
    op.create_index("idx_audit_ts", "audit_log", ["ts"])
    op.create_index("idx_audit_event", "audit_log", ["event_type"])
    op.create_index("idx_audit_actor", "audit_log", ["actor_type", "actor_id"])

    op.create_table(
        "daily_risk_state",
        sa.Column("trading_date", sa.Text, primary_key=True),
        sa.Column("account_realised_pnl", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("account_unrealised_pnl", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("total_orders_placed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kill_switch_active", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("kill_switch_at", sa.Text),
        sa.Column("notes", sa.Text),
    )
    op.create_table(
        "daily_strategy_pnl",
        sa.Column("trading_date", sa.Text, primary_key=True),
        sa.Column("strategy_instance_id", sa.Text, sa.ForeignKey("strategy_instance.id"), primary_key=True),
        sa.Column("realised_pnl", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("unrealised_pnl", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("trade_count", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "bar",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("exchange", sa.Text, primary_key=True),
        sa.Column("timeframe", sa.Text, primary_key=True),
        sa.Column("ts", sa.Text, primary_key=True),
        sa.Column("open", sa.Numeric, nullable=False),
        sa.Column("high", sa.Numeric, nullable=False),
        sa.Column("low", sa.Numeric, nullable=False),
        sa.Column("close", sa.Numeric, nullable=False),
        sa.Column("volume", sa.Integer, nullable=False),
    )
    op.create_index("idx_bar_symbol_tf", "bar", ["symbol", "timeframe"])

    op.create_table(
        "backtest_run",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("strategy_class_id", sa.Integer, sa.ForeignKey("strategy_class.id"), nullable=False),
        sa.Column("strategy_class_version", sa.Text, nullable=False),
        sa.Column("params_json", sa.Text, nullable=False),
        sa.Column("instruments_json", sa.Text, nullable=False),
        sa.Column("timeframe", sa.Text, nullable=False),
        sa.Column("from_ts", sa.Text, nullable=False),
        sa.Column("to_ts", sa.Text, nullable=False),
        sa.Column("initial_capital", sa.Numeric, nullable=False),
        sa.Column("slippage_bps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fee_config_json", sa.Text),
        sa.Column("metrics_json", sa.Text),
        sa.Column("equity_curve_json", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("finished_at", sa.Text),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "backtest_trade",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, sa.ForeignKey("backtest_run.id"), nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("entry_ts", sa.Text, nullable=False),
        sa.Column("entry_price", sa.Numeric, nullable=False),
        sa.Column("exit_ts", sa.Text),
        sa.Column("exit_price", sa.Numeric),
        sa.Column("pnl", sa.Numeric),
        sa.Column("tag", sa.Text),
    )
    op.create_index("idx_backtest_trade_run", "backtest_trade", ["run_id"])

    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("totp_secret", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("last_login_at", sa.Text),
    )
    op.create_table(
        "session",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("expires_at", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.Text, nullable=False),
        sa.Column("ip", sa.Text),
        sa.Column("user_agent", sa.Text),
    )

    op.create_table(
        "notification_channel",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("config_json", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_table(
        "notification_rule",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("channel_id", sa.Integer, sa.ForeignKey("notification_channel.id"), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("min_severity", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    for table in [
        "notification_rule", "notification_channel",
        "session", "app_user",
        "backtest_trade", "backtest_run",
        "bar", "daily_strategy_pnl", "daily_risk_state",
        "audit_log", "position", "fill", "order_record",
        "strategy_instance", "broker_connection",
        "broker_class", "strategy_class",
    ]:
        op.drop_table(table)
