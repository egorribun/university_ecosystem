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
) -> tuple[ModuleType, list[str], list[Any]]:
    """Run the historical upgrade against an inspector/DDL recording adapter."""
    migration = _load_migration(MIGRATION)
    selected = tables if tables is not None else migration.CORE_TABLES
    statements: list[str] = []
    columns: list[Any] = []
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    inspector = SimpleNamespace(
        get_table_names=lambda: ["tenants", *selected],
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

        def get_context(self) -> Any:
            return self

        def autocommit_block(self) -> Any:
            return nullcontext()

        def create_index(self, *_args: Any, **_kwargs: Any) -> None:
            return None

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


def test_aud277_historical_permissive_policy_is_paired_with_restrictive_tenant_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    for table in migration.CORE_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in statements
        restrictive = [
            sql
            for sql in statements
            if sql.startswith(f"CREATE POLICY tenant_isolation_policy ON {table} ")
        ]
        assert len(restrictive) == 1
        assert "AS RESTRICTIVE" in restrictive[0]
        assert "current_setting('app.bypass_rls', true) = 'on'" in restrictive[0]
        assert "OR tenant_id IS NULL" in restrictive[0]
        assert (
            "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
            in restrictive[0]
        )
        permissive = [
            sql
            for sql in statements
            if sql.startswith(f"CREATE POLICY default_permissive_policy ON {table} ")
        ]
        if table == "messages":
            assert permissive == []
        else:
            assert permissive == [
                f"CREATE POLICY default_permissive_policy ON {table} AS PERMISSIVE "
                "USING (true) WITH CHECK (true);"
            ]

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
