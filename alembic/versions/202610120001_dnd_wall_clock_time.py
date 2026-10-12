"""Store quiet-hour boundaries as local wall-clock times.

The IANA zone remains in user_preferences.timezone. PostgreSQL timetz stores a
per-value offset without a date, so that old offset cannot be recovered after
conversion and downgrade is deliberately blocked.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610120001"
down_revision: str | None = "202610010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

downgrade_policy: str = "irreversible"
downgrade_reason: str = (
    "quiet-hour wall-clock conversion discards per-value TIMETZ offsets"
)


def upgrade() -> None:
    """Keep each stored clock reading and discard its unusable fixed offset."""
    op.alter_column(
        "user_preferences",
        "dnd_start",
        existing_type=sa.Time(timezone=True),
        type_=sa.Time(timezone=False),
        existing_nullable=True,
        postgresql_using="dnd_start::text::time",
    )
    op.alter_column(
        "user_preferences",
        "dnd_end",
        existing_type=sa.Time(timezone=True),
        type_=sa.Time(timezone=False),
        existing_nullable=True,
        postgresql_using="dnd_end::text::time",
    )


def downgrade() -> None:
    """Do not invent offsets that the local wall-clock model no longer has."""
    raise RuntimeError(downgrade_reason)
