"""Failure-path closure tests for cache version mutations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cache_versioning import CacheVersionManager
from app.deps.cache import RedisCache


def _redis_cache() -> MagicMock:
    cache = MagicMock(spec=RedisCache)
    cache.enabled = True
    return cache


@pytest.mark.asyncio
async def test_increment_swallows_redis_errors():
    manager = CacheVersionManager(prefix="events:list")

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        side_effect=OSError("connection failed"),
    ):
        await manager.increment(_redis_cache())


@pytest.mark.asyncio
async def test_get_version_returns_zero_for_non_numeric_value():
    manager = CacheVersionManager(prefix="events:list")
    client = AsyncMock()
    client.get.return_value = b"not-a-number"

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        assert await manager.get_version(_redis_cache()) == "0"


@pytest.mark.asyncio
async def test_reset_swallows_redis_errors():
    manager = CacheVersionManager(prefix="events:list")

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        side_effect=OSError("connection failed"),
    ):
        await manager.reset(_redis_cache())


@pytest.mark.asyncio
async def test_reset_writes_zero_to_redis():
    manager = CacheVersionManager(prefix="events:list")
    client = AsyncMock()

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        await manager.reset(_redis_cache())

    client.set.assert_awaited_once_with("events:list:version", "0")
