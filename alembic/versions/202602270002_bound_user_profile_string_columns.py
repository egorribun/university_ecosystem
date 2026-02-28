"""Bound previously-unbounded String columns in UserProfile and EducationPath.

PERF-4 (audit 2026-02-26): All text fields in user_profiles and
user_education_paths were declared as unbounded String (TEXT in PostgreSQL).
Without a column-level constraint an attacker or bug can store multi-MB
values, causing OOM on bulk user list queries where these tables are
selectin-loaded.  Bounds are set to values reflecting real-world semantics.

Revision ID: 202602270002
Revises: 202602270001
Create Date: 2026-02-26 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202602270002"
down_revision: str | None = "202602270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply column length constraints to user_profiles and user_education_paths."""
    # SQLite does not enforce VARCHAR(n) length limits, so these constraints are
    # meaningless there.  The table name "user_profiles" also only exists on
    # PostgreSQL deployments; on SQLite the chain uses "user_profile_details"
    # with a different column set.  Skip entirely on non-PostgreSQL.
    if op.get_bind().dialect.name != "postgresql":
        return

    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.alter_column(
            "full_name",
            existing_type=sa.Text(),
            type_=sa.String(256),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "avatar_url",
            existing_type=sa.Text(),
            type_=sa.String(2048),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "cover_url",
            existing_type=sa.Text(),
            type_=sa.String(2048),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "about",
            existing_type=sa.Text(),
            type_=sa.String(4096),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "telegram",
            existing_type=sa.Text(),
            type_=sa.String(128),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.Text(),
            type_=sa.String(256),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "achievements",
            existing_type=sa.Text(),
            type_=sa.String(2048),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "position",
            existing_type=sa.Text(),
            type_=sa.String(256),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "department",
            existing_type=sa.Text(),
            type_=sa.String(256),
            existing_nullable=True,
        )

    # ── user_education_paths ──────────────────────────────────────────────────
    with op.batch_alter_table("user_education_paths") as batch_op:
        batch_op.alter_column(
            "institute",
            existing_type=sa.Text(),
            type_=sa.String(512),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "course",
            existing_type=sa.Text(),
            type_=sa.String(64),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "education_level",
            existing_type=sa.Text(),
            type_=sa.String(128),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "track",
            existing_type=sa.Text(),
            type_=sa.String(256),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "program",
            existing_type=sa.Text(),
            type_=sa.String(512),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "record_book_number",
            existing_type=sa.Text(),
            type_=sa.String(64),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Revert column length constraints back to unbounded TEXT."""
    if op.get_bind().dialect.name != "postgresql":
        return

    with op.batch_alter_table("user_profiles") as batch_op:
        for col in (
            "full_name",
            "avatar_url",
            "cover_url",
            "about",
            "telegram",
            "status",
            "achievements",
            "position",
            "department",
        ):
            batch_op.alter_column(
                col,
                existing_type=sa.String(),  # length will be dropped by Postgres
                type_=sa.Text(),
                existing_nullable=True,
            )

    with op.batch_alter_table("user_education_paths") as batch_op:
        for col in (
            "institute",
            "course",
            "education_level",
            "track",
            "program",
            "record_book_number",
        ):
            batch_op.alter_column(
                col,
                existing_type=sa.String(),
                type_=sa.Text(),
                existing_nullable=True,
            )
