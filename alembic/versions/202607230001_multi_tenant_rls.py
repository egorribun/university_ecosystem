"""Multi-tenant Row Level Security (RLS) and tenants schema.

Revision ID: 202607230001
Revises: a3f8c1d2e047
Create Date: 2026-07-23 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202607230001"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "a3f8c1d2e047"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_TABLES = (
    "users",
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Create tenants table if not exists
    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("domain", sa.String(length=256), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
            sa.UniqueConstraint("domain"),
        )
        op.create_index(
            "ix_tenants_slug",
            "tenants",
            ["slug"],
            unique=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_tenants_domain",
            "tenants",
            ["domain"],
            unique=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_tenants_is_active",
            "tenants",
            ["is_active"],
            unique=False,
            postgresql_concurrently=True,
        )

    # 2. Add tenant_id columns, foreign keys, and indexes across core entity tables
    for table_name in CORE_TABLES:
        if table_name not in tables:
            continue

        columns = [col["name"] for col in inspector.get_columns(table_name)]
        if "tenant_id" not in columns:
            op.add_column(
                table_name,
                sa.Column(
                    "tenant_id",
                    sa.UUID(),
                    sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                    nullable=True,
                ),
            )
            is_partitioned = table_name in (
                "notifications",
                "data_access_logs",
                "notification_deliveries",
                "failed_login_attempts",
            )
            op.create_index(
                f"ix_{table_name}_tenant_id",
                table_name,
                ["tenant_id"],
                unique=False,
                postgresql_concurrently=not is_partitioned,
            )

        # 3. Enable RLS and create isolation policy on PostgreSQL
        if bind.dialect.name == "postgresql":
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;"
                )
            )
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;"
                )
            )
            if table_name != "messages":
                op.execute(  # nosemgrep
                    sa.text(  # nosemgrep
                        f"DROP POLICY IF EXISTS default_permissive_policy ON {table_name};"
                    )
                )
                op.execute(  # nosemgrep
                    sa.text(  # nosemgrep
                        f"CREATE POLICY default_permissive_policy ON {table_name} AS PERMISSIVE "
                        f"USING (true) WITH CHECK (true);"
                    )
                )
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};"
                )
            )
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"CREATE POLICY tenant_isolation_policy ON {table_name} AS RESTRICTIVE "
                    f"USING (current_setting('app.bypass_rls', true) = 'on' "
                    f"OR tenant_id IS NULL "
                    f"OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    for table_name in CORE_TABLES:
        if table_name not in tables:
            continue

        if bind.dialect.name == "postgresql":
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"DROP POLICY IF EXISTS default_permissive_policy ON {table_name};"
                )
            )
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};"
                )
            )
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;"
                )
            )

        columns = [col["name"] for col in inspector.get_columns(table_name)]
        if "tenant_id" in columns:
            op.drop_index(f"ix_{table_name}_tenant_id", table_name=table_name)
            op.drop_column(table_name, "tenant_id")

    if "tenants" in tables:
        op.drop_table("tenants")
