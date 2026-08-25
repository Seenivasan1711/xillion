"""reconciliation_report

Revision ID: 012
Revises: 011
Create Date: 2026-08-25 00:00:00.000000

CP14 / M01 (automation-platform-spec/08-JOBS-POSTMARKET.md): persisted,
queryable daily broker-vs-internal reconciliation, not just a log line --
the spec's own "block tomorrow's trading if not CLEAN" rule needs a durable
record to check against.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_report",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trading_date", sa.Text, nullable=False),
        sa.Column("broker_name", sa.Text, nullable=False),
        sa.Column("checked_at", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("position_mismatches_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("eod_open_positions_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("notes_json", sa.Text, nullable=False, server_default="[]"),
    )
    op.create_index("idx_reconciliation_date", "reconciliation_report", ["trading_date"])


def downgrade() -> None:
    op.drop_index("idx_reconciliation_date", table_name="reconciliation_report")
    op.drop_table("reconciliation_report")
