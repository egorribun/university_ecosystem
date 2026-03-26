import datetime as dt
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import fakeredis.aioredis
import pytest_asyncio

import app.models as models
from app.core.config import settings
from app.deps import cache as cache_module


class _TestingRedisCache(cache_module.RedisCache):
    async def _get_client(self):
        if self._client is None:
            self._client = fakeredis.aioredis.FakeRedis(
                encoding="utf-8", decode_responses=True
            )
        return self._client

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(key) for key in keys if key]
        if not filtered:
            return

        client = await self._get_client()

        # Separate exact keys and patterns
        to_delete = []
        for key in filtered:
            if "*" in key:
                # Use standard keys() method which fakeredis now supports
                matched = await client.keys(key)
                if matched:
                    to_delete.extend(matched)
            else:
                to_delete.append(key)

        if to_delete:
            # Deduplicate and delete
            unique_to_delete = list(set(to_delete))
            await client.delete(*unique_to_delete)


@pytest_asyncio.fixture
async def fake_cache(mock_global_redis) -> AsyncIterator[_TestingRedisCache]:
    """Fixture to inject fakeredis for cache tests."""
    from app.core import cache as core_cache

    original_enabled = settings.cache_enabled
    settings.cache_enabled = True
    cache_module.set_cache_backend(None)

    cache = _TestingRedisCache(
        url=settings.cache_redis_url,
        default_ttl=settings.cache_default_ttl_seconds,
    )
    cache._client = mock_global_redis
    cache_module.set_cache_backend(cache)

    # Inject into global caches
    fake_client = mock_global_redis
    orig_sched_redis = core_cache.schedule_cache._redis
    orig_news_redis = core_cache.news_cache._redis

    core_cache.schedule_cache._redis = fake_client
    core_cache.news_cache._redis = fake_client

    # Clear L1 memory caches
    core_cache.schedule_cache.l1.clear()
    core_cache.news_cache.l1.clear()

    try:
        yield cache
    finally:
        # Restore originals
        core_cache.schedule_cache._redis = orig_sched_redis
        core_cache.news_cache._redis = orig_news_redis
        core_cache.schedule_cache.l1.clear()
        core_cache.news_cache.l1.clear()

        await cache.close()
        cache_module.set_cache_backend(None)
        settings.cache_enabled = original_enabled


@pytest_asyncio.fixture
async def story_factory(db_session) -> Callable[..., Awaitable[models.Story]]:
    async def _factory(**kwargs) -> models.Story:
        now = dt.datetime.now(dt.UTC)
        defaults = {
            "title": f"Story {uuid.uuid4().hex[:8]}",
            "short_text": "Story body",
            "expires_at": now + dt.timedelta(hours=24),
            "published_at": now,
            "is_active": True,
        }
        defaults.update(kwargs)
        story = models.Story(**defaults)
        db_session.add(story)
        await db_session.commit()
        await db_session.refresh(story)
        return story

    return _factory
