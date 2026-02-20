"""add_functional_email_index

Revision ID: f2d2414a6b67
Revises: 202602050001
Create Date: 2026-02-19 23:39:48.536098

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2d2414a6b67"
down_revision: str | None = "202602050001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_users_email", table_name="users")
    op.create_index(
        "ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_email_lower", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
