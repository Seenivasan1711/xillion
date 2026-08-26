"""bar_coverage, market_holiday

Revision ID: 005
Revises: 004
Create Date: 2026-08-24 00:00:00.000000

CP2 (data warehouse): tracks which date ranges are already fetched per
(symbol, exchange, timeframe, provider), so BarWarehouse can persist once and
serve every later request from Postgres with zero provider HTTP calls. See
xillion/data/warehouse.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bar_coverage",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("exchange", sa.Text, primary_key=True),
        sa.Column("timeframe", sa.Text, primary_key=True),
        sa.Column("provider_name", sa.Text, primary_key=True),
        sa.Column("from_date", sa.Text, nullable=False),
        sa.Column("to_date", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )

    op.create_table(
        "market_holiday",
        sa.Column("exchange", sa.Text, primary_key=True),
        sa.Column("holiday_date", sa.Text, primary_key=True),
        sa.Column("description", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("market_holiday")
    op.drop_table("bar_coverage")
