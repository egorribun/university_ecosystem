import fakeredis.aioredis
import pytest

from app.deps.cache import NullCache, RedisCache, etag_matches, format_etag


class _RedisCacheForTests(RedisCache):
    __test__ = False

    async def _get_client(self):  # type: ignore[override]
        if self._client is None:
            self._client = fakeredis.aioredis.FakeRedis(
                encoding="utf-8", decode_responses=True
            )
        return self._client


@pytest.mark.anyio
async def test_null_cache_noop():
    cache = NullCache()
    assert cache.enabled is False
    assert await cache.get("missing") is None
    entry = await cache.set("key", {"value": 1})
    assert entry.payload == {"value": 1}
    await cache.invalidate("key")


@pytest.mark.anyio
async def test_redis_cache_roundtrip():
    cache = _RedisCacheForTests(url="redis://localhost:6379/0", default_ttl=5)
    payload = {"foo": "bar"}
    entry = await cache.set("test:key", payload)
    assert entry.etag
    cached = await cache.get("test:key")
    assert cached is not None
    assert cached.payload == payload
    assert cached.etag == entry.etag
    await cache.invalidate("test:key")
    assert await cache.get("test:key") is None
    await cache.close()


def test_etag_helpers():
    etag = "abc123"
    assert format_etag(etag) == '"abc123"'
    assert etag_matches(etag, '"abc123"') is True
    assert etag_matches(etag, 'W/"abc123"') is True
    assert etag_matches(etag, '"zzz", "abc123"') is True
    assert etag_matches(etag, '"zzz"') is False
    assert etag_matches(etag, None) is False
