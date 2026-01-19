"""Create active sessions table."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202503010001"
down_revision: str | None = "202502010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply Create active sessions table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "active_sessions" in inspector.get_table_names():
        return

    op.create_table(
        "active_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("jti", name="uq_active_sessions_jti"),
    )
    op.create_index(
        "ix_active_sessions_user_id", "active_sessions", ["user_id"], unique=False
    )
    op.create_index(
        "ix_active_sessions_expires_at", "active_sessions", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_active_sessions_revoked_at", "active_sessions", ["revoked_at"], unique=False
    )
    op.create_index("ix_active_sessions_jti", "active_sessions", ["jti"], unique=True)


def downgrade() -> None:
    """Revert Create active sessions table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "active_sessions" not in inspector.get_table_names():
        return

    # Get existing indexes to check before dropping
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("active_sessions")}

    if "ix_active_sessions_jti" in existing_indexes:
        op.drop_index("ix_active_sessions_jti", table_name="active_sessions")
    if "ix_active_sessions_revoked_at" in existing_indexes:
        op.drop_index("ix_active_sessions_revoked_at", table_name="active_sessions")
    if "ix_active_sessions_expires_at" in existing_indexes:
        op.drop_index("ix_active_sessions_expires_at", table_name="active_sessions")
    if "ix_active_sessions_user_id" in existing_indexes:
        op.drop_index("ix_active_sessions_user_id", table_name="active_sessions")
    op.drop_table("active_sessions")
