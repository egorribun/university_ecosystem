"""Add pending_email column to users table.

Schema drift fix (2026-03-09): The ``pending_email`` column was added to the
``User`` SQLAlchemy model (``app/models/users.py``) but no Alembic migration
was ever created for it, causing an ``UndefinedColumnError`` whenever the ORM
tried to INSERT or SELECT from the ``users`` table using the current model.

The column stores a new (unconfirmed) e-mail address while the user still
owns the old one.  It is intentionally nullable: ``NULL`` means no pending
change is in progress.

Revision ID: 202603090001
Revises: 202603070001
Create Date: 2026-03-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603090001"
down_revision: str | None = "202603070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable pending_email VARCHAR column to users."""
    op.add_column(
        "users",
        sa.Column("pending_email", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Drop pending_email column from users."""
    op.drop_column("users", "pending_email")
