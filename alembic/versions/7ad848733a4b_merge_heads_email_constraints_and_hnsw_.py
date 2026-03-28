"""merge heads: email_constraints and hnsw_index

Revision ID: 7ad848733a4b
Revises: 202603230001, 33160e3a674f
Create Date: 2026-03-28 04:47:46.210433

"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "7ad848733a4b"  # pragma: allowlist secret
down_revision: str | None = ("202603230001", "33160e3a674f")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
