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

    # Skip on SQLite - this table uses PostgreSQL-specific types
    if bind.dialect.name == "sqlite":
        return

    if not _table_exists(inspector, table_name):
        op.create_table(
            table_name,
            # PostgreSQL partitioned tables require every unique/PK constraint to
            # include all partitioning columns.  Since we partition by created_at,
            # the PK must be (id, created_at) — not just (id).
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("subject_user_id", sa.Integer(), nullable=True),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", sa.String(length=128), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("context", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", "created_at"),
            sa.ForeignKeyConstraint(
                ["actor_user_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["subject_user_id"], ["users.id"], ondelete="SET NULL"
            ),
            # Declare as RANGE-partitioned so fresh CI schemas accept inserts.
            # The DEFAULT partition below absorbs rows until monthly partitions
            # are created by migration 202607020001.
            postgresql_partition_by="RANGE (created_at)",
        )
        # Create the DEFAULT partition immediately so any INSERT succeeds before
        # the monthly-partition migration runs.
        if bind.dialect.name == "postgresql":
            op.execute(
                sa.text(
                    "CREATE TABLE IF NOT EXISTS data_access_logs_default "
                    "PARTITION OF data_access_logs DEFAULT"
                )
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
    bind = op.get_bind()

    # Skip on SQLite
    if bind.dialect.name == "sqlite":
        return

    inspector = sa.inspect(bind)
    table_name = "data_access_logs"

    # Skip if table doesn't exist
    if not _table_exists(inspector, table_name):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}

    if "ix_data_access_logs_resource" in existing_indexes:
        op.drop_index("ix_data_access_logs_resource", table_name=table_name)
    if "ix_data_access_logs_created_at" in existing_indexes:
        op.drop_index("ix_data_access_logs_created_at", table_name=table_name)
    if "ix_data_access_logs_subject" in existing_indexes:
        op.drop_index("ix_data_access_logs_subject", table_name=table_name)
    if "ix_data_access_logs_actor" in existing_indexes:
        op.drop_index("ix_data_access_logs_actor", table_name=table_name)
    op.drop_table(table_name)
