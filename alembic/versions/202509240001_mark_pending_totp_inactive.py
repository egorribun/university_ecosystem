from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202509240001"
down_revision: str | None = "202509230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "mfa_totp_enrollments"


def _alter_is_active_default(server_default: sa.sql.elements.TextClause) -> None:
    """Adjust the default in a dialect-friendly way."""

    bind = op.get_bind()
    alter_kwargs = {
        "existing_type": sa.Boolean(),
        "existing_nullable": False,
        "server_default": server_default,
    }
    if bind.dialect.name == "sqlite":
        # SQLite does not support ``ALTER TABLE .. ALTER COLUMN`` syntax.
        # batch_alter_table would require table reflection which fails if FK
        # target tables don't exist. Skip this on SQLite for CI compatibility.
        return
    from typing import Any, cast

    op.alter_column(_TABLE_NAME, "is_active", **cast(dict[str, Any], alter_kwargs))


def _table_exists(inspector) -> bool:
    return _TABLE_NAME in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector):
        return

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            """
            UPDATE mfa_totp_enrollments
            SET is_active = FALSE
            WHERE confirmed_at IS NULL AND is_active = TRUE
            """
        )
    )

    _alter_is_active_default(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "false"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector):
        return

    _alter_is_active_default(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "true"
        )
    )

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            """
            UPDATE mfa_totp_enrollments
            SET is_active = TRUE
            WHERE confirmed_at IS NULL AND is_active = FALSE
            """
        )
    )
