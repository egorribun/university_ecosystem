"""init

Revision ID: b05ae64aaeef
Revises:
Create Date: 2025-05-29 03:49:18.226417

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "b05ae64aaeef"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    if context.is_offline_mode():
        return
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("event_attendance"):
        return
    columns = {column["name"] for column in inspector.get_columns("event_attendance")}
    if "attended" not in columns:
        return
    with op.batch_alter_table("event_attendance") as batch_op:
        batch_op.drop_column("attended")


def downgrade() -> None:
    """Downgrade schema."""

    if context.is_offline_mode():
        return
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("event_attendance"):
        return
    columns = {column["name"] for column in inspector.get_columns("event_attendance")}
    if "attended" in columns:
        return
    with op.batch_alter_table("event_attendance") as batch_op:
        batch_op.add_column(
            sa.Column("attended", sa.Boolean(), autoincrement=False, nullable=True)
        )
