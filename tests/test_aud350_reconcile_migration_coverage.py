from __future__ import annotations

import importlib.util
from pathlib import Path
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
    ) -> None:
        self.migration = migration
        self.all_uuid_columns_present = all_uuid_columns_present
        self.user_stats_present = user_stats_present
        self.foreign_keys_present = foreign_keys_present
        self.unique_constraints_present = unique_constraints_present

    def get_columns(self, table_name: str) -> list[dict[str, str]]:
        return [{"name": "uuid_id"}] if self.all_uuid_columns_present else []

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


class _Operations:
    def __init__(self, bind: object) -> None:
        self.bind = bind
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_bind(self) -> object:
        return self.bind

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
):
    migration = _load_migration()
    bind = object()
    operations = _Operations(bind)
    inspector = _Inspector(
        migration,
        all_uuid_columns_present=all_uuid_columns_present,
        user_stats_present=user_stats_present,
        foreign_keys_present=foreign_keys_present,
        unique_constraints_present=unique_constraints_present,
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
    assert sum(call[0] == "drop_index" for call in operations.calls) == 28
    assert (
        sum(call[0] == "drop_constraint" for call in operations.calls)
        == len(migration._FK_SPECS) + 4
    )
