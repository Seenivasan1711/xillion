"""strategy_instance.auto_start

Revision ID: 009
Revises: 008
Create Date: 2026-08-24 00:00:00.000000

CP9: opt-in flag so an instance can be started automatically at market open
and stopped at market close by the scheduler in
xillion/engine/market_scheduler.py. An instance not marked for this is left
entirely to manual start/stop, same as before this column existed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategy_instance",
        sa.Column("auto_start", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("strategy_instance", "auto_start")
