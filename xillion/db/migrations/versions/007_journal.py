"""journal_note, strategy_version_history

Revision ID: 007
Revises: 006
Create Date: 2026-08-24 00:00:00.000000

CP6: journal_note holds manual failure-mode tags and "what changed" notes
for journal entries auto-classification can't honestly claim (see
xillion/engine/journal.py's docstring for which modes have real evidence
behind them and which don't). strategy_version_history is an append-only
log of every (version, code_hash) a strategy class has had -- strategy_class
itself is upserted in place on every plugin sync, which would otherwise
silently lose this the moment a strategy file changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "journal_note",
        sa.Column("source", sa.Text, primary_key=True),
        sa.Column("source_id", sa.Text, primary_key=True),
        sa.Column("failure_mode", sa.Text),
        sa.Column("change_made", sa.Text),
        sa.Column("updated_at", sa.Text, nullable=False),
    )

    op.create_table(
        "strategy_version_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "strategy_class_id", sa.Integer, sa.ForeignKey("strategy_class.id"), nullable=False
        ),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("recorded_at", sa.Text, nullable=False),
    )
    op.create_index(
        "idx_strategy_version_history_class", "strategy_version_history", ["strategy_class_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_strategy_version_history_class", table_name="strategy_version_history")
    op.drop_table("strategy_version_history")
    op.drop_table("journal_note")
