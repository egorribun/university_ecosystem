from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202506010001"
down_revision: str | None = "202505250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "notifications"
_DEDUPE_COLUMN = sa.Column("dedupe_key", sa.String(length=255), nullable=True)
_DEDUPE_INDEX_NAME = "ix_notifications_user_dedupe"


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
    """Apply Add dedupe key to notifications."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _DEDUPE_COLUMN.name):
        op.add_column(_TABLE_NAME, _DEDUPE_COLUMN)

    if not _index_exists(bind, _TABLE_NAME, _DEDUPE_INDEX_NAME):
        op.create_index(
            _DEDUPE_INDEX_NAME,
            _TABLE_NAME,
            ["user_id", "dedupe_key"],
        )

    op.execute(
        sa.text(
            "UPDATE notifications SET dedupe_key = 'legacy:' || CAST(id AS TEXT) "
            "WHERE dedupe_key IS NULL"
        )
    )


def downgrade() -> None:
    """Revert Add dedupe key to notifications."""
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _index_exists(bind, _TABLE_NAME, _DEDUPE_INDEX_NAME):
        op.drop_index(_DEDUPE_INDEX_NAME, table_name=_TABLE_NAME)

    if _column_exists(bind, _TABLE_NAME, _DEDUPE_COLUMN.name):
        op.drop_column(_TABLE_NAME, _DEDUPE_COLUMN.name)
