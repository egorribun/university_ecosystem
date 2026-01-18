"""fix_groups_id_sequence

Revision ID: 2956fd6376cc
Revises: 148642dd1207
Create Date: 2026-01-19 01:55:04.405903

This migration fixes the groups.id column to properly use a PostgreSQL sequence
for auto-increment. The previous migration used alter_column with autoincrement=True,
which doesn't properly create a sequence in PostgreSQL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2956fd6376cc"
down_revision: str | None = "148642dd1207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create and attach a sequence to groups.id for PostgreSQL autoincrement."""
    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        return

    # Check if sequence already exists
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_sequences WHERE schemaname = 'public' "
            "AND sequencename = 'groups_id_seq'"
        )
    ).fetchone()

    if result:
        # Sequence exists, just ensure it's attached to the column
        op.execute(
            "ALTER TABLE groups ALTER COLUMN id SET DEFAULT nextval('groups_id_seq')"
        )
        return

    # Create the sequence
    op.execute("CREATE SEQUENCE IF NOT EXISTS groups_id_seq AS INTEGER")

    # Get the current max id to set the sequence value
    max_id_result = bind.execute(sa.text("SELECT COALESCE(MAX(id), 0) FROM groups"))
    max_id = max_id_result.scalar() or 0

    # Set the sequence to start after the max existing id
    if max_id > 0:
        op.execute(f"SELECT setval('groups_id_seq', {max_id})")

    # Attach the sequence to the column as default
    op.execute(
        "ALTER TABLE groups ALTER COLUMN id SET DEFAULT nextval('groups_id_seq')"
    )

    # Own the sequence by the column so it's dropped when the column is dropped
    op.execute("ALTER SEQUENCE groups_id_seq OWNED BY groups.id")


def downgrade() -> None:
    """Remove the sequence default from groups.id."""
    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        return

    # Remove the default
    op.execute("ALTER TABLE groups ALTER COLUMN id DROP DEFAULT")

    # Drop the sequence
    op.execute("DROP SEQUENCE IF EXISTS groups_id_seq")
