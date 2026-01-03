"""drop legacy user columns

Revision ID: 202511240001
Revises: fix_sender_id_type
Create Date: 2025-11-24 00:00:00

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "202511240001"
down_revision = "fix_sender_id_type"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if users table exists
    if "users" not in inspector.get_table_names():
        return

    # SQLite doesn't support DROP COLUMN - skip on SQLite
    if bind.dialect.name == "sqlite":
        return

    # Get existing columns
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    # Drop columns if they exist
    columns_to_drop = ["dnd_enabled", "dnd_start", "dnd_end", "timezone"]
    for col in columns_to_drop:
        if col in existing_columns:
            op.drop_column("users", col)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if users table exists
    if "users" not in inspector.get_table_names():
        return

    # SQLite - skip
    if bind.dialect.name == "sqlite":
        return

    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    # Add columns back if they don't exist
    if "timezone" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "timezone", sa.VARCHAR(length=64), autoincrement=False, nullable=True
            ),
        )
    if "dnd_end" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("dnd_end", postgresql.TIME(), autoincrement=False, nullable=True),
        )
    if "dnd_start" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("dnd_start", postgresql.TIME(), autoincrement=False, nullable=True),
        )
    if "dnd_enabled" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "dnd_enabled",
                sa.BOOLEAN(),
                server_default=sa.text("false"),
                autoincrement=False,
                nullable=False,
            ),
        )

