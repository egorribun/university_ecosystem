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
async def test_get_version_returns_numeric_value_and_zero_for_missing_key():
    manager = CacheVersionManager(prefix="events:list")
    client = AsyncMock()

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        client.get.return_value = b"7"
        assert await manager.get_version(_redis_cache()) == "7"

        client.get.return_value = None
        assert await manager.get_version(_redis_cache()) == "0"


@pytest.mark.asyncio
async def test_get_version_swallows_redis_errors():
    manager = CacheVersionManager(prefix="events:list")

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        side_effect=OSError("connection failed"),
    ):
        assert await manager.get_version(_redis_cache()) == "0"


@pytest.mark.asyncio
async def test_increment_uses_incr_and_falls_back_to_get_set():
    manager = CacheVersionManager(prefix="events:list")
    client = AsyncMock()

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        await manager.increment(_redis_cache())

    client.incr.assert_awaited_once_with("events:list:version")

    class _GetSetClient:
        def __init__(self) -> None:
            self.get = AsyncMock(return_value=b"4")
            self.set = AsyncMock()

    fallback = _GetSetClient()
    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=fallback,
    ):
        await manager.increment(_redis_cache())

    fallback.get.assert_awaited_once_with("events:list:version")
    fallback.set.assert_awaited_once_with("events:list:version", "5")


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


@pytest.mark.asyncio
async def test_non_redis_and_disabled_fallbacks_and_deterministic_key():
    manager = CacheVersionManager(prefix="events:list")
    disabled = MagicMock()
    disabled.enabled = False

    with patch("app.core.cache_versioning.get_cache", return_value=disabled):
        assert await manager.get_version() == "0"
        await manager.increment()
        await manager.reset()

    enabled_non_redis = MagicMock()
    enabled_non_redis.enabled = True
    assert await manager.get_version(enabled_non_redis) == "0"
    await manager.increment(enabled_non_redis)
    await manager.reset(enabled_non_redis)

    key = manager.build_cache_key(
        locale="en",
        version="7",
        page=2,
        filters={"role": "student"},
    )
    assert key.startswith("events:list:7:en:")
    assert len(key.rsplit(":", 1)[-1]) == 64
