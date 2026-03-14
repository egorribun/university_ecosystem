"""Add failed_outbox_events DLQ table.

MOD-08 (audit 2026-03-14): Dead Letter Queue for outbox events that exceed
max_retries. Enables manual inspection, replay, and resolution tracking.

Revision ID: 202603140004
Revises: 202603140003
Create Date: 2026-03-14 14:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "202603140004"
down_revision: str | None = "202603140003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "failed_outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("original_event_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_failed_outbox_events_original_event_id",
        "failed_outbox_events",
        ["original_event_id"],
    )
    op.create_index(
        "ix_failed_outbox_events_event_type",
        "failed_outbox_events",
        ["event_type"],
    )
    op.create_index(
        "ix_failed_outbox_events_aggregate_id",
        "failed_outbox_events",
        ["aggregate_id"],
    )
    op.create_index(
        "ix_failed_outbox_events_failed_at",
        "failed_outbox_events",
        ["failed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_failed_outbox_events_failed_at", "failed_outbox_events")
    op.drop_index("ix_failed_outbox_events_aggregate_id", "failed_outbox_events")
    op.drop_index("ix_failed_outbox_events_event_type", "failed_outbox_events")
    op.drop_index("ix_failed_outbox_events_original_event_id", "failed_outbox_events")
    op.drop_table("failed_outbox_events")
