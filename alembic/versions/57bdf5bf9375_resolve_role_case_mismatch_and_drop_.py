"""resolve role case mismatch and drop legacy constraint

Revision ID: 57bdf5bf9375
Revises: 3081a2b724cc
Create Date: 2026-01-20 17:19:16.422393

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "57bdf5bf9375"
down_revision: str | None = "3081a2b724cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    # 1. Ensure all existing roles are lowercase
    # This was partially done in 148642dd1207 but we do it again for robustness
    if is_postgres:
        op.execute("""
            UPDATE users
            SET role = LOWER(role::text)::userrole
            WHERE role::text != LOWER(role::text)
        """)
    else:
        op.execute("UPDATE users SET role = LOWER(role)")

    # 2. Drop the problematic constraint if it exists
    # We use raw SQL for Postgres to ensure we can drop it by name
    if is_postgres:
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_valid")
    else:
        # For SQLite/others, we check if it exists first
        from sqlalchemy import inspect

        inspector = inspect(conn)
        constraints = [
            c["name"] for c in inspector.get_check_constraints("users") if c["name"]
        ]

        if "ck_users_role_valid" in constraints:
            with op.batch_alter_table("users") as batch_op:
                batch_op.drop_constraint("ck_users_role_valid", type_="check")


def downgrade() -> None:
    """Downgrade schema."""
    # We don't want to restore the problematic constraint as it breaks registration.
    # However, for symmetry we could add a "safe" version if needed.
    # Given the goal is to REMOVE the blocker, we keep it simple.
    pass
