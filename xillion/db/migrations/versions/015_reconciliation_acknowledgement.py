"""reconciliation_report acknowledgement

Revision ID: 015
Revises: 014
Create Date: 2026-08-28 00:00:00.000000

CP14/M01's own design says a non-CLEAN reconciliation must "block tomorrow's
trading, require manual sign-off to resume" -- the report existed and was
queryable (012) but nothing ever gated trading on it, and there was no way
to record that a human actually reviewed a DISCREPANCY/FAILED day. This adds
the sign-off columns; the gating itself lives in xillion/engine/
eod_scheduler.py and the acknowledge endpoint in xillion/api/reconciliation.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_report",
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("reconciliation_report", sa.Column("acknowledged_at", sa.Text, nullable=True))
    op.add_column("reconciliation_report", sa.Column("acknowledged_by", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("reconciliation_report", "acknowledged_by")
    op.drop_column("reconciliation_report", "acknowledged_at")
    op.drop_column("reconciliation_report", "acknowledged")
