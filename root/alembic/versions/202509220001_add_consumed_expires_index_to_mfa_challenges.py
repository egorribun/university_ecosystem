"""Add composite index for MFA challenge cleanup"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202509220001"
down_revision: str | Sequence[str] | None = "202509210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "mfa_challenges"
_INDEX_NAME = "ix_mfa_challenges_consumed_expires"


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE_NAME):
        return
    if _index_exists(bind, _TABLE_NAME, _INDEX_NAME):
        return
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["consumed_at", "expires_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _index_exists(bind, _TABLE_NAME, _INDEX_NAME):
        return
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
