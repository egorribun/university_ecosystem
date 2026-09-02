"""Add aggregate_id_uuid and sequence_number to stored_events for causal ordering.

DEBT-01 (audit 2026-03-14): OutboxWorker with skip_locked=True and multiple
workers processes events from the same aggregate out of causal order. Adding
aggregate_id_uuid + sequence_number enables DISTINCT ON (aggregate_id_uuid)
ORDER BY aggregate_id_uuid, sequence_number to guarantee per-aggregate ordering
while still allowing parallel processing across different aggregates.

Revision ID: 202603140003
Revises: 202603140002
Create Date: 2026-03-14 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202603140003"
down_revision: str | None = "202603140002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stored_events", sa.Column("aggregate_id_uuid", sa.UUID(), nullable=True)
    )
    op.add_column(
        "stored_events", sa.Column("sequence_number", sa.BigInteger(), nullable=True)
    )

    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stored_events_aggregate_uuid "
                    "ON stored_events (aggregate_id_uuid, sequence_number) "
                    "WHERE processed_at IS NULL AND aggregate_id_uuid IS NOT NULL"
                )
            )
    else:
        op.create_index(
            "ix_stored_events_aggregate_uuid",
            "stored_events",
            ["aggregate_id_uuid", "sequence_number"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "DROP INDEX CONCURRENTLY IF EXISTS ix_stored_events_aggregate_uuid"
                )
            )
    else:
        op.drop_index("ix_stored_events_aggregate_uuid", "stored_events")
    op.drop_column("stored_events", "sequence_number")
    op.drop_column("stored_events", "aggregate_id_uuid")
