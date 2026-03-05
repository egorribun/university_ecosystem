from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.events import (
    _encode_payload_with_etag,
    _events_list_cache_key,
    events_cache_version,
)
from app.deps.cache import RedisCache


@pytest.mark.asyncio
async def test_events_list_cache_key():
    key = _events_list_cache_key(
        locale="en",
        search="Test",
        event_type="workshop",
        location="Room 101",
        is_active=True,
        limit=10,
        cursor=None,
        version="1",
    )
    assert "events:list:1:en:" in key
    # Check normalization
    key2 = _events_list_cache_key(
        locale="EN",
        search="  test  ",
        event_type="Workshop",
        location="room 101",
        is_active=True,
        limit=10,
        cursor=None,
        version="1",
    )
    assert key == key2


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


def test_encode_payload_with_etag():
    payload = {"id": 1, "name": "Event"}
    encoded, digest, strong_header = _encode_payload_with_etag(payload)

    assert encoded == payload
    assert isinstance(digest, str)
    assert strong_header.startswith('"')
    assert digest in strong_header
