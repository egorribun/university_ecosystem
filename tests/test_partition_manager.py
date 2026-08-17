import asyncio
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
        mock_conn.dialect.identifier_preparer = mock_preparer

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

        mock_drop_result = MagicMock()

        # Bound SELECT statements use execute(); validated PostgreSQL DDL uses
        # exec_driver_sql(), which is the SQLAlchemy API for driver-level DDL.
        from app.services.partition_manager import PARTITIONED_TABLES

        num_tables = len(PARTITIONED_TABLES)
        mock_conn.execute.side_effect = [mock_old_partitions] * num_tables
        mock_conn.exec_driver_sql.side_effect = [mock_create_result] * (
            2 + num_tables
        ) + [mock_drop_result] * num_tables
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
