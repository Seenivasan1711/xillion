"""data_provider_class, data_provider_credential

Revision ID: 004
Revises: 003
Create Date: 2026-08-03 00:00:00.000000

Adds the plugin registry + credential tables for the new pluggable
historical-data-provider system (see xillion/core/data_provider_base.py).
Brand-new tables (unlike 003_broker_credential.py, which retrofitted a table
that already existed out-of-band) -- portable op.create_table, not raw SQL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_provider_class",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, unique=True, nullable=False),
        sa.Column("module_path", sa.Text, nullable=False),
        sa.Column("class_name", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("capabilities_json", sa.Text, nullable=False),
        sa.Column("discovered_at", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.Text, nullable=False),
    )

    op.create_table(
        "data_provider_credential",
        sa.Column("name", sa.Text, primary_key=True),
        sa.Column("provider_name", sa.Text, nullable=False),
        sa.Column("encrypted_payload", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("data_provider_credential")
    op.drop_table("data_provider_class")
