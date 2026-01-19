"""add login history

Revision ID: 202601130003
Revises: 202601130002
Create Date: 2026-01-13 21:20:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202601130003"
down_revision = "202601130002"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("login_history"):
        op.create_table(
            "login_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("ip_address", sa.String(length=45), nullable=False),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("country", sa.String(length=2), nullable=True),
            sa.Column("city", sa.String(length=128), nullable=True),
            sa.Column("latitude", sa.String(length=20), nullable=True),
            sa.Column("longitude", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("is_suspicious", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # Check for indexes
    indexes = (
        {ix["name"] for ix in inspector.get_indexes("login_history")}
        if inspector.has_table("login_history")
        else set()
    )

    if "ix_login_history_created_at" not in indexes:
        op.create_index(
            op.f("ix_login_history_created_at"),
            "login_history",
            ["created_at"],
            unique=False,
        )
    if "ix_login_history_user_id" not in indexes:
        op.create_index(
            op.f("ix_login_history_user_id"), "login_history", ["user_id"], unique=False
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("login_history"):
        op.drop_table("login_history")
