"""mt5_historical_request

Revision ID: 019
Revises: 018
Create Date: 2026-08-29 00:00:00.000000

Gold Lane B1 backtest data source: extends the same "queue in the DB, the
local bridge polls and fulfils it" shape mt5_pending_order (014) already
uses for live orders to on-demand historical OHLC. See
xillion/db/models.py's MT5HistoricalRequest docstring for the full picture.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mt5_historical_request",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("broker_connection_name", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("timeframe", sa.Text, nullable=False),
        sa.Column("from_date", sa.Text, nullable=False),
        sa.Column("to_date", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("bars_json", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.Column("requested_at", sa.Text, nullable=False),
        sa.Column("completed_at", sa.Text),
    )
    op.create_index("idx_mt5_historical_request_status", "mt5_historical_request", ["status"])
    op.create_index(
        "idx_mt5_historical_request_conn",
        "mt5_historical_request",
        ["broker_connection_name"],
    )


def downgrade() -> None:
    op.drop_table("mt5_historical_request")
