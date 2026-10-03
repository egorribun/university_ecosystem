"""Retire unused runtime models while retaining their database tables.

The historical filename is kept to preserve the revision identity. Neither
upgrade nor downgrade removes schemas or rows: the application no longer uses
``user_stats`` or ``vector_chunks``, but deleting them requires a separately
reviewed maintenance plan and backup evidence. Alembic still owns and compares
their exact schemas through ``app.core.db.retained_table_metadata``.

This revision is part of the unreleased consolidation change. A database that
already ran its earlier destructive draft needs restoration from a backup;
recreating empty tables would not recover its data.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "202610010001"
down_revision: str | None = "202609300002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Retain both historical tables and all their data during online rollout."""


def downgrade() -> None:
    """The prior revision already owns these unchanged schemas and rows."""
