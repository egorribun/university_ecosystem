"""Remove MFA recovery code support."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202509250001"
down_revision: str | None = "202509240001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_USERS_TABLE = "users"
_RECOVERY_TABLE = "mfa_recovery_codes"


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)

    if _USERS_TABLE in tables:
        user_columns = _column_names(inspector, _USERS_TABLE)
        user_indexes = _index_names(inspector, _USERS_TABLE)
        if "ix_users_mfa_recovery_codes_generated_at" in user_indexes:
            op.drop_index(
                "ix_users_mfa_recovery_codes_generated_at",
                table_name=_USERS_TABLE,
            )
        if "mfa_recovery_codes_generated_at" in user_columns:
            op.drop_column(_USERS_TABLE, "mfa_recovery_codes_generated_at")

    if _RECOVERY_TABLE in tables:
        op.drop_table(_RECOVERY_TABLE)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)

    if _USERS_TABLE in tables:
        user_columns = _column_names(inspector, _USERS_TABLE)
        user_indexes = _index_names(inspector, _USERS_TABLE)
        if "mfa_recovery_codes_generated_at" not in user_columns:
            op.add_column(
                _USERS_TABLE,
                sa.Column(
                    "mfa_recovery_codes_generated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )
        if (
            "ix_users_mfa_recovery_codes_generated_at" not in user_indexes
            and "mfa_recovery_codes_generated_at" in _column_names(inspector, _USERS_TABLE)
        ):
            op.create_index(
                "ix_users_mfa_recovery_codes_generated_at",
                _USERS_TABLE,
                ["mfa_recovery_codes_generated_at"],
            )

    tables = _table_names(sa.inspect(bind))
    if _RECOVERY_TABLE not in tables:
        op.create_table(
            _RECOVERY_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(f"{_USERS_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_hash", sa.String(length=255), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "code_hash", name="uq_mfa_recovery_codes_hash"),
        )
        op.create_index(f"ix_{_RECOVERY_TABLE}_user_id", _RECOVERY_TABLE, ["user_id"])
        op.create_index(f"ix_{_RECOVERY_TABLE}_used_at", _RECOVERY_TABLE, ["used_at"])
