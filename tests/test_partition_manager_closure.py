from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import partition_manager as manager


class _Preparer:
    def quote(self, name: str) -> str:
        return f'"{name}"'


class _Result:
    def __init__(self, partitions=()):
        self.partitions = list(partitions)

    def scalars(self):
        return self

    def all(self):
        return list(self.partitions)


class _Connection:
    def __init__(
        self,
        *,
        partitions=(),
        range_bounds=(),
        drop_error=False,
        default_error=False,
        partition_create_error_name=None,
    ):
        self.dialect = SimpleNamespace(
            name="postgresql",
            identifier_preparer=_Preparer(),
        )
        self.partitions = partitions
        self.range_bounds = range_bounds
        self.drop_error = drop_error
        self.default_error = default_error
        self.partition_create_error_name = partition_create_error_name
        self.executed = []
        self.operations = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, *args):
        sql = str(statement)
        self.executed.append((sql, args))
        self.operations.append(("execute", sql))
        if self.default_error and "DEFAULT" in sql:
            raise OSError("default partition unavailable")
        if self.drop_error and "DROP TABLE" in sql:
            raise OSError("drop unavailable")
        if (
            self.partition_create_error_name
            and f'CREATE TABLE "{self.partition_create_error_name}"' in sql
        ):
            raise OSError("range partition unavailable")
        if "SELECT child.relname" in sql:
            return _Result(self.partitions)
        if "pg_get_expr(child.relpartbound" in sql:
            return _Result(self.range_bounds)
        return _Result()

    async def exec_driver_sql(self, statement):
        return await self.execute(statement)

    async def commit(self):
        self.operations.append(("commit", ""))
        self.commits += 1

    async def rollback(self):
        self.operations.append(("rollback", ""))
        self.rollbacks += 1


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


@pytest.mark.asyncio
async def test_partition_ddl_lock_binds_the_exact_parent_table_name() -> None:
    connection = MagicMock()
    connection.execute = AsyncMock()

    await manager._lock_partition_ddl(connection, "notifications")

    statement, parameters = connection.execute.await_args.args
    assert str(statement) == "SELECT pg_advisory_xact_lock(hashtext(:table_name))"
    assert parameters == {"table_name": "notifications"}


def _info(name="notifications_y2026m04", start="2026-04-01", end="2026-05-01"):
    return SimpleNamespace(name=name, start_date=start, end_date=end)


async def _run(monkeypatch, connection, *, tables, warmup=0, retention=0, rust):
    monkeypatch.setattr(manager, "engine", _Engine(connection))
    monkeypatch.setattr(manager, "PARTITIONED_TABLES", tables)
    settings = SimpleNamespace(
        partition_warmup_months=warmup,
        partition_retention_days=retention,
    )
    monkeypatch.setattr("app.core.config.settings", settings)
    with patch.dict(sys.modules, {"rust_ext": rust}):
        await manager.ensure_partitions_exist()


@pytest.mark.asyncio
async def test_default_partition_validation_and_ddl_failure(monkeypatch):
    rust = MagicMock()
    connection = _Connection(default_error=True)
    await _run(monkeypatch, connection, tables=[], rust=rust)
    assert connection.commits == 0
    assert connection.rollbacks == 2

    real_regex = manager._SAFE_IDENTIFIER_RE

    class _RejectNotifications:
        def match(self, value):
            if value in {"notifications", "notification_deliveries"}:
                return None
            return real_regex.match(value)

    monkeypatch.setattr(manager, "_SAFE_IDENTIFIER_RE", _RejectNotifications())
    connection = _Connection()
    await _run(monkeypatch, connection, tables=[], rust=rust)
    assert connection.executed == []


@pytest.mark.asyncio
async def test_future_partition_validation_and_rust_error(monkeypatch):
    rust = MagicMock()
    rust.get_partition_info.return_value = _info(name="bad;drop")
    connection = _Connection()
    await _run(
        monkeypatch,
        connection,
        tables=[("notifications", "created_at")],
        rust=rust,
    )
    assert not any("bad;drop" in sql for sql, _ in connection.executed)

    rust.get_partition_info.return_value = _info()
    connection = _Connection()
    await _run(
        monkeypatch,
        connection,
        tables=[("bad-table", "created_at")],
        rust=rust,
    )
    assert not any('PARTITION OF "bad-table"' in sql for sql, _ in connection.executed)

    rust.get_partition_info.side_effect = RuntimeError("rust unavailable")
    connection = _Connection()
    await _run(
        monkeypatch,
        connection,
        tables=[("notifications", "created_at")],
        rust=rust,
    )
    assert connection.commits == 2


@pytest.mark.asyncio
async def test_future_partition_reuses_existing_range_with_a_different_name(
    monkeypatch,
):
    """A legacy monthly name must not cause an overlapping RANGE partition."""

    rust = MagicMock()
    rust.get_partition_info.return_value = _info(
        name="notifications_y2026m08",
        start="2026-08-01T00:00:00+00:00",
        end="2026-09-01T00:00:00+00:00",
    )
    connection = _Connection(
        range_bounds=(
            "FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00')",
        ),
    )

    await _run(
        monkeypatch,
        connection,
        tables=[("notifications", "created_at")],
        rust=rust,
    )

    assert not any("notifications_y2026m08" in sql for sql, _ in connection.executed)
    range_queries = [
        (sql, args)
        for sql, args in connection.executed
        if "pg_get_expr(child.relpartbound" in sql
    ]
    assert range_queries
    assert range_queries[0][1] == ({"table_name": "notifications"},)


@pytest.mark.asyncio
async def test_failed_range_ddl_rolls_back_before_the_next_partition(monkeypatch):
    rust = MagicMock()
    rust.get_partition_info.side_effect = lambda table, _offset: _info(
        name=f"{table}_y2026m08",
        start="2026-08-01T00:00:00+00:00",
        end="2026-09-01T00:00:00+00:00",
    )
    connection = _Connection(
        partition_create_error_name="notifications_y2026m08",
    )

    await _run(
        monkeypatch,
        connection,
        tables=[
            ("notifications", "created_at"),
            ("data_access_logs", "created_at"),
        ],
        rust=rust,
    )

    failed_ddl = next(
        index
        for index, operation in enumerate(connection.operations)
        if "notifications_y2026m08" in operation[1]
    )
    rollback = next(
        index
        for index, operation in enumerate(
            connection.operations[failed_ddl + 1 :],
            start=failed_ddl + 1,
        )
        if operation[0] == "rollback"
    )
    next_ddl = next(
        index
        for index, operation in enumerate(
            connection.operations[rollback + 1 :],
            start=rollback + 1,
        )
        if "data_access_logs_y2026m08" in operation[1]
    )

    assert failed_ddl < rollback < next_ddl


def test_partition_bound_matching_normalises_legacy_catalog_timestamps():
    assert manager._partition_bound_matches(
        "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')",
        "2026-08-01T00:00:00+00:00",
        "2026-09-01T00:00:00+00:00",
    )
    assert manager._partition_bound_matches(
        "FOR VALUES FROM ('2026-08-01 03:00:00+03:00') "
        "TO ('2026-09-01 03:00:00+03:00')",
        "2026-08-01T00:00:00Z",
        "2026-09-01T00:00:00Z",
    )
    assert manager._normalise_partition_timestamp(object()) is None
    assert manager._normalise_partition_timestamp("not-a-timestamp") is None
    assert not manager._partition_bound_matches(
        None,
        "2026-08-01T00:00:00+00:00",
        "2026-09-01T00:00:00+00:00",
    )


def test_normalise_partition_timestamp_rewrites_zulu_suffix_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TrackingDateTime(datetime):
        inputs: ClassVar[list[str]] = []

        @classmethod
        def fromisoformat(cls, value: str) -> datetime:
            cls.inputs.append(value)
            return datetime.fromisoformat(value)

    monkeypatch.setattr(manager, "datetime", TrackingDateTime)

    parsed = manager._normalise_partition_timestamp("2026-08-01T00:00:00Z")

    assert parsed == datetime(2026, 8, 1, tzinfo=UTC)
    assert TrackingDateTime.inputs == ["2026-08-01T00:00:00+00:00"]


@pytest.mark.parametrize(
    ("bound", "start_date_iso", "end_date_iso"),
    (
        (
            "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')",
            "2026-08-01T00:00:00+00:00",
            None,
        ),
        (
            "FOR VALUES FROM ('2026-08-01') TO ('not-a-timestamp')",
            "2026-08-01T00:00:00+00:00",
            "2026-09-01T00:00:00+00:00",
        ),
        (
            "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')",
            None,
            "2026-09-01T00:00:00+00:00",
        ),
        (
            "FOR VALUES FROM ('not-a-timestamp') TO ('2026-09-01')",
            "not-a-timestamp",
            "2026-09-01T00:00:00+00:00",
        ),
        (
            "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')",
            "2026-08-02T00:00:00+00:00",
            "2026-09-02T00:00:00+00:00",
        ),
    ),
)
def test_partition_bound_matching_requires_four_valid_timestamps(
    bound, start_date_iso, end_date_iso
):
    """Malformed catalog or requested bounds must never be considered equal."""

    assert not manager._partition_bound_matches(
        bound,
        start_date_iso,
        end_date_iso,
    )


@pytest.mark.asyncio
async def test_partition_pruning_covers_expired_nonexpired_invalid_and_ddl_error(
    monkeypatch,
):
    rust = MagicMock()
    rust.get_partition_info.return_value = _info()
    rust.is_partition_expired.side_effect = lambda name, *_: name != "not_expired"
    connection = _Connection(
        partitions=("not_expired", "bad;drop", "old_partition"),
        drop_error=True,
    )
    await _run(
        monkeypatch,
        connection,
        tables=[("notifications", "created_at")],
        retention=30,
        rust=rust,
    )
    assert any("CREATE TABLE" in sql for sql, _ in connection.executed)
    assert any("DROP TABLE" in sql for sql, _ in connection.executed)
    assert not any('"bad;drop"' in sql for sql, _ in connection.executed)


@pytest.mark.asyncio
async def test_scheduler_logs_infrastructure_errors_and_can_stop(monkeypatch):
    calls = 0

    async def _ensure():
        nonlocal calls
        calls += 1
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(manager, "ensure_partitions_exist", _ensure)
    stop = await manager.start_partition_management_scheduler(interval_seconds=0.001)
    await asyncio.sleep(0.01)
    await stop()
    assert calls >= 1
