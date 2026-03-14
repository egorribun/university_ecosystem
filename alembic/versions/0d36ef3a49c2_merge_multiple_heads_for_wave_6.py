"""Merge multiple heads for Wave 6

Revision ID: 0d36ef3a49c2
Revises: 202603090001, 202603130003
Create Date: 2026-03-14 02:39:00.710104

"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "0d36ef3a49c2"  # pragma: allowlist secret
down_revision: str | None = ("202603090001", "202603130003")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
