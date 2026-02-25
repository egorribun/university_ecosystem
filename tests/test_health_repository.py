from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.health_repository import HealthRepository
from app.schemas.dtos.analytics import HealthStatsDTO


@pytest.mark.asyncio
async def test_check_connectivity_success():
    mock_conn = AsyncMock()
    repo = HealthRepository(mock_conn)
    assert await repo.check_connectivity() is True
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_check_connectivity_failure():
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("DB Down")
    repo = HealthRepository(mock_conn)
    assert await repo.check_connectivity() is False


@pytest.mark.asyncio
async def test_check_notification_queue_accessible_success():
    mock_conn = AsyncMock()
    repo = HealthRepository(mock_conn)
    assert await repo.check_notification_queue_accessible() is True


@pytest.mark.asyncio
async def test_check_notification_queue_accessible_failure():
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("Table missing")
    repo = HealthRepository(mock_conn)
    assert await repo.check_notification_queue_accessible() is False


@pytest.mark.asyncio
async def test_get_table_count_pg_success():
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (100,)
    mock_conn.execute.return_value = mock_result

    repo = HealthRepository(mock_conn)
    count = await repo.get_table_count("users")
    assert count == 100


@pytest.mark.asyncio
async def test_get_table_count_fallback():
    mock_conn = AsyncMock()

    # First call (PG) fails
    # Second call (Fallback) succeeds
    mock_result_fallback = MagicMock()
    mock_result_fallback.fetchone.return_value = (50,)

    mock_conn.execute.side_effect = [
        Exception("Not PG"),  # First call: pg_class
        mock_result_fallback,  # Second call: COUNT(*)
    ]

    repo = HealthRepository(mock_conn)
    count = await repo.get_table_count("users")
    assert count == 50
    assert mock_conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_table_count_failure():
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("Total failure")

    repo = HealthRepository(mock_conn)
    count = await repo.get_table_count("users")
    assert count is None


@pytest.mark.asyncio
async def test_get_connection_stats_success():
    mock_conn = AsyncMock()
    mock_result = MagicMock()
    # active_connections, commits, rollbacks, cache_hits, disk_reads
    # In HealthRepository.get_connection_stats:
    # row[0] = numbackends
    # row[1] = xact_commit
    # row[2] = xact_rollback
    # row[3] = blks_hit
    # row[4] = blks_read
    mock_result.fetchone.return_value = (10, 100, 5, 90, 10)
    mock_conn.execute.return_value = mock_result

    repo = HealthRepository(mock_conn)
    stats = await repo.get_connection_stats()
    assert stats.active_connections == 10
    assert stats.commits == 100
    assert stats.rollbacks == 5
    assert stats.cache_hit_ratio == 0.9


@pytest.mark.asyncio
async def test_get_connection_stats_failure():
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("Not PG")
    repo = HealthRepository(mock_conn)
    stats = await repo.get_connection_stats()
    assert stats == HealthStatsDTO(
        active_connections=0, commits=0, rollbacks=0, cache_hit_ratio=1.0
    )
