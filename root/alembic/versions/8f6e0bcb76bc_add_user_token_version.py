"""add token_version to users

Revision ID: 8f6e0bcb76bc
Revises: ffe470bc9ca2
Create Date: 2024-05-13 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op


revision: str = "8f6e0bcb76bc"
down_revision: Union[str, Sequence[str], None] = "ffe470bc9ca2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = {table for table in inspector.get_table_names()}
    if "users" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "token_version" in columns:
        return

    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.execute(sa.text("UPDATE users SET token_version = 0 WHERE token_version IS NULL"))
    if bind.dialect.name != "sqlite":
        op.alter_column("users", "token_version", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = {table for table in inspector.get_table_names()}
    if "users" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "token_version" in columns:
        op.drop_column("users", "token_version")
