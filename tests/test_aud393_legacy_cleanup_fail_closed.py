"""AUD-393: legacy-ID cleanup must stop on the first DDL failure.

The historical revision 202602010004 used to catch every exception around each
DROP/ADD statement, log it, and continue. These tests drive the real migration
module with recording Alembic-like adapters, so they exercise both the
PostgreSQL SQL it emits and the SQLite batch path without a database.
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202602010004_drop_legacy_columns.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aud393_cleanup", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Batch:
    def __init__(self, events: list[tuple[str, Any]], table: str) -> None:
        self.events = events
        self.table = table

    def drop_constraint(self, name: str, type_: str) -> None:
        self.events.append(("batch-drop-constraint", (self.table, name, type_)))

    def drop_column(self, name: str) -> None:
        self.events.append(("batch-drop-column", (self.table, name)))

    def add_column(self, column: sa.Column[Any]) -> None:
        self.events.append(("batch-add-column", (self.table, column.name)))


class _Operations:
    """Records raw SQL and batch operations; ``fail_on`` raises for matching SQL."""

    def __init__(self, dialect: str, fail_on: str | None = None) -> None:
        self.dialect = dialect
        self.fail_on = fail_on
        self.events: list[tuple[str, Any]] = []

    def get_bind(self) -> Any:
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    def execute(self, statement: Any) -> None:
        sql = " ".join(str(statement).split())
        self.events.append(("sql", sql))
        if self.fail_on is not None and self.fail_on in sql:
            raise RuntimeError(f"simulated DDL failure: {sql}")

    @contextmanager
    def batch_alter_table(self, table: str):
        batch = _Batch(self.events, table)
        yield batch


class _Inspector:
    def __init__(
        self,
        tables: set[str],
        columns: dict[str, set[str]] | None = None,
        unique: dict[str, set[str]] | None = None,
    ) -> None:
        self.tables = tables
        self.columns = columns or {}
        self.unique = unique or {}

    def has_table(self, table: str) -> bool:
        return table in self.tables

    def get_columns(self, table: str) -> list[dict[str, str]]:
        return [{"name": name} for name in sorted(self.columns.get(table, set()))]

    def get_unique_constraints(self, table: str) -> list[dict[str, str]]:
        return [{"name": name} for name in sorted(self.unique.get(table, set()))]


def _prepare(
    monkeypatch: pytest.MonkeyPatch,
    operations: _Operations,
    inspector: _Inspector,
) -> ModuleType:
    migration = _load_migration()
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)
    return migration


def _sql_events(operations: _Operations) -> list[str]:
    return [value for kind, value in operations.events if kind == "sql"]


def test_postgres_upgrade_stops_at_first_failed_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without the fix the broad handler logs this failure and keeps going, so the
    # later FK cleanup statements would run on an aborted PostgreSQL transaction.
    operations = _Operations("postgresql", fail_on='DROP COLUMN IF EXISTS "legacy_id"')
    inspector = _Inspector({"users", "messages"})
    migration = _prepare(monkeypatch, operations, inspector)

    with pytest.raises(RuntimeError, match="simulated DDL failure"):
        migration.upgrade()

    statements = _sql_events(operations)
    assert statements == [
        'ALTER TABLE "users" DROP COLUMN IF EXISTS "legacy_id" CASCADE',
    ]


def test_postgres_upgrade_stops_at_first_failed_foreign_key_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations(
        "postgresql", fail_on='DROP COLUMN IF EXISTS "legacy_created_by"'
    )
    inspector = _Inspector({"events", "messages"})
    migration = _prepare(monkeypatch, operations, inspector)

    with pytest.raises(RuntimeError, match="simulated DDL failure"):
        migration.upgrade()

    assert _sql_events(operations)[-1] == (
        'ALTER TABLE "events" DROP COLUMN IF EXISTS "legacy_created_by" CASCADE'
    )


def test_postgres_upgrade_drops_active_session_constraint_then_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("postgresql")
    inspector = _Inspector({"active_sessions", "users"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.upgrade()

    statements = _sql_events(operations)
    constraint = (
        'ALTER TABLE "active_sessions" '
        'DROP CONSTRAINT IF EXISTS "uq_active_sessions_legacy_id" CASCADE'
    )
    column = 'ALTER TABLE "active_sessions" DROP COLUMN IF EXISTS "legacy_id" CASCADE'
    assert statements.index(constraint) < statements.index(column)
    assert 'ALTER TABLE "users" DROP COLUMN IF EXISTS "legacy_id" CASCADE' in (
        statements
    )
    assert (
        'ALTER TABLE "users" DROP COLUMN IF EXISTS "legacy_group_id" CASCADE'
        in statements
    )


def test_upgrade_skips_absent_tables_on_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("postgresql")
    inspector = _Inspector(set())
    migration = _prepare(monkeypatch, operations, inspector)

    migration.upgrade()

    assert _sql_events(operations) == []


def test_sqlite_upgrade_drops_only_present_unique_constraint_and_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("sqlite")
    inspector = _Inspector(
        {"active_sessions", "users", "messages"},
        columns={
            "active_sessions": {"legacy_id"},
            "users": {"legacy_group_id"},
            "messages": set(),
        },
        unique={"active_sessions": {"uq_active_sessions_legacy_id"}},
    )
    migration = _prepare(monkeypatch, operations, inspector)

    migration.upgrade()

    assert (
        "batch-drop-constraint",
        ("active_sessions", "uq_active_sessions_legacy_id", "unique"),
    ) in operations.events
    assert ("batch-drop-column", ("active_sessions", "legacy_id")) in operations.events
    assert ("batch-drop-column", ("users", "legacy_group_id")) in operations.events
    # Absent legacy columns and constraints are skipped rather than dropped.
    assert ("batch-drop-column", ("messages", "legacy_id")) not in operations.events
    assert not any(
        kind == "batch-drop-constraint" and value[0] == "users"
        for kind, value in operations.events
    )


def test_sqlite_upgrade_skips_absent_columns_and_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("sqlite")
    inspector = _Inspector({"users"}, columns={"users": set()})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.upgrade()

    assert not any(kind.startswith("batch-") for kind, _ in operations.events)


def test_sqlite_upgrade_propagates_batch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("sqlite")
    inspector = _Inspector({"users"}, columns={"users": {"legacy_id"}})
    migration = _prepare(monkeypatch, operations, inspector)

    def _fail(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("batch refused")

    monkeypatch.setattr(operations, "batch_alter_table", _fail)

    with pytest.raises(RuntimeError, match="batch refused"):
        migration.upgrade()


def test_postgres_downgrade_adds_legacy_columns_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("postgresql")
    inspector = _Inspector({"chats", "users"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.downgrade()

    # Only tables that exist receive restored columns; typing follows the table.
    assert _sql_events(operations) == [
        'ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "legacy_id" INTEGER',
        'ALTER TABLE "chats" ADD COLUMN IF NOT EXISTS "legacy_id" VARCHAR',
        'ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "legacy_group_id" INTEGER',
    ]


def test_postgres_downgrade_restores_string_foreign_key_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("postgresql")
    inspector = _Inspector({"messages", "attachments", "users"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.downgrade()

    statements = _sql_events(operations)
    assert (
        'ALTER TABLE "messages" ADD COLUMN IF NOT EXISTS "legacy_chat_id" VARCHAR'
        in statements
    )
    assert (
        'ALTER TABLE "attachments" ADD COLUMN IF NOT EXISTS "legacy_message_id" '
        "VARCHAR" in statements
    )
    assert (
        'ALTER TABLE "messages" ADD COLUMN IF NOT EXISTS "legacy_sender_id" INTEGER'
        in statements
    )


def test_postgres_downgrade_propagates_failed_add(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("postgresql", fail_on='"legacy_id" INTEGER')
    inspector = _Inspector({"users"})
    migration = _prepare(monkeypatch, operations, inspector)

    with pytest.raises(RuntimeError, match="simulated DDL failure"):
        migration.downgrade()


def test_sqlite_downgrade_adds_only_absent_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("sqlite")
    inspector = _Inspector(
        {"messages", "users", "events"},
        columns={
            "messages": {"legacy_id", "legacy_chat_id"},
            "users": set(),
            "events": set(),
        },
    )
    migration = _prepare(monkeypatch, operations, inspector)

    migration.downgrade()

    added = [value for kind, value in operations.events if kind == "batch-add-column"]
    assert ("users", "legacy_id") in added
    assert ("events", "legacy_created_by") in added
    # Columns that already exist are never re-added on SQLite.
    assert ("messages", "legacy_id") not in added
    assert ("messages", "legacy_chat_id") not in added


def test_sqlite_downgrade_propagates_batch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations("sqlite")
    inspector = _Inspector({"users"}, columns={"users": set()})
    migration = _prepare(monkeypatch, operations, inspector)

    def _fail(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("batch refused")

    monkeypatch.setattr(operations, "batch_alter_table", _fail)

    with pytest.raises(RuntimeError, match="batch refused"):
        migration.downgrade()
