"""merge_heads

Revision ID: 202602270001
Revises: 202602260001, 4e39503c07cd
Create Date: 2026-02-27 10:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "202602270001"
down_revision: str | None = ("202602260001", "4e39503c07cd")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
