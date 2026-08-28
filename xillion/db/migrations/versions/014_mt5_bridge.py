"""mt5_pending_order, mt5_bridge_tick

Revision ID: 014
Revises: 013
Create Date: 2026-08-28 00:00:00.000000

Gold Lane B1 (XAUUSD via Funding Pips MT5). The MT5 desktop terminal only
runs on the machine it's installed on -- xillion's Render backend can't run
it directly. These two tables are the hand-off point between
brokers/mt5_funding_pips.py (runs inside the backend, queues orders/reads
prices) and a separate local bridge process (mt5_bridge/bridge.py, runs
next to the real terminal) that polls for pending orders and reports back
fills/prices over xillion's own REST API.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mt5_pending_order",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("broker_connection_name", sa.Text, nullable=False),
        sa.Column("client_order_id", sa.Text, nullable=False, unique=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("quantity", sa.Text, nullable=False),
        sa.Column("order_type", sa.Text, nullable=False),
        sa.Column("price", sa.Text),
        sa.Column("stop_loss", sa.Text),
        sa.Column("take_profit", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="PENDING"),
        sa.Column("mt5_ticket_id", sa.Text),
        sa.Column("avg_fill_price", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("idx_mt5_pending_order_status", "mt5_pending_order", ["status"])
    op.create_index("idx_mt5_pending_order_conn", "mt5_pending_order", ["broker_connection_name"])

    op.create_table(
        "mt5_bridge_tick",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("broker_connection_name", sa.Text, nullable=False),
        sa.Column("ltp", sa.Text, nullable=False),
        sa.Column("bid", sa.Text),
        sa.Column("ask", sa.Text),
        sa.Column("updated_at", sa.Text, nullable=False),
    )

    op.create_table(
        "mt5_bridge_state",
        sa.Column("broker_connection_name", sa.Text, primary_key=True),
        sa.Column("positions_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("margins_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("holdings_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mt5_bridge_state")
    op.drop_table("mt5_bridge_tick")
    op.drop_index("idx_mt5_pending_order_conn", table_name="mt5_pending_order")
    op.drop_index("idx_mt5_pending_order_status", table_name="mt5_pending_order")
    op.drop_table("mt5_pending_order")
