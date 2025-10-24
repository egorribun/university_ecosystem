"""Add retry metadata to notification queue jobs."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202507100001"
down_revision: Union[str, None] = "202506150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_queue_jobs",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "notification_queue_jobs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_queue_jobs",
        sa.Column(
            "dead_lettered",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_notification_queue_jobs_dead_lettered",
        "notification_queue_jobs",
        ["dead_lettered"],
        unique=False,
    )
    op.create_index(
        "ix_notification_queue_jobs_next_retry_at",
        "notification_queue_jobs",
        ["next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_queue_jobs_next_retry_at",
        table_name="notification_queue_jobs",
    )
    op.drop_index(
        "ix_notification_queue_jobs_dead_lettered",
        table_name="notification_queue_jobs",
    )
    op.drop_column("notification_queue_jobs", "dead_lettered")
    op.drop_column("notification_queue_jobs", "next_retry_at")
    op.drop_column("notification_queue_jobs", "last_error")
