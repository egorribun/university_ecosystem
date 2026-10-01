"""Add a private ownership key for the synthetic demo study group."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202609300002"
down_revision: str | None = "202609300001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing groups remain unmarked. Their old natural key (name/course/
    # faculty) cannot prove ownership, so the seeder rejects an unmarked
    # canonical collision. Recover a legacy seeded group only after an
    # operator verifies its provenance, then set demo_seed_key to
    # `ue-demo-v1:group:class` for that exact group ID in a reviewed one-off
    # transaction. Never adopt a group based only on its visible fields.
    op.add_column(
        "groups",
        sa.Column("demo_seed_key", sa.String(length=96), nullable=True),
    )
    op.create_unique_constraint("uq_groups_demo_seed_key", "groups", ["demo_seed_key"])


def downgrade() -> None:
    # Drop only the marker schema. Group and schedule rows are preserved.
    op.drop_constraint("uq_groups_demo_seed_key", "groups", type_="unique")
    op.drop_column("groups", "demo_seed_key")
