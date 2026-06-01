"""Add reply_to_message_id self-FK to messages (Wave 207 reply/quote)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300004"
down_revision: str | None = "202605300003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "messages"
_COLUMN_NAME = "reply_to_message_id"
_INDEX_NAME = "ix_messages_reply_to_message_id"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Apply: add the reply_to_message_id self-FK (+ index) to messages.

    ``ondelete="SET NULL"`` (not CASCADE): a reply is a standalone message that
    merely references an earlier one, so it survives its target's deletion — the
    column nulls out and the FE renders an "original deleted" placeholder. The
    inline ForeignKey is rendered by alembic's add_column on PostgreSQL; the
    auto-generated constraint is dropped automatically with the column on
    downgrade. The explicit index serves the SET NULL sweep (PG must find every
    row referencing a just-deleted message id), mirroring Attachment's DEBT-02
    FK-without-index rationale.
    """
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _COLUMN_NAME):
        op.add_column(
            _TABLE_NAME,
            # Fresh sa.Column per upgrade() call so the up/down/up idempotency
            # check never re-uses an object already bound to a Table.
            sa.Column(
                _COLUMN_NAME,
                sa.UUID(as_uuid=True),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(_INDEX_NAME, _TABLE_NAME, [_COLUMN_NAME])


def downgrade() -> None:
    """Revert: drop the index + reply_to_message_id column from messages.

    drop_column on PostgreSQL drops the column's dependent FK constraint
    automatically, so only the explicit index needs an explicit drop.
    """
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _column_exists(bind, _TABLE_NAME, _COLUMN_NAME):
        op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
