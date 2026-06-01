"""Add forwarded_from_* fields to messages (Wave 211 forwarding snapshot-copy)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300007"
down_revision: str | None = "202605300006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "messages"
_NAME_COLUMN = "forwarded_from_name"
_CHAT_ID_COLUMN = "forwarded_from_chat_id"
_MESSAGE_ID_COLUMN = "forwarded_from_message_id"
_MESSAGE_ID_INDEX = "ix_messages_forwarded_from_message_id"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Apply: add the three Wave 211 forwarding columns to messages.

    Snapshot-copy model — a forwarded message is a self-contained copy in the
    destination chat: ``forwarded_from_name`` is the denormalized "Forwarded
    from X" label (the only field the FE renders); the two ``*_id`` columns are
    AUDIT-ONLY (never serialized, never dereferenced cross-chat). All
    ``ondelete="SET NULL"`` (like the W207 reply self-FK, NOT CASCADE) so
    deleting the source chat/message never deletes the forward. Only
    ``forwarded_from_message_id`` is indexed — a self-FK to messages.id whose
    SET NULL sweep can fire in bulk on chat hard-delete (chat_id CASCADE), the
    reply_to_message_id / DEBT-02 rationale; ``forwarded_from_chat_id`` matches
    the un-indexed Chat.created_by SET NULL FK (chats.id sweeps are rare). A
    fresh ``sa.Column`` per ``upgrade()`` call keeps up/down/up idempotency from
    re-binding an object already attached to a Table.
    """
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _NAME_COLUMN):
        op.add_column(
            _TABLE_NAME,
            sa.Column(_NAME_COLUMN, sa.String(length=128), nullable=True),
        )

    if not _column_exists(bind, _TABLE_NAME, _CHAT_ID_COLUMN):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                _CHAT_ID_COLUMN,
                sa.UUID(as_uuid=True),
                sa.ForeignKey("chats.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    if not _column_exists(bind, _TABLE_NAME, _MESSAGE_ID_COLUMN):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                _MESSAGE_ID_COLUMN,
                sa.UUID(as_uuid=True),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(_MESSAGE_ID_INDEX, _TABLE_NAME, [_MESSAGE_ID_COLUMN])


def downgrade() -> None:
    """Revert: drop the index + the three Wave 211 forwarding columns.

    ``drop_column`` on PostgreSQL drops each column's dependent FK constraint
    automatically, so only the explicit index on forwarded_from_message_id needs
    an explicit drop (and only when that column still exists).
    """
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _column_exists(bind, _TABLE_NAME, _MESSAGE_ID_COLUMN):
        op.drop_index(_MESSAGE_ID_INDEX, table_name=_TABLE_NAME)
        op.drop_column(_TABLE_NAME, _MESSAGE_ID_COLUMN)

    if _column_exists(bind, _TABLE_NAME, _CHAT_ID_COLUMN):
        op.drop_column(_TABLE_NAME, _CHAT_ID_COLUMN)

    if _column_exists(bind, _TABLE_NAME, _NAME_COLUMN):
        op.drop_column(_TABLE_NAME, _NAME_COLUMN)
