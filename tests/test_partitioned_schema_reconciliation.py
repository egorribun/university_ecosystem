"""Contracts for repairing constraints dropped by the range-table rebuild."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "alembic" / "versions" / "202608270003_reconcile_partitioned_schema.py"
)
LEGACY_PARTITION_MIGRATION = (
    ROOT / "alembic" / "versions" / "202607020001_create_range_partitions.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "partitioned_schema_reconcile", MIGRATION
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves postponed annotations through ``sys.modules``;
    # register the dynamically loaded migration just like Alembic does.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_legacy_partition_migration():
    spec = importlib.util.spec_from_file_location(
        "legacy_partition_migration", LEGACY_PARTITION_MIGRATION
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _RelkindResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def first(self):
        return (self.value,)

    def fetchone(self):
        return (self.value,)


class _RelkindConnection:
    class dialect:
        name = "postgresql"

    def __init__(self, value: object) -> None:
        self.value = value

    def execute(self, *_args, **_kwargs):
        return _RelkindResult(self.value)


class _PartitionResult:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[str]]:
        return self.rows


class _PartitionConnection:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.rows = rows
        self.statement = ""

    def execute(self, statement, *_args, **_kwargs):
        self.statement = str(statement)
        return _PartitionResult(self.rows)


class _PartitionKeyConnection:
    class dialect:
        name = "postgresql"

    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return _PartitionResult(self.rows)


def test_revision_follows_failed_login_reconciliation() -> None:
    migration = _load_migration()

    assert migration.revision == "202608270003"
    assert migration.down_revision == "202608270002"


def test_contract_covers_partitioned_audit_and_notification_tables() -> None:
    migration = _load_migration()

    assert set(migration._TABLE_CONTRACTS) == {
        "data_access_logs",
        "failed_login_attempts",
        "notifications",
        "notification_deliveries",
    }
    assert migration._TABLE_CONTRACTS["data_access_logs"].primary_key == (
        "id",
        "created_at",
    )
    assert migration._TABLE_CONTRACTS["notifications"].primary_key == (
        "id",
        "created_at",
    )
    assert migration._TABLE_CONTRACTS["notification_deliveries"].primary_key == (
        "id",
        "attempted_at",
    )
    assert migration._TABLE_CONTRACTS["failed_login_attempts"].primary_key == (
        "id",
        "attempted_at",
    )


def test_primary_key_matching_requires_exact_ordered_columns() -> None:
    migration = _load_migration()

    assert migration._primary_key_matches(
        {"constrained_columns": ["id", "created_at"]},
        ("id", "created_at"),
    )
    assert not migration._primary_key_matches(
        {"constrained_columns": ["created_at", "id"]},
        ("id", "created_at"),
    )
    assert not migration._primary_key_matches({}, ("id", "created_at"))


def test_foreign_key_matching_rejects_wrong_action_or_target() -> None:
    migration = _load_migration()
    expected = migration.ForeignKeySpec(
        name="fk_data_access_logs_actor_user_id",
        columns=("actor_user_id",),
        referred_table="users",
        referred_columns=("id",),
        ondelete="SET NULL",
    )

    assert migration._foreign_key_matches(
        {
            "constrained_columns": ["actor_user_id"],
            "referred_table": "users",
            "referred_columns": ["id"],
            "options": {"ondelete": "SET NULL"},
        },
        expected,
    )
    assert not migration._foreign_key_matches(
        {
            "constrained_columns": ["actor_user_id"],
            "referred_table": "users",
            "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        },
        expected,
    )
    assert not migration._foreign_key_matches(
        {
            "constrained_columns": ["actor_user_id"],
            "referred_table": "other_users",
            "referred_columns": ["id"],
            "options": {"ondelete": "SET NULL"},
        },
        expected,
    )


def test_index_matching_requires_columns_and_non_unique_definition() -> None:
    migration = _load_migration()

    assert migration._index_matches(
        {"column_names": ["actor_user_id"], "unique": False},
        ("actor_user_id",),
    )
    assert not migration._index_matches(
        {"column_names": ["subject_user_id"], "unique": False},
        ("actor_user_id",),
    )
    assert not migration._index_matches(
        {"column_names": ["actor_user_id"], "unique": True},
        ("actor_user_id",),
    )


def test_unique_constraint_matching_requires_exact_columns() -> None:
    migration = _load_migration()

    assert migration._unique_matches(
        {
            "column_names": [
                "notification_id",
                "channel",
                "subscription_id",
                "attempted_at",
            ]
        },
        ("notification_id", "channel", "subscription_id", "attempted_at"),
    )
    assert not migration._unique_matches(
        {"column_names": ["notification_id", "channel"]},
        ("notification_id", "channel", "subscription_id", "attempted_at"),
    )


def test_wrong_existing_constraint_fails_closed() -> None:
    migration = _load_migration()

    with pytest.raises(RuntimeError, match="primary key"):
        migration._assert_existing_or_missing(
            "notifications",
            "primary key",
            [{"constrained_columns": ["id"]}],
            ("id", "created_at"),
            migration._primary_key_matches,
        )


def test_catalog_relkind_bytes_are_normalized_for_asyncpg() -> None:
    migration = _load_migration()
    legacy = _load_legacy_partition_migration()
    connection = _RelkindConnection(b"p")

    assert migration._get_relkind(connection, "notifications") == "p"
    assert legacy._get_relkind(connection, "notifications") == "p"

    regular = _RelkindConnection(b"r")
    assert migration._get_relkind(regular, "failed_login_attempts") == "r"
    assert legacy._get_relkind(regular, "failed_login_attempts") == "r"


def test_legacy_partition_listing_excludes_non_partition_inheritance() -> None:
    legacy = _load_legacy_partition_migration()
    connection = _PartitionConnection([("notifications_2026_08",)])

    # The database predicate, rather than a caller-side name heuristic, is
    # authoritative: only actual PostgreSQL partition children may suppress
    # creation of the corresponding range partition.
    assert legacy._existing_partition_names(connection, "notifications") == {
        "notifications_2026_08"
    }
    assert "parent.relkind = 'p'" in connection.statement
    assert "child.relispartition" in connection.statement


def test_partition_contract_requires_range_key_column() -> None:
    migration = _load_migration()

    assert migration._partition_key_matches(
        _PartitionKeyConnection([("r", "created_at")]), "notifications", "created_at"
    )
    assert migration._partition_key_matches(
        _PartitionKeyConnection([(b"r", "created_at")]), "notifications", "created_at"
    )
    assert not migration._partition_key_matches(
        _PartitionKeyConnection([("h", "created_at")]), "notifications", "created_at"
    )
    assert not migration._partition_key_matches(
        _PartitionKeyConnection([("r", "attempted_at")]), "notifications", "created_at"
    )
