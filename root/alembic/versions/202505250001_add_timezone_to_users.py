"""Add timezone column to users"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202505250001"
down_revision: Union[str, None] = "202505200001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "users"
_TIMEZONE_COLUMN = sa.Column("timezone", sa.String(length=64), nullable=True)


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Apply Add timezone column to users."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _TIMEZONE_COLUMN.name):
        op.add_column(_TABLE_NAME, _TIMEZONE_COLUMN)


def downgrade() -> None:
    """Revert Add timezone column to users."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _column_exists(bind, _TABLE_NAME, _TIMEZONE_COLUMN.name):
        op.drop_column(_TABLE_NAME, _TIMEZONE_COLUMN.name)
