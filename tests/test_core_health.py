from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.health import (
    HealthStatus,
    check_database_connectivity,
    check_database_health,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    # execute must be an AsyncMock because it's awaited
    db.execute = AsyncMock()
    # get_bind is synchronous in SQLAlchemy AsyncSession
    db.get_bind = MagicMock()
    return db


@pytest.mark.asyncio
async def test_check_database_health_healthy(mock_db):
    # Mock latency to be healthy
    with patch("time.perf_counter", side_effect=[0, 0.01]):  # 10ms
        result = await check_database_health(mock_db)
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms == 10.0
        assert "normally" in result.message


@pytest.mark.asyncio
async def test_check_database_health_degraded(mock_db):
    # Mock latency to be degraded (slow)
    with patch("time.perf_counter", side_effect=[0, 0.1]):  # 100ms
        result = await check_database_health(mock_db)
        assert result.status == HealthStatus.DEGRADED
        assert "slow" in result.message


@pytest.mark.asyncio
async def test_check_database_health_very_slow(mock_db):
    # Mock latency to be very slow
    with patch("time.perf_counter", side_effect=[0, 0.3]):  # 300ms
        result = await check_database_health(mock_db)
        assert result.status == HealthStatus.DEGRADED
        assert "very slow" in result.message


@pytest.mark.asyncio
async def test_check_database_health_with_pool_stats(mock_db):
    class MockPool:
        def size(self):
            return 10

        def checkedout(self):
            return 2

    class MockEngine:
        pool = MockPool()

    with patch("app.core.database.get_read_engine", return_value=MockEngine()):
        result = await check_database_health(mock_db)
    assert result.pool_size == 10
    assert result.pool_checked_out == 2


@pytest.mark.asyncio
async def test_check_database_health_pool_stats_failure(mock_db):
    mock_db.get_bind.side_effect = Exception("Bind error")

    # Should not crash, just log and return None for pool stats
    result = await check_database_health(mock_db)
    assert result.pool_size is None
    assert result.pool_checked_out is None


@pytest.mark.asyncio
async def test_check_database_health_sqlalchemy_error(mock_db):
    mock_db.execute.side_effect = SQLAlchemyError("Connection failed")

    result = await check_database_health(mock_db)
    assert result.status == HealthStatus.UNHEALTHY
    assert result.error == "Connection failed"
    assert result.message == "Database connection failed"


@pytest.mark.asyncio
async def test_check_database_connectivity_success(mock_db):
    result = await check_database_connectivity(mock_db)
    assert result is True


@pytest.mark.asyncio
async def test_check_database_connectivity_failure(mock_db):
    mock_db.execute.side_effect = Exception("Fail")
    result = await check_database_connectivity(mock_db)
    assert result is False
