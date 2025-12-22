import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.partition_manager import (
    PARTITIONED_TABLES,
    ensure_partitions_exist,
    start_partition_management_scheduler,
)


class TestPartitionManager:
    @pytest.mark.asyncio
    async def test_ensure_partitions_exist_non_postgresql(self):
        """Should skip if not PostgreSQL."""
        mock_conn = AsyncMock()
        mock_conn.dialect.name = "sqlite"

        with patch("app.services.partition_manager.engine") as mock_engine:
            mock_engine.connect.return_value.__aenter__.return_value = mock_conn

            await ensure_partitions_exist()
            mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_partitions_exist_postgresql(self):
        """Should execute CREATE TABLE on PostgreSQL."""
        mock_conn = AsyncMock()
        mock_conn.dialect.name = "postgresql"
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()

        with patch("app.services.partition_manager.engine") as mock_engine:
            mock_engine.connect.return_value.__aenter__.return_value = mock_conn

            await ensure_partitions_exist(months_ahead=0)

            # verify it tries to create tables for current month
            assert mock_conn.execute.call_count >= len(PARTITIONED_TABLES)
            mock_conn.commit.assert_called()

    @pytest.mark.asyncio
    async def test_scheduler_lifecycle(self):
        """Should start and be able to stop scheduler."""
        with patch(
            "app.services.partition_manager.ensure_partitions_exist",
            new_callable=AsyncMock,
        ) as mock_ensure:
            # use small interval
            stop_func = await start_partition_management_scheduler(interval_seconds=0.1)

            # wait a bit for it to run at least once
            await asyncio.sleep(0.2)

            assert mock_ensure.called

            await stop_func()
