"""broker_connection failover_connection_id

Revision ID: 017
Revises: 016
Create Date: 2026-08-29 00:00:00.000000

Broker failover (automation-platform-spec 13-IMPLEMENTATION-ROADMAP.md
"Broker failover: Dhan <-> Zerodha", 15-RUNBOOK-AND-OBSERVABILITY.md
"switch to secondary broker for exits only"). Self-referencing FK: null by
default, nothing fails over until a connection has this explicitly set.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "broker_connection",
        sa.Column("failover_connection_id", sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        "fk_broker_connection_failover",
        "broker_connection",
        "broker_connection",
        ["failover_connection_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_broker_connection_failover", "broker_connection", type_="foreignkey")
    op.drop_column("broker_connection", "failover_connection_id")
