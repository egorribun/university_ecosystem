"""Add edited_at and deleted_at columns to messages (Wave 205 edit + soft-delete)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300002"
down_revision: str | None = "202605300001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "messages"
# Column names only — fresh sa.Column objects are constructed per upgrade() call so
# the up/down/up idempotency check never re-uses an object already bound to a Table.
_COLUMN_NAMES = ("edited_at", "deleted_at")


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Apply: add edited_at + deleted_at columns to messages."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    for name in _COLUMN_NAMES:
        if not _column_exists(bind, _TABLE_NAME, name):
            op.add_column(
                _TABLE_NAME, sa.Column(name, sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    """Revert: drop edited_at + deleted_at columns from messages."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    for name in reversed(_COLUMN_NAMES):
        if _column_exists(bind, _TABLE_NAME, name):
            op.drop_column(_TABLE_NAME, name)
