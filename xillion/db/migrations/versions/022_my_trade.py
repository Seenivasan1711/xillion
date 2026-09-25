"""my_trade

Revision ID: 022
Revises: 021
Create Date: 2026-09-26 00:00:00.000000

"My Trades": Rakesh's own trades, imported from an MT5 History report or
entered by hand, tagged by setup -- to measure whether his discretionary
setups have an edge from real fills. See MyTrade in xillion/db/models.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "my_trade",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("account", sa.Text, nullable=False, server_default="fundingpips"),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("volume_lots", sa.Numeric, nullable=False),
        sa.Column("open_time", sa.Text, nullable=False),
        sa.Column("open_price", sa.Numeric, nullable=False),
        sa.Column("close_time", sa.Text),
        sa.Column("close_price", sa.Numeric),
        sa.Column("stop_loss", sa.Numeric),
        sa.Column("take_profit", sa.Numeric),
        sa.Column("commission", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("swap", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("profit", sa.Numeric),
        sa.Column("setup_tag", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("followed_plan", sa.Boolean),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text),
        sa.UniqueConstraint("account", "external_id", name="uq_my_trade_account_ticket"),
    )
    op.create_index("idx_my_trade_open_time", "my_trade", ["open_time"])
    op.create_index("idx_my_trade_setup", "my_trade", ["setup_tag"])


def downgrade() -> None:
    op.drop_index("idx_my_trade_setup", table_name="my_trade")
    op.drop_index("idx_my_trade_open_time", table_name="my_trade")
    op.drop_table("my_trade")
