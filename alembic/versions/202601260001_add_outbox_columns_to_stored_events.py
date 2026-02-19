"""Add outbox columns to stored_events

Revision ID: 202601260001
Revises: 3f1cf9168805
Create Date: 2026-01-26 15:22:00.000000

"""

import contextlib
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202601260001"
down_revision: str | None = "1b15294cc8d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add outbox worker columns to stored_events table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = [col["name"] for col in inspector.get_columns("stored_events")]

    if "processed_at" not in existing_columns:
        op.add_column(
            "stored_events",
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            op.f("ix_stored_events_processed_at"),
            "stored_events",
            ["processed_at"],
            unique=False,
        )

    if "error_count" not in existing_columns:
        op.add_column(
            "stored_events",
            sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index(
            op.f("ix_stored_events_error_count"),
            "stored_events",
            ["error_count"],
            unique=False,
        )

    if "last_error" not in existing_columns:
        op.add_column(
            "stored_events",
            sa.Column("last_error", sa.String(), nullable=True),
        )


def downgrade() -> None:
    """Remove outbox worker columns from stored_events table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = [col["name"] for col in inspector.get_columns("stored_events")]

    if "last_error" in existing_columns:
        op.drop_column("stored_events", "last_error")

    if "error_count" in existing_columns:
        with contextlib.suppress(Exception):
            op.drop_index(
                op.f("ix_stored_events_error_count"), table_name="stored_events"
            )
        op.drop_column("stored_events", "error_count")

    if "processed_at" in existing_columns:
        with contextlib.suppress(Exception):
            op.drop_index(
                op.f("ix_stored_events_processed_at"), table_name="stored_events"
            )
        op.drop_column("stored_events", "processed_at")
