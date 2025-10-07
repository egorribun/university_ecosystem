"""add is_used to invite_codes

Revision ID: 6bdc356a128b
Revises: a4bfc1ba3076
Create Date: 2025-05-31 16:57:52.071516

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bdc356a128b"
down_revision: str | None = "a4bfc1ba3076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "invite_codes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("invite_codes")}
    if "is_used" in columns:
        return
    op.add_column("invite_codes", sa.Column("is_used", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    if "invite_codes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("invite_codes")}
    if "is_used" not in columns:
        return
    op.drop_column("invite_codes", "is_used")
