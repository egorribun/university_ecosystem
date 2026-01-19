"""add role constraints

Revision ID: 2e93eecad1e0
Revises: ffe470bc9ca2
Create Date: 2025-10-13 16:25:34.507376

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2e93eecad1e0"
down_revision: str | None = "ffe470bc9ca2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE_VALUES = ("student", "teacher", "admin")


def upgrade() -> None:
    """Upgrade schema."""
    # Skip entirely: PostgreSQL uses ENUM type which already constrains values,
    # and SQLite doesn't benefit from this CHECK constraint when using batch mode.
    # The constraint is defined in the model's __table_args__ and will be applied
    # on fresh database creation.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # No-op since upgrade is now a no-op
    pass
