"""Add data access logs table

Revision ID: 202507010001
Revises: 202506200001
Create Date: 2025-07-01 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202507010001"
down_revision: str | None = "202506200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "data_access_logs"

    if not _table_exists(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("subject_user_id", sa.Integer(), nullable=True),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", sa.String(length=128), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("context", sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["actor_user_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["subject_user_id"], ["users.id"], ondelete="SET NULL"
            ),
        )

    inspector = sa.inspect(bind)
    existing_indexes = (
        {index["name"] for index in inspector.get_indexes(table_name)}
        if _table_exists(inspector, table_name)
        else set()
    )

    indexes = {
        "ix_data_access_logs_actor": ["actor_user_id"],
        "ix_data_access_logs_subject": ["subject_user_id"],
        "ix_data_access_logs_created_at": ["created_at"],
        "ix_data_access_logs_resource": ["resource_type", "resource_id"],
    }

    for name, columns in indexes.items():
        if name not in existing_indexes:
            op.create_index(name, table_name, columns)


def downgrade() -> None:
    op.drop_index("ix_data_access_logs_resource", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_created_at", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_subject", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_actor", table_name="data_access_logs")
    op.drop_table("data_access_logs")
