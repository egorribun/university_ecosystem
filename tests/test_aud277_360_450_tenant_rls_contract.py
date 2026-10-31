"""Characterize historical tenant RLS and the currently mapped write path.

These assertions describe the existing migration, including its limitations;
they are not acceptance of tenant isolation. A future forward migration must
replace the corresponding characterization with its own security contract.
"""

from __future__ import annotations

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/202607230001_multi_tenant_rls.py"
MESSAGE_MIGRATION = ROOT / "alembic/versions/202603170003_enable_rls_on_messages.py"


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"audit_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture_tenant_upgrade(
    monkeypatch: pytest.MonkeyPatch,
    tables: tuple[str, ...] | None = None,
    *,
    missing_tenant_column: bool = False,
    tenants_present: bool = True,
    dialect: str = "postgresql",
) -> tuple[ModuleType, list[str], list[Any]]:
    """Run the historical upgrade against an inspector/DDL recording adapter."""
    migration = _load_migration(MIGRATION)
    selected = tables if tables is not None else migration.CORE_TABLES
    statements: list[str] = []
    columns: list[Any] = []
    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    inspector = SimpleNamespace(
        get_table_names=lambda: [
            *(["tenants"] if tenants_present else []),
            *selected,
        ],
        get_columns=lambda _name: []
        if missing_tenant_column
        else [{"name": "tenant_id"}],
    )

    class Operations:
        def get_bind(self) -> Any:
            return bind

        def execute(self, statement: Any) -> None:
            statements.append(str(statement))

        def add_column(self, _name: str, column: Any) -> None:
            columns.append(column)

        def create_table(self, name: str, *_args: Any, **_kwargs: Any) -> None:
            statements.append(f"-- create_table {name}")

        def get_context(self) -> Any:
            return self

        def autocommit_block(self) -> Any:
            return nullcontext()

        def create_index(self, *args: Any, **_kwargs: Any) -> None:
            statements.append(f"-- create_index {args[0]} {args[1]}")

    monkeypatch.setattr(migration, "op", Operations())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    migration.upgrade()
    return migration, statements, columns


def capture_message_upgrade(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    migration = _load_migration(MESSAGE_MIGRATION)
    statements: list[str] = []
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=lambda statement: statements.append(str(statement)),
    )
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: bind))
    migration.upgrade()
    return statements


def test_aud277_removes_permissive_true_and_scopes_each_tenant_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconciled AUD-277/360/450 contract for the in-place RLS revision.

    No table keeps the historical ``USING (true)`` policy. The tenant predicate
    is the only allow on tables without another permissive policy, so it is
    PERMISSIVE there; ``messages`` keeps its participant policy and therefore
    carries the tenant predicate as a RESTRICTIVE policy that ANDs with it.
    """
    migration, statements, _ = capture_tenant_upgrade(monkeypatch)
    assert migration.CORE_TABLES == (
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
    assert sum("default_permissive_policy" in sql for sql in statements) == len(
        migration.CORE_TABLES
    )
    assert not any(
        sql.startswith("CREATE POLICY default_permissive_policy") for sql in statements
    )
    assert not any("USING (true)" in sql for sql in statements)
    assert (
        statements.count(
            "CREATE OR REPLACE FUNCTION ue_rls_assign_session_tenant() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN IF NEW.tenant_id IS NULL THEN NEW.tenant_id := "
            "NULLIF(current_setting('app.current_tenant', true), '')::uuid; END IF; "
            "RETURN NEW; END $$;"
        )
        == 1
    )
    for table in migration.CORE_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in statements
        tenant_policy = [
            sql
            for sql in statements
            if sql.startswith(f"CREATE POLICY tenant_isolation_policy ON {table} ")
        ]
        assert len(tenant_policy) == 1
        expected_type = "RESTRICTIVE" if table == "messages" else "PERMISSIVE"
        assert f"AS {expected_type} FOR ALL" in tenant_policy[0]
        # AUD-450: privilege comes only from dedicated role membership.
        assert (
            "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER')" in tenant_policy[0]
        )
        assert "app.bypass_rls" not in tenant_policy[0]
        # AUD-360: NULL tenant rows are never visible to a tenant predicate.
        assert (
            "tenant_id IS NOT NULL AND tenant_id = NULLIF("
            "current_setting('app.current_tenant', true), '')::uuid" in tenant_policy[0]
        )
        predicate = (
            tenant_policy[0].split(" USING (", 1)[1].split(") WITH CHECK (", 1)[0]
        )
        assert tenant_policy[0].count(predicate) == 2
        assert f"DROP TRIGGER IF EXISTS ue_rls_assign_tenant ON {table};" in statements
        assert (
            f"CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION ue_rls_assign_session_tenant();"
        ) in statements

    message_statements = capture_message_upgrade(monkeypatch)
    participant_policy = next(
        sql
        for sql in message_statements
        if "CREATE POLICY messages_participant_isolation" in sql
    )
    assert "AS PERMISSIVE" in participant_policy
    assert "current_setting('app.current_user_id', TRUE)::uuid" in participant_policy
    assert "FROM   chat_participants" in participant_policy


def test_aud360_mapped_news_insert_omits_nullable_migration_owned_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.database import Base
    from app.core.db.retained_table_metadata import build_migration_metadata
    from app.models.news import News

    migration, _, added_columns = capture_tenant_upgrade(
        monkeypatch, ("news",), missing_tenant_column=True
    )
    assert migration.revision == "202607230001"
    assert len(added_columns) == 1
    column = added_columns[0]
    assert column.name == "tenant_id"
    assert column.nullable is True and column.server_default is None

    runtime_table = Base.metadata.tables["news"]
    assert "tenant_id" not in runtime_table.c
    retained = build_migration_metadata(Base.metadata).tables["news"].c.tenant_id
    assert retained.nullable is True
    assert retained.info["migration_owned_by_revision"] == migration.revision

    compiled = (
        insert(News)
        .values(title="A title", content="A body")
        .compile(dialect=postgresql.dialect())
    )
    assert "tenant_id" not in compiled.params
    assert "tenant_id" not in str(compiled)


def capture_tenant_downgrade(
    monkeypatch: pytest.MonkeyPatch,
    tables: tuple[str, ...] | None = None,
    *,
    tenants_present: bool = True,
    tenant_column_present: bool = True,
    dialect: str = "postgresql",
) -> list[str]:
    """Run the historical downgrade against an inspector/DDL recording adapter."""
    migration = _load_migration(MIGRATION)
    selected = tables if tables is not None else migration.CORE_TABLES
    statements: list[str] = []
    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    inspector = SimpleNamespace(
        get_table_names=lambda: [
            *(["tenants"] if tenants_present else []),
            *selected,
        ],
        get_columns=lambda _name: [{"name": "tenant_id"}]
        if tenant_column_present
        else [],
    )

    class Operations:
        def get_bind(self) -> Any:
            return bind

        def execute(self, statement: Any) -> None:
            statements.append(str(statement))

        def drop_index(self, name: str, table_name: str) -> None:
            statements.append(f"-- drop_index {name} {table_name}")

        def drop_column(self, table_name: str, column_name: str) -> None:
            statements.append(f"-- drop_column {table_name}.{column_name}")

        def drop_table(self, name: str) -> None:
            statements.append(f"-- drop_table {name}")

    monkeypatch.setattr(migration, "op", Operations())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    migration.downgrade()
    return statements


def test_upgrade_creates_tenants_and_partitioned_tenant_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, statements, added_columns = capture_tenant_upgrade(
        monkeypatch,
        ("notifications", "news"),
        missing_tenant_column=True,
        tenants_present=False,
    )
    assert "-- create_table tenants" in statements
    assert "-- create_index ix_tenants_slug tenants" in statements
    assert "-- create_index ix_notifications_tenant_id notifications" in statements
    assert "-- create_index ix_news_tenant_id news" in statements
    assert [column.name for column in added_columns] == ["tenant_id", "tenant_id"]


def test_downgrade_removes_tenant_triggers_policies_function_and_bypass_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(MIGRATION)
    statements = capture_tenant_downgrade(monkeypatch)
    for table in migration.CORE_TABLES:
        assert f"DROP TRIGGER IF EXISTS ue_rls_assign_tenant ON {table};" in statements
        assert (
            f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};" in statements
        )
        assert f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;" in statements
        assert f"-- drop_index ix_{table}_tenant_id {table}" in statements
        assert f"-- drop_column {table}.tenant_id" in statements
    assert "-- drop_table tenants" in statements
    assert "DROP FUNCTION IF EXISTS ue_rls_assign_session_tenant();" in statements
    assert any("DROP ROLE ue_rls_bypass" in sql for sql in statements)


def test_downgrade_skips_absent_tenants_table_and_tenant_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = capture_tenant_downgrade(
        monkeypatch,
        ("news",),
        tenants_present=False,
        tenant_column_present=False,
    )
    assert not any(sql.startswith("-- drop_") for sql in statements)
    assert "DROP TRIGGER IF EXISTS ue_rls_assign_tenant ON news;" in statements


@pytest.mark.parametrize("dialect", ["sqlite"])
def test_non_postgres_revision_emits_only_portable_column_ddl(
    monkeypatch: pytest.MonkeyPatch, dialect: str
) -> None:
    _, upgrade_statements, added_columns = capture_tenant_upgrade(
        monkeypatch,
        ("news",),
        missing_tenant_column=True,
        tenants_present=False,
        dialect=dialect,
    )
    assert len(added_columns) == 1
    assert not any(
        marker in sql
        for sql in upgrade_statements
        for marker in ("ROW LEVEL", "POLICY", "FUNCTION", "ROLE", "TRIGGER")
    )
    downgrade_statements = capture_tenant_downgrade(
        monkeypatch, ("news",), tenants_present=False, dialect=dialect
    )
    assert downgrade_statements == [
        "-- drop_index ix_news_tenant_id news",
        "-- drop_column news.tenant_id",
    ]
