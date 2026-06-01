"""Add read_at column to messages (Wave 203 read receipts)"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605300001"
down_revision: str | None = "202605070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "messages"
_READ_AT_COLUMN = sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Apply Add read_at column to messages."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _READ_AT_COLUMN.name):
        op.add_column(_TABLE_NAME, _READ_AT_COLUMN)


def downgrade() -> None:
    """Revert Add read_at column to messages."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _column_exists(bind, _TABLE_NAME, _READ_AT_COLUMN.name):
        op.drop_column(_TABLE_NAME, _READ_AT_COLUMN.name)
