"""Focused historical migration guards for malformed and partial catalogs.

The existing PostgreSQL integration suites remain the authoritative data-copy,
sequence, FK-rebinding, and idempotence checks. These contracts target defensive
catalog and dialect exits that are awkward to reproduce as stable live races.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"


def _load_revision(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        mapping: dict[str, Any] | None = None,
        first: tuple[Any, ...] | None = None,
    ) -> None:
        self.rows = [] if rows is None else rows
        self.mapping = mapping
        self.first = first

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.mapping

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.first


class _Bind:
    def __init__(
        self,
        dialect: str,
        *,
        results: list[_Result] | None = None,
    ) -> None:
        self.dialect = SimpleNamespace(
            name=dialect,
            identifier_preparer=postgresql.dialect().identifier_preparer,
        )
        self.results = [] if results is None else results
        self.statements: list[str] = []
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.statements.append(str(statement))
        self.calls.append((str(statement), args, kwargs))
        if self.results:
            return self.results.pop(0)
        return _Result()


class _Operations:
    def __init__(self, bind: _Bind) -> None:
        self._bind = bind
        self.writes: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_bind(self) -> _Bind:
        return self._bind

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self.writes.append(("execute", args, kwargs))

    def __getattr__(self, name: str):
        if name.startswith(("create_", "drop_", "alter_", "add_")):

            def record(*args: Any, **kwargs: Any) -> None:
                self.writes.append((name, args, kwargs))

            return record
        raise AttributeError(name)


class _Inspector:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables

    def get_table_names(self) -> list[str]:
        return sorted(self.tables)


def _fk_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "constraint_oid": 17,
        "relation_oid": 23,
        "constraint_name": "fk_audit_parent",
        "validated": True,
        "inheritance_count": 0,
        "relation_kind": "r",
        "schema_name": "public",
        "relation_name": "audit_rows",
        "definition": "FOREIGN KEY (parent_id, created_at) REFERENCES public.parents(id, created_at)",
        "referenced_columns": ["id", "created_at"],
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("row", "expected"),
    [(None, None), (("p",), "p"), ((b"p",), "p")],
    ids=["absent-relation", "psycopg-char", "asyncpg-char"],
)
def test_range_relkind_normalizes_catalog_values_from_postgres_drivers(
    row: tuple[str | bytes] | None, expected: str | None
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_relkind_driver"
    )
    bind = _Bind("postgresql", results=[_Result(first=row)])

    assert migration._get_relkind(bind, "audit_rows") == expected
    assert len(bind.statements) == 1


def test_range_migration_is_noop_off_postgresql_and_empty_range_count_skips_sql() -> (
    None
):
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_dialect_guard"
    )
    bind = _Bind("sqlite")
    operations = _Operations(bind)
    migration.op = operations

    migration.upgrade()
    migration.downgrade()

    assert operations.writes == []
    assert bind.statements == []
    assert migration._count_rows_for_ranges(bind, "audit_rows", "created_at", []) == 0
    assert bind.statements == []


def test_range_migration_skips_unexpected_upgrade_relations_and_heap_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_catalog_skip"
    )
    bind = _Bind("postgresql")
    operations = _Operations(bind)
    migration.op = operations

    monkeypatch.setattr(migration, "_get_relkind", lambda _conn, _name: None)
    timeout_statements = [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    migration.upgrade()
    assert bind.statements == timeout_statements
    assert operations.writes == []

    monkeypatch.setattr(migration, "_get_relkind", lambda _conn, _name: "v")
    migration.upgrade()
    assert bind.statements == timeout_statements * 2
    assert operations.writes == []

    monkeypatch.setattr(migration, "_get_relkind", lambda _conn, _name: "r")
    migration.downgrade()
    assert bind.statements == timeout_statements * 2
    assert operations.writes == []


def test_heap_conversion_rechecks_staging_relation_after_parent_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_staging_race"
    )
    bind = _Bind("postgresql")
    relkinds = iter((None, "r"))
    monkeypatch.setattr(migration, "_get_relkind", lambda *_args: next(relkinds))

    with pytest.raises(RuntimeError, match=r"staging relation .* already exists"):
        migration._convert_to_partitioned(bind, "audit_rows", "created_at")

    assert len(bind.statements) == 1
    assert bind.statements[0].startswith("LOCK TABLE ")
    assert "RENAME TO" not in bind.statements[0]


def test_heap_conversion_aborts_if_inbound_fk_catalog_changes_after_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_fk_catalog_race"
    )
    bind = _Bind("postgresql")
    snapshots = iter(([_fk_row()], []))
    locked: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(migration, "_get_relkind", lambda *_args: None)
    monkeypatch.setattr(
        migration, "_incoming_foreign_keys", lambda *_args: next(snapshots)
    )
    monkeypatch.setattr(
        migration,
        "_lock_foreign_key_relations",
        lambda _conn, keys: locked.append(keys),
    )

    with pytest.raises(RuntimeError, match="Inbound foreign keys changed"):
        migration._convert_to_partitioned(bind, "audit_rows", "created_at")

    assert locked == [[_fk_row()]]
    assert len(bind.statements) == 1
    assert bind.statements[0].startswith("LOCK TABLE ")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"validated": False}, "is not validated"),
        ({"inheritance_count": 1}, "unsupported table inheritance"),
        ({"relation_kind": "v"}, "unsupported relation kind"),
    ],
    ids=["unvalidated-fk", "inherited-fk", "unsupported-owner-kind"],
)
def test_range_redistribution_rejects_unsafe_inbound_fk_catalog_rows(
    overrides: dict[str, Any], message: str
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_fk_catalog"
    )
    bind = _Bind("postgresql", results=[_Result(rows=[_fk_row(**overrides)])])

    with pytest.raises(RuntimeError, match=message):
        migration._incoming_foreign_keys(bind, "notifications")

    assert len(bind.statements) == 1
    assert "SELECT" in bind.statements[0]


@pytest.mark.parametrize(
    "restored",
    [
        None,
        {
            "convalidated": False,
            "conparentid": 0,
            "definition": _fk_row()["definition"],
        },
        {
            "convalidated": True,
            "conparentid": 17,
            "definition": _fk_row()["definition"],
        },
        {"convalidated": True, "conparentid": 0, "definition": "different FK"},
    ],
    ids=[
        "missing-after-restore",
        "unvalidated-after-restore",
        "child-constraint",
        "definition-drift",
    ],
)
def test_range_migration_fails_closed_when_restored_fk_does_not_match_snapshot(
    restored: dict[str, Any] | None,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_fk_restore"
    )
    bind = _Bind(
        "postgresql",
        results=[_Result(), _Result(), _Result(mapping=restored)],
    )

    with pytest.raises(
        RuntimeError, match="Could not restore validated inbound foreign key"
    ):
        migration._restore_incoming_foreign_keys(bind, [_fk_row()])

    assert len(bind.statements) == 3
    assert "ADD CONSTRAINT" in bind.statements[0]
    assert "NOT VALID" in bind.statements[0]
    assert "VALIDATE CONSTRAINT" in bind.statements[1]
    assert "SELECT convalidated" in bind.statements[2]


def test_legacy_partitioning_migration_non_postgresql_paths_are_noops() -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py", "legacy_partitioning_dialect_guard"
    )
    bind = _Bind("sqlite")
    operations = _Operations(bind)
    migration.op = operations

    migration.upgrade()
    migration.downgrade()

    assert bind.statements == []
    assert operations.writes == []


def test_legacy_partitioning_fresh_schema_upgrade_and_downgrade_are_noops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py", "legacy_partitioning_empty_catalog"
    )
    bind = _Bind("postgresql")
    operations = _Operations(bind)
    migration.op = operations
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector(set()))

    migration.upgrade()
    migration.downgrade()

    assert bind.statements == []
    assert operations.writes == []


def test_trusted_device_sqlite_upgrade_and_downgrade_are_noops() -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py", "trusted_device_dialect_guard"
    )
    bind = _Bind("sqlite")
    operations = _Operations(bind)
    migration.op = operations

    migration.upgrade()
    migration.downgrade()

    assert bind.statements == []
    assert operations.writes == []


def test_trusted_device_missing_anchor_tables_skip_upgrade_and_historical_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py", "trusted_device_empty_catalog_guard"
    )
    bind = _Bind("postgresql")
    operations = _Operations(bind)
    migration.op = operations
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector(set()))

    migration.upgrade()
    migration.downgrade()

    assert bind.statements == []
    assert operations.writes == []


class _ScalarResult(_Result):
    def __init__(self, value: Any) -> None:
        super().__init__()
        self.value = value

    def scalar_one(self) -> Any:
        return self.value


class _CatalogInspector(_Inspector):
    def __init__(
        self,
        tables: set[str],
        *,
        indexes: dict[str, set[str]] | None = None,
        columns: dict[str, dict[str, Any]] | None = None,
        constraints: dict[str, set[str]] | None = None,
        foreign_keys: dict[str, set[str]] | None = None,
    ) -> None:
        super().__init__(tables)
        self.indexes = {} if indexes is None else indexes
        self.columns = {} if columns is None else columns
        self.constraints = {} if constraints is None else constraints
        self.foreign_keys = {} if foreign_keys is None else foreign_keys

    def get_indexes(self, table_name: str) -> list[dict[str, str]]:
        return [{"name": name} for name in sorted(self.indexes.get(table_name, set()))]

    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        return [
            {"name": name, "type": column_type}
            for name, column_type in self.columns.get(table_name, {}).items()
        ]

    def get_unique_constraints(self, table_name: str) -> list[dict[str, str]]:
        return [
            {"name": name} for name in sorted(self.constraints.get(table_name, set()))
        ]

    def get_foreign_keys(self, table_name: str) -> list[dict[str, str]]:
        return [
            {"name": name} for name in sorted(self.foreign_keys.get(table_name, set()))
        ]


class _CatalogOperations(_Operations):
    def f(self, name: str) -> str:
        return name


def test_range_upgrade_aborts_when_inbound_fk_snapshot_changes_after_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_locked_fk_drift"
    )
    bind = _Bind("postgresql")
    migration.op = _Operations(bind)
    monkeypatch.setattr(
        migration, "_PARTITIONED_TABLES", (("notifications", "created_at"),)
    )
    monkeypatch.setattr(migration, "_get_relkind", lambda _conn, _table_name: "p")
    monkeypatch.setattr(
        migration,
        "_existing_partition_names",
        lambda _conn, _table_name: {"notifications_default"},
    )
    monkeypatch.setattr(migration, "_count_rows_for_ranges", lambda *_args: 1)
    snapshots = iter(([_fk_row()], []))
    locked: list[list[dict[str, Any]]] = []
    dropped: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(
        migration, "_incoming_foreign_keys", lambda *_args: next(snapshots)
    )
    monkeypatch.setattr(
        migration,
        "_lock_foreign_key_relations",
        lambda _conn, rows: locked.append(rows),
    )
    monkeypatch.setattr(
        migration,
        "_drop_incoming_foreign_keys",
        lambda _conn, rows: dropped.append(rows),
    )

    with pytest.raises(RuntimeError, match="Inbound foreign keys changed"):
        migration.upgrade()

    assert locked == [[_fk_row()]]
    assert dropped == []
    assert bind.statements == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
        'LOCK TABLE "public"."notifications" IN ACCESS EXCLUSIVE MODE',
    ]


@pytest.mark.parametrize(
    ("row_counts", "message", "default_reattached"),
    [
        ([1, 1], "Could not redistribute all matching rows", False),
        ([1, 0, 2], "Redistribution row count changed", True),
    ],
    ids=["default-still-has-matching-rows", "parent-count-changed"],
)
def test_range_upgrade_stops_when_default_redistribution_counts_diverge(
    monkeypatch: pytest.MonkeyPatch,
    row_counts: list[int],
    message: str,
    default_reattached: bool,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py",
        "range_partition_redistribution_counts",
    )
    bind = _Bind("postgresql")
    migration.op = _Operations(bind)
    monkeypatch.setattr(
        migration, "_PARTITIONED_TABLES", (("notifications", "created_at"),)
    )
    monkeypatch.setattr(migration, "_get_relkind", lambda _conn, _name: "p")
    monkeypatch.setattr(
        migration,
        "_existing_partition_names",
        lambda _conn, _name: {"notifications_default"},
    )
    counts = iter(row_counts)
    monkeypatch.setattr(
        migration, "_count_rows_for_ranges", lambda *_args: next(counts)
    )
    monkeypatch.setattr(migration, "_incoming_foreign_keys", lambda *_args: [])
    monkeypatch.setattr(migration, "_lock_foreign_key_relations", lambda *_args: None)
    monkeypatch.setattr(migration, "_drop_incoming_foreign_keys", lambda *_args: None)
    restored: list[bool] = []
    monkeypatch.setattr(
        migration,
        "_restore_incoming_foreign_keys",
        lambda *_args: restored.append(True),
    )
    table_factory = sa.Table

    def table_without_reflection(name: str, metadata: sa.MetaData, **_kwargs: Any):
        return table_factory(
            name,
            metadata,
            sa.Column("id", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    monkeypatch.setattr(sa, "Table", table_without_reflection)

    with pytest.raises(RuntimeError, match=message):
        migration.upgrade()

    statements = "\n".join(bind.statements)
    assert "INSERT INTO" in statements
    assert "DELETE FROM" in statements
    assert ("ATTACH PARTITION" in statements) is default_reattached
    assert restored == []


def test_range_partitioned_downgrade_drops_each_month_and_default_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "202607020001_create_range_partitions.py", "range_partition_downgrade_window"
    )
    bind = _Bind("postgresql")
    migration.op = _Operations(bind)
    monkeypatch.setattr(
        migration, "_PARTITIONED_TABLES", (("notifications", "created_at"),)
    )
    monkeypatch.setattr(migration, "_get_relkind", lambda _conn, _name: "p")

    migration.downgrade()

    expected_months = migration._MONTHS_BACK + migration._MONTHS_FORWARD + 1
    assert len(bind.statements) == expected_months + 1
    assert all(
        statement.startswith("DROP TABLE IF EXISTS notifications_")
        for statement in bind.statements
    )
    assert bind.statements[-1] == "DROP TABLE IF EXISTS notifications_default"


def test_partitioning_no_catalog_row_is_treated_as_unpartitioned_before_recheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_no_catalog_row",
    )

    class StopBeforeConversion(Exception):
        pass

    class StopAfterSecondCatalogRead(_Bind):
        def __init__(self) -> None:
            super().__init__("postgresql", results=[_Result(first=None)])
            self.catalog_read_attempts = 0

        def execute(self, statement: Any, *_args: Any, **_kwargs: Any) -> _Result:
            self.catalog_read_attempts += 1
            if self.catalog_read_attempts == 2:
                raise StopBeforeConversion
            return super().execute(statement, *_args, **_kwargs)

    bind = StopAfterSecondCatalogRead()
    operations = _CatalogOperations(bind)
    migration.op = operations
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector({"notifications"}))

    with pytest.raises(StopBeforeConversion):
        migration.upgrade()

    assert bind.catalog_read_attempts == 2
    assert len(bind.statements) == 1
    assert bind.statements[0].startswith("SELECT relkind FROM pg_class c")
    assert operations.writes == []


@pytest.mark.parametrize(
    ("heap_relkind", "partitioned_relkind"),
    [(("r",), ("p",)), ((b"r",), (b"p",))],
    ids=["text-catalog-values", "bytes-catalog-values"],
)
def test_partitioning_rechecks_notifications_after_concurrent_partitioning(
    monkeypatch: pytest.MonkeyPatch,
    heap_relkind: tuple[str | bytes, ...],
    partitioned_relkind: tuple[str | bytes, ...],
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_concurrent_catalog_recheck",
    )
    bind = _Bind(
        "postgresql",
        results=[
            _Result(first=heap_relkind),
            _Result(first=partitioned_relkind),
            _Result(first=partitioned_relkind),
        ],
    )
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _Inspector({"notifications", "notification_deliveries"})
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)

    migration.upgrade()

    sql = [
        str(args[0]) for name, args, _kwargs in operations.writes if name == "execute"
    ]
    assert sql == ["DROP TABLE IF EXISTS notifications_old CASCADE"]
    assert not any("RENAME TO notifications_old" in statement for statement in sql)
    assert len(bind.statements) == 3


def test_partitioning_missing_sequence_fails_before_old_table_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_missing_sequence",
    )
    bind = _Bind(
        "postgresql",
        results=[
            _Result(first=("r",)),
            _Result(first=("r",)),
            _ScalarResult(None),
        ],
    )
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _Inspector({"notifications"})
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)

    with pytest.raises(
        RuntimeError, match=r"Missing SERIAL sequence for notifications\.id"
    ):
        migration.upgrade()

    sql = [
        str(args[0]) for name, args, _kwargs in operations.writes if name == "execute"
    ]
    assert "ALTER TABLE notifications RENAME TO notifications_old" in sql
    assert sql.count("DROP TABLE IF EXISTS notifications_old CASCADE") == 1
    assert "DROP TABLE notifications_old" not in sql


def test_partitioning_upgrade_is_noop_when_notifications_are_already_partitioned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_already_partitioned",
    )
    bind = _Bind("postgresql", results=[_Result(first=("p",))])
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _Inspector({"notifications"})
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)

    migration.upgrade()

    assert len(bind.statements) == 1
    assert operations.writes == []


def test_partitioning_historical_downgrade_drops_stale_staging_tables_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_historical_downgrade_staging",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _Inspector(
        {
            "notification_deliveries",
            "notification_deliveries_part",
            "notifications",
            "notifications_part",
            "data_access_logs",
            "data_access_logs_part",
        }
    )
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)

    migration.downgrade()

    sql = [args[0] for name, args, _kwargs in operations.writes if name == "execute"]
    for stale, parent in (
        ("notification_deliveries_part", "notification_deliveries"),
        ("notifications_part", "notifications"),
        ("data_access_logs_part", "data_access_logs"),
    ):
        drop_at = sql.index(f"DROP TABLE {stale}")
        rename_at = sql.index(f"ALTER TABLE {parent} RENAME TO {parent}_part")
        assert drop_at < rename_at
    assert any(
        statement.lstrip().startswith("CREATE TABLE notifications (")
        for statement in sql
    )
    assert "CREATE TABLE notification_deliveries" in "\n".join(sql)
    assert "CREATE TABLE data_access_logs" in "\n".join(sql)


def test_partitioning_historical_downgrade_skips_absent_child_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_historical_downgrade_partial_catalog",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _Inspector({"notifications"})
    monkeypatch.setattr(sa, "inspect", lambda _bind: inspector)

    migration.downgrade()

    sql = [args[0] for name, args, _kwargs in operations.writes if name == "execute"]
    assert any(
        statement.lstrip().startswith("CREATE TABLE notifications (")
        for statement in sql
    )
    assert any(
        "INSERT INTO notifications SELECT * FROM notifications_part" in statement
        for statement in sql
    )
    assert not any("notification_deliveries" in statement for statement in sql)
    assert not any("data_access_logs" in statement for statement in sql)


@pytest.mark.parametrize(
    "attendance_columns",
    [{"registered_at": sa.Integer()}, {}],
    ids=["legacy-column-needs-normalization", "optional-column-absent"],
)
def test_trusted_device_upgrade_uses_partial_existing_catalog_safely(
    monkeypatch: pytest.MonkeyPatch,
    attendance_columns: dict[str, Any],
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py",
        "trusted_device_partial_existing_catalog",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _CatalogInspector(
        {
            "event_attendance",
            "notifications",
            "notification_deliveries",
            "push_subscriptions",
            "users",
            "user_push_topics",
        },
        indexes={
            "notifications": {"ix_notifications_dedupe_key"},
            "push_subscriptions": {
                "ix_push_subscriptions_active",
                "ix_push_subscriptions_updated_at",
            },
            "users": {"ux_users_lower_email"},
            "user_push_topics": {"ix_user_push_topics_updated_at"},
        },
        columns={
            "event_attendance": attendance_columns,
            "notification_deliveries": {
                "status_code": sa.Integer(),
                "detail": sa.Text(),
                "delivered_at": sa.DateTime(timezone=True),
            },
            "notifications": {
                "created_at": sa.DateTime(timezone=True),
                "read_at": sa.DateTime(timezone=True),
            },
            "push_subscriptions": {
                "user_id": sa.Integer(),
                "created_at": sa.DateTime(timezone=True),
                "updated_at": sa.DateTime(timezone=True),
                "active": sa.Boolean(),
            },
            "users": {
                "spotify_token_expires_at": sa.DateTime(timezone=True),
                "spotify_last_checked_at": sa.DateTime(timezone=True),
            },
        },
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration.upgrade()

    assert any(
        name == "create_foreign_key"
        and args[:3]
        == ("push_subscriptions_user_id_fkey", "push_subscriptions", "users")
        and kwargs.get("ondelete") == "CASCADE"
        for name, args, kwargs in operations.writes
    )
    assert not any(
        name == "drop_constraint" for name, _args, _kwargs in operations.writes
    )
    assert any(
        name == "alter_column" and args[:2] == ("event_attendance", "registered_at")
        for name, args, _kwargs in operations.writes
    ) is bool(attendance_columns)
    absent_tables = {
        "events",
        "schedule",
        "news",
        "mfa_challenges",
        "invite_codes",
        "password_reset_tokens",
        "active_sessions",
    }
    assert not any(
        any(table in repr((args, kwargs)) for table in absent_tables)
        for _name, args, kwargs in operations.writes
    )


def test_trusted_device_upgrade_skips_table_removed_from_second_catalog_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py",
        "trusted_device_changing_catalog_guard",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    first_tables = {
        "event_attendance",
        "notifications",
        "notification_deliveries",
        "push_subscriptions",
        "users",
        "user_push_topics",
    }
    second_tables = first_tables - {"event_attendance"}
    inspector = _CatalogInspector(
        first_tables,
        indexes={
            "notifications": {"ix_notifications_dedupe_key"},
            "push_subscriptions": {
                "ix_push_subscriptions_active",
                "ix_push_subscriptions_updated_at",
            },
            "users": {"ux_users_lower_email"},
            "user_push_topics": {"ix_user_push_topics_updated_at"},
        },
        columns={
            "event_attendance": {"registered_at": sa.Integer()},
            "notification_deliveries": {
                "status_code": sa.Integer(),
                "detail": sa.Text(),
                "delivered_at": sa.DateTime(timezone=True),
            },
            "notifications": {
                "created_at": sa.DateTime(timezone=True),
                "read_at": sa.DateTime(timezone=True),
            },
            "push_subscriptions": {
                "user_id": sa.Integer(),
                "created_at": sa.DateTime(timezone=True),
                "updated_at": sa.DateTime(timezone=True),
                "active": sa.Boolean(),
            },
            "users": {
                "spotify_token_expires_at": sa.DateTime(timezone=True),
                "spotify_last_checked_at": sa.DateTime(timezone=True),
            },
        },
    )
    catalog_reads: list[set[str]] = []
    column_reads: list[str] = []
    original_get_columns = inspector.get_columns

    def get_table_names() -> list[str]:
        snapshot = first_tables if not catalog_reads else second_tables
        inspector.tables = snapshot
        catalog_reads.append(snapshot)
        return sorted(snapshot)

    def get_columns(table_name: str) -> list[dict[str, Any]]:
        column_reads.append(table_name)
        return original_get_columns(table_name)

    monkeypatch.setattr(inspector, "get_table_names", get_table_names)
    monkeypatch.setattr(inspector, "get_columns", get_columns)
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration.upgrade()

    assert catalog_reads == [first_tables, second_tables]
    assert "event_attendance" not in column_reads
    assert "users" in column_reads
    assert not any(
        name == "alter_column" and args[0] == "event_attendance"
        for name, args, _kwargs in operations.writes
    )
    assert any(
        name == "create_foreign_key"
        and args[:3]
        == ("push_subscriptions_user_id_fkey", "push_subscriptions", "users")
        for name, args, _kwargs in operations.writes
    )


def test_trusted_device_downgrade_avoids_optional_table_ddl_on_users_only_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py",
        "trusted_device_downgrade_users_only_catalog",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _CatalogInspector(
        {"users"}, indexes={"users": {"ux_users_lower_email"}}
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration.downgrade()

    assert [name for name, _args, _kwargs in operations.writes] == [
        "alter_column",
        "alter_column",
    ]
    assert all(args[0] == "users" for _name, args, _kwargs in operations.writes)


def test_trusted_device_downgrade_handles_present_and_missing_optional_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py",
        "trusted_device_downgrade_partial_catalog",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _CatalogInspector(
        {
            "users",
            "notifications",
            "notification_deliveries",
            "push_subscriptions",
            "active_sessions",
        },
        indexes={
            "users": {"ux_users_lower_email"},
            "push_subscriptions": {
                "ix_push_subscriptions_active",
                "ix_push_subscriptions_updated_at",
            },
        },
        columns={
            "notification_deliveries": {
                "delivered_at": sa.DateTime(timezone=True),
            },
            "push_subscriptions": {
                "created_at": sa.DateTime(timezone=True),
                "user_id": sa.Integer(),
            },
        },
        constraints={"active_sessions": {"uq_active_sessions_jti"}},
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration.downgrade()

    add_columns = [
        args[1].name
        for name, args, _kwargs in operations.writes
        if name == "add_column" and args[0] == "push_subscriptions"
    ]
    assert add_columns == ["active", "updated_at"]
    assert any(
        name == "create_foreign_key"
        and args[1:3] == ("push_subscriptions", "users")
        and kwargs.get("ondelete") == "SET NULL"
        for name, args, kwargs in operations.writes
    )
    assert not any(
        name == "drop_column" and args[0] == "notification_deliveries"
        for name, args, _kwargs in operations.writes
    )
    assert not any(
        name == "create_unique_constraint" and args[1] == "active_sessions"
        for name, args, _kwargs in operations.writes
    )
    absent_tables = {
        "events",
        "schedule",
        "news",
        "mfa_challenges",
        "invite_codes",
        "password_reset_tokens",
        "user_push_topics",
        "event_attendance",
    }
    assert not any(
        any(table in repr((args, kwargs)) for table in absent_tables)
        for _name, args, kwargs in operations.writes
    )


def test_trusted_device_downgrade_skips_additions_for_existing_optional_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py",
        "trusted_device_downgrade_existing_optional_columns",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    inspector = _CatalogInspector(
        {"users", "notifications", "push_subscriptions"},
        indexes={
            "users": {"ux_users_lower_email"},
            "notifications": {"ix_notifications_dedupe_key"},
            "push_subscriptions": {
                "ix_push_subscriptions_active",
                "ix_push_subscriptions_updated_at",
            },
        },
        columns={
            "push_subscriptions": {
                "active": sa.Boolean(),
                "updated_at": sa.DateTime(timezone=True),
                "created_at": sa.DateTime(timezone=True),
                "user_id": sa.Integer(),
            }
        },
        foreign_keys={"push_subscriptions": {"push_subscriptions_user_id_fkey"}},
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration.downgrade()

    push_additions = [
        args[1].name
        for name, args, _kwargs in operations.writes
        if name == "add_column" and args[0] == "push_subscriptions"
    ]
    assert push_additions == []
    assert any(
        name == "drop_constraint"
        and args[:2] == ("push_subscriptions_user_id_fkey", "push_subscriptions")
        for name, args, _kwargs in operations.writes
    )
    assert any(
        name == "create_foreign_key"
        and args[:3]
        == ("push_subscriptions_user_id_fkey", "push_subscriptions", "users")
        and kwargs.get("ondelete") == "SET NULL"
        for name, args, kwargs in operations.writes
    )


def test_trusted_device_upgrade_rejects_required_tables_missing_from_second_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_revision(
        "db31ef5d7ea4_add_trusted_devices.py",
        "trusted_device_upgrade_missing_required_tables",
    )
    bind = _Bind("postgresql")
    operations = _CatalogOperations(bind)
    migration.op = operations
    first_tables = {
        "event_attendance",
        "notification_deliveries",
        "notifications",
        "push_subscriptions",
        "user_push_topics",
        "users",
    }
    second_tables = first_tables - {"users", "notifications"}
    inspector = _CatalogInspector(first_tables)
    catalog_snapshots: list[set[str]] = []

    def get_table_names() -> list[str]:
        snapshot = first_tables if not catalog_snapshots else second_tables
        inspector.tables = snapshot
        catalog_snapshots.append(snapshot)
        return sorted(snapshot)

    monkeypatch.setattr(inspector, "get_table_names", get_table_names)
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    with pytest.raises(RuntimeError) as exc_info:
        migration.upgrade()

    assert str(exc_info.value) == (
        "db31ef5d7ea4 requires existing tables before upgrade DDL; missing: notifications, users"
    )
    assert catalog_snapshots == [first_tables, second_tables]
    assert operations.writes == []


@pytest.mark.parametrize(
    "max_id",
    [None, 0],
    ids=["empty-table", "zero-id-row"],
)
def test_partitioning_empty_notifications_resets_sequence_as_not_called(
    monkeypatch: pytest.MonkeyPatch,
    max_id: int | None,
) -> None:
    migration = _load_revision(
        "6a898bba5589_implement_partitioning.py",
        "legacy_partitioning_empty_sequence_reset",
    )
    sequence_name = "public.notifications_id_seq"
    bind = _Bind(
        "postgresql",
        results=[
            _Result(first=("r",)),
            _Result(first=("r",)),
            _ScalarResult(sequence_name),
            _ScalarResult(max_id),
        ],
    )
    operations = _CatalogOperations(bind)
    migration.op = operations
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector({"notifications"}))

    migration.upgrade()

    calls = bind.calls
    sequence_index = next(
        i
        for i, (statement, _args, _kwargs) in enumerate(calls)
        if "pg_get_serial_sequence" in statement
    )
    max_id_index = next(
        i
        for i, (statement, _args, _kwargs) in enumerate(calls)
        if "max(id)" in statement and "FROM notifications" in statement
    )
    setval_index = next(
        i
        for i, (statement, _args, _kwargs) in enumerate(calls)
        if "SELECT setval(CAST(:sequence_name AS regclass)" in statement
    )
    assert sequence_index < max_id_index < setval_index
    assert len(calls) == 5
    assert calls[sequence_index][1] == ({"table_name": "notifications"},)
    assert calls[setval_index][1] == (
        {"sequence_name": sequence_name, "set_value": 1, "is_called": False},
    )
    assert calls[setval_index][2] == {}
    assert bind.results == []

    executed_sql = [
        str(args[0]) for name, args, _kwargs in operations.writes if name == "execute"
    ]
    rename_index = next(
        i
        for i, statement in enumerate(executed_sql)
        if "ALTER TABLE notifications RENAME TO notifications_old" in statement
    )
    insert_index = next(
        i
        for i, statement in enumerate(executed_sql)
        if "INSERT INTO notifications (" in statement
    )
    cleanup_statement = "DROP TABLE IF EXISTS notifications_old CASCADE"
    cleanup_indexes = [
        i for i, statement in enumerate(executed_sql) if statement == cleanup_statement
    ]
    assert rename_index < insert_index < cleanup_indexes[-1]
    assert len(cleanup_indexes) == 2
    assert executed_sql[-1] == cleanup_statement
