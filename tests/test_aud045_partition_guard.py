from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import partition_manager as manager


class _Preparer:
    def quote(self, name: str) -> str:
        return f'"{name}"'

    def quote_schema(self, name: str) -> str:
        return self.quote(name)

    def quote_identifier(self, name: str) -> str:
        return self.quote(name)


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def scalars(self):
        return _Result([getattr(row, "partition_name", row) for row in self.rows])

    def scalar(self):
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        return self.rows[0]


class _CatalogConnection:
    def __init__(
        self, candidate, *, changed_after_lock=False, timeout_ms="0", lock=True
    ):
        self.dialect = SimpleNamespace(
            name="postgresql", identifier_preparer=_Preparer()
        )
        self.candidate = candidate
        self.changed_after_lock = changed_after_lock
        self.timeout_ms = timeout_ms
        self.lock = lock
        self.sql = []
        self.calls = []
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def begin_nested(self):
        return self

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.sql.append(sql)
        self.calls.append((sql, parameters))
        if "pg_try_advisory_xact_lock" in sql:
            return _Result([self.lock])
        if "current_setting('transaction_isolation')" in sql:
            return _Result(["read committed"])
        if "pg_catalog.pg_settings" in sql:
            return _Result([self.timeout_ms])
        if "pg_inherits" in sql and "partition_name" in sql:
            if self.changed_after_lock and parameters and parameters.get("child_oid"):
                return _Result()
            return _Result([self.candidate])
        return _Result()

    async def exec_driver_sql(self, sql):
        self.sql.append(sql)
        return _Result()

    async def commit(self):
        pass

    async def rollback(self):
        self.rollbacks += 1


def _candidate(bound: str):
    return SimpleNamespace(
        parent_oid=11,
        parent_schema="public",
        child_oid=12,
        child_schema="public",
        partition_name="notifications_y1999m01",
        partition_bound=bound,
    )


async def _run(monkeypatch, candidate, *, changed_after_lock=False, connection=None):
    if connection is None:
        connection = _CatalogConnection(
            candidate, changed_after_lock=changed_after_lock
        )
    monkeypatch.setattr(manager, "engine", SimpleNamespace(connect=lambda: connection))
    monkeypatch.setattr(
        manager, "PARTITIONED_TABLES", [("notifications", "created_at")]
    )
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(partition_warmup_months=0, partition_retention_days=30),
    )
    rust = MagicMock()
    rust.get_partition_info.return_value = SimpleNamespace(
        name="notifications_y2026m01", start_date="2026-01-01", end_date="2026-02-01"
    )
    rust.is_partition_expired.return_value = True
    with patch.dict(sys.modules, {"rust_ext": rust}):
        await manager.ensure_partitions_exist()
    return [sql for sql in connection.sql if sql.startswith("DROP TABLE")]


@pytest.mark.asyncio
async def test_pruner_rejects_old_name_attached_to_future_bounds(monkeypatch):
    candidate = _candidate("FOR VALUES FROM ('2099-01-01') TO ('2099-02-01')")

    assert await _run(monkeypatch, candidate) == []


@pytest.mark.asyncio
async def test_pruner_drops_the_qualified_catalog_relation(monkeypatch):
    candidate = _candidate("FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')")

    assert await _run(monkeypatch, candidate) == [
        'DROP TABLE "public"."notifications_y1999m01"'
    ]


@pytest.mark.asyncio
async def test_pruner_revalidates_relation_after_lock(monkeypatch):
    candidate = _candidate("FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')")

    assert await _run(monkeypatch, candidate, changed_after_lock=True) == []


@pytest.mark.parametrize(
    ("name", "bound", "retention", "expected"),
    [
        (
            "notifications_y1999m01",
            "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            30,
            True,
        ),
        (
            "notifications_1999_01",
            "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            30,
            True,
        ),
        (
            "notifications_1999_1",
            "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            30,
            False,
        ),
        (
            "notifications_0000_01",
            "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            30,
            False,
        ),
        (
            "notifications_9999_12",
            "FOR VALUES FROM ('9999-12-01') TO ('9999-12-31')",
            30,
            False,
        ),
        ("notifications_y1999m01", "DEFAULT", 30, False),
        (
            "notifications_y1999m01",
            "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            0,
            False,
        ),
        (
            "notifications_y1999m01",
            "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            10**20,
            False,
        ),
    ],
)
def test_expiry_requires_canonical_name_matching_actual_month(
    name, bound, retention, expected
):
    item = manager._PartitionCandidate(11, "public", 12, "public", name, bound)

    assert (
        manager._expired_partition_has_matching_bounds("notifications", item, retention)
        is expected
    )


def test_expiry_uses_strict_cutoff_and_normalizes_catalog_timezones(monkeypatch):
    class FixedDatetime(datetime):
        current = datetime(1999, 3, 3, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return (
                cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
            )

    monkeypatch.setattr(manager, "datetime", FixedDatetime)
    item = manager._PartitionCandidate(
        11,
        "public",
        12,
        "public",
        "notifications_1999_01",
        "FOR VALUES FROM ('1998-12-31 19:00:00-05:00') "
        "TO ('1999-01-31 19:00:00-05:00')",
    )

    assert not manager._expired_partition_has_matching_bounds("notifications", item, 30)
    FixedDatetime.current += timedelta(microseconds=1)
    assert manager._expired_partition_has_matching_bounds("notifications", item, 30)


@pytest.mark.asyncio
async def test_pruner_preserves_stricter_caller_statement_timeout():
    item = manager._PartitionCandidate(
        11,
        "public",
        12,
        "public",
        "notifications_y1999m01",
        "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
    )
    connection = _CatalogConnection(item, timeout_ms="1000")
    rust = MagicMock()
    rust.is_partition_expired.return_value = True

    assert await manager._prune_expired_partition(
        connection, "notifications", "created_at", 30, rust, item
    )
    assert [
        parameters["timeout"]
        for sql, parameters in connection.calls
        if "set_config('statement_timeout'" in sql
    ] == ["1000ms", "1000ms", "1000ms", "1000ms"]


@pytest.mark.asyncio
async def test_candidate_discovery_bounds_wait_without_changing_caller_timeout():
    item = manager._PartitionCandidate(
        11,
        "public",
        12,
        "public",
        "notifications_y1999m01",
        "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
    )
    connection = _CatalogConnection(item, timeout_ms="1000")

    assert await manager._list_prunable_partitions(
        connection, "notifications", "created_at"
    ) == [item]
    assert [
        parameters["timeout"]
        for sql, parameters in connection.calls
        if "set_config('statement_timeout'" in sql
    ] == ["1000ms", "1000ms"]


@pytest.mark.asyncio
async def test_pruner_leaves_relation_untouched_when_worker_lock_is_busy():
    item = manager._PartitionCandidate(
        11,
        "public",
        12,
        "public",
        "notifications_y1999m01",
        "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
    )
    connection = _CatalogConnection(item, lock=False)
    rust = MagicMock()
    rust.is_partition_expired.return_value = True

    assert not await manager._prune_expired_partition(
        connection, "notifications", "created_at", 30, rust, item
    )
    assert not any(sql.startswith("DROP TABLE") for sql in connection.sql)


@pytest.mark.asyncio
@pytest.mark.parametrize("isolation", ["repeatable read", "serializable"])
async def test_pruner_refuses_a_fixed_snapshot(isolation):
    item = manager._PartitionCandidate(
        11,
        "public",
        12,
        "public",
        "notifications_y1999m01",
        "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
    )

    class FixedSnapshotConnection(_CatalogConnection):
        async def execute(self, statement, parameters=None):
            if "current_setting('transaction_isolation')" in str(statement):
                return _Result([isolation])
            return await super().execute(statement, parameters)

    connection = FixedSnapshotConnection(item)
    rust = MagicMock()
    rust.is_partition_expired.return_value = True

    assert not await manager._prune_expired_partition(
        connection, "notifications", "created_at", 30, rust, item
    )
    assert not any(sql.startswith("DROP TABLE") for sql in connection.sql)


@pytest.mark.asyncio
async def test_pruner_respects_native_expiry_and_rejects_unsafe_identifiers():
    item = manager._PartitionCandidate(
        11,
        "public",
        12,
        "public",
        "notifications_y1999m01",
        "FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
    )
    connection = _CatalogConnection(item)
    rust = MagicMock()
    rust.is_partition_expired.return_value = False

    assert not await manager._prune_expired_partition(
        connection, "notifications", "created_at", 30, rust, item
    )
    rust.is_partition_expired.return_value = True
    unsafe = manager._PartitionCandidate(
        11, "public", 12, "public", "unsafe-name_y1999m01", item.partition_bound
    )
    assert not await manager._prune_expired_partition(
        connection, "unsafe-name", "created_at", 30, rust, unsafe
    )
    long_table = "t" * 56
    oversized = manager._PartitionCandidate(
        11, "public", 12, "public", f"{long_table}_y1999m01", item.partition_bound
    )
    assert not await manager._prune_expired_partition(
        connection, long_table, "created_at", 30, rust, oversized
    )
    assert not any(sql.startswith("DROP TABLE") for sql in connection.sql)


@pytest.mark.asyncio
async def test_worker_rolls_back_and_continues_when_discovery_fails(monkeypatch):
    item = _candidate("FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')")
    connection = _CatalogConnection(item)
    monkeypatch.setattr(
        manager,
        "_list_prunable_partitions",
        AsyncMock(side_effect=SQLAlchemyError("synthetic discovery failure")),
    )

    assert await _run(monkeypatch, item, connection=connection) == []
    assert connection.rollbacks == 1


@pytest.mark.asyncio
async def test_worker_rolls_back_and_propagates_unexpected_pruning_failure(monkeypatch):
    item = _candidate("FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')")
    connection = _CatalogConnection(item)
    monkeypatch.setattr(
        manager,
        "_prune_expired_partition",
        AsyncMock(side_effect=SQLAlchemyError("synthetic pruning failure")),
    )

    with pytest.raises(SQLAlchemyError, match="synthetic pruning failure"):
        await _run(monkeypatch, item, connection=connection)
    assert connection.rollbacks == 1
