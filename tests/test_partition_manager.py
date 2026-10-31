import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.partition_manager import (
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
