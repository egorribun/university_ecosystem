from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202507310004"
down_revision = "202507310003"
branch_labels = None
depends_on = None


def _ensure_no_duplicates(bind) -> None:
    duplicates = bind.execute(
        sa.text(
            "SELECT lower(email) AS normalized, COUNT(*) AS count "
            "FROM users GROUP BY lower(email) HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicates:
        conflicts = ", ".join(row._mapping["normalized"] for row in duplicates)
        raise RuntimeError(
            f"Duplicate user emails found after normalization: {conflicts}"
        )


def upgrade() -> None:
    bind = op.get_bind()

    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "email" not in user_columns:
        return

    op.execute(sa.text("UPDATE users SET email = lower(email)"))

    _ensure_no_duplicates(bind)

    dialect = bind.dialect.name
    if dialect in {"postgresql", "sqlite"}:
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_lower_email "
                "ON users (lower(email))"
            )
        )
    else:
        op.create_index(
            "ux_users_lower_email",
            "users",
            [sa.text("lower(email)")],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect in {"postgresql", "sqlite"}:
        op.execute(sa.text("DROP INDEX IF EXISTS ux_users_lower_email"))
    else:
        op.drop_index("ux_users_lower_email", table_name="users")
