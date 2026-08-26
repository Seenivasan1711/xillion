"""system_log

Revision ID: 010
Revises: 009
Create Date: 2026-08-24 00:00:00.000000

CP9: the Logs page (frontend/src/pages/Logs.tsx) was built to render a live
WebSocket "log" feed and claimed "scrollback retained for 24h" -- but
nothing in the backend ever emitted that event type at all, and there was
no persistence, so a page reload lost everything and there was never
anything to lose in the first place. This table plus
xillion/observability/log_capture.py fixes both halves: every structlog
event app-wide is now captured, persisted here, and broadcast live.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text, nullable=False),
        sa.Column("level", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("fields_json", sa.Text, nullable=False),
    )
    op.create_index("idx_system_log_ts", "system_log", ["ts"])
    op.create_index("idx_system_log_level", "system_log", ["level"])


def downgrade() -> None:
    op.drop_index("idx_system_log_level", table_name="system_log")
    op.drop_index("idx_system_log_ts", table_name="system_log")
    op.drop_table("system_log")
