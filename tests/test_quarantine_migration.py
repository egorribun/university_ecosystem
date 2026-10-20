from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "202610200001_add_quarantine_storage_ledger.py"
)


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value


class _Bind:
    def __init__(self, *, dialect: str = "postgresql", schema: Any = "public") -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.schema = schema
        self.statements: list[str] = []

    def execute(self, statement: Any) -> _Result:
        sql = str(statement)
        self.statements.append(sql)
        assert sql == "SELECT current_schema()"
        return _Result(self.schema)


class _Inspector:
    def __init__(self, scopes: bool = False, reservations: bool = False) -> None:
        self.scopes = scopes
        self.reservations = reservations
        self.queries: list[str] = []

    def has_table(self, table: str, *, schema: str) -> bool:
        assert schema == "public"
        self.queries.append(table)
        return {
            "quarantine_storage_scopes": self.scopes,
            "quarantine_reservations": self.reservations,
        }[table]


class _Operations:
    def __init__(self, bind: _Bind | None, *, as_sql: bool = False) -> None:
        self._bind = bind
        self._context = SimpleNamespace(as_sql=as_sql)
        self.get_bind_calls = 0
        self.schema_writes: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_context(self) -> SimpleNamespace:
        return self._context

    def get_bind(self) -> _Bind | None:
        self.get_bind_calls += 1
        return self._bind

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("execute", args, kwargs))

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("create_table", args, kwargs))

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("create_index", args, kwargs))


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "quarantine_ledger_migration_contract", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _bind_migration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    bind: _Bind | None = None,
    inspector: _Inspector | None = None,
    as_sql: bool = False,
) -> tuple[Any, _Operations]:
    migration = _load_migration()
    operations = _Operations(bind, as_sql=as_sql)
    monkeypatch.setattr(migration, "op", operations)
    if inspector is not None:
        monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    return migration, operations


def test_migration_rejects_offline_before_binding() -> None:
    migration, operations = _bind_migration(pytest.MonkeyPatch(), as_sql=True)

    with pytest.raises(RuntimeError, match="requires online PostgreSQL"):
        migration.upgrade()

    assert operations.get_bind_calls == 0
    assert operations.schema_writes == []


def test_migration_rejects_non_postgresql_without_schema_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = _Bind(dialect="sqlite")
    migration, operations = _bind_migration(monkeypatch, bind=bind)

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        migration.upgrade()

    assert bind.statements == []
    assert operations.schema_writes == []


@pytest.mark.parametrize("schema", [None, "", 17])
def test_migration_rejects_unresolved_schema(
    monkeypatch: pytest.MonkeyPatch, schema: Any
) -> None:
    bind = _Bind(schema=schema)
    migration, operations = _bind_migration(monkeypatch, bind=bind)

    with pytest.raises(RuntimeError, match="Cannot resolve current schema"):
        migration.upgrade()

    assert bind.statements == ["SELECT current_schema()"]
    assert operations.schema_writes == []


@pytest.mark.parametrize(
    ("scopes", "reservations", "expected_queries"),
    [
        (True, False, ["quarantine_storage_scopes"]),
        (
            False,
            True,
            [
                "quarantine_storage_scopes",
                "quarantine_reservations",
            ],
        ),
    ],
)
def test_migration_rejects_preexisting_ledger_tables(
    monkeypatch: pytest.MonkeyPatch,
    scopes: bool,
    reservations: bool,
    expected_queries: list[str],
) -> None:
    bind = _Bind()
    inspector = _Inspector(scopes=scopes, reservations=reservations)
    migration, operations = _bind_migration(monkeypatch, bind=bind, inspector=inspector)

    with pytest.raises(RuntimeError, match="require manual review"):
        migration.upgrade()

    assert inspector.queries == expected_queries
    assert operations.schema_writes == []


def test_migration_emits_both_ledger_tables_and_bounded_expiry_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = _Bind()
    inspector = _Inspector()
    migration, operations = _bind_migration(monkeypatch, bind=bind, inspector=inspector)

    migration.upgrade()

    writes = operations.schema_writes
    assert [kind for kind, _args, _kwargs in writes] == [
        "execute",
        "execute",
        "create_table",
        "create_table",
        "create_index",
    ]
    scope_table = writes[2][1]
    reservation_table = writes[3][1]
    index = writes[4][1]
    assert scope_table[0] == "quarantine_storage_scopes"
    assert reservation_table[0] == "quarantine_reservations"
    assert index == (
        "ix_quarantine_reservations_expiry",
        "quarantine_reservations",
        ["scope_id", "status", "expires_at"],
    )
    assert inspector.queries == [
        "quarantine_storage_scopes",
        "quarantine_reservations",
    ]


def test_migration_downgrade_refuses_to_drop_quota_evidence() -> None:
    migration = _load_migration()
    expected_reason = (
        "Quarantine reservation ledger is irreversible: dropping it would release "
        "quota charges for objects that may still exist"
    )

    assert migration.downgrade_policy == "irreversible"
    assert migration.downgrade_reason == expected_reason
    with pytest.raises(RuntimeError) as error:
        migration.downgrade()
    assert str(error.value) == expected_reason
