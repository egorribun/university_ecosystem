import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.js.errors import InvalidKeyError, NoKeysError

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


@pytest.mark.asyncio
async def test_nats_kv_cache_invalidate_empty_bucket_pattern():
    kv = AsyncMock()
    kv.keys.side_effect = NoKeysError()
    cache = NatsKVCache(bucket="test_bucket", default_ttl=60)
    cache._kv = kv

    await cache.invalidate("user:*")

    kv.keys.assert_awaited_once_with()
    kv.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_nats_kv_cache_invalidate_continues_after_empty_pattern():
    kv = AsyncMock()
    kv.keys.side_effect = [NoKeysError(), ["user:1", "other:2"]]
    cache = NatsKVCache(bucket="test_bucket", default_ttl=60)
    cache._kv = kv

    await cache.invalidate("missing:*", "exact-key", "user:*")

    assert kv.keys.await_count == 2
    assert [call.args[0] for call in kv.delete.await_args_list] == [
        "exact-key",
        "user:1",
    ]


@pytest.mark.asyncio
async def test_nats_kv_cache_invalidate_preserves_unexpected_listing_errors():
    kv = AsyncMock()
    kv.keys.side_effect = RuntimeError("key listing failed")
    cache = NatsKVCache(bucket="test_bucket", default_ttl=60)
    cache._kv = kv

    with pytest.raises(RuntimeError, match="key listing failed"):
        await cache.invalidate("user:*")

    kv.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_nats_kv_cache_invalidate_only_handles_empty_listing_errors():
    kv = AsyncMock()
    kv.keys.return_value = ["user:1"]
    kv.delete.side_effect = NoKeysError()
    cache = NatsKVCache(bucket="test_bucket", default_ttl=60)
    cache._kv = kv

    with pytest.raises(NoKeysError):
        await cache.invalidate("user:*")

    kv.delete.assert_awaited_once_with("user:1")


class _GrammarCheckedKV:
    """In-memory KV that enforces the NATS key grammar the way the real client does."""

    _VALID_KEY = re.compile(r"^[-/_=\.a-zA-Z0-9]+$")

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def _check(self, key: str) -> None:
        if not self._VALID_KEY.match(key):
            raise InvalidKeyError(key)

    async def put(self, key: str, value: bytes) -> None:
        self._check(key)
        self.store[key] = value

    async def get(self, key: str) -> SimpleNamespace | None:
        self._check(key)
        if key not in self.store:
            return None
        return SimpleNamespace(value=self.store[key])

    async def delete(self, key: str) -> None:
        self._check(key)
        self.store.pop(key, None)

    async def keys(self) -> list[str]:
        if not self.store:
            raise NoKeysError()
        return list(self.store)


@pytest.mark.asyncio
async def test_nats_kv_cache_round_trips_colon_keys_and_glob_invalidation():
    """AUD-094: colon-separated cache keys are valid NATS KV keys, and glob
    invalidation still removes the matching entries."""
    kv = _GrammarCheckedKV()
    cache = NatsKVCache(bucket="cache", default_ttl=60)

    with patch.object(cache, "_get_kv", AsyncMock(return_value=kv)):
        await cache.set("v1:chat:1:participants", {"n": 1})
        await cache.set("v1:chat:2:participants", {"n": 2})
        await cache.set("v1:news:1", {"n": 3})

        chat = await cache.get("v1:chat:1:participants")
        assert chat is not None
        assert chat.payload == {"n": 1}

        await cache.invalidate("v1:chat:*")

        assert await cache.get("v1:chat:1:participants") is None
        assert await cache.get("v1:chat:2:participants") is None
        news = await cache.get("v1:news:1")
        assert news is not None
        assert news.payload == {"n": 3}


@pytest.mark.parametrize(
    ("key", "encoded"),
    [
        ("test_key", "test_key"),
        ("user:1", "user=3a1"),
        ("a=b", "a=3db"),
        ("café", "caf=c3=a9"),
    ],
)
def test_nats_kv_key_encoding_is_valid_and_reversible(key, encoded):
    from app.deps.cache import _decode_kv_key, _encode_kv_key

    assert _encode_kv_key(key) == encoded
    assert _decode_kv_key(encoded) == key
    assert _decode_kv_key(_encode_kv_key(key)) == key
    # Stored keys written as raw legacy names still decode to themselves.
    assert _decode_kv_key("user:1") == "user:1"


def test_nats_kv_key_decoding_keeps_non_utf8_escapes_raw():
    from app.deps.cache import _decode_kv_key

    assert _decode_kv_key("=ff") == "=ff"
