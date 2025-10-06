"""add department and position to user

Revision ID: 2bc18c38157c
Revises: 6bdc356a128b
Create Date: 2025-05-31 17:47:10.978803

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2bc18c38157c"
down_revision: Union[str, None] = "6bdc356a128b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "department" not in columns:
        op.add_column("users", sa.Column("department", sa.String(), nullable=True))
    if "position" not in columns:
        op.add_column("users", sa.Column("position", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "position" in columns:
        op.drop_column("users", "position")
    if "department" in columns:
        op.drop_column("users", "department")
