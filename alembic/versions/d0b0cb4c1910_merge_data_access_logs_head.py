"""Merge data access logs head into main branch

Revision ID: d0b0cb4c1910
Revises: 202507010001, 306c0a36d925
Create Date: 2025-07-15 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "d0b0cb4c1910"
down_revision: str | Sequence[str] | None = ("202507010001", "306c0a36d925")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge heads."""
    pass


def downgrade() -> None:
    """Unmerge heads."""
    pass
