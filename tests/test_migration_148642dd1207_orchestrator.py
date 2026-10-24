from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = PROJECT_ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"


def _load_migration() -> Any:
    name = "private_migration_148642dd1207_coverage"
    spec = importlib.util.spec_from_file_location(name, CANDIDATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Result:
    def fetchone(self) -> None:
        return None

    def first(self) -> None:
        return None


class _Bind:
    def __init__(self, dialect: str) -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.executed: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.executed.append((statement, args, kwargs))
        return _Result()


class _Inspector:
    def __init__(
        self,
        source: str,
        *,
        tables_present: bool = True,
        all_indexes: bool = False,
        groups_id_integer: bool = False,
        all_user_columns: bool = False,
        truthy: bool = True,
        active_session_unique: bool = False,
        user_group_fk: bool = False,
    ) -> None:
        self.tables_present = tables_present
        self.all_indexes = all_indexes
        self.groups_id_integer = groups_id_integer
        self.all_user_columns = all_user_columns
        self.truthy = truthy
        self.active_session_unique = active_session_unique
        self.user_group_fk = user_group_fk
        self.index_names = set(re.findall(r"['\"](ix_[A-Za-z0-9_]+)['\"]", source))
        self.user_columns = {
            "id",
            "group_id",
            "webauthn_id",
            "avatar_url",
            "cover_url",
            "about",
            "record_book_number",
            "status",
            "institute",
            "course",
            "education_level",
            "track",
            "program",
            "telegram",
            "achievements",
            "spotify_access_token",
            "spotify_last_track_url",
            "spotify_refresh_token",
            "spotify_last_album_image_url",
            "dnd_end",
            "spotify_scope",
            "spotify_last_track_id",
            "spotify_last_checked_at",
            "dnd_start",
            "dnd_enabled",
            "spotify_token_expires_at",
            "timezone",
            "spotify_user_id",
        }

    def __bool__(self) -> bool:
        return self.truthy

    def has_table(self, table: str) -> bool:
        return self.tables_present

    def get_columns(self, table: str) -> list[dict[str, Any]]:
        if table == "groups":
            group_type: Any = sa.Integer() if self.groups_id_integer else sa.String()
            names = ["id"]
            if self.all_user_columns:
                names.extend(["course", "faculty"])
            return [
                {"name": name, "type": group_type if name == "id" else sa.String()}
                for name in names
            ]
        if table == "users":
            names = sorted(self.user_columns) if self.all_user_columns else ["id"]
            return [{"name": name, "type": sa.Integer()} for name in names]
        return []

    def get_indexes(self, table: str) -> list[dict[str, str]]:
        if not self.all_indexes:
            return []
        return [{"name": name} for name in sorted(self.index_names)]

    def get_foreign_keys(self, table: str) -> list[dict[str, str]]:
        if table == "users" and self.user_group_fk:
            return [{"name": "fk_users_group_id_groups"}]
        return []

    def get_unique_constraints(self, table: str) -> list[dict[str, str]]:
        if table == "active_sessions" and self.active_session_unique:
            return [{"name": "uq_active_sessions_jti"}]
        return []


class _Batch:
    def __init__(
        self, events: list[tuple[str, str, tuple[Any, ...], dict[str, Any]]], table: str
    ):
        self.events = events
        self.table = table

    def f(self, name: str) -> str:
        return name

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> None:
            self.events.append(("batch", name, (self.table, *args), kwargs))

        return record


class _BatchContext:
    def __init__(self, batch: _Batch):
        self.batch = batch

    def __enter__(self) -> _Batch:
        return self.batch

    def __exit__(self, *_exc: Any) -> None:
        return None


class _Ops:
    def __init__(self, bind: _Bind) -> None:
        self.bind = bind
        self.events: list[tuple[str, str, tuple[Any, ...], dict[str, Any]]] = []

    def get_bind(self) -> _Bind:
        return self.bind

    def f(self, name: str) -> str:
        return name

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> None:
        self.events.append(("op", "execute", (statement, *args), kwargs))

    def batch_alter_table(self, table: str, *args: Any, **kwargs: Any) -> _BatchContext:
        return _BatchContext(_Batch(self.events, table))

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> None:
            self.events.append(("op", name, args, kwargs))

        return record


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dialect: str,
    tables_present: bool = True,
    all_indexes: bool = False,
    groups_id_integer: bool = False,
    all_user_columns: bool = False,
    inspector_truthy: bool = True,
    active_session_unique: bool = False,
    user_group_fk: bool = False,
) -> tuple[Any, _Ops, _Inspector]:
    migration = _load_migration()
    bind = _Bind(dialect)
    ops = _Ops(bind)
    inspector = _Inspector(
        CANDIDATE.read_text(encoding="utf-8"),
        tables_present=tables_present,
        all_indexes=all_indexes,
        groups_id_integer=groups_id_integer,
        all_user_columns=all_user_columns,
        truthy=inspector_truthy,
        active_session_unique=active_session_unique,
        user_group_fk=user_group_fk,
    )
    monkeypatch.setattr(migration, "op", ops)
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    # The backfill has its own PG-backed behavioral suite; this harness records
    # the migration's orchestration calls without pretending to emulate data.
    monkeypatch.setattr(migration, "_backfill_spotify_integrations", lambda: None)
    migration.SKIPPED_TABLES.clear()
    return migration, ops, inspector


def _event_names(ops: _Ops, method: str) -> set[str]:
    return {
        str(args[1])
        for kind, name, args, _kwargs in ops.events
        if kind == "batch" and name == method and len(args) > 1
    }


def _executed_sql(ops: _Ops) -> str:
    return "\n".join(
        str(args[0])
        for kind, name, args, _kwargs in ops.events
        if kind == "op" and name == "execute" and args
    ).upper()


@pytest.mark.parametrize(
    ("dialect", "expected_sql"),
    [
        (
            "postgresql",
            [
                "SET LOCAL lock_timeout = '10s'",
                "SET LOCAL statement_timeout = '60s'",
            ],
        ),
        ("sqlite", []),
        ("mysql", []),
    ],
)
@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
def test_upgrade_sets_postgresql_timeouts_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
    dialect: str,
    expected_sql: list[str],
    offline: bool,
) -> None:
    migration, ops, _ = _install(monkeypatch, dialect=dialect)
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: offline)

    class _InspectionReached(RuntimeError):
        pass

    def stop_at_inspection(_bind: Any) -> Any:
        raise _InspectionReached

    monkeypatch.setattr(migration.sa, "inspect", stop_at_inspection)

    with pytest.raises(_InspectionReached):
        migration.upgrade()

    assert all(
        kind == "op" and name == "execute" for kind, name, _args, _kwargs in ops.events
    )
    assert [str(args[0]) for _kind, _name, args, _kwargs in ops.events] == expected_sql


def test_upgrade_postgresql_runs_legacy_shadow_conversion_with_existing_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        all_indexes=True,
        all_user_columns=True,
        active_session_unique=True,
        user_group_fk=True,
    )

    migration.upgrade()

    sql = _executed_sql(ops)
    assert "ADD COLUMN IF NOT EXISTS ID__INTEGER INTEGER" in sql
    assert "DROP INDEX IF EXISTS IX_GROUPS_ID" in sql
    assert "CK_ACTIVE_SESSIONS_SIGNING_KEY_NOT_NULL" in sql
    assert "DROP COLUMN" in sql
    assert not any(
        kind == "op" and name == "create_table"
        for kind, name, _args, _kwargs in ops.events
    )


def test_upgrade_postgresql_already_integer_groups_takes_retry_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        all_indexes=True,
        groups_id_integer=True,
        all_user_columns=True,
    )

    migration.upgrade()

    sql = _executed_sql(ops)
    assert "DROP INDEX IF EXISTS IX_GROUPS_ID" in sql
    assert "ID__INTEGER" not in sql


def test_upgrade_non_postgresql_adds_missing_group_columns_and_uses_mysql_autoincrement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="mysql",
        all_indexes=True,
        all_user_columns=False,
    )

    migration.upgrade()

    group_columns = {
        str(args[1].name)
        for kind, name, args, _kwargs in ops.events
        if kind == "batch" and name == "add_column" and len(args) > 1
    }
    group_alter = [
        kwargs
        for kind, name, args, kwargs in ops.events
        if kind == "batch" and name == "alter_column" and args[:2] == ("groups", "id")
    ]
    assert {"course", "faculty"} <= group_columns
    assert group_alter and group_alter[0].get("autoincrement") is True


def test_upgrade_postgresql_tables_without_indexes_takes_create_index_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        all_indexes=False,
        groups_id_integer=True,
        all_user_columns=False,
    )

    migration.upgrade()

    sql = _executed_sql(ops)
    assert "ID__INTEGER" not in sql
    assert "DROP INDEX IF EXISTS IX_GROUPS_ID" not in sql
    created_indexes = _event_names(ops, "create_index")
    assert "ix_users_group_id" in created_indexes
    assert "ix_users_webauthn_id" in created_indexes


def test_upgrade_postgresql_legacy_group_cutover_without_existing_group_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        all_indexes=False,
        groups_id_integer=False,
        all_user_columns=True,
    )

    migration.upgrade()

    sql = _executed_sql(ops)
    assert "DROP COLUMN ID" in sql
    assert "CREATE INDEX IF NOT EXISTS IX_GROUPS_ID" in sql


def test_upgrade_non_postgresql_preserves_existing_group_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="sqlite",
        all_indexes=True,
        all_user_columns=True,
    )

    migration.upgrade()

    group_adds = [
        args[1].name
        for kind, name, args, _kwargs in ops.events
        if kind == "batch"
        and name == "add_column"
        and len(args) > 1
        and args[0] == "groups"
        and hasattr(args[1], "name")
    ]
    assert group_adds == []


def test_upgrade_postgresql_with_absent_tables_takes_create_and_skip_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        tables_present=False,
    )

    migration.upgrade()

    created = {
        str(args[0])
        for kind, name, args, _kwargs in ops.events
        if kind == "op" and name == "create_table" and args
    }
    assert {"chats", "spotify_integrations"} <= created
    assert "ADD COLUMN IF NOT EXISTS ID__INTEGER INTEGER" not in _executed_sql(ops)


def test_upgrade_uses_empty_metadata_when_inspector_is_falsey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="sqlite",
        all_indexes=True,
        all_user_columns=False,
        inspector_truthy=False,
    )

    migration.upgrade()

    group_adds = [
        args[1].name
        for kind, name, args, _kwargs in ops.events
        if kind == "batch"
        and name == "add_column"
        and len(args) > 1
        and hasattr(args[1], "name")
    ]
    assert "course" in group_adds and "faculty" in group_adds


def test_downgrade_emits_only_recorded_actions_for_postgresql_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        all_indexes=True,
        all_user_columns=True,
        active_session_unique=True,
        user_group_fk=True,
    )

    migration.downgrade()

    sql = _executed_sql(ops)
    assert "ID__VARCHAR VARCHAR(20)" in sql
    assert "DROP CONSTRAINT IF EXISTS CK_ACTIVE_SESSIONS_SIGNING_KEY_NOT_NULL" in sql
    assert "ALTER COLUMN SIGNING_KEY DROP NOT NULL" in sql
    assert (
        sum(1 for kind, name, *_ in ops.events if kind == "op" and name == "drop_table")
        > 10
    )


def test_downgrade_covers_missing_tables_and_indexes_without_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="sqlite",
        tables_present=False,
        all_indexes=False,
        all_user_columns=False,
    )

    migration.downgrade()

    dropped_tables = [
        args[0]
        for kind, name, args, _kwargs in ops.events
        if kind == "op" and name == "drop_table" and args
    ]
    assert dropped_tables == []
    assert not _executed_sql(ops)


def test_postgresql_downgrade_skips_groups_shadow_reversal_when_groups_are_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="postgresql",
        tables_present=False,
        all_indexes=False,
    )

    migration.downgrade()

    sql = _executed_sql(ops)
    assert "ID__VARCHAR" not in sql
    assert "LOCK TABLE GROUPS" not in sql


def test_downgrade_existing_tables_without_indexes_takes_create_index_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="sqlite",
        all_indexes=False,
        all_user_columns=False,
    )

    migration.downgrade()

    created_indexes = _event_names(ops, "create_index")
    assert "ix_groups_id" in created_indexes
    assert "ix_users_spotify_user_id" in created_indexes
    assert "ix_users_spotify_token_expires_at" in created_indexes


def test_downgrade_covers_existing_tables_indexes_and_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, _ = _install(
        monkeypatch,
        dialect="sqlite",
        all_indexes=True,
        all_user_columns=True,
        active_session_unique=True,
        user_group_fk=True,
    )

    migration.downgrade()

    assert "ix_spotify_integrations_token_expires_at" in _event_names(ops, "drop_index")
    assert "fk_users_group_id_groups" in _event_names(ops, "drop_constraint")
    assert "faculty" in _event_names(ops, "drop_column")
    assert "course" in _event_names(ops, "drop_column")


def test_upgrade_inspection_error_falls_back_before_first_table_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    bind = _Bind("sqlite")
    ops = _Ops(bind)
    monkeypatch.setattr(migration, "op", ops)
    monkeypatch.setattr(
        migration, "context", SimpleNamespace(is_offline_mode=lambda: False)
    )
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda _bind: (_ for _ in ()).throw(sa.exc.NoInspectionAvailable("offline")),
    )
    monkeypatch.setattr(migration, "_backfill_spotify_integrations", lambda: None)

    class _ReachedFirstCreate(RuntimeError):
        pass

    def stop_at_first_create(*_args: Any, **_kwargs: Any) -> None:
        raise _ReachedFirstCreate

    monkeypatch.setattr(migration, "safe_create_table", stop_at_first_create)

    with pytest.raises(_ReachedFirstCreate):
        migration.upgrade()
    assert any(
        kind == "batch" and name == "alter_column" for kind, name, *_ in ops.events
    )


def test_upgrade_with_unavailable_inspector_exposes_later_unconditional_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    bind = _Bind("sqlite")
    ops = _Ops(bind)
    monkeypatch.setattr(migration, "op", ops)
    monkeypatch.setattr(
        migration, "context", SimpleNamespace(is_offline_mode=lambda: False)
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: None)
    monkeypatch.setattr(migration, "_backfill_spotify_integrations", lambda: None)

    with pytest.raises(AttributeError, match="has_table"):
        migration.upgrade()

    assert any(
        kind == "batch" and name == "alter_column" for kind, name, *_ in ops.events
    )
