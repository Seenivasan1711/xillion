"""option_chain_snapshot

Revision ID: 011
Revises: 010
Create Date: 2026-08-25 00:00:00.000000

Backtest-mode options resolution (Options Stage 2, CP11 follow-up):
BacktestEngine's context had no way to answer get_spot/resolve_strike/
get_option_price -- the live `instrument` table is a truncate-and-reload
cache of TODAY's listing only, useless for "what did NIFTY's chain look
like on 2026-03-06". This table is a date-scoped snapshot instead, built
from NSE bhavcopy's own per-contract columns (including UndrlygPric, the
exchange's own recorded underlying close -- used as the backtest spot
proxy) rather than parsing strike/expiry out of tradingsymbol strings.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "option_chain_snapshot",
        sa.Column("trade_date", sa.Text, primary_key=True),
        sa.Column("exchange", sa.Text, primary_key=True),
        sa.Column("tradingsymbol", sa.Text, primary_key=True),
        sa.Column("underlying", sa.Text, nullable=False),
        sa.Column("expiry", sa.Text),
        sa.Column("strike", sa.Numeric),
        sa.Column("option_type", sa.Text),
        sa.Column("lot_size", sa.Integer, nullable=False),
        sa.Column("close", sa.Numeric, nullable=False),
        sa.Column("underlying_price", sa.Numeric),
    )
    op.create_index(
        "idx_option_chain_lookup", "option_chain_snapshot",
        ["underlying", "exchange", "trade_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_option_chain_lookup", table_name="option_chain_snapshot")
    op.drop_table("option_chain_snapshot")
