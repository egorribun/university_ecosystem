import asyncio
import runpy
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import database
from app.services import partition_manager as manager
from app.services.partition_manager import (
    PartitionMaintenanceError,
    ensure_partitions_exist,
    start_partition_management_scheduler,
)


@pytest.mark.asyncio
async def test_ensure_partitions_exist_postgresql_mock(monkeypatch):
    # Mock settings
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.partition_warmup_months = 0
        mock_settings.partition_retention_days = 30

        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.dialect.name = "postgresql"
        # The real code uses conn.dialect.identifier_preparer.quote() for safe DDL
        mock_preparer = MagicMock()
        mock_preparer.quote = MagicMock(side_effect=lambda name: f'"{name}"')
        mock_preparer.quote_identifier = MagicMock(side_effect=lambda name: f'"{name}"')
        mock_conn.dialect.identifier_preparer = mock_preparer
        mock_conn.begin_nested = MagicMock()
        mock_conn.begin_nested.return_value.__aenter__ = AsyncMock()
        mock_conn.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)

        # Correctly mock the async context manager for engine.connect()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock()

        # Monkeypatch the engine in the module
        monkeypatch.setattr("app.services.partition_manager.engine", mock_engine)

        # Mock result for partition listing
        mock_create_result = MagicMock()

        mock_old_partitions = MagicMock()
        mock_old_partitions.scalars.return_value.all.return_value = [
            "notifications_y1999m01"
        ]
        mock_old_partitions.all.return_value = [
            SimpleNamespace(
                parent_oid=11,
                parent_schema="public",
                child_oid=12,
                child_schema="public",
                partition_name="notifications_y1999m01",
                partition_bound="FOR VALUES FROM ('1999-01-01') TO ('1999-02-01')",
            )
        ]
        mock_old_partitions.scalar_one.return_value = True

        # Bound SELECT statements use execute(); validated PostgreSQL DDL uses
        # exec_driver_sql(), which is the SQLAlchemy API for driver-level DDL.
        # The manager now performs additional bound lookups and advisory-lock
        # calls before each idempotent DDL operation.  Every catalog query in
        # this focused mock may return the same harmless legacy partition.
        def execute_result(statement, *_args):
            result = MagicMock()
            if "current_setting('transaction_isolation')" in str(statement):
                result.scalar_one.return_value = "read committed"
                return result
            if "pg_catalog.pg_settings" in str(statement):
                result.scalar_one.return_value = "0"
                return result
            return mock_old_partitions

        mock_conn.execute.side_effect = execute_result
        mock_conn.exec_driver_sql.return_value = mock_create_result
        mock_conn.commit = AsyncMock()

        # Mock rust_ext
        mock_partition_info = MagicMock()
        mock_partition_info.name = "notifications_y2026m04"
        mock_partition_info.start_date = "2026-04-01"
        mock_partition_info.end_date = "2026-05-01"

        mock_rust = MagicMock()
        mock_rust.get_partition_info.return_value = mock_partition_info
        mock_rust.is_partition_expired.return_value = True

        with patch.dict("sys.modules", {"rust_ext": mock_rust}):
            await ensure_partitions_exist()

        # Verify execute was called for CREATE TABLE
        # We check the SQL string inside the TextClause
        found_create = False
        for call in mock_conn.exec_driver_sql.call_args_list:
            sql = str(call[0][0])
            if "CREATE TABLE" in sql:
                found_create = True
                break
        assert found_create, "CREATE TABLE not found in execute calls"

        # Verify DROP TABLE was attempted for old partition
        found_drop = False
        for call in mock_conn.exec_driver_sql.call_args_list:
            sql = str(call[0][0])
            if "DROP TABLE" in sql:
                found_drop = True
                break
        assert found_drop, "DROP TABLE not found in execute calls"


@pytest.mark.asyncio
async def test_ensure_partitions_exist_skipped_on_sqlite(monkeypatch):
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.dialect.name = "sqlite"
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    monkeypatch.setattr("app.services.partition_manager.engine", mock_engine)

    await ensure_partitions_exist()
    assert mock_conn.execute.call_count == 0
    assert mock_conn.exec_driver_sql.call_count == 0


@pytest.mark.asyncio
async def test_partition_scheduler():
    from app.services import partition_manager

    with patch.object(
        partition_manager, "ensure_partitions_exist", new_callable=AsyncMock
    ) as mock_ensure:
        stop_func = await start_partition_management_scheduler(interval_seconds=0.01)
        await asyncio.sleep(0.05)
        await stop_func()
        assert mock_ensure.called


def _engine_and_conn(dialect_name: str = "postgresql") -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.dialect = SimpleNamespace(
        name=dialect_name,
        identifier_preparer=SimpleNamespace(
            quote=lambda name: f'"{name}"',
            quote_identifier=lambda name: f'"{name}"',
        ),
    )
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
    engine.dispose = AsyncMock()
    return engine, conn


@contextmanager
def _ensure_mocks(
    engine: MagicMock,
    *,
    authority: bool = True,
    rust_name: str = "data_access_logs_y2026m11",
) -> Iterator[SimpleNamespace]:
    """Replace each catalog and DDL helper so ensure's branches run in isolation."""
    rust = MagicMock()
    rust.get_partition_info.return_value = SimpleNamespace(
        name=rust_name, start_date="2026-11-01", end_date="2026-12-01"
    )
    mocks = SimpleNamespace(
        authority=AsyncMock(return_value=authority),
        lock=AsyncMock(),
        range_exists=AsyncMock(return_value=False),
        prunable=AsyncMock(return_value=[]),
        isolate=AsyncMock(),
        revoke=AsyncMock(),
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(manager, "engine", engine))
        stack.enter_context(
            patch(
                "app.core.config.settings",
                SimpleNamespace(
                    partition_warmup_months=0, partition_retention_days=365
                ),
            )
        )
        stack.enter_context(patch.dict("sys.modules", {"rust_ext": rust}))
        stack.enter_context(
            patch.object(manager, "_has_partition_ddl_authority", mocks.authority)
        )
        stack.enter_context(patch.object(manager, "_lock_partition_ddl", mocks.lock))
        stack.enter_context(
            patch.object(manager, "_range_partition_exists", mocks.range_exists)
        )
        stack.enter_context(
            patch.object(manager, "_list_prunable_partitions", mocks.prunable)
        )
        stack.enter_context(
            patch.object(manager, "_isolate_audit_partitions", mocks.isolate)
        )
        stack.enter_context(
            patch.object(manager, "_revoke_runtime_access", mocks.revoke)
        )
        yield mocks


@pytest.mark.asyncio
async def test_ensure_refuses_a_login_without_ddl_authority_before_any_ddl() -> None:
    engine, conn = _engine_and_conn()
    with _ensure_mocks(engine, authority=False) as mocks:
        assert await ensure_partitions_exist() is False
    mocks.lock.assert_not_called()
    mocks.isolate.assert_not_called()
    conn.exec_driver_sql.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_reports_no_refusal_for_non_postgresql_dialects() -> None:
    engine, conn = _engine_and_conn("sqlite")
    with _ensure_mocks(engine) as mocks:
        assert await ensure_partitions_exist() is True
    mocks.authority.assert_not_called()
    conn.exec_driver_sql.assert_not_called()


@pytest.mark.asyncio
async def test_audit_leaf_is_revoked_inside_the_transaction_that_creates_it() -> None:
    events: list[tuple[str, str]] = []
    engine, conn = _engine_and_conn()
    conn.exec_driver_sql.side_effect = lambda sql, *_: events.append(("sql", str(sql)))
    conn.commit.side_effect = lambda: events.append(("commit", ""))
    with _ensure_mocks(engine) as mocks:
        mocks.revoke.side_effect = lambda _conn, relation: events.append(
            ("revoke", relation)
        )
        assert await ensure_partitions_exist() is True

    relation = '"data_access_logs_y2026m11"'
    assert [event for event in events if event[0] == "revoke"] == [("revoke", relation)]
    position = events.index(("revoke", relation))
    assert events[position - 1][0] == "sql"
    assert "CREATE TABLE" in events[position - 1][1]
    assert events[position + 1] == ("commit", "")


@pytest.mark.asyncio
async def test_failed_creation_is_logged_and_skipped_when_not_strict() -> None:
    engine, conn = _engine_and_conn()
    conn.exec_driver_sql.side_effect = _fail_non_default_creates
    with (
        _ensure_mocks(engine) as mocks,
        patch.object(manager, "logger") as logger,
    ):
        assert await ensure_partitions_exist() is True
    mocks.isolate.assert_awaited_once()
    assert logger.error.call_count == 3


@pytest.mark.asyncio
async def test_failed_creation_raises_after_isolation_when_strict() -> None:
    engine, conn = _engine_and_conn()
    conn.exec_driver_sql.side_effect = _fail_non_default_creates
    with _ensure_mocks(engine) as mocks:
        with pytest.raises(PartitionMaintenanceError, match="3 partition creation"):
            await ensure_partitions_exist(strict=True)
    mocks.isolate.assert_awaited_once()


@pytest.mark.asyncio
async def test_strict_run_without_failures_returns_true() -> None:
    engine, _conn = _engine_and_conn()
    with _ensure_mocks(engine) as mocks:
        assert await ensure_partitions_exist(strict=True) is True
    mocks.isolate.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_default_partition_raises_after_isolation_when_strict() -> None:
    engine, conn = _engine_and_conn()
    conn.exec_driver_sql.side_effect = _fail_default_creates
    with _ensure_mocks(engine) as mocks:
        with pytest.raises(PartitionMaintenanceError, match="2 partition creation"):
            await ensure_partitions_exist(strict=True)
    mocks.isolate.assert_awaited_once()


def _fail_non_default_creates(sql: object, *_: object) -> None:
    if "CREATE TABLE" in str(sql) and "DEFAULT" not in str(sql):
        raise OSError("synthetic partition creation failure")


def _fail_default_creates(sql: object, *_: object) -> None:
    if "CREATE TABLE" in str(sql) and "DEFAULT" in str(sql):
        raise OSError("synthetic default partition failure")


@pytest.mark.asyncio
async def test_isolation_revokes_every_attached_audit_leaf() -> None:
    _engine, conn = _engine_and_conn()
    rows = [
        SimpleNamespace(
            child_schema="public", partition_name="data_access_logs_y2026m11"
        ),
        SimpleNamespace(
            child_schema="archive", partition_name="data_access_logs_y2025m01"
        ),
    ]
    conn.execute.return_value = SimpleNamespace(all=lambda: rows)
    with patch.object(manager, "_revoke_runtime_access", AsyncMock()) as revoke:
        await manager._isolate_audit_partitions(conn)
    assert [call.args[1] for call in revoke.await_args_list] == [
        '"public"."data_access_logs_y2026m11"',
        '"archive"."data_access_logs_y2025m01"',
    ]
    conn.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_isolation_with_no_attached_leaves_issues_no_write() -> None:
    _engine, conn = _engine_and_conn()
    conn.execute.return_value = SimpleNamespace(all=lambda: [])
    with patch.object(manager, "_revoke_runtime_access", AsyncMock()) as revoke:
        await manager._isolate_audit_partitions(conn)
    revoke.assert_not_awaited()
    conn.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_skips_a_missing_runtime_role() -> None:
    _engine, conn = _engine_and_conn()
    conn.execute.return_value = SimpleNamespace(scalar_one=lambda: False)
    await manager._revoke_runtime_access(conn, '"public"."data_access_logs_y2026m11"')
    conn.exec_driver_sql.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_removes_every_runtime_grant_on_the_leaf() -> None:
    _engine, conn = _engine_and_conn()
    conn.execute.return_value = SimpleNamespace(scalar_one=lambda: True)
    await manager._revoke_runtime_access(conn, '"public"."data_access_logs_y2026m11"')
    conn.exec_driver_sql.assert_awaited_once_with(
        'REVOKE ALL ON "public"."data_access_logs_y2026m11" FROM ue_app'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", [True, False])
async def test_ddl_authority_probe_reads_the_schema_create_privilege(
    authority: bool,
) -> None:
    _engine, conn = _engine_and_conn()
    conn.execute.return_value = SimpleNamespace(scalar_one=lambda: authority)
    assert await manager._has_partition_ddl_authority(conn) is authority
    statement = str(conn.execute.await_args.args[0])
    assert "has_schema_privilege" in statement
    assert "'CREATE'" in statement


@pytest.mark.asyncio
async def test_run_maintenance_refuses_the_runtime_login_with_exit_status_one() -> None:
    engine, _conn = _engine_and_conn()
    with (
        patch.object(manager, "engine", engine),
        patch.object(
            manager, "ensure_partitions_exist", AsyncMock(return_value=False)
        ) as ensure,
    ):
        assert await manager.run_maintenance() == 1
    ensure.assert_awaited_once_with(strict=True)
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_maintenance_succeeds_with_exit_status_zero() -> None:
    engine, _conn = _engine_and_conn()
    with (
        patch.object(manager, "engine", engine),
        patch.object(manager, "ensure_partitions_exist", AsyncMock(return_value=True)),
    ):
        assert await manager.run_maintenance() == 0
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        PartitionMaintenanceError("leaf not isolated"),
        OSError("connection reset"),
        ValueError("unparsed bound 2026-13-99"),
        TypeError("unexpected rust payload"),
    ],
)
async def test_run_maintenance_fails_closed_on_any_maintenance_failure(
    failure: Exception,
) -> None:
    engine, _conn = _engine_and_conn()
    with (
        patch.object(manager, "engine", engine),
        patch.object(
            manager, "ensure_partitions_exist", AsyncMock(side_effect=failure)
        ),
        patch.object(manager, "logger") as logger,
    ):
        assert await manager.run_maintenance() == 1
    logger.error.assert_called_once_with(
        "Partition maintenance failed (%s)", type(failure).__name__
    )
    assert str(failure) not in str(logger.error.call_args)
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_maintenance_lets_interrupts_propagate() -> None:
    engine, _conn = _engine_and_conn()
    with (
        patch.object(manager, "engine", engine),
        patch.object(
            manager,
            "ensure_partitions_exist",
            AsyncMock(side_effect=KeyboardInterrupt),
        ),
    ):
        with pytest.raises(KeyboardInterrupt):
            await manager.run_maintenance()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_maintenance_exits_one_when_a_default_partition_fails() -> None:
    engine, conn = _engine_and_conn()
    conn.exec_driver_sql.side_effect = _fail_default_creates
    with (
        _ensure_mocks(engine),
        patch.object(manager, "logger") as logger,
    ):
        assert await manager.run_maintenance() == 1
    logger.error.assert_called_with(
        "Partition maintenance failed (%s)", "PartitionMaintenanceError"
    )
    engine.dispose.assert_awaited_once()


def test_main_returns_the_maintenance_status() -> None:
    with patch.object(manager, "run_maintenance", AsyncMock(return_value=7)):
        assert manager.main() == 7


def test_module_entrypoint_exits_with_the_maintenance_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _conn = _engine_and_conn("sqlite")
    monkeypatch.setattr(database, "engine", engine)
    # runpy executes a fresh copy; drop the cached module so it is not re-imported.
    monkeypatch.delitem(sys.modules, "app.services.partition_manager")
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("app.services.partition_manager", run_name="__main__")
    assert exit_info.value.code == 0
