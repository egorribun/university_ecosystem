from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202507310003"
down_revision = "202507310002"
branch_labels = None
depends_on = None


_SQLITE_WHERE = sa.text("dead_lettered = 0 AND claimed_at IS NULL")
_POSTGRESQL_WHERE = sa.text("dead_lettered = false AND claimed_at IS NULL")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {
        index["name"]
        for index in inspector.get_indexes("notification_queue_jobs")
    }

    if "ix_notification_queue_jobs_pending_claim" in indexes:
        return

    op.create_index(
        "ix_notification_queue_jobs_pending_claim",
        "notification_queue_jobs",
        ["next_retry_at", "enqueued_at", "id"],
        unique=False,
        sqlite_where=_SQLITE_WHERE,
        postgresql_where=_POSTGRESQL_WHERE,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {
        index["name"]
        for index in inspector.get_indexes("notification_queue_jobs")
    }

    if "ix_notification_queue_jobs_pending_claim" not in indexes:
        return

    op.drop_index(
        "ix_notification_queue_jobs_pending_claim",
        table_name="notification_queue_jobs",
    )
