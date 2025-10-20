"""Add client metadata columns to active sessions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "202505200001"
down_revision: Union[str, None] = "202505010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "active_sessions"
_IP_ADDRESS_COLUMN = sa.Column("ip_address", sa.String(length=64), nullable=True)
_USER_AGENT_COLUMN = sa.Column("user_agent", sa.String(length=512), nullable=True)
_LAST_SEEN_COLUMN = sa.Column(
    "last_seen_at", sa.DateTime(timezone=True), nullable=True
)
_LAST_SEEN_INDEX_NAME = "ix_active_sessions_last_seen_at"


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
    """Apply Add client metadata columns to active sessions."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _IP_ADDRESS_COLUMN.name):
        op.add_column(_TABLE_NAME, _IP_ADDRESS_COLUMN)

    if not _column_exists(bind, _TABLE_NAME, _USER_AGENT_COLUMN.name):
        op.add_column(_TABLE_NAME, _USER_AGENT_COLUMN)

    if not _column_exists(bind, _TABLE_NAME, _LAST_SEEN_COLUMN.name):
        op.add_column(_TABLE_NAME, _LAST_SEEN_COLUMN)

    if not _index_exists(bind, _TABLE_NAME, _LAST_SEEN_INDEX_NAME):
        op.create_index(
            _LAST_SEEN_INDEX_NAME,
            _TABLE_NAME,
            [_LAST_SEEN_COLUMN.name],
            unique=False,
        )


def downgrade() -> None:
    """Revert Add client metadata columns to active sessions."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _index_exists(bind, _TABLE_NAME, _LAST_SEEN_INDEX_NAME):
        op.drop_index(_LAST_SEEN_INDEX_NAME, table_name=_TABLE_NAME)

    if _column_exists(bind, _TABLE_NAME, _LAST_SEEN_COLUMN.name):
        op.drop_column(_TABLE_NAME, _LAST_SEEN_COLUMN.name)

    if _column_exists(bind, _TABLE_NAME, _USER_AGENT_COLUMN.name):
        op.drop_column(_TABLE_NAME, _USER_AGENT_COLUMN.name)

    if _column_exists(bind, _TABLE_NAME, _IP_ADDRESS_COLUMN.name):
        op.drop_column(_TABLE_NAME, _IP_ADDRESS_COLUMN.name)
