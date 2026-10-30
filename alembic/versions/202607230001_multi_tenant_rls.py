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

# AUD-277/360/450: privileged access is granted by membership in this dedicated
# NOLOGIN role, never by a GUC that any SQL session can set. Application
# sessions are scoped to one tenant through app.current_tenant instead.
BYPASS_ROLE = "ue_rls_bypass"

# A row is visible only to a bypass-role member or to the tenant it belongs to.
# NULL tenant_id rows therefore stay hidden from every tenant session (AUD-360).
_TENANT_PREDICATE = (
    f"pg_has_role(current_user, '{BYPASS_ROLE}', 'MEMBER') "
    "OR (tenant_id IS NOT NULL "
    "AND tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
)


def _create_bypass_role() -> None:
    """Create the NOLOGIN bypass role once, so policies can reference it."""
    op.execute(  # nosemgrep
        sa.text(  # nosemgrep
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles "
            "WHERE rolname = 'ue_rls_bypass') THEN "
            "CREATE ROLE ue_rls_bypass NOLOGIN; END IF; END $$;"
        )
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
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_tenants_slug",
                "tenants",
                ["slug"],
                unique=True,
                postgresql_concurrently=True,
            )
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_tenants_domain",
                "tenants",
                ["domain"],
                unique=True,
                postgresql_concurrently=True,
            )
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_tenants_is_active",
                "tenants",
                ["is_active"],
                unique=False,
                postgresql_concurrently=True,
            )

    # The policies below reference the bypass role, so it must exist first.
    if bind.dialect.name == "postgresql":
        _create_bypass_role()

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
            if is_partitioned:
                op.create_index(
                    f"ix_{table_name}_tenant_id",
                    table_name,
                    ["tenant_id"],
                    unique=False,
                    postgresql_concurrently=False,
                )
            else:
                with op.get_context().autocommit_block():
                    op.create_index(
                        f"ix_{table_name}_tenant_id",
                        table_name,
                        ["tenant_id"],
                        unique=False,
                        postgresql_concurrently=True,
                    )

        # 3. Enable RLS and create the tenant policy on PostgreSQL
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
            # AUD-277: the former permissive USING (true) policy is removed. The
            # tenant predicate is the only policy that grants row access on the
            # tables that have no other permissive policy.
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
            # messages keeps its participant permissive policy, so the tenant
            # predicate must stay restrictive there to be ANDed with it.
            policy_type = "RESTRICTIVE" if table_name == "messages" else "PERMISSIVE"
            op.execute(  # nosemgrep
                sa.text(  # nosemgrep
                    f"CREATE POLICY tenant_isolation_policy ON {table_name} AS {policy_type} "
                    f"FOR ALL USING ({_TENANT_PREDICATE}) "
                    f"WITH CHECK ({_TENANT_PREDICATE});"
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

    if bind.dialect.name == "postgresql":
        op.execute(  # nosemgrep
            sa.text(  # nosemgrep
                "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles "
                "WHERE rolname = 'ue_rls_bypass') THEN "
                "DROP ROLE ue_rls_bypass; END IF; END $$;"
            )
        )
