"""create push subscriptions table"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f9d2b1f5e2d0"
down_revision: str | None = "c8d0b5515f2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table: str) -> bool:
    return table in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return any(col["name"] == column for col in _insp().get_columns(table))


def _has_index(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    inspector = _insp()
    has_index = getattr(inspector, "has_index", None)
    if callable(has_index):
        try:
            return bool(has_index(table, name))
        except (NotImplementedError, TypeError):
            pass
    return any(ix.get("name") == name for ix in inspector.get_indexes(table))


def _create_index_safe(
    name: str, table: str, columns: list[str], *, unique: bool = False
) -> None:
    if not _table_exists(table) or _has_index(table, name):
        return
    try:
        op.create_index(name, table, columns, unique=unique, if_not_exists=True)
    except TypeError:
        if not _has_index(table, name):
            op.create_index(name, table, columns, unique=unique)


def _drop_index_safe(name: str, table: str) -> None:
    if not _table_exists(table):
        return
    try:
        op.drop_index(name, table_name=table, if_exists=True)
    except TypeError:
        if _has_index(table, name):
            op.drop_index(name, table_name=table)


def upgrade() -> None:
    # Skip if users table doesn't exist (FK dependency)
    if not _table_exists("users"):
        return

    if not _table_exists("push_subscriptions"):
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "user_id",
                sa.UUID,
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
    else:
        if not _column_exists("push_subscriptions", "topics"):
            op.add_column(
                "push_subscriptions",
                sa.Column(
                    "topics", sa.JSON, nullable=False, server_default=sa.text("'[]'")
                ),
            )
        if not _column_exists("push_subscriptions", "created_at"):
            op.add_column(
                "push_subscriptions",
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )
        if not _column_exists("push_subscriptions", "last_seen_at"):
            op.add_column(
                "push_subscriptions",
                sa.Column("last_seen_at", sa.DateTime(timezone=True)),
            )
        if not _column_exists("push_subscriptions", "user_agent"):
            op.add_column(
                "push_subscriptions",
                sa.Column("user_agent", sa.String(512)),
            )
        if not _column_exists("push_subscriptions", "endpoint"):
            op.add_column(
                "push_subscriptions",
                sa.Column("endpoint", sa.Text, nullable=False),
            )

    _create_index_safe(
        op.f("ix_push_subscriptions_user_id"),
        "push_subscriptions",
        ["user_id"],
    )
    _create_index_safe(
        op.f("ix_push_subscriptions_endpoint"),
        "push_subscriptions",
        ["endpoint"],
        unique=True,
    )
    _create_index_safe(
        op.f("ix_push_subscriptions_created_at"),
        "push_subscriptions",
        ["created_at"],
    )
    _create_index_safe(
        op.f("ix_push_subscriptions_last_seen_at"),
        "push_subscriptions",
        ["last_seen_at"],
    )


def downgrade() -> None:
    if not _table_exists("push_subscriptions"):
        return

    _drop_index_safe(op.f("ix_push_subscriptions_last_seen_at"), "push_subscriptions")
    _drop_index_safe(op.f("ix_push_subscriptions_created_at"), "push_subscriptions")
    _drop_index_safe(op.f("ix_push_subscriptions_user_id"), "push_subscriptions")
    _drop_index_safe(op.f("ix_push_subscriptions_endpoint"), "push_subscriptions")
    op.drop_table("push_subscriptions")
