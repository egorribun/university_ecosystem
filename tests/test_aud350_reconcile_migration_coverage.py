from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "alembic"
    / "versions"
    / "202603280001_reconcile_post_uuid_migration_drift.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "aud350_reconcile_post_uuid_candidate", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


class _Inspector:
    def __init__(
        self,
        migration: Any,
        *,
        all_uuid_columns_present: bool,
        user_stats_present: bool,
        foreign_keys_present: bool,
        unique_constraints_present: bool,
        record_id_integer: bool = False,
    ) -> None:
        self.migration = migration
        self.all_uuid_columns_present = all_uuid_columns_present
        self.user_stats_present = user_stats_present
        self.foreign_keys_present = foreign_keys_present
        self.unique_constraints_present = unique_constraints_present
        self.record_id_integer = record_id_integer

    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        # SQLAlchemy reflection always reports every column's "type".
        columns: list[dict[str, Any]] = (
            [{"name": "uuid_id", "type": sa.UUID()}]
            if self.all_uuid_columns_present
            else []
        )
        if table_name == "notification_queue_jobs" and self.record_id_integer:
            columns.append({"name": "record_id", "type": sa.Integer()})
        return columns

    def get_table_names(self) -> list[str]:
        names = {table for _name, table in self.migration._SHADOW_INDEXES}
        names.update(table for table, _column in self.migration._UUID_ID_COLUMNS)
        names.update(table for table, *_rest in self.migration._FK_SPECS)
        names.update(
            table for _name, table, _columns in self.migration._INDEXES
        ) if hasattr(self.migration, "_INDEXES") else None
        names.update(
            {"failed_outbox_events", "notification_queue_jobs", "stored_events"}
        )
        if self.user_stats_present:
            names.add("user_stats")
        else:
            names.discard("user_stats")
        return sorted(names)

    def get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]:
        if not self.foreign_keys_present:
            return []
        keys = [
            {"name": f"fk_{table}_{column}"}
            for table, column, _ref_table, _ref_column, _ondelete in self.migration._FK_SPECS
            if table == table_name
        ]
        if table_name == "notification_deliveries":
            keys.append({"name": "fk_notification_deliveries_notification"})
        if table_name == "users":
            keys.append({"name": None})
        return keys

    def get_unique_constraints(self, table_name: str) -> list[dict[str, Any]]:
        if not self.unique_constraints_present:
            return []
        expected = {
            "news_likes": ["uq_news_like_user_news"],
            "notification_deliveries": ["uq_notification_delivery_once"],
            "users": ["uq_users_email"],
        }
        constraints = [{"name": name} for name in expected.get(table_name, [])]
        if table_name == "users":
            constraints.append({"name": None})
        return constraints


class _AutocommitBlock:
    def __init__(self, operations: _Operations) -> None:
        self.operations = operations

    def __enter__(self) -> _AutocommitBlock:
        self.operations._record("autocommit_block")
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class _MigrationContext:
    as_sql = False

    def __init__(self, operations: _Operations) -> None:
        self.operations = operations

    def autocommit_block(self) -> _AutocommitBlock:
        return _AutocommitBlock(self.operations)


class _Operations:
    def __init__(self, bind: object) -> None:
        self.bind = bind
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_bind(self) -> object:
        return self.bind

    def get_context(self) -> _MigrationContext:
        return _MigrationContext(self)

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> None:
        self._record("execute", statement, *args, **kwargs)

    def drop_column(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_column", *args, **kwargs)

    def drop_table(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_table", *args, **kwargs)

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_table", *args, **kwargs)

    def alter_column(self, *args: Any, **kwargs: Any) -> None:
        self._record("alter_column", *args, **kwargs)

    def create_foreign_key(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_foreign_key", *args, **kwargs)

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_index", *args, **kwargs)

    def create_unique_constraint(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_unique_constraint", *args, **kwargs)

    def drop_index(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_index", *args, **kwargs)

    def drop_constraint(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_constraint", *args, **kwargs)


def _bind_migration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    all_uuid_columns_present: bool,
    user_stats_present: bool,
    foreign_keys_present: bool,
    unique_constraints_present: bool,
    record_id_integer: bool = False,
):
    migration = _load_migration()
    bind = _CatalogBind(migration)
    operations = _Operations(bind)
    inspector = _Inspector(
        migration,
        all_uuid_columns_present=all_uuid_columns_present,
        user_stats_present=user_stats_present,
        foreign_keys_present=foreign_keys_present,
        unique_constraints_present=unique_constraints_present,
        record_id_integer=record_id_integer,
    )
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda observed: inspector
        if observed is bind
        else pytest.fail("migration inspected an unexpected connection"),
    )
    return migration, operations


def test_upgrade_creates_missing_schema_and_uses_explicit_utc_cast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(
        monkeypatch,
        all_uuid_columns_present=False,
        user_stats_present=False,
        foreign_keys_present=False,
        unique_constraints_present=False,
    )

    migration.upgrade()

    target = next(
        call
        for call in operations.calls
        if call[0] == "alter_column" and call[1][:2] == ("stored_events", "created_at")
    )
    assert target[2]["postgresql_using"] == "created_at AT TIME ZONE 'UTC'"
    assert isinstance(target[2]["existing_type"], sa.TIMESTAMP)
    assert isinstance(target[2]["type_"], sa.DateTime)
    assert target[2]["type_"].timezone is True
    assert target[2]["existing_nullable"] is False
    assert any(
        call[0] == "create_table" and call[1][0] == "user_stats"
        for call in operations.calls
    )
    assert (
        sum(call[0] == "create_foreign_key" for call in operations.calls)
        == len(migration._FK_SPECS) + 1
    )
    assert sum(call[0] == "create_unique_constraint" for call in operations.calls) == 3


def test_upgrade_removes_uuid_compatibility_columns_and_legacy_user_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(
        monkeypatch,
        all_uuid_columns_present=True,
        user_stats_present=True,
        foreign_keys_present=True,
        unique_constraints_present=True,
    )

    migration.upgrade()

    dropped_columns = [call for call in operations.calls if call[0] == "drop_column"]
    assert len(dropped_columns) == len(migration._UUID_ID_COLUMNS)
    assert any(
        call[0] == "drop_table" and call[1] == ("user_stats",)
        for call in operations.calls
    )
    assert not any(call[0] == "create_foreign_key" for call in operations.calls)
    assert not any(call[0] == "create_unique_constraint" for call in operations.calls)


@pytest.mark.parametrize("record_id_integer", [False, True])
def test_upgrade_dead_letters_only_integer_record_ids_before_the_uuid_cast(
    monkeypatch: pytest.MonkeyPatch,
    record_id_integer: bool,
) -> None:
    """AUD-351: legacy integer jobs are dead-lettered, then cast via their own id."""
    migration, operations = _bind_migration(
        monkeypatch,
        all_uuid_columns_present=False,
        user_stats_present=False,
        foreign_keys_present=False,
        unique_constraints_present=False,
        record_id_integer=record_id_integer,
    )

    migration.upgrade()

    dead_letter_updates = [
        call
        for call in operations.calls
        if call[0] == "execute"
        and "SET dead_lettered = true" in str(call[1][0])
        and "AUD-351" in str(call[1][0])
    ]
    record_alters = [
        call
        for call in operations.calls
        if call[0] == "alter_column"
        and call[1][:2]
        == (
            "notification_queue_jobs",
            "record_id",
        )
    ]
    if record_id_integer:
        assert len(dead_letter_updates) == 1
        assert len(record_alters) == 1
        assert record_alters[0][2]["postgresql_using"] == "id"
        assert record_alters[0][2]["existing_type"].__class__ is sa.Integer
        assert record_alters[0][2]["type_"].__class__ is sa.UUID
    else:
        assert dead_letter_updates == []
        assert record_alters == []


def test_downgrade_executes_every_revision_owned_reverse_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    operations = _Operations(object())
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    assert [call for call in operations.calls if call[0] == "drop_table"] == [
        ("drop_table", ("user_stats",), {})
    ]
    # 28 reconcile indexes plus the AUD-278 event full-text GIN index.
    assert sum(call[0] == "drop_index" for call in operations.calls) == 29
    assert (
        sum(call[0] == "drop_constraint" for call in operations.calls)
        == len(migration._FK_SPECS) + 4
    )


class _CatalogResult:
    def __init__(self, state: object) -> None:
        self.state = state

    def scalar_one(self) -> object:
        return self.state


class _CatalogBind:
    def __init__(
        self, migration: Any, state: object = "valid", dialect: str = "postgresql"
    ) -> None:
        self.migration = migration
        self.state = state
        self.dialect = SimpleNamespace(name=dialect)
        self.statements: list[str] = []

    def execute(self, statement: Any) -> _CatalogResult:
        sql = str(statement)
        assert sql == self.migration._EVENT_SEARCH_INDEX_STATE_SQL
        self.statements.append(sql)
        return _CatalogResult(self.state)


@pytest.mark.parametrize("state", ["conflict", None, "", "unknown", False])
def test_event_search_prelude_rejects_noncanonical_catalog_before_any_ddl(
    monkeypatch: pytest.MonkeyPatch, state: object
) -> None:
    migration = _load_migration()
    bind = _CatalogBind(migration, state)
    operations = _Operations(bind)
    monkeypatch.setattr(migration, "op", operations)

    with pytest.raises(RuntimeError, match="requires reviewed repair"):
        migration.upgrade()

    assert bind.statements == [migration._EVENT_SEARCH_INDEX_STATE_SQL]
    assert operations.calls == []


def test_event_search_prelude_keeps_valid_index_without_autocommit_or_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    bind = _CatalogBind(migration)
    operations = _Operations(bind)
    monkeypatch.setattr(migration, "op", operations)

    migration._ensure_event_search_index()

    assert bind.statements == [migration._EVENT_SEARCH_INDEX_STATE_SQL]
    assert operations.calls == []


def test_missing_event_search_index_finishes_guarded_prelude_before_shadow_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(
        monkeypatch,
        all_uuid_columns_present=False,
        user_stats_present=False,
        foreign_keys_present=False,
        unique_constraints_present=False,
    )
    operations.bind.state = "absent"

    migration.upgrade()

    prefix = operations.calls[:4]
    assert prefix[0] == ("autocommit_block", (), {})
    assert [str(call[1][0]) for call in prefix[1:]] == [
        migration._event_search_index_guard(require_present=False),
        (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_search_vector "
            "ON public.events USING gin (search_vector)"
        ),
        migration._event_search_index_guard(require_present=True),
    ]
    assert all(call[0] == "execute" for call in prefix[1:])
    assert str(operations.calls[4][1][0]).startswith("DROP INDEX IF EXISTS ")
    assert sum(call[0] == "autocommit_block" for call in operations.calls) == 1
    assert not any(
        "DROP INDEX CONCURRENTLY" in str(call[1]) for call in operations.calls
    )


@pytest.mark.parametrize("offline", [False, True])
def test_event_search_prelude_does_not_issue_postgresql_sql_for_sqlite(
    monkeypatch: pytest.MonkeyPatch, offline: bool
) -> None:
    migration = _load_migration()
    bind = _CatalogBind(migration, dialect="sqlite")
    operations = _Operations(bind)
    context = _MigrationContext(operations)
    context.as_sql = offline
    monkeypatch.setattr(operations, "get_context", lambda: context)
    monkeypatch.setattr(migration, "op", operations)

    migration._ensure_event_search_index()

    assert bind.statements == []
    assert operations.calls == []


def test_event_search_prelude_rejects_an_unsupported_dialect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    bind = _CatalogBind(migration, dialect="sqlite")
    bind.dialect.name = "unknown"
    operations = _Operations(bind)
    monkeypatch.setattr(migration, "op", operations)

    with pytest.raises(RuntimeError, match="unsupported event search index dialect"):
        migration._ensure_event_search_index()

    assert bind.statements == []
    assert operations.calls == []


def test_offline_prelude_never_reads_a_fake_catalog_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    bind = _CatalogBind(migration, state=None)
    operations = _Operations(bind)
    context = _MigrationContext(operations)
    context.as_sql = True
    monkeypatch.setattr(operations, "get_context", lambda: context)
    monkeypatch.setattr(migration, "op", operations)

    migration._ensure_event_search_index()

    assert bind.statements == []
    assert operations.calls[0] == ("autocommit_block", (), {})
    assert [str(call[1][0]) for call in operations.calls[1:]] == [
        migration._event_search_index_guard(require_present=False),
        (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_search_vector "
            "ON public.events USING gin (search_vector)"
        ),
        migration._event_search_index_guard(require_present=True),
    ]


@pytest.mark.parametrize("phase", ["preflight", "create", "postflight"])
def test_prelude_statement_failure_propagates_before_reconciliation_ddl(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    migration = _load_migration()
    bind = _CatalogBind(migration, state="absent")
    operations = _Operations(bind)
    monkeypatch.setattr(migration, "op", operations)
    ordered = [
        migration._event_search_index_guard(require_present=False),
        (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_search_vector "
            "ON public.events USING gin (search_vector)"
        ),
        migration._event_search_index_guard(require_present=True),
    ]
    failing = ordered[["preflight", "create", "postflight"].index(phase)]
    failure = RuntimeError("controlled prelude statement failure")
    execute = operations.execute

    def execute_or_fail(statement: Any, *args: Any, **kwargs: Any) -> None:
        execute(statement, *args, **kwargs)
        if str(statement) == failing:
            raise failure

    monkeypatch.setattr(operations, "execute", execute_or_fail)

    with pytest.raises(RuntimeError) as caught:
        migration.upgrade()

    assert caught.value is failure
    assert [str(call[1][0]) for call in operations.calls[1:]] == ordered[
        : ordered.index(failing) + 1
    ]
    assert operations.calls[0] == ("autocommit_block", (), {})
