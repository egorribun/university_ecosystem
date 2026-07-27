"""Branch closure tests for health repository fallbacks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.health_repository import HealthRepository


@pytest.mark.asyncio
async def test_get_table_count_falls_back_for_negative_estimate():
    connection = AsyncMock()
    negative = MagicMock()
    negative.fetchone.return_value = (-1,)
    fallback = MagicMock()
    fallback.fetchone.return_value = (7,)
    connection.execute.side_effect = [negative, fallback]

    assert await HealthRepository(connection).get_table_count("users") == 7


@pytest.mark.asyncio
async def test_get_connection_stats_returns_defaults_for_empty_result():
    connection = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None
    connection.execute.return_value = result

    stats = await HealthRepository(connection).get_connection_stats()

    assert stats.active_connections == 0
    assert stats.cache_hit_ratio == 1.0
