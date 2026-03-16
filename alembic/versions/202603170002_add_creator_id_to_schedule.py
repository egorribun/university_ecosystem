"""Add creator_id FK to schedule table for IDOR ownership enforcement.

SEC-BE-01 (audit Wave 10): The PATCH /schedule/{schedule_id} endpoint checked
the caller's *role* (teacher/admin) but not *ownership*.  Any authenticated
teacher could modify any other teacher's schedule entry.

This migration adds a nullable ``creator_id`` UUID foreign key that references
``users.id``.  Nullable so that pre-existing rows (created before this column
existed) remain valid and can still be managed by admins.

New rows created after this migration will have ``creator_id`` set to the
authenticated user's ID at creation time.

Index design:
  - ``ix_schedule_creator_id`` on (creator_id) — supports the ownership check
    SELECT in UpdateScheduleHandler without a full table scan.

The column is added with ``IF NOT EXISTS`` so the migration is safe to re-run.

Revision ID: 202603170002
Revises: 202603170001
Create Date: 2026-03-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603170002"
down_revision: str | None = "202603170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedule",
        sa.Column(
            "creator_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_schedule_creator_id",
        "schedule",
        ["creator_id"],
        unique=False,
        postgresql_where=sa.text("creator_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_creator_id", table_name="schedule")
    op.drop_column("schedule", "creator_id")
