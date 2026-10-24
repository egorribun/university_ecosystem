from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"
)

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "aud348_migration_under_test", MIGRATION_PATH
)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = migration
spec.loader.exec_module(migration)


class _Result:
    def __init__(self, row: Any = None) -> None:
        self.row = row

    def fetchone(self) -> Any:
        return self.row

    def first(self) -> Any:
        return self.row


class _CaptureOp:
    def __init__(self, bind: Any = None) -> None:
        self.bind = bind
        self.executed: list[Any] = []
        self.created: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_bind(self) -> Any:
        return self.bind

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> None:
        self.executed.append(statement)

    def create_table(self, table_name: str, *args: Any, **kwargs: Any) -> None:
        self.created.append((table_name, args, kwargs))


class _Inspector:
    def __init__(
        self, *, exists: bool = True, columns: list[dict[str, Any]] | None = None
    ):
        self.exists = exists
        self.columns = columns or [{"name": "id"}, {"name": "created_at"}]
        self.calls: list[tuple[str, str]] = []

    def has_table(self, name: str, schema: str | None = None) -> bool:
        self.calls.append(("has_table", name))
        return self.exists

    def get_columns(self, name: str, schema: str | None = None) -> list[dict[str, Any]]:
        self.calls.append(("get_columns", name))
        return self.columns


def _sql(statement: Any) -> str:
    return str(statement)


@pytest.fixture(autouse=True)
def _reset_migration_global_state() -> None:
    migration.SKIPPED_TABLES.clear()
    yield
    migration.SKIPPED_TABLES.clear()


@pytest.fixture
def sqlite_operations(monkeypatch: pytest.MonkeyPatch):
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    operations = Operations(MigrationContext.configure(connection))
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


@pytest.mark.parametrize(
    "row",
    [
        ("c", False, True),
        ("c", None, True),
        ("c", True, None),
    ],
    ids=["wrong_column", "missing_column_proof", "missing_predicate_proof"],
)
def test_not_null_check_rejects_unproven_catalog_identity(
    monkeypatch: pytest.MonkeyPatch, row: tuple[str, bool | None, bool | None]
) -> None:
    operation = _CaptureOp(_ConstraintBind(row))
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    with pytest.raises(
        RuntimeError, match="does not match the required NOT NULL check"
    ):
        migration._ensure_postgresql_not_null_check(
            "active_sessions", "ck_signing", "signing_key"
        )
    assert operation.executed == []


def test_safe_create_table_creates_missing_table_and_skips_existing_schema(
    sqlite_operations,
) -> None:
    connection = sqlite_operations
    migration.safe_create_table(
        "helper_probe", sa.Column("id", sa.Integer(), primary_key=True)
    )
    assert sa.inspect(connection).has_table("helper_probe")
    assert "helper_probe" not in migration.SKIPPED_TABLES

    migration.safe_create_table("helper_probe", sa.Column("later", sa.Text()))
    assert "helper_probe" in migration.SKIPPED_TABLES
    assert [c["name"] for c in sa.inspect(connection).get_columns("helper_probe")] == [
        "id"
    ]

    with migration.safe_batch_alter_table("helper_probe") as batch_op:
        batch_op.add_column(sa.Column("ignored", sa.Text()))
    assert [c["name"] for c in sa.inspect(connection).get_columns("helper_probe")] == [
        "id"
    ]


def test_safe_create_table_fails_open_to_create_when_inspection_is_unavailable(
    sqlite_operations, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = sqlite_operations
    real_inspect = sa.inspect

    def unavailable(_bind: Any) -> Any:
        raise sa.exc.NoInspectionAvailable("no inspector")

    monkeypatch.setattr(migration.sa, "inspect", unavailable)
    migration.safe_create_table("uninspected_probe", sa.Column("id", sa.Integer()))
    assert real_inspect(connection).has_table("uninspected_probe")


def test_safe_create_table_handles_name_error_from_offline_inspection(
    sqlite_operations, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = sqlite_operations
    real_inspect = sa.inspect

    def missing_name(_bind: Any) -> Any:
        raise NameError("inspection context absent")

    monkeypatch.setattr(migration.sa, "inspect", missing_name)
    migration.safe_create_table("offline_probe", sa.Column("id", sa.Integer()))
    assert "offline_probe" in real_inspect(connection).get_table_names()


def test_safe_batch_alter_table_delegates_real_schema_change_when_not_skipped(
    sqlite_operations,
) -> None:
    connection = sqlite_operations
    migration.op.create_table("batch_probe", sa.Column("id", sa.Integer()))

    with migration.safe_batch_alter_table("batch_probe") as batch_op:
        batch_op.add_column(sa.Column("payload", sa.String(length=24)))

    columns = sa.inspect(connection).get_columns("batch_probe")
    assert [column["name"] for column in columns] == ["id", "payload"]
    assert str(columns[1]["type"]) == "VARCHAR(24)"


class _PartitionConnection:
    def __init__(self, row: Any, dialect_name: str = "postgresql") -> None:
        self.dialect = SimpleNamespace(name=dialect_name)
        self.row = row
        self.queries: list[tuple[Any, Any]] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self.queries.append((statement, params))
        return _Result(self.row)


def _patch_partition_probe(
    monkeypatch: pytest.MonkeyPatch,
    connection: _PartitionConnection,
    inspector: _Inspector | None,
) -> _CaptureOp:
    operation = _CaptureOp(connection)
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    if inspector is not None:
        monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    return operation


def test_ensure_partitioned_is_silent_in_offline_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: True),
    )
    migration.ensure_partitioned(
        "events", "CREATE TABLE events (...) PARTITION BY RANGE (ts)", "ts"
    )
    assert operation.executed == []
    assert operation.bind is None


def test_ensure_partitioned_ignores_non_postgresql_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PartitionConnection(("r",), "sqlite")
    operation = _patch_partition_probe(monkeypatch, connection, None)
    migration.ensure_partitioned(
        "events", "CREATE TABLE events (...) PARTITION BY RANGE (ts)", "ts"
    )
    assert connection.queries == []
    assert operation.executed == []


def test_ensure_partitioned_returns_when_table_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PartitionConnection(("r",))
    inspector = _Inspector(exists=False)
    operation = _patch_partition_probe(monkeypatch, connection, inspector)
    migration.ensure_partitioned(
        "events", "CREATE TABLE events (...) PARTITION BY RANGE (ts)", "ts"
    )
    assert inspector.calls == [("has_table", "events")]
    assert connection.queries == []
    assert operation.executed == []


def test_ensure_partitioned_returns_when_inspection_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PartitionConnection(("r",))
    operation = _patch_partition_probe(monkeypatch, connection, None)

    def unavailable(_bind: Any) -> Any:
        raise sa.exc.NoInspectionAvailable("reflection unavailable")

    monkeypatch.setattr(migration.sa, "inspect", unavailable)
    migration.ensure_partitioned(
        "events", "CREATE TABLE events (...) PARTITION BY RANGE (ts)", "ts"
    )
    assert connection.queries == []
    assert operation.executed == []


@pytest.mark.parametrize("partition_marker", ["p", b"p"])
def test_ensure_partitioned_preserves_existing_partitioned_table(
    monkeypatch: pytest.MonkeyPatch, partition_marker: str | bytes
) -> None:
    connection = _PartitionConnection((partition_marker,))
    inspector = _Inspector()
    operation = _patch_partition_probe(monkeypatch, connection, inspector)
    migration.ensure_partitioned(
        "events", "CREATE TABLE events (...) PARTITION BY RANGE (ts)", "ts"
    )
    assert len(connection.queries) == 1
    assert "SELECT relkind FROM pg_class WHERE relname = :table_name" in _sql(
        connection.queries[0][0]
    )
    assert connection.queries[0][1] == {"table_name": "events"}
    assert operation.executed == []
    assert inspector.calls == [("has_table", "events")]


def test_ensure_partitioned_rebuilds_heap_and_copies_reflected_columns_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PartitionConnection((b"r",))
    inspector = _Inspector(columns=[{"name": "id"}, {"name": "created_at"}])
    operation = _patch_partition_probe(monkeypatch, connection, inspector)
    create_sql = "CREATE TABLE events (id integer, created_at date) PARTITION BY RANGE (created_at)"

    migration.ensure_partitioned("events", create_sql, "created_at")

    sql = [_sql(statement) for statement in operation.executed]
    assert sql == [
        "DROP TABLE IF EXISTS events_old CASCADE",
        "ALTER TABLE events RENAME TO events_old",
        create_sql,
        "CREATE TABLE IF NOT EXISTS events_default PARTITION OF events DEFAULT",
        "INSERT INTO events (id, created_at) SELECT id, created_at FROM events_old",
        "DROP TABLE events_old",
    ]
    assert inspector.calls == [("has_table", "events"), ("get_columns", "events_old")]


def test_ensure_partitioned_rebuilds_when_catalog_row_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _PartitionConnection(None)
    inspector = _Inspector()
    operation = _patch_partition_probe(monkeypatch, connection, inspector)
    migration.ensure_partitioned(
        "events", "CREATE TABLE events (id integer) PARTITION BY RANGE (id)", "id"
    )
    assert len(operation.executed) == 6
    assert (
        "INSERT INTO events (id, created_at) SELECT id, created_at FROM events_old"
        in map(_sql, operation.executed)
    )


def test_not_null_check_renders_additive_statement_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: True),
    )
    migration._ensure_postgresql_not_null_check(
        "active_sessions", "ck_signing", "signing_key"
    )
    assert [_sql(statement) for statement in operation.executed] == [
        "ALTER TABLE active_sessions ADD CONSTRAINT ck_signing "
        "CHECK (signing_key IS NOT NULL) NOT VALID"
    ]


@pytest.mark.parametrize(
    "bind", [None, SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))]
)
def test_not_null_check_uses_additive_fallback_without_postgresql(
    monkeypatch: pytest.MonkeyPatch, bind: Any
) -> None:
    operation = _CaptureOp(bind)
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    migration._ensure_postgresql_not_null_check(
        "active_sessions", "ck_signing", "signing_key"
    )
    assert [_sql(statement) for statement in operation.executed] == [
        "ALTER TABLE active_sessions ADD CONSTRAINT ck_signing "
        "CHECK (signing_key IS NOT NULL) NOT VALID"
    ]


class _ConstraintBind:
    def __init__(self, row: Any) -> None:
        self.dialect = SimpleNamespace(name="postgresql")
        self.row = row
        self.queries: list[tuple[Any, Any]] = []

    def execute(self, statement: Any, params: Any) -> _Result:
        self.queries.append((statement, params))
        return _Result(self.row)


def test_not_null_check_accepts_exact_catalog_proof_without_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = _ConstraintBind((b"c", True, True))
    operation = _CaptureOp(bind)
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    migration._ensure_postgresql_not_null_check(
        "active_sessions", "ck_signing", "signing_key"
    )
    assert len(bind.queries) == 1
    assert bind.queries[0][1] == {
        "table_name": "active_sessions",
        "constraint_name": "ck_signing",
        "column_name": "signing_key",
    }
    query = _sql(bind.queries[0][0])
    assert "c.conkey = ARRAY[a.attnum]" in query
    assert "a.attname = :column_name" in query
    assert "NOT a.attisdropped" in query
    assert "NOT c.connoinherit" in query
    assert "pg_catalog.pg_get_expr(c.conbin, c.conrelid)" in query
    assert "pg_catalog.format('(%I IS NOT NULL)', :column_name)" in query
    assert operation.executed == []


@pytest.mark.parametrize(
    "row",
    [
        ("f", True, True),
        ("c", True, False),
    ],
)
def test_not_null_check_rejects_same_name_wrong_catalog_contract(
    monkeypatch: pytest.MonkeyPatch, row: tuple[str, bool, bool]
) -> None:
    operation = _CaptureOp(_ConstraintBind(row))
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    with pytest.raises(
        RuntimeError, match="does not match the required NOT NULL check"
    ):
        migration._ensure_postgresql_not_null_check(
            "active_sessions", "ck_signing", "signing_key"
        )
    assert operation.executed == []


def test_not_null_check_adds_when_postgresql_has_no_same_name_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = _ConstraintBind(None)
    operation = _CaptureOp(bind)
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    migration._ensure_postgresql_not_null_check(
        "active_sessions", "ck_signing", "signing_key"
    )
    assert len(bind.queries) == 1
    assert len(operation.executed) == 1
    assert "CHECK (signing_key IS NOT NULL) NOT VALID" in _sql(operation.executed[0])


@pytest.mark.parametrize(
    ("bind", "offline"),
    [
        (None, False),
        (SimpleNamespace(dialect=SimpleNamespace(name="postgresql")), True),
        (SimpleNamespace(dialect=SimpleNamespace(name="sqlite")), False),
    ],
)
def test_postgresql_lock_guard_skips_missing_offline_or_nonpostgres_bind(
    monkeypatch: pytest.MonkeyPatch, bind: Any, offline: bool
) -> None:
    operation = _CaptureOp(bind)
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: offline),
    )
    migration._lock_postgresql_groups_id(bind)
    assert operation.executed == []


def test_postgresql_lock_uses_bounded_timeout_and_transaction_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    operation = _CaptureOp(bind)
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    migration._lock_postgresql_groups_id(bind)
    assert len(operation.executed) == 2
    assert _sql(operation.executed[0]) == "SET LOCAL lock_timeout = '10s'"
    assert _sql(operation.executed[1]) == (
        "SELECT pg_advisory_xact_lock(__[POSTCOMPILE_lock_id])"
    )
    lock_param = operation.executed[1]._bindparams["lock_id"]
    assert lock_param.value == migration._GROUPS_ID_LOCK_ID
    assert lock_param.literal_execute is True


def test_groups_id_type_detection_uses_actual_sqlalchemy_reflection(
    sqlite_operations,
) -> None:
    connection = sqlite_operations
    connection.exec_driver_sql("CREATE TABLE groups (id INTEGER NOT NULL)")
    assert migration._groups_id_is_integer(sa.inspect(connection)) is True

    connection.exec_driver_sql("DROP TABLE groups")
    connection.exec_driver_sql("CREATE TABLE groups (id VARCHAR(20))")
    assert migration._groups_id_is_integer(sa.inspect(connection)) is False

    connection.exec_driver_sql("DROP TABLE groups")
    connection.exec_driver_sql("CREATE TABLE groups (label VARCHAR(20))")
    assert migration._groups_id_is_integer(sa.inspect(connection)) is False
    assert migration._groups_id_is_integer(None) is False


def test_composite_fk_preflight_sql_rejects_only_composite_references_to_groups_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    migration._reject_composite_groups_foreign_keys()
    assert len(operation.executed) == 1
    sql = _sql(operation.executed[0])
    assert "WHERE c.contype = 'f'" in sql
    assert "c.confrelid = 'groups'::regclass" in sql
    assert "HAVING array_length(c.confkey, 1) > 1" in sql
    assert "bool_or(parent.attname = 'id')" in sql
    assert "RAISE EXCEPTION" in sql
    assert "composite FK %" in sql


def test_fk_capture_sql_preserves_key_order_and_references_groups_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    migration._capture_groups_foreign_keys()
    assert len(operation.executed) == 2
    capture_sql = _sql(operation.executed[0])
    assert "CREATE TEMP TABLE _groups_fk_restore ON COMMIT DROP AS" in capture_sql
    assert "array_agg(child.attname ORDER BY key.ord)" in capture_sql
    assert "array_agg(parent.attname ORDER BY key.ord)" in capture_sql
    assert "HAVING bool_or(parent.attname = 'id')" in capture_sql
    drop_sql = _sql(operation.executed[1])
    assert "SELECT conname, child_table FROM _groups_fk_restore" in drop_sql
    assert "ALTER TABLE %s DROP CONSTRAINT %I" in drop_sql


def test_fk_column_conversion_rejects_unallowlisted_type_before_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    with pytest.raises(ValueError, match="unsupported groups FK target type"):
        migration._convert_captured_fk_columns("INTEGER; DROP TABLE users")
    assert operation.executed == []


@pytest.mark.parametrize(
    ("target_type", "expected_check"),
    [
        ("INTEGER", "CAST(%I AS numeric) > 2147483647"),
        ("VARCHAR(20)", "length(CAST(%I AS text)) > 20"),
    ],
)
def test_fk_column_conversion_emits_allowlisted_validating_ordered_sql(
    monkeypatch: pytest.MonkeyPatch,
    target_type: str,
    expected_check: str,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    migration._convert_captured_fk_columns(target_type)
    assert len(operation.executed) == 1
    sql = _sql(operation.executed[0])
    assert expected_check in sql
    assert "fk.parent_names[ordinal] <> 'id'" in sql
    assert "column_type = lower('" + target_type + "')" in sql
    assert "ALTER TABLE %s ALTER COLUMN %I TYPE " + target_type in sql
    assert "__TARGET_TYPE__" not in sql


def test_fk_restore_sql_preserves_match_actions_and_deferral_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    monkeypatch.setattr(migration, "op", operation)
    migration._restore_groups_foreign_keys()
    assert len(operation.executed) == 1
    sql = _sql(operation.executed[0])
    for clause in (
        "WHEN 'f' THEN ' MATCH FULL'",
        "WHEN 'p' THEN ' MATCH PARTIAL'",
        "WHEN 'r' THEN ' ON UPDATE RESTRICT'",
        "WHEN 'c' THEN ' ON UPDATE CASCADE'",
        "WHEN 'n' THEN ' ON UPDATE SET NULL'",
        "WHEN 'd' THEN ' ON UPDATE SET DEFAULT'",
        "WHEN 'r' THEN ' ON DELETE RESTRICT'",
        "WHEN 'c' THEN ' ON DELETE CASCADE'",
        "WHEN 'n' THEN ' ON DELETE SET NULL'",
        "WHEN 'd' THEN ' ON DELETE SET DEFAULT'",
        "THEN ' DEFERRABLE INITIALLY DEFERRED'",
        "THEN ' DEFERRABLE'",
        "ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%s)",
        "REFERENCES %s (%s)%s%s%s%s",
    ):
        assert clause in sql


def test_signing_key_check_skips_when_table_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    inspector = _Inspector(exists=False)
    monkeypatch.setattr(migration, "op", operation)
    migration._postgresql_signing_key_check(inspector)
    assert operation.executed == []


def test_signing_key_check_runs_preflight_then_validated_not_null_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _CaptureOp()
    ensured: list[tuple[str, str, str]] = []
    monkeypatch.setattr(migration, "op", operation)
    monkeypatch.setattr(
        migration,
        "_ensure_postgresql_not_null_check",
        lambda *args: ensured.append(args),
    )
    migration._postgresql_signing_key_check(_Inspector(exists=True))

    assert len(operation.executed) == 3
    assert "active_sessions WHERE signing_key IS NULL" in _sql(operation.executed[0])
    assert ensured == [
        (
            "active_sessions",
            migration._ACTIVE_SESSION_SIGNING_KEY_CHECK,
            "signing_key",
        )
    ]
    assert "VALIDATE CONSTRAINT" in _sql(operation.executed[1])
    assert "ALTER COLUMN signing_key SET NOT NULL" in _sql(operation.executed[2])
