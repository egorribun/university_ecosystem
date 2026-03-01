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
    """Apply column length constraints and unify user_profiles schema."""
    if op.get_bind().dialect.name != "postgresql":
        return

    # 1. Standardize table name: user_profile_details -> user_profiles
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "user_profile_details" in tables and "user_profiles" not in tables:
        op.rename_table("user_profile_details", "user_profiles")

    # 2. Sync columns: Move full_name, avatar_url, cover_url from users -> user_profiles
    # These were left in 'users' by previous partial refactors but are now
    # expected in 'user_profiles' by the SQLAlchemy model and this audit sweep.
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    profile_columns = {c["name"] for c in inspector.get_columns("user_profiles")}

    # Add missing columns to user_profiles
    with op.batch_alter_table("user_profiles") as batch_op:
        if "full_name" not in profile_columns:
            batch_op.add_column(sa.Column("full_name", sa.String(256), nullable=True))
        if "avatar_url" not in profile_columns:
            batch_op.add_column(sa.Column("avatar_url", sa.String(2048), nullable=True))
        if "cover_url" not in profile_columns:
            batch_op.add_column(sa.Column("cover_url", sa.String(2048), nullable=True))

    # Data Migration: Copy values from users to user_profiles
    if "full_name" in user_columns:
        op.execute(
            """
            UPDATE user_profiles
            SET
                full_name = users.full_name,
                avatar_url = users.avatar_url,
                cover_url = users.cover_url
            FROM users
            WHERE user_profiles.user_id = users.id
            """
        )

    # 3. Apply constraints and bounds
    with op.batch_alter_table("user_profiles") as batch_op:
        # These are already VARCHAR in some versions but Text in others.
        # batch_op.alter_column is idempotent for VARCHAR length increases.
        for col, size in [
            ("full_name", 256),
            ("avatar_url", 2048),
            ("cover_url", 2048),
            ("about", 4096),
            ("telegram", 128),
            ("status", 256),
            ("achievements", 2048),
            ("position", 256),
            ("department", 256),
        ]:
            batch_op.alter_column(
                col,
                type_=sa.String(size),
                existing_type=sa.Text(),
                existing_nullable=True,
            )

    # 4. Clean up 'users' table
    with op.batch_alter_table("users") as batch_op:
        if "full_name" in user_columns:
            batch_op.drop_column("full_name")
        if "avatar_url" in user_columns:
            batch_op.drop_column("avatar_url")
        if "cover_url" in user_columns:
            batch_op.drop_column("cover_url")

    # 5. user_education_paths constraints
    with op.batch_alter_table("user_education_paths") as batch_op:
        for col, size in [
            ("institute", 512),
            ("course", 64),
            ("education_level", 128),
            ("track", 256),
            ("program", 512),
            ("record_book_number", 64),
        ]:
            batch_op.alter_column(
                col,
                type_=sa.String(size),
                existing_type=sa.Text(),
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

    # Restore table name only if we are on a version that expects the old name
    # but since this migration chain now standardizes on user_profiles,
    # downgrading column types is usually enough. If a hard downgrade to
    # user_profile_details is needed, it would be here.

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
