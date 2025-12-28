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


# Tests for tag-based cache invalidation
def test_cache_tag_enum():
    from app.services.cache_invalidation import CacheTag

    assert CacheTag.SCHEDULE == "tag:schedule"
    assert CacheTag.USER == "tag:user"
    assert CacheTag.EVENT == "tag:event"
    assert CacheTag.NEWS == "tag:news"
    assert CacheTag.GROUPS == "tag:groups"
    assert CacheTag.NOTIFICATIONS == "tag:notifications"


def test_get_tags_for_key():
    from app.services.cache_invalidation import CacheTag, get_tags_for_key

    # Schedule keys
    assert get_tags_for_key("schedule:group:123") == [CacheTag.SCHEDULE]

    # User keys
    assert get_tags_for_key("user:profile:456") == [CacheTag.USER]

    # Event keys
    assert get_tags_for_key("event:789") == [CacheTag.EVENT]
    assert get_tags_for_key("event:list") == [CacheTag.EVENT]

    # News keys
    assert get_tags_for_key("news:101") == [CacheTag.NEWS]
    assert get_tags_for_key("news:list") == [CacheTag.NEWS]

    # Groups keys
    assert get_tags_for_key("groups:list") == [CacheTag.GROUPS]

    # Unknown keys return empty list
    assert get_tags_for_key("random:key") == []
    assert get_tags_for_key("") == []


def test_cache_key_generators():
    from app.services.cache_invalidation import (
        event_cache_key,
        events_list_cache_key,
        news_cache_key,
        news_list_cache_key,
        schedule_cache_key,
        user_cache_key,
    )

    assert schedule_cache_key(1) == "schedule:group:1"
    assert user_cache_key(42) == "user:profile:42"
    assert event_cache_key(99) == "event:99"
    assert events_list_cache_key() == "event:list"
    assert news_cache_key(10) == "news:10"
    assert news_list_cache_key() == "news:list"


@pytest.mark.anyio
async def test_cache_invalidator_context_manager():
    from app.services.cache_invalidation import CacheInvalidator

    async with CacheInvalidator() as inv:
        inv.schedule(group_id=1)
        inv.user(user_id=42)
        inv.event(event_id=99)
        inv.news(news_id=10)

        # Keys are queued but not yet flushed
        assert len(inv._keys) == 6  # 1 + 1 + 2 + 2

    # After exiting context, keys are flushed


@pytest.mark.anyio
async def test_cache_invalidator_flush():
    from app.services.cache_invalidation import CacheInvalidator

    inv = CacheInvalidator()
    inv.schedule(group_id=1)
    inv.schedule(group_id=1)  # Duplicate
    inv.user(user_id=42)

    count = await inv.flush()
    # Should dedupe: 1 schedule + 1 user = 2 unique keys
    assert count == 2
    assert len(inv._keys) == 0

    # Flushing again returns 0
    count2 = await inv.flush()
    assert count2 == 0

