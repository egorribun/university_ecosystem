"""AUD-274: quiet-hour and timezone columns survive revision 202511240001.

The old upgrade dropped ``users.dnd_*`` and ``users.timezone`` before revision
148642dd1207 created ``user_preferences`` and copied those values into it. These
tests keep the historical upgrade free of DDL and pin the later backfill contract.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIGRATION = VERSIONS / "202511240001_drop_legacy_user_columns.py"
BACKFILL_SOURCE = VERSIONS / "148642dd1207_fix_missing_tables.py"
QUIET_HOUR_COLUMNS = ("dnd_enabled", "dnd_start", "dnd_end", "timezone")


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aud274_drop_user_cols", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Operations:
    """Records every schema operation; upgrade must not issue any."""

    def __init__(self, dialect: str = "postgresql") -> None:
        self.dialect = dialect
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def get_bind(self) -> Any:
        self.calls.append(("get_bind", ()))
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    def drop_column(self, table: str, column: str) -> None:
        self.calls.append(("drop_column", (table, column)))

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.calls.append(("add_column", (table, column.name)))

    def execute(self, statement: Any) -> None:
        self.calls.append(("execute", (str(statement),)))


class _Inspector:
    def __init__(self, tables: set[str], user_columns: set[str]) -> None:
        self.tables = tables
        self.user_columns = user_columns

    def get_table_names(self) -> list[str]:
        return sorted(self.tables)

    def get_columns(self, table: str) -> list[dict[str, str]]:
        assert table == "users"
        return [{"name": name} for name in sorted(self.user_columns)]


def _prepare(
    monkeypatch: pytest.MonkeyPatch,
    operations: _Operations,
    inspector: _Inspector,
) -> ModuleType:
    migration = _load_migration()
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)
    return migration


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_upgrade_keeps_quiet_hour_columns_for_later_backfill(
    monkeypatch: pytest.MonkeyPatch, dialect: str
) -> None:
    operations = _Operations(dialect)
    inspector = _Inspector({"users"}, set(QUIET_HOUR_COLUMNS) | {"id"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.upgrade()

    # Revision 148642dd1207 owns the copy and the eventual drop, so this
    # revision neither reads nor drops the user preference values.
    assert operations.calls == []


def test_upgrade_is_noop_without_users_table(monkeypatch: pytest.MonkeyPatch) -> None:
    operations = _Operations()
    migration = _prepare(monkeypatch, operations, _Inspector(set(), set()))

    migration.upgrade()

    assert operations.calls == []


def test_downgrade_restores_only_missing_quiet_hour_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations()
    inspector = _Inspector({"users"}, {"id", "dnd_enabled"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.downgrade()

    added = [args for kind, args in operations.calls if kind == "add_column"]
    assert added == [
        ("users", "timezone"),
        ("users", "dnd_end"),
        ("users", "dnd_start"),
    ]


def test_downgrade_restores_all_columns_when_none_are_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations()
    inspector = _Inspector({"users"}, {"id"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.downgrade()

    added = [args[1] for kind, args in operations.calls if kind == "add_column"]
    assert added == ["timezone", "dnd_end", "dnd_start", "dnd_enabled"]


@pytest.mark.parametrize(
    ("tables", "dialect"),
    [(set(), "postgresql"), ({"users"}, "sqlite")],
)
def test_downgrade_skips_missing_users_table_and_sqlite(
    monkeypatch: pytest.MonkeyPatch, tables: set[str], dialect: str
) -> None:
    operations = _Operations(dialect)
    migration = _prepare(monkeypatch, operations, _Inspector(tables, set()))

    migration.downgrade()

    assert operations.calls == [("get_bind", ())]


def test_later_backfill_copies_every_quiet_hour_column_before_users_drop() -> None:
    # The preservation contract lives in 148642dd1207. Pin its field list and its
    # position before the users DROP COLUMN block so this revision stays safe.
    source = BACKFILL_SOURCE.read_text(encoding="utf-8")
    match = re.search(r"fields = \(([^)]*)\)", source)
    assert match is not None
    fields = tuple(re.findall(r'"(\w+)"', match.group(1)))
    assert fields == QUIET_HOUR_COLUMNS
    backfill_call = source.index("    _backfill_user_preferences()\n")
    users_drop = source.index('if "dnd_end" in existing_users_columns:')
    assert backfill_call < users_drop


def test_downgrade_adds_nothing_when_quiet_hour_columns_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = _Operations()
    inspector = _Inspector({"users"}, set(QUIET_HOUR_COLUMNS) | {"id"})
    migration = _prepare(monkeypatch, operations, inspector)

    migration.downgrade()

    assert [kind for kind, _ in operations.calls] == ["get_bind"]
