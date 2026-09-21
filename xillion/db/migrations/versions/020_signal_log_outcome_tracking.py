"""signal_log_outcome_tracking

Revision ID: 020
Revises: 019
Create Date: 2026-09-21 00:00:00.000000

Gold Sweep-Reversal's "did you take this call, and how did it go" tracking
-- generic to any alert-mode ENTER signal, not Gold-specific. See
xillion/db/models.py's SignalLog docstring for the full picture.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signal_log", sa.Column("user_action", sa.Text))
    op.add_column("signal_log", sa.Column("user_action_at", sa.Text))
    op.add_column("signal_log", sa.Column("user_action_source", sa.Text))
    op.add_column("signal_log", sa.Column("outcome", sa.Text))
    op.add_column("signal_log", sa.Column("outcome_notes", sa.Text))
    op.add_column("signal_log", sa.Column("outcome_recorded_at", sa.Text))
    op.create_index("idx_signal_log_user_action", "signal_log", ["user_action"])


def downgrade() -> None:
    op.drop_index("idx_signal_log_user_action", table_name="signal_log")
    op.drop_column("signal_log", "outcome_recorded_at")
    op.drop_column("signal_log", "outcome_notes")
    op.drop_column("signal_log", "outcome")
    op.drop_column("signal_log", "user_action_source")
    op.drop_column("signal_log", "user_action_at")
    op.drop_column("signal_log", "user_action")
