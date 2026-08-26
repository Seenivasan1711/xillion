"""Backfill columns/index missed by earlier ad-hoc create_all() calls

Revision ID: 013
Revises: 012
Create Date: 2026-08-26 00:00:00.000000

The real production DB was stamped to head (012) on 2026-08-25 after an
incident where ad-hoc `init_db()`/`create_all()` calls against it (this
session, before the guards added in commit 1a14f55) had already created
every table. That stamp assumed create_all() had produced a schema
equivalent to running every migration -- which is false for any table that
was first created by create_all() BEFORE a later migration added a column
to it: create_all() only creates missing tables, it never ALTERs an
existing one. `strategy_instance` was created (migration 001) before
`auto_start` existed in the codebase (migration 009, 2026-08-24), so the
real table never got that column -- confirmed live-crashing in production
("column strategy_instance.auto_start does not exist") and via a direct
information_schema audit. Same story for `signal_log` (created migration
002) vs. its migration 006 (tag/parent_signal_id/target_price/
stop_loss_price + index) and migration 008 (ai_confidence) columns.

Every other table already matched its migration exactly in that audit, so
this migration only touches these two. `IF NOT EXISTS` throughout so this
is a no-op (not an error) on any DB where create_all() never ran ad-hoc and
migrations 006/008/009 already applied for real.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS tag TEXT")
    op.execute(
        "ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS parent_signal_id "
        "INTEGER REFERENCES signal_log(id)"
    )
    op.execute("ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS target_price NUMERIC")
    op.execute("ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS stop_loss_price NUMERIC")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_signal_log_open_entry ON signal_log "
        "(strategy_instance_id, underlying_symbol, tag, signal_type)"
    )
    op.execute("ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS ai_confidence NUMERIC")
    op.execute(
        "ALTER TABLE strategy_instance ADD COLUMN IF NOT EXISTS auto_start "
        "BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_signal_log_open_entry")
    op.execute("ALTER TABLE signal_log DROP COLUMN IF EXISTS ai_confidence")
    op.execute("ALTER TABLE signal_log DROP COLUMN IF EXISTS stop_loss_price")
    op.execute("ALTER TABLE signal_log DROP COLUMN IF EXISTS target_price")
    op.execute("ALTER TABLE signal_log DROP COLUMN IF EXISTS parent_signal_id")
    op.execute("ALTER TABLE signal_log DROP COLUMN IF EXISTS tag")
    op.execute("ALTER TABLE strategy_instance DROP COLUMN IF EXISTS auto_start")
