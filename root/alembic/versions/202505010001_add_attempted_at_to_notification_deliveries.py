"""Add attempted_at column to notification deliveries."""

import textwrap
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202505010001"
down_revision: Union[str, None] = "202503150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "notification_deliveries"
_COLUMN_NAME = "attempted_at"
_INDEX_NAME = "ix_notification_deliveries_attempted_at"


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
    """Apply Add attempted_at column to notification deliveries."""
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _COLUMN_NAME):
        with op.batch_alter_table(_TABLE_NAME) as batch_op:
            batch_op.add_column(
                sa.Column(_COLUMN_NAME, sa.DateTime(timezone=True), nullable=True)
            )

        # Prefer historical timestamps when available to avoid inflating retention windows.
        op.execute(
            sa.text(
                textwrap.dedent(
                    """
                    UPDATE {table} AS nd
                    SET {column} = COALESCE(nd.delivered_at, n.created_at, NOW())
                    FROM notifications AS n
                    WHERE nd.notification_id = n.id AND nd.{column} IS NULL
                    """
                ).format(table=_TABLE_NAME, column=_COLUMN_NAME)
            )
        )
        op.execute(
            sa.text(
                textwrap.dedent(
                    """
                    UPDATE {table}
                    SET {column} = NOW()
                    WHERE {column} IS NULL
                    """
                ).format(table=_TABLE_NAME, column=_COLUMN_NAME)
            )
        )

        with op.batch_alter_table(_TABLE_NAME) as batch_op:
            batch_op.alter_column(
                _COLUMN_NAME,
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            )
    else:
        with op.batch_alter_table(_TABLE_NAME) as batch_op:
            batch_op.alter_column(
                _COLUMN_NAME,
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            )

    if not _index_exists(bind, _TABLE_NAME, _INDEX_NAME):
        try:
            op.create_index(
                _INDEX_NAME,
                _TABLE_NAME,
                [_COLUMN_NAME],
                unique=False,
                if_not_exists=True,
            )
        except TypeError:
            if not _index_exists(bind, _TABLE_NAME, _INDEX_NAME):
                op.create_index(
                    _INDEX_NAME,
                    _TABLE_NAME,
                    [_COLUMN_NAME],
                    unique=False,
                )


def downgrade() -> None:
    """Revert Add attempted_at column to notification deliveries."""
    bind = op.get_bind()
    if not _column_exists(bind, _TABLE_NAME, _COLUMN_NAME):
        return

    if _index_exists(bind, _TABLE_NAME, _INDEX_NAME):
        try:
            op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME, if_exists=True)
        except TypeError:
            if _index_exists(bind, _TABLE_NAME, _INDEX_NAME):
                op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        batch_op.drop_column(_COLUMN_NAME)
