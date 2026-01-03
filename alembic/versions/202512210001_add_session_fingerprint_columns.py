"""Add fingerprint columns to active sessions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202512210001"
down_revision: str | None = "d0b0cb4c1910"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "active_sessions"
_ACCEPT_LANGUAGE_COLUMN = sa.Column(
    "accept_language", sa.String(length=256), nullable=True
)
_FINGERPRINT_HASH_COLUMN = sa.Column(
    "fingerprint_hash", sa.String(length=64), nullable=True
)
_FINGERPRINT_INDEX_NAME = "ix_active_sessions_fingerprint_hash"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(ix.get("name") == index_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Add accept_language and fingerprint_hash columns to active_sessions."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _ACCEPT_LANGUAGE_COLUMN.name):
        op.add_column(_TABLE_NAME, _ACCEPT_LANGUAGE_COLUMN)

    if not _column_exists(bind, _TABLE_NAME, _FINGERPRINT_HASH_COLUMN.name):
        op.add_column(_TABLE_NAME, _FINGERPRINT_HASH_COLUMN)

    if not _index_exists(bind, _TABLE_NAME, _FINGERPRINT_INDEX_NAME):
        op.create_index(
            _FINGERPRINT_INDEX_NAME,
            _TABLE_NAME,
            [_FINGERPRINT_HASH_COLUMN.name],
            unique=False,
        )


def downgrade() -> None:
    """Remove accept_language and fingerprint_hash columns from active_sessions."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _index_exists(bind, _TABLE_NAME, _FINGERPRINT_INDEX_NAME):
        op.drop_index(_FINGERPRINT_INDEX_NAME, table_name=_TABLE_NAME)

    if _column_exists(bind, _TABLE_NAME, _FINGERPRINT_HASH_COLUMN.name):
        op.drop_column(_TABLE_NAME, _FINGERPRINT_HASH_COLUMN.name)

    if _column_exists(bind, _TABLE_NAME, _ACCEPT_LANGUAGE_COLUMN.name):
        op.drop_column(_TABLE_NAME, _ACCEPT_LANGUAGE_COLUMN.name)
