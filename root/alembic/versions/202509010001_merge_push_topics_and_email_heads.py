"""Merge push topic preferences and email normalization heads."""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision: str = "202509010001"
down_revision: tuple[str, str] | None = ("202506250001", "202507310004")
branch_labels = None
depends_on = None


def upgrade() -> None:  # noqa: D401 - Alembic migration hook.
    """Consolidate the divergent migration branches."""


def downgrade() -> None:  # noqa: D401 - Alembic migration hook.
    """No downgrade steps for merge migration."""
