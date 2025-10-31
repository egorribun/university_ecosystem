"""Add retry metadata to notification queue jobs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202507100001"
down_revision: str | None = "202506150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("notification_queue_jobs")
    }

    if "last_error" not in existing_columns:
        op.add_column(
            "notification_queue_jobs",
            sa.Column("last_error", sa.Text(), nullable=True),
        )

    if "next_retry_at" not in existing_columns:
        op.add_column(
            "notification_queue_jobs",
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "dead_lettered" not in existing_columns:
        op.add_column(
            "notification_queue_jobs",
            sa.Column(
                "dead_lettered",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("notification_queue_jobs")
    }

    if "ix_notification_queue_jobs_dead_lettered" not in existing_indexes:
        op.create_index(
            "ix_notification_queue_jobs_dead_lettered",
            "notification_queue_jobs",
            ["dead_lettered"],
            unique=False,
        )

    if "ix_notification_queue_jobs_next_retry_at" not in existing_indexes:
        op.create_index(
            "ix_notification_queue_jobs_next_retry_at",
            "notification_queue_jobs",
            ["next_retry_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("notification_queue_jobs")
    }
    if "ix_notification_queue_jobs_next_retry_at" in existing_indexes:
        op.drop_index(
            "ix_notification_queue_jobs_next_retry_at",
            table_name="notification_queue_jobs",
        )
    if "ix_notification_queue_jobs_dead_lettered" in existing_indexes:
        op.drop_index(
            "ix_notification_queue_jobs_dead_lettered",
            table_name="notification_queue_jobs",
        )

    existing_columns = {
        column["name"] for column in inspector.get_columns("notification_queue_jobs")
    }
    if "dead_lettered" in existing_columns:
        op.drop_column("notification_queue_jobs", "dead_lettered")
    if "next_retry_at" in existing_columns:
        op.drop_column("notification_queue_jobs", "next_retry_at")
    if "last_error" in existing_columns:
        op.drop_column("notification_queue_jobs", "last_error")
