"""create push_subscriptions table"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9d2b1f5e2d0"
down_revision: Union[str, None] = "c8d0b5515f2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the push_subscriptions table."""

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_index(
        op.f("ix_push_subscriptions_endpoint"),
        "push_subscriptions",
        ["endpoint"],
        unique=True,
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"),
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_push_subscriptions_created_at"),
        "push_subscriptions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_push_subscriptions_last_seen_at"),
        "push_subscriptions",
        ["last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the push_subscriptions table."""

    op.drop_index(
        op.f("ix_push_subscriptions_last_seen_at"), table_name="push_subscriptions"
    )
    op.drop_index(
        op.f("ix_push_subscriptions_created_at"), table_name="push_subscriptions"
    )
    op.drop_index(
        op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions"
    )
    op.drop_index(
        op.f("ix_push_subscriptions_endpoint"), table_name="push_subscriptions"
    )
    op.drop_table("push_subscriptions")
