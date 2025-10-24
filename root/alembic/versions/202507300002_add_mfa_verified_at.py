from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202507300002"
down_revision: str | None = "202507300001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ACTIVE_SESSIONS_TABLE = "active_sessions"


def _column_names(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, _ACTIVE_SESSIONS_TABLE)
    indexes = _index_names(inspector, _ACTIVE_SESSIONS_TABLE)

    if "mfa_verified_at" not in columns:
        op.add_column(
            _ACTIVE_SESSIONS_TABLE,
            sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "ix_active_sessions_mfa_verified_at" not in indexes:
        op.create_index(
            "ix_active_sessions_mfa_verified_at",
            _ACTIVE_SESSIONS_TABLE,
            ["mfa_verified_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = _index_names(inspector, _ACTIVE_SESSIONS_TABLE)
    columns = _column_names(inspector, _ACTIVE_SESSIONS_TABLE)

    if "ix_active_sessions_mfa_verified_at" in indexes:
        op.drop_index(
            "ix_active_sessions_mfa_verified_at",
            table_name=_ACTIVE_SESSIONS_TABLE,
        )
    if "mfa_verified_at" in columns:
        op.drop_column(_ACTIVE_SESSIONS_TABLE, "mfa_verified_at")
