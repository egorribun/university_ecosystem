"""add lesson_type to schedule

Revision ID: 30fa2627aa5e
Revises: 4fa4374013f3
Create Date: 2025-06-01 12:30:15.217983

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "30fa2627aa5e"
down_revision: str | None = "4fa4374013f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "schedule" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("schedule")}
    if "lesson_type" not in columns:
        op.add_column("schedule", sa.Column("lesson_type", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "schedule" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("schedule")}
    if "lesson_type" in columns:
        op.drop_column("schedule", "lesson_type")
