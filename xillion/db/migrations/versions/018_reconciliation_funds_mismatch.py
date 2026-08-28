"""reconciliation_report funds_mismatch

Revision ID: 018
Revises: 017
Create Date: 2026-08-29 00:00:00.000000

M01's own scope (08-JOBS-POSTMARKET.md) covers positions, orders/fills, AND
funds -- 012 shipped positions, 016 shipped orders/fills, both honestly
flagging funds (broker P&L vs computed P&L) as the one piece left. This
adds the column for it; xillion/engine/reconciliation.py's new
_reconcile_funds() is what populates it. Nullable, unlike order_mismatches_
json's default-"[]" -- funds reconciliation is a single optional finding
(or none), not a list, and is null whenever the broker doesn't support
Broker.get_realised_pnl_today() at all (a clean skip, not "nothing found").
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_report",
        sa.Column("funds_mismatch_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reconciliation_report", "funds_mismatch_json")
