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
    # Callers check the table first, so the column lookup needs no guard here.
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _reply_index_state(bind) -> str | None:
    """Return None when the reply index is absent, otherwise "valid" or "invalid".

    PostgreSQL keeps a catalog row for a CONCURRENTLY build that failed midway,
    flagged ``indisvalid = false``. Other dialects have no such state.
    """
    if op.get_context().as_sql:
        # Offline SQL has no catalog to read; render the ordinary build path.
        return None
    if bind.dialect.name != "postgresql":
        names = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE_NAME)}
        return "valid" if _INDEX_NAME in names else None
    return bind.execute(
        sa.text(
            "SELECT CASE WHEN i.indisvalid THEN 'valid' ELSE 'invalid' END "
            "FROM pg_index i WHERE i.indexrelid = to_regclass(:name)"
        ),
        {"name": _INDEX_NAME},
    ).scalar()


def _ensure_reply_index(bind) -> None:
    """Build the reply index CONCURRENTLY, repairing an interrupted build first.

    The column change commits before the concurrent build, so a failed build
    leaves the column in place with no index or an INVALID one. A rerun must
    rebuild that index instead of treating the column as proof it exists.
    """
    state = _reply_index_state(bind)
    if state == "valid":
        return
    # AUD-275: a plain CREATE INDEX takes a SHARE lock that blocks every message
    # write for the whole build. CONCURRENTLY runs outside the migration
    # transaction, which is why both statements sit in an autocommit block.
    with op.get_context().autocommit_block():
        if state == "invalid":
            op.drop_index(
                _INDEX_NAME,
                table_name=_TABLE_NAME,
                postgresql_concurrently=True,
            )
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            [_COLUMN_NAME],
            postgresql_concurrently=True,
        )


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
    _ensure_reply_index(bind)


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
