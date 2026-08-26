"""broker_credential (missed by 001_initial)

Revision ID: 003
Revises: 002
Create Date: 2026-07-27 00:00:00.000000

The BrokerCredential ORM model (xillion/db/models.py) was never given a
migration in 001_initial.py. On SQLite dev this went unnoticed because
init_db()'s Base.metadata.create_all() (a dev convenience, see
xillion/db/session.py) silently filled the gap. Against a fresh Postgres
database with `uvicorn --workers 2`, both workers' create_all() race to
CREATE TABLE broker_credential concurrently and one loses with
"duplicate key value violates unique constraint pg_type_typname_nsp_index".

Uses IF NOT EXISTS / IF EXISTS (raw SQL, portable across SQLite and
Postgres) since the table may already have been created out-of-band by
whichever worker won that race on a given deployment.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS broker_credential (
            name TEXT NOT NULL,
            broker_name TEXT NOT NULL,
            encrypted_payload TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (name)
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS broker_credential")
