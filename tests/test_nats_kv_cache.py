from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.deps.cache import NatsKVCache


@pytest.mark.asyncio
async def test_nats_kv_cache_get_set():
    # Mock NATS connection and JetStream
    mock_kv = AsyncMock()
    mock_js = MagicMock()
    mock_js.key_value = AsyncMock(return_value=mock_kv)

    with patch("app.core.nats_broker.broker") as mock_broker:
        mock_broker.is_connected = True
        mock_broker.js = mock_js

        cache = NatsKVCache(bucket="test_bucket", default_ttl=60)

        # Test SET
        payload = {"data": "test"}
        entry = await cache.set("test_key", payload)

        assert entry.payload == payload
        assert mock_kv.put.called

        # Test GET
        mock_entry = MagicMock()
        import orjson

        mock_entry.value = orjson.dumps(
            {
                "etag": entry.etag,
                "payload": payload,
                "stored_at": entry.stored_at,
                "ttl_seconds": entry.ttl_seconds,
            }
        )
        mock_kv.get.return_value = mock_entry

        retrieved = await cache.get("test_key")
        assert retrieved is not None
        assert retrieved.payload == payload
        assert retrieved.etag == entry.etag


@pytest.mark.asyncio
async def test_nats_kv_cache_invalidate():
    mock_kv = AsyncMock()
    mock_js = MagicMock()
    mock_js.key_value = AsyncMock(return_value=mock_kv)

    with patch("app.core.nats_broker.broker") as mock_broker:
        mock_broker.is_connected = True
        mock_broker.js = mock_js

        cache = NatsKVCache(bucket="test_bucket", default_ttl=60)

        # Test exact invalidation
        await cache.invalidate("key1", "key2")
        assert mock_kv.delete.call_count == 2

        # Test pattern invalidation
        mock_kv.keys.return_value = ["user:1", "user:2", "other:3"]
        mock_kv.delete.reset_mock()

        await cache.invalidate("user:*")
        assert mock_kv.delete.call_count == 2
        # Verify it called delete for matching keys
        calls = [c.args[0] for c in mock_kv.delete.call_args_list]
        assert "user:1" in calls
        assert "user:2" in calls
        assert "other:3" not in calls


@pytest.mark.asyncio
async def test_create_cache_backend_nats():
    from app.deps.cache import create_cache_backend

    # Mock settings
    with patch("app.deps.cache.settings") as mock_settings:
        mock_settings.cache_enabled = True
        mock_settings.cache_backend = "nats"
        mock_settings.cache_backend_normalized = "nats"
        mock_settings.cache_nats_bucket = "ue_cache"
        mock_settings.cache_default_ttl_seconds = 300

        backend = create_cache_backend()
        assert isinstance(backend, NatsKVCache)
        assert backend._bucket_name == "ue_cache"
        assert backend._default_ttl == 300
