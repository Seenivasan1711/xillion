"""signal_log lifecycle columns (tag, parent_signal_id, target/stop-loss)

Revision ID: 006
Revises: 005
Create Date: 2026-08-24 00:00:00.000000

CP4: signal_log previously stored the setup tag in its `signal_type` column
and had no ENTER/EXIT distinction or way to link an exit back to the entry
it closes -- every signal was effectively a one-shot fire, matching the
docstring's aspiration ("e.g. ENTER | EXIT") but not the actual behaviour.
This adds the columns needed for a real entry -> target/stop-loss -> exit
lifecycle: `tag` (pairing key), `parent_signal_id` (self-FK, set on EXIT
rows), `target_price`, `stop_loss_price`.

No backfill of existing rows: pre-CP4 rows have their (mis-used) tag value
sitting in `signal_type` already, and there's no reliable way to tell which
of those were "entries" vs one-shot alerts after the fact -- they stay as
they are, readable as `signal_type="SIGNAL"`-shaped history from before this
migration. Nothing currently reads signal_log outside this migration (no
API, no UI existed before CP4), so there are no consumers to break.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signal_log", sa.Column("tag", sa.Text))
    op.add_column(
        "signal_log", sa.Column("parent_signal_id", sa.Integer, sa.ForeignKey("signal_log.id"))
    )
    op.add_column("signal_log", sa.Column("target_price", sa.Numeric))
    op.add_column("signal_log", sa.Column("stop_loss_price", sa.Numeric))
    op.create_index(
        "idx_signal_log_open_entry",
        "signal_log",
        ["strategy_instance_id", "underlying_symbol", "tag", "signal_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_signal_log_open_entry", table_name="signal_log")
    op.drop_column("signal_log", "stop_loss_price")
    op.drop_column("signal_log", "target_price")
    op.drop_column("signal_log", "parent_signal_id")
    op.drop_column("signal_log", "tag")
