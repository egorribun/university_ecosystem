"""add about to event

Revision ID: 7ea701e08870
Revises: 7db0b7a03e37
Create Date: 2025-06-04 01:08:34.347366

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ea701e08870"
down_revision: str | None = "7db0b7a03e37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("events")}
    if "about" not in columns:
        op.add_column("events", sa.Column("about", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("events")}
    if "about" in columns:
        op.drop_column("events", "about")
