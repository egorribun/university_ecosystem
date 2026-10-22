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
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.execute("SET LOCAL statement_timeout = '60s'")

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
    op.execute(
        sa.text(
            "-- UNIQUE cannot be added NOT VALID in PostgreSQL; existing rows stay "
            "unmarked and this timeout-bounded revision validates atomically.\n"
            "-- squawk-ignore constraint-missing-not-valid\n"
            "ALTER TABLE groups ADD CONSTRAINT uq_groups_demo_seed_key "
            "UNIQUE (demo_seed_key)"
        )
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.execute("SET LOCAL statement_timeout = '60s'")

    # Drop only the marker schema. Group and schedule rows are preserved.
    op.drop_constraint("uq_groups_demo_seed_key", "groups", type_="unique")
    op.drop_column("groups", "demo_seed_key")
