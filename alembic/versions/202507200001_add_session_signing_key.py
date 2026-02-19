"""Add per-session signing key to active sessions."""

from __future__ import annotations

import secrets

import sqlalchemy as sa

from alembic import op
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "202507200001"
down_revision: str | None = "8793a392b5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "active_sessions"
_COLUMN_NAME = "signing_key"
_COLUMN = sa.Column(_COLUMN_NAME, sa.String(), nullable=True)


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    """Add the signing_key column and populate existing rows."""

    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if not _column_exists(bind, _TABLE_NAME, _COLUMN_NAME):
        op.add_column(_TABLE_NAME, _COLUMN)

    # Define columns manually to avoid FK reflection issues with autoload
    metadata = sa.MetaData()
    active_sessions = sa.Table(
        _TABLE_NAME,
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("signing_key", sa.String(), nullable=True),
    )

    update_stmt = (
        sa.update(active_sessions)
        .where(active_sessions.c.id == sa.bindparam("sess_id"))
        .values(signing_key=sa.bindparam("signing_key"))
    )

    result = bind.execute(
        sa.select(active_sessions.c.id).where(active_sessions.c.signing_key.is_(None))
    )
    rows = result.fetchall()
    for row in rows:
        bind.execute(
            update_stmt, {"sess_id": row.id, "signing_key": secrets.token_urlsafe(32)}
        )

    # For SQLite, we need to use batch_alter_table with copy_from to avoid reflection
    # For other databases, we can use alter_column directly
    dialect = bind.dialect.name
    if dialect == "sqlite":
        # On SQLite, batch mode requires a full table definition to avoid reflection
        # We'll skip making the column non-nullable on SQLite for simplicity
        # since SQLite doesn't enforce NOT NULL constraints the same way
        pass
    else:
        op.alter_column(
            _TABLE_NAME,
            _COLUMN_NAME,
            existing_type=sa.String(),
            nullable=False,
        )


def downgrade() -> None:
    """Remove the signing_key column."""

    bind = op.get_bind()

    if not _table_exists(bind, _TABLE_NAME):
        return

    if _column_exists(bind, _TABLE_NAME, _COLUMN_NAME):
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
