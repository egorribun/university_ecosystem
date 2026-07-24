"""Add HMAC cryptographic hash chaining columns (prev_hash, hash) to stored_events table.

Revision ID: 202607240001
Revises: 202607230001
Create Date: 2026-07-24 21:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202607240001"
down_revision: str | Sequence[str] | None = "202607230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "stored_events" in tables:
        columns = [col["name"] for col in inspector.get_columns("stored_events")]
        if "prev_hash" not in columns:
            op.add_column(
                "stored_events",
                sa.Column("prev_hash", sa.String(length=64), nullable=True),
            )
        if "hash" not in columns:
            op.add_column(
                "stored_events",
                sa.Column("hash", sa.String(length=64), nullable=True),
            )
            op.create_index(
                "ix_stored_events_hash",
                "stored_events",
                ["hash"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "stored_events" in tables:
        columns = [col["name"] for col in inspector.get_columns("stored_events")]
        indexes = {idx["name"] for idx in inspector.get_indexes("stored_events")}

        if "ix_stored_events_hash" in indexes:
            op.drop_index("ix_stored_events_hash", table_name="stored_events")
        if "hash" in columns:
            op.drop_column("stored_events", "hash")
        if "prev_hash" in columns:
            op.drop_column("stored_events", "prev_hash")
