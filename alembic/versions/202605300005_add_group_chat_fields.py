"""Add group-chat identity fields to chats (Wave 209 G1: chat_type/name/created_by)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300005"
down_revision: str | None = "202605300004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "chats"
_CHAT_TYPE = "chat_type"
_NAME = "name"
_CREATED_BY = "created_by"
_CHECK_NAME = "ck_chats_chat_type"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Apply: add chat_type/name/created_by group-identity columns to chats.

    chat_type carries server_default="dm" so every existing row is backfilled in
    the same ALTER (no separate UPDATE) and the untouched create_chat DM path
    needs no chat_type kwarg — the DB supplies "dm". The named CheckConstraint
    mirrors the model __table_args__ (ck_chats_chat_type) so autogenerate stays
    clean. created_by is a SET NULL self-soft-FK to users (owner deletion must
    not cascade-delete the group). Each add is guarded so up/down/up is
    idempotent; fresh sa.Column objects per call so none is re-bound to a Table.
    """
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _CHAT_TYPE):
        op.add_column(
            _TABLE_NAME,
            sa.Column(_CHAT_TYPE, sa.String(20), nullable=False, server_default="dm"),
        )
        op.create_check_constraint(
            _CHECK_NAME, _TABLE_NAME, "chat_type IN ('dm', 'group')"
        )

    if not _column_exists(bind, _TABLE_NAME, _NAME):
        op.add_column(_TABLE_NAME, sa.Column(_NAME, sa.String(128), nullable=True))

    if not _column_exists(bind, _TABLE_NAME, _CREATED_BY):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                _CREATED_BY,
                sa.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Revert: drop created_by, name, the chat_type check constraint + column.

    drop_column on PostgreSQL drops a column's dependent FK constraint
    automatically (created_by); the named CHECK on chat_type is dropped
    explicitly first so the up/down/up cycle is unambiguous.
    """
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _column_exists(bind, _TABLE_NAME, _CREATED_BY):
        op.drop_column(_TABLE_NAME, _CREATED_BY)

    if _column_exists(bind, _TABLE_NAME, _NAME):
        op.drop_column(_TABLE_NAME, _NAME)

    if _column_exists(bind, _TABLE_NAME, _CHAT_TYPE):
        op.drop_constraint(_CHECK_NAME, _TABLE_NAME, type_="check")
        op.drop_column(_TABLE_NAME, _CHAT_TYPE)
