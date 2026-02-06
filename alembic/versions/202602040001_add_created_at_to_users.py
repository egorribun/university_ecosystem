"""add created_at to users

Revision ID: 202602040001
Revises: 202602010004
Create Date: 2026-02-04 18:45:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202602040001"
down_revision = "202602010004"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("users")]

    if "created_at" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )
        op.create_index(
            op.f("ix_users_created_at"), "users", ["created_at"], unique=False
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("users")]

    if "created_at" in columns:
        op.drop_index(op.f("ix_users_created_at"), table_name="users")
        op.drop_column("users", "created_at")
