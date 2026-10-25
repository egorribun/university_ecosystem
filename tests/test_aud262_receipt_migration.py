"""Fail-closed guards for the durable chat-send receipt migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "202610250001_add_chat_send_receipts.py"
)


def _load_migration() -> Any:
    assert MIGRATION_PATH.is_file(), "Durable chat-send receipt migration is missing"
    spec = importlib.util.spec_from_file_location(
        "aud262_receipt_migration_contract", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


class _Bind:
    def __init__(self, dialect: str = "postgresql", schema: Any = "public") -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.schema = schema
        self.reads: list[str] = []

    def execute(self, statement: Any) -> Any:
        self.reads.append(str(statement))
        assert str(statement) == "SELECT current_schema()"
        return SimpleNamespace(scalar_one=lambda: self.schema)


class _Operations:
    def __init__(self, bind: _Bind, *, offline: bool = False) -> None:
        self.bind = bind
        self.offline = offline
        self.bind_requests = 0
        self.writes: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_context(self) -> Any:
        return SimpleNamespace(as_sql=self.offline)

    def get_bind(self) -> _Bind:
        self.bind_requests += 1
        return self.bind

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self.writes.append(("execute", args, kwargs))

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        self.writes.append(("create_table", args, kwargs))

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self.writes.append(("create_index", args, kwargs))


def _bind_migration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dialect: str = "postgresql",
    schema: Any = "public",
    offline: bool = False,
    exists: bool = False,
) -> tuple[Any, _Operations]:
    migration = _load_migration()
    operations = _Operations(_Bind(dialect, schema), offline=offline)

    def has_table(table: str, *, schema: str) -> bool:
        assert table == "chat_send_receipts"
        assert schema == operations.bind.schema
        return exists

    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(
        migration.sa, "inspect", lambda _bind: SimpleNamespace(has_table=has_table)
    )
    return migration, operations


def test_receipt_migration_refuses_offline_before_connection_or_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(monkeypatch, offline=True)

    with pytest.raises(RuntimeError, match="requires online PostgreSQL"):
        migration.upgrade()

    assert operations.bind_requests == 0
    assert operations.bind.reads == []
    assert operations.writes == []


def test_receipt_migration_refuses_other_dialects_before_catalog_or_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(monkeypatch, dialect="sqlite")

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        migration.upgrade()

    assert operations.bind.reads == []
    assert operations.writes == []


@pytest.mark.parametrize("schema", [None, "", 17])
def test_receipt_migration_refuses_unresolved_schema_before_writes(
    monkeypatch: pytest.MonkeyPatch, schema: Any
) -> None:
    migration, operations = _bind_migration(monkeypatch, schema=schema)

    with pytest.raises(RuntimeError, match="Cannot resolve current schema"):
        migration.upgrade()

    assert operations.bind.reads == ["SELECT current_schema()"]
    assert operations.writes == []


def test_receipt_migration_refuses_preexisting_table_without_modification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(monkeypatch, exists=True)

    with pytest.raises(RuntimeError, match="require manual review"):
        migration.upgrade()

    assert operations.writes == []


def test_receipt_upgrade_emits_constrained_private_schema_before_rls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(monkeypatch)

    migration.upgrade()

    writes = operations.writes
    assert [kind for kind, _args, _kwargs in writes] == [
        "execute",
        "execute",
        "create_table",
        "create_index",
        "create_index",
        "create_index",
        "execute",
        "execute",
        "execute",
    ]
    assert str(writes[0][1][0]) == "SET LOCAL lock_timeout = '10s'"
    assert str(writes[1][1][0]) == "SET LOCAL statement_timeout = '60s'"
    table_args = writes[2][1]
    assert table_args[0] == "chat_send_receipts"
    columns = {
        column.name: column
        for column in table_args[1:]
        if isinstance(column, sa.Column)
    }
    assert set(columns) == {
        "id",
        "chat_id",
        "user_id",
        "key_digest",
        "message_id",
        "completed_at",
        "expires_at",
    }
    assert {name for name, column in columns.items() if column.nullable} == {
        "message_id"
    }
    assert columns["key_digest"].type.length == 64
    assert columns["completed_at"].type.timezone is True
    assert columns["expires_at"].type.timezone is True
    assert all(column.server_default is None for column in columns.values())
    constraints = [
        item for item in table_args[1:] if isinstance(item, sa.UniqueConstraint)
    ]
    assert len(constraints) == 1
    assert constraints[0].name == "uq_chat_send_receipts_chat_user_key"
    assert [list(args) for kind, args, _kwargs in writes if kind == "create_index"] == [
        ["ix_chat_send_receipts_message_id", "chat_send_receipts", ["message_id"]],
        ["ix_chat_send_receipts_user_id", "chat_send_receipts", ["user_id"]],
        [
            "ix_chat_send_receipts_expires_at",
            "chat_send_receipts",
            ["expires_at", "id"],
        ],
    ]


def test_receipt_downgrade_refuses_before_any_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(monkeypatch)
    expected_reason = (
        "Dropping chat send receipts can discard committed idempotency history "
        "and permit duplicate messages"
    )

    with pytest.raises(RuntimeError) as failure:
        migration.downgrade()

    assert str(failure.value) == expected_reason
    assert migration.downgrade_policy == "irreversible"
    assert migration.downgrade_reason == expected_reason
    assert operations.bind_requests == 0
    assert operations.bind.reads == []
    assert operations.writes == []


def test_receipt_model_registers_only_private_storage_columns() -> None:
    import app.models as models

    receipt_type = getattr(models, "ChatSendReceipt", None)
    assert receipt_type is not None, "Durable chat-send receipt model is not registered"
    table = receipt_type.__table__
    assert models.Base.metadata.tables["chat_send_receipts"] is table
    assert set(table.columns.keys()) == {
        "id",
        "chat_id",
        "user_id",
        "key_digest",
        "message_id",
        "completed_at",
        "expires_at",
    }
    assert not sa.inspect(receipt_type).relationships
    assert table.c.id.default is not None
    assert {column.name for column in table.columns if column.nullable} == {
        "message_id"
    }
    assert {
        (foreign_key.parent.name, foreign_key.target_fullname, foreign_key.ondelete)
        for foreign_key in table.foreign_keys
    } == {
        ("chat_id", "chats.id", "CASCADE"),
        ("user_id", "users.id", "CASCADE"),
        ("message_id", "messages.id", "SET NULL"),
    }
