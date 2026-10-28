"""Source-bound checks for the already-corrected historical partition upgrade.

The other historical hazards in this audit still need a safe migration plan;
this module deliberately does not assert that destructive behavior is correct.
PostgreSQL integration remains necessary for sequence and transaction semantics.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "6a898bba5589_implement_partitioning.py"
)
CLEANUP_MIGRATION = MIGRATION.with_name("202602010004_drop_legacy_columns.py")
TABLES = ("data_access_logs", "notifications", "notification_deliveries")


def _load_migration():
    spec = importlib.util.spec_from_file_location("aud271_partitioning", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, scalar: Any = None, row: tuple[str] | None = None) -> None:
        self.scalar = scalar
        self.row = row

    def scalar_one(self) -> Any:
        return self.scalar

    def fetchone(self) -> tuple[str] | None:
        return self.row


class _Bind:
    def __init__(self, maxima: dict[str, int | None], missing: str | None = None):
        self.dialect = SimpleNamespace(name="postgresql")
        self.maxima = maxima
        self.missing = missing
        self.events: list[tuple[str, Any]] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = " ".join(str(statement).split())
        if "FROM pg_class" in sql:
            return _Result(row=("r",))
        if "pg_get_serial_sequence" in sql:
            assert params is not None
            table = params["table_name"]
            self.events.append(("sequence", table))
            return _Result(None if table == self.missing else f"public.{table}_id_seq")
        if "max(id)" in sql:
            match = re.search(r"\bFROM (\w+)\b", sql)
            assert match is not None
            table = match.group(1)
            self.events.append(("maximum", table))
            return _Result(self.maxima[table])
        if "setval(" in sql:
            assert params is not None
            self.events.append(("setval", dict(params)))
            return _Result()
        raise AssertionError(f"Unexpected catalog query: {sql}")


class _Operations:
    def __init__(self, bind: _Bind) -> None:
        self.bind = bind

    def get_bind(self) -> _Bind:
        return self.bind

    def execute(self, statement: Any) -> None:
        self.bind.events.append(("ddl", " ".join(str(statement).split())))


def _prepare(monkeypatch: pytest.MonkeyPatch, bind: _Bind):
    migration = _load_migration()
    migration.op = _Operations(bind)
    inspector = SimpleNamespace(get_table_names=lambda: list(TABLES))
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)
    return migration


@pytest.mark.parametrize(
    ("maxima", "expected"),
    [
        (
            {
                "data_access_logs": 600,
                "notifications": 900,
                "notification_deliveries": 700,
            },
            {
                "data_access_logs": (600, True),
                "notifications": (900, True),
                "notification_deliveries": (700, True),
            },
        ),
        (
            {
                "data_access_logs": None,
                "notifications": 0,
                "notification_deliveries": -1,
            },
            {
                "data_access_logs": (1, False),
                "notifications": (1, False),
                "notification_deliveries": (1, False),
            },
        ),
    ],
    ids=["copied-positive-ids", "empty-and-nonpositive-ids"],
)
def test_aud271_upgrade_resets_each_serial_after_copy_before_old_table_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    maxima: dict[str, int | None],
    expected: dict[str, tuple[int, bool]],
) -> None:
    bind = _Bind(maxima)
    migration = _prepare(monkeypatch, bind)

    migration.upgrade()

    resets = [value for kind, value in bind.events if kind == "setval"]
    assert resets == [
        {
            "sequence_name": f"public.{table}_id_seq",
            "set_value": expected[table][0],
            "is_called": expected[table][1],
        }
        for table in TABLES
    ]
    for table in TABLES:
        copied = next(
            i
            for i, (kind, value) in enumerate(bind.events)
            if kind == "ddl" and value.startswith(f"INSERT INTO {table} ")
        )
        sequence = bind.events.index(("sequence", table))
        maximum = bind.events.index(("maximum", table))
        reset = next(
            i
            for i, (kind, value) in enumerate(bind.events)
            if kind == "setval" and value["sequence_name"] == f"public.{table}_id_seq"
        )
        cleanup = next(
            i
            for i, (kind, value) in enumerate(bind.events)
            if i > copied
            and kind == "ddl"
            and value
            in {
                f"DROP TABLE {table}_old",
                f"DROP TABLE IF EXISTS {table}_old CASCADE",
            }
        )
        assert copied < sequence < maximum < reset < cleanup


@pytest.mark.parametrize("missing", TABLES)
def test_aud271_upgrade_missing_sequence_stops_before_copied_source_is_dropped(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    bind = _Bind(dict.fromkeys(TABLES, 10), missing=missing)
    migration = _prepare(monkeypatch, bind)

    with pytest.raises(
        RuntimeError, match=rf"Missing SERIAL sequence for {missing}\.id"
    ):
        migration.upgrade()

    assert ("sequence", missing) in bind.events
    assert ("maximum", missing) not in bind.events
    assert not any(
        kind == "setval" and value["sequence_name"] == f"public.{missing}_id_seq"
        for kind, value in bind.events
    )
    copied = next(
        i
        for i, (kind, value) in enumerate(bind.events)
        if kind == "ddl" and value.startswith(f"INSERT INTO {missing} ")
    )
    assert not any(
        kind == "ddl"
        and value
        in {
            f"DROP TABLE {missing}_old",
            f"DROP TABLE IF EXISTS {missing}_old CASCADE",
        }
        for kind, value in bind.events[copied + 1 :]
    )


def test_aud393_cleanup_preserves_module_catalogs_across_repeated_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location("aud393_cleanup", CLEANUP_MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    bind = _Bind({})
    migration.op = _Operations(bind)
    inspector = SimpleNamespace(has_table=lambda table: table in {"users", "messages"})
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)
    tables_before = tuple(migration.TABLES_TO_CLEANUP)
    foreign_keys_before = tuple(migration.FK_TO_CLEANUP)

    migration.upgrade()
    migration.downgrade()
    migration.upgrade()

    assert tuple(migration.TABLES_TO_CLEANUP) == tables_before
    assert tuple(migration.FK_TO_CLEANUP) == foreign_keys_before
    assert any(
        kind == "ddl" and 'ALTER TABLE "users" DROP COLUMN' in value
        for kind, value in bind.events
    )
    assert any(
        kind == "ddl" and 'ALTER TABLE "messages" ADD COLUMN' in value
        for kind, value in bind.events
    )
