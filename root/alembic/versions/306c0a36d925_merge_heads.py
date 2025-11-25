"""merge_heads

Revision ID: 306c0a36d925
Revises: 202511240001, b85f4f3edc89
Create Date: 2025-11-24 21:21:59.394861

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "306c0a36d925"
down_revision: str | None = ("202511240001", "b85f4f3edc89")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
