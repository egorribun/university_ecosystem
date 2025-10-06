from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "f9d2b1f5e2d0"
down_revision: Union[str, None] = "c8d0b5515f2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(inspector, table: str, name: str) -> bool:
    for ix in inspector.get_indexes(table):
        if ix.get("name") == name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = {t for t in inspector.get_table_names()}
    if "push_subscriptions" not in tables:
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("endpoint", sa.Text, nullable=False),
            sa.Column("p256dh", sa.String(200), nullable=False),
            sa.Column("auth", sa.String(200), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("user_agent", sa.String(512)),
            sa.Column("last_seen_at", sa.DateTime(timezone=True)),
            sa.Column(
                "topics", sa.JSON, nullable=False, server_default=sa.text("'[]'")
            ),
        )
        op.create_index(
            op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"]
        )
        op.create_index(
            op.f("ix_push_subscriptions_endpoint"),
            "push_subscriptions",
            ["endpoint"],
            unique=True,
        )
        op.create_index(
            op.f("ix_push_subscriptions_created_at"),
            "push_subscriptions",
            ["created_at"],
        )
        op.create_index(
            op.f("ix_push_subscriptions_last_seen_at"),
            "push_subscriptions",
            ["last_seen_at"],
        )
    else:
        cols = {c["name"] for c in inspector.get_columns("push_subscriptions")}
        if "topics" not in cols:
            op.add_column(
                "push_subscriptions",
                sa.Column(
                    "topics", sa.JSON, nullable=False, server_default=sa.text("'[]'")
                ),
            )
        if "created_at" not in cols:
            op.add_column(
                "push_subscriptions",
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )
        if "last_seen_at" not in cols:
            op.add_column(
                "push_subscriptions",
                sa.Column("last_seen_at", sa.DateTime(timezone=True)),
            )
        if "user_agent" not in cols:
            op.add_column("push_subscriptions", sa.Column("user_agent", sa.String(512)))
        if "endpoint" not in cols:
            op.add_column(
                "push_subscriptions", sa.Column("endpoint", sa.Text, nullable=False)
            )
        if not _index_exists(
            inspector, "push_subscriptions", op.f("ix_push_subscriptions_user_id")
        ):
            op.create_index(
                op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"]
            )
        endpoint_ix_name = op.f("ix_push_subscriptions_endpoint")
        if not _index_exists(inspector, "push_subscriptions", endpoint_ix_name):
            op.create_index(
                endpoint_ix_name, "push_subscriptions", ["endpoint"], unique=True
            )
        if not _index_exists(
            inspector, "push_subscriptions", op.f("ix_push_subscriptions_created_at")
        ):
            op.create_index(
                op.f("ix_push_subscriptions_created_at"),
                "push_subscriptions",
                ["created_at"],
            )
        if not _index_exists(
            inspector, "push_subscriptions", op.f("ix_push_subscriptions_last_seen_at")
        ):
            op.create_index(
                op.f("ix_push_subscriptions_last_seen_at"),
                "push_subscriptions",
                ["last_seen_at"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = {t for t in inspector.get_table_names()}
    if "push_subscriptions" in tables:
        indexes = {ix.get("name") for ix in inspector.get_indexes("push_subscriptions")}
        if op.f("ix_push_subscriptions_last_seen_at") in indexes:
            op.drop_index(
                op.f("ix_push_subscriptions_last_seen_at"),
                table_name="push_subscriptions",
            )
        if op.f("ix_push_subscriptions_created_at") in indexes:
            op.drop_index(
                op.f("ix_push_subscriptions_created_at"),
                table_name="push_subscriptions",
            )
        if op.f("ix_push_subscriptions_user_id") in indexes:
            op.drop_index(
                op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions"
            )
        if op.f("ix_push_subscriptions_endpoint") in indexes:
            op.drop_index(
                op.f("ix_push_subscriptions_endpoint"), table_name="push_subscriptions"
            )
        op.drop_table("push_subscriptions")
