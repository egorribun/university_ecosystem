"""Create durable notification queue table."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202506150001"
down_revision: Union[str, None] = "202506010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "notification_queue_jobs"
_KIND_CHECK = "ck_notification_queue_jobs_kind"
_UNIQUE_NAME = "uq_notification_queue_jobs_kind_record"
_INDEX_NAME = "ix_notification_queue_jobs_kind_record"


def upgrade() -> None:
    """Create durable notification queue backing table."""

    op.create_table(
        _TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=True),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.CheckConstraint("kind IN ('event', 'news')", name=_KIND_CHECK),
        sa.UniqueConstraint("kind", "record_id", name=_UNIQUE_NAME),
    )
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["kind", "record_id"],
    )
    op.create_index(
        "ix_notification_queue_jobs_claimed_at",
        _TABLE_NAME,
        ["claimed_at"],
    )


def downgrade() -> None:
    """Drop durable notification queue backing table."""

    op.drop_index("ix_notification_queue_jobs_claimed_at", table_name=_TABLE_NAME)
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
