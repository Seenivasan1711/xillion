"""proposed_strategy_change

Revision ID: 021
Revises: 020
Create Date: 2026-09-22 00:00:00.000000

JEV / LLM-assisted decision-making (task-tracker.md's SESSION SPRINT item
17): an LLM can propose a strategy parameter change with its reasoning, but
never apply one itself -- this table is the queue of proposals awaiting (or
having received) Rakesh's explicit approve/reject.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposed_strategy_change",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "strategy_instance_id", sa.Text, sa.ForeignKey("strategy_instance.id"), nullable=False
        ),
        sa.Column("proposed_params_json", sa.Text, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("proposed_by", sa.Text, nullable=False, server_default="JEV"),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("telegram_message_id", sa.Integer),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("decided_at", sa.Text),
        sa.Column("decided_by", sa.Text),
    )
    op.create_index(
        "idx_proposed_change_instance", "proposed_strategy_change", ["strategy_instance_id"]
    )
    op.create_index("idx_proposed_change_status", "proposed_strategy_change", ["status"])


def downgrade() -> None:
    op.drop_index("idx_proposed_change_status", table_name="proposed_strategy_change")
    op.drop_index("idx_proposed_change_instance", table_name="proposed_strategy_change")
    op.drop_table("proposed_strategy_change")
