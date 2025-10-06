"""add parity to schedule

Revision ID: 4fa4374013f3
Revises: 7ad8a9a11478
Create Date: 2025-06-01 12:09:40.762927

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4fa4374013f3"
down_revision: Union[str, None] = "7ad8a9a11478"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "schedule" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("schedule")}
    if "parity" not in columns:
        op.add_column("schedule", sa.Column("parity", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "schedule" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("schedule")}
    if "parity" in columns:
        op.drop_column("schedule", "parity")
