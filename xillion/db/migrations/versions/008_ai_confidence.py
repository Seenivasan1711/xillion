"""signal_log.ai_confidence

Revision ID: 008
Revises: 007
Create Date: 2026-08-24 00:00:00.000000

CP8: the pre-trade AI confidence hook writes a 0-100 score here for ENTER
signals when an AI confidence backend is configured (AI_CONFIDENCE_URL) --
NULL otherwise, same as before this migration. The journal (CP6) surfaces
this alongside the signal's actual outcome so the prediction can be checked
against reality over time, not just trusted on faith.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signal_log", sa.Column("ai_confidence", sa.Numeric))


def downgrade() -> None:
    op.drop_column("signal_log", "ai_confidence")
