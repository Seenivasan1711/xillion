"""instrument master + signal log (options alert mode)

Revision ID: 002
Revises: 001
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument",
        sa.Column("instrument_token", sa.Integer, primary_key=True),
        sa.Column("exchange", sa.Text, nullable=False),
        sa.Column("tradingsymbol", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("expiry", sa.Text),
        sa.Column("strike", sa.Numeric),
        sa.Column("option_type", sa.Text),
        sa.Column("segment", sa.Text, nullable=False),
        sa.Column("lot_size", sa.Integer, nullable=False),
        sa.Column("tick_size", sa.Numeric, nullable=False),
        sa.Column("last_updated", sa.Text, nullable=False),
    )
    op.create_index("idx_instrument_resolve", "instrument", ["name", "expiry", "option_type", "strike"])
    op.create_index("idx_instrument_symbol", "instrument", ["tradingsymbol", "exchange"])

    op.create_table(
        "signal_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("strategy_instance_id", sa.Text, sa.ForeignKey("strategy_instance.id"), nullable=False),
        sa.Column("ts", sa.Text, nullable=False),
        sa.Column("underlying_symbol", sa.Text, nullable=False),
        sa.Column("resolved_tradingsymbol", sa.Text),
        sa.Column("signal_type", sa.Text, nullable=False),
        sa.Column("side", sa.Text),
        sa.Column("price", sa.Numeric),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("notified", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("notified_at", sa.Text),
        sa.Column("context_json", sa.Text),
    )
    op.create_index("idx_signal_log_instance_ts", "signal_log", ["strategy_instance_id", "ts"])
    op.create_index("idx_signal_log_underlying_ts", "signal_log", ["underlying_symbol", "ts"])


def downgrade() -> None:
    for table in ["signal_log", "instrument"]:
        op.drop_table(table)
