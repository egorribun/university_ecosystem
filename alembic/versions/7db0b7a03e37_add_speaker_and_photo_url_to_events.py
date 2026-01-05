"""add speaker and photo_url to events

Revision ID: 7db0b7a03e37
Revises: 30fa2627aa5e
Create Date: 2025-06-02 17:03:26.759896

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7db0b7a03e37"
down_revision: str | None = "30fa2627aa5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("events")}
    if "speaker" not in columns:
        op.add_column("events", sa.Column("speaker", sa.String(), nullable=True))
    if "image_url" not in columns:
        op.add_column("events", sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("events")}
    if "image_url" in columns:
        op.drop_column("events", "image_url")
    if "speaker" in columns:
        op.drop_column("events", "speaker")
