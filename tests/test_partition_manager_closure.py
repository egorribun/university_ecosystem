from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    def __init__(self, *, partitions=(), drop_error=False, default_error=False):
        self.dialect = SimpleNamespace(
            name="postgresql",
            identifier_preparer=_Preparer(),
        )
        self.partitions = partitions
        self.drop_error = drop_error
        self.default_error = default_error
        self.executed = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, *args):
        sql = str(statement)
        self.executed.append((sql, args))
        if self.default_error and "DEFAULT" in sql:
            raise OSError("default partition unavailable")
        if self.drop_error and "DROP TABLE" in sql:
            raise OSError("drop unavailable")
        if "SELECT child.relname" in sql:
            return _Result(self.partitions)
        return _Result()

    async def commit(self):
        self.commits += 1


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


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
