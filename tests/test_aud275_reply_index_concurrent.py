"""AUD-275: the reply index on messages is built without blocking writes.

Revision 202605300004 added ``messages.reply_to_message_id`` and then ran a plain
``CREATE INDEX``, which blocks every message write for the whole build. These
tests render the real revision through Alembic's SQL generator and check that the
index is created CONCURRENTLY, outside the migration transaction.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202605300004_add_reply_to_message_id.py"
)
INDEX_SQL = (
    "CREATE INDEX CONCURRENTLY ix_messages_reply_to_message_id "
    "ON messages (reply_to_message_id)"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aud275_reply", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Inspector:
    def __init__(self, tables: set[str], message_columns: set[str]) -> None:
        self.tables = tables
        self.message_columns = message_columns

    def get_table_names(self) -> list[str]:
        return sorted(self.tables)

    def get_columns(self, table: str) -> list[dict[str, str]]:
        assert table == "messages"
        return [{"name": name} for name in sorted(self.message_columns)]


def _use_online_context(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    # The state reader asks op whether it is rendering offline SQL.
    online = SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=False))
    monkeypatch.setattr(module, "op", online)


def _render(
    monkeypatch: pytest.MonkeyPatch,
    inspector: _Inspector,
    direction: str = "upgrade",
    index_state: str | None = None,
) -> str:
    module = _load_migration()
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(module, "op", Operations(context))
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)
    # Offline rendering has no catalog to query, so the index state is injected.
    monkeypatch.setattr(module, "_reply_index_state", lambda _bind: index_state)
    getattr(module, direction)()
    return output.getvalue()


class _Result:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar(self) -> object:
        return self.value


class _Bind:
    def __init__(self, dialect: str, value: object = None) -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.value = value
        self.statements: list[str] = []

    def execute(self, statement: Any, params: dict[str, str]) -> _Result:
        self.statements.append(str(statement))
        return _Result(self.value)


def _statements(sql: str) -> list[str]:
    return [" ".join(part.split()) for part in sql.split(";") if part.strip()]


def test_upgrade_builds_reply_index_concurrently_outside_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render(monkeypatch, _Inspector({"messages"}, {"id", "chat_id"}))
    statements = _statements(sql)

    add_column = next(s for s in statements if "ADD COLUMN reply_to_message_id" in s)
    assert add_column.startswith("ALTER TABLE messages ADD COLUMN")
    index = statements.index(INDEX_SQL)
    assert statements.index(add_column) < index
    # The autocommit block commits the column change before the concurrent build.
    assert any(s == "COMMIT" for s in statements[:index])
    assert "CREATE INDEX ix_messages_reply_to_message_id" not in sql


def test_upgrade_is_noop_when_column_and_valid_index_already_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render(
        monkeypatch,
        _Inspector({"messages"}, {"id", "reply_to_message_id"}),
        index_state="valid",
    )

    assert sql.strip() == ""


def test_upgrade_builds_missing_index_without_adding_column_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A previous run can commit the column and then fail before the build.
    sql = _render(
        monkeypatch,
        _Inspector({"messages"}, {"id", "reply_to_message_id"}),
    )
    statements = _statements(sql)

    assert not any("ADD COLUMN" in statement for statement in statements)
    assert INDEX_SQL in statements


def test_upgrade_rebuilds_invalid_reply_index_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An interrupted CONCURRENTLY build leaves an INVALID index behind (AUD-275).
    sql = _render(
        monkeypatch,
        _Inspector({"messages"}, {"id", "reply_to_message_id"}),
        index_state="invalid",
    )
    statements = _statements(sql)

    drop_sql = "DROP INDEX CONCURRENTLY ix_messages_reply_to_message_id"
    assert drop_sql in statements
    assert statements.index(drop_sql) < statements.index(INDEX_SQL)
    assert any(statement == "COMMIT" for statement in statements[:-1])
    assert not any("ADD COLUMN" in statement for statement in statements)


def test_reply_index_state_reads_postgresql_catalog_validity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_migration()
    _use_online_context(monkeypatch, module)

    assert module._reply_index_state(_Bind("postgresql", "valid")) == "valid"
    assert module._reply_index_state(_Bind("postgresql", "invalid")) == "invalid"
    assert module._reply_index_state(_Bind("postgresql", None)) is None


def test_reply_index_state_uses_inspector_outside_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_migration()
    _use_online_context(monkeypatch, module)
    bind = _Bind("sqlite")
    monkeypatch.setattr(
        sa,
        "inspect",
        lambda _bind: SimpleNamespace(
            get_indexes=lambda _table: [{"name": "ix_messages_reply_to_message_id"}]
        ),
    )

    assert module._reply_index_state(bind) == "valid"
    monkeypatch.setattr(
        sa, "inspect", lambda _bind: SimpleNamespace(get_indexes=lambda _t: [])
    )
    assert module._reply_index_state(bind) is None
    assert bind.statements == []


def test_upgrade_is_noop_without_messages_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render(monkeypatch, _Inspector(set(), set()))

    assert sql.strip() == ""


def test_downgrade_drops_index_and_column_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render(
        monkeypatch,
        _Inspector({"messages"}, {"id", "reply_to_message_id"}),
        direction="downgrade",
    )

    assert "DROP INDEX ix_messages_reply_to_message_id" in sql
    assert "ALTER TABLE messages DROP COLUMN reply_to_message_id" in sql


def test_downgrade_is_noop_when_column_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _render(
        monkeypatch,
        _Inspector({"messages"}, {"id"}),
        direction="downgrade",
    )

    assert sql.strip() == ""


def test_downgrade_is_noop_without_messages_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render(monkeypatch, _Inspector(set(), set()), direction="downgrade")

    assert sql.strip() == ""


def test_reply_index_is_never_built_with_plain_create_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render(monkeypatch, _Inspector({"messages"}, {"id"}))

    plain = [
        statement
        for statement in _statements(sql)
        if statement.startswith("CREATE INDEX ")
        and not statement.startswith("CREATE INDEX CONCURRENTLY ")
        and "ix_messages_reply_to_message_id" in statement
    ]
    assert plain == []
    assert any(statement == INDEX_SQL for statement in _statements(sql))


def test_upgrade_renders_add_column_before_any_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql: Any = _render(monkeypatch, _Inspector({"messages"}, {"id"}))

    assert sql.index("ADD COLUMN reply_to_message_id") < sql.index("COMMIT")


def test_offline_render_builds_index_without_querying_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Offline SQL has no catalog, so the real state reader must not execute SQL.
    module = _load_migration()
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(module, "op", Operations(context))
    monkeypatch.setattr(
        sa,
        "inspect",
        lambda _bind: _Inspector({"messages"}, {"id", "reply_to_message_id"}),
    )

    module.upgrade()

    assert INDEX_SQL in _statements(output.getvalue())
    assert "pg_index" not in output.getvalue()
