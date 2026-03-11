from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.events import events_cache_version
from app.deps.cache import RedisCache


@pytest.mark.asyncio
async def test_get_events_list_version_no_cache():
    mock_cache = MagicMock()
    mock_cache.enabled = False

    version = await events_cache_version.get_version(mock_cache)
    assert version == "0"


@pytest.mark.asyncio
async def test_get_events_list_version_redis():
    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True
    mock_client = AsyncMock()
    mock_cache._get_client = AsyncMock(return_value=mock_client)

    # Case 1: Value exists
    mock_client.get.return_value = b"5"
    version = await events_cache_version.get_version(mock_cache)
    assert version == "5"

    # Case 2: Value miss (returns None)
    mock_client.get.return_value = None
    version = await events_cache_version.get_version(mock_cache)
    assert version == "0"

    # Case 3: Redis Error
    mock_cache._get_client.side_effect = OSError("Connection failed")
    version = await events_cache_version.get_version(mock_cache)
    assert version == "0"


@pytest.mark.asyncio
async def test_increment_events_list_version_no_cache():
    mock_cache = MagicMock()
    mock_cache.enabled = False

    # Simpler approach: call it and ensure no error
    await events_cache_version.increment(mock_cache)


@pytest.mark.asyncio
async def test_increment_events_list_version_redis():
    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True
    mock_client = AsyncMock()
    mock_cache._get_client = AsyncMock(return_value=mock_client)

    # Case 1: Client has incr
    mock_client.incr = AsyncMock()
    await events_cache_version.increment(mock_cache)
    mock_client.incr.assert_called_once_with("events:list:version")

    # Case 2: Client has no incr (manual update)
    del mock_client.incr
    mock_client.get.return_value = b"10"
    await events_cache_version.increment(mock_cache)
    mock_client.set.assert_called_with("events:list:version", "11")



