"""merge_heads

Revision ID: 125613bc3543
Revises: 202603140004, 202603170003, wave14_composite_indexes
Create Date: 2026-03-19 23:24:36.124930

"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "125613bc3543"
down_revision: str | None = ("202603140004", "202603170003", "wave14_composite_indexes")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
