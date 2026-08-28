"""reconciliation_report order_mismatches

Revision ID: 016
Revises: 015
Create Date: 2026-08-29 00:00:00.000000

M01's own scope (08-JOBS-POSTMARKET.md) covers positions, orders/fills, AND
funds -- CP14 (012) only shipped positions, honestly flagging orders/fills
as a follow-up. This adds the column for it; xillion/engine/
reconciliation.py's new _reconcile_orders() is what populates it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_report",
        sa.Column("order_mismatches_json", sa.Text, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("reconciliation_report", "order_mismatches_json")
