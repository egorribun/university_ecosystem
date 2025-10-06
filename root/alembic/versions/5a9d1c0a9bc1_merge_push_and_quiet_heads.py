"""merge push subscriptions and quiet hours branches"""

from typing import Sequence, Union

revision: str = "5a9d1c0a9bc1"
down_revision: Union[str, tuple[str, ...], None] = (
    "23d991e593b5",
    "f9d2b1f5e2d0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge heads without applying additional DDL."""
    # No-op merge revision to join divergent heads.
    pass


def downgrade() -> None:
    """Downgrade is a no-op; merge nodes cannot be undone automatically."""
    pass
