"""W136 SW4: failed_login_attempts.user_id nullable + ondelete SET NULL.

Closes W135 §Honesty #3. Pre-W136 the production schema enforced NOT NULL on
``user_id`` via the inherited UserFK mixin (model-side ``nullable=False``),
which contradicted the original migration ``2025070100011`` intent that
``user_id`` be ``nullable=True``. Result: ``register_failed_attempt(email,
user_id=None)`` for unknown emails raised ``NotNullViolation`` — surfaced
during W135 SW2 Docker chain verification.

W136 SW4 restores the original intent: user_id nullable + ondelete SET NULL
so failed-login rows survive user deletion (audit trail).

Revision ID: 202605070001
Revises: 202603280001
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202605070001"
down_revision: str | None = "202603280001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make failed_login_attempts.user_id nullable + change FK ondelete to SET NULL."""
    bind = op.get_bind()
    if bind is None:
        return

    inspector = sa.inspect(bind)
    if "failed_login_attempts" not in inspector.get_table_names():
        return

    # Drop existing FK so we can re-create with SET NULL action.
    fks = inspector.get_foreign_keys("failed_login_attempts")
    for fk in fks:
        if fk["constrained_columns"] == ["user_id"] and fk["name"]:
            op.drop_constraint(fk["name"], "failed_login_attempts", type_="foreignkey")

    # Make column nullable (no-op if already nullable; idempotent on re-runs).
    op.alter_column(
        "failed_login_attempts",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True)
        if bind.dialect.name == "postgresql"
        else sa.String(36),
        nullable=True,
    )

    # Re-create FK with SET NULL action.
    op.create_foreign_key(
        "fk_failed_login_attempts_user_id",
        "failed_login_attempts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Revert: user_id NOT NULL + ondelete CASCADE.

    NOTE: This downgrade DELETEs all failed_login_attempts rows where
    user_id IS NULL (orphaned attempts) before tightening the constraint,
    otherwise the ALTER COLUMN would fail.
    """
    bind = op.get_bind()
    if bind is None:
        return

    inspector = sa.inspect(bind)
    if "failed_login_attempts" not in inspector.get_table_names():
        return

    # Purge NULL rows so NOT NULL ALTER succeeds.
    op.execute(sa.text("DELETE FROM failed_login_attempts WHERE user_id IS NULL"))

    fks = inspector.get_foreign_keys("failed_login_attempts")
    for fk in fks:
        if fk["constrained_columns"] == ["user_id"] and fk["name"]:
            op.drop_constraint(fk["name"], "failed_login_attempts", type_="foreignkey")

    op.alter_column(
        "failed_login_attempts",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True)
        if bind.dialect.name == "postgresql"
        else sa.String(36),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_failed_login_attempts_user_id",
        "failed_login_attempts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
