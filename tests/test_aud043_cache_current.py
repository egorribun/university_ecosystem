"""Current news warmup behavior across cold cache generations."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text, update

import app.models as models
from app.api.deps.etag import generate_cache_key
from app.core import database
from app.core.cache_versioning import news_cache_version
from app.deps.cache import MemoryCache, NatsKVCache, TieredCache
from app.services import cache_warmup
from app.services.news_service import NewsService


def _cold_cache(kind):
    if kind == "memory":
        return MemoryCache()
    if kind == "tiered":
        return TieredCache(MemoryCache(), MemoryCache())

    class KV:
        def __init__(self):
            self.values = {}

        async def get(self, key):
            value = self.values.get(key)
            return SimpleNamespace(value=value) if value is not None else None

        async def put(self, key, value):
            self.values[key] = value

    cache = NatsKVCache("test", 60)
    cache._kv = KV()
    return cache


async def _run_warmup(cache, schedule=None):
    with (
        patch.object(cache_warmup.settings, "cache_warmup_enabled", True),
        patch("app.services.cache_warmup.get_cache", return_value=cache),
        patch("app.services.cache_warmup._warm_schedule", schedule or AsyncMock()),
        patch("app.services.cache_warmup._warm_stats", AsyncMock()),
    ):
        await cache_warmup.warm_cache()


async def _assert_current_news(cache, async_client, title):
    version = await news_cache_version.get_version(cache)
    key = generate_cache_key(
        cache_prefix=news_cache_version.prefix,
        version=version,
        locale="ru",
        params={"limit": 20, "cursor": None, "__tenant_id": ""},
    )
    entry = await cache.get(key)
    calls = []
    original = NewsService.list_news

    async def tracked_list_news(self, **kwargs):
        calls.append(kwargs)
        return await original(self, **kwargs)

    with (
        patch("app.api.deps.etag.get_cache", return_value=cache),
        patch.object(NewsService, "list_news", tracked_list_news),
    ):
        response = await async_client.get("/news", headers={"Accept-Language": "ru"})

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == title
    if entry is None:
        assert len(calls) == 1
    else:
        assert entry.payload["items"][0]["title"] == title
        assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "tiered", "nats"])
async def test_cold_news_warmup_is_consumed_and_still_invalidated(
    kind, async_client, db_session
):
    cache = _cold_cache(kind)
    news = models.News(
        title="First title",
        content="Content",
        title_en="First title",
        content_en="Content",
    )
    db_session.add(news)
    await db_session.commit()

    await _run_warmup(cache)

    calls = []
    original = NewsService.list_news

    async def tracked_list_news(self, **kwargs):
        calls.append(kwargs)
        return await original(self, **kwargs)

    with (
        patch("app.api.deps.etag.get_cache", return_value=cache),
        patch.object(NewsService, "list_news", tracked_list_news),
    ):
        for locale in ("ru", "en"):
            response = await async_client.get(
                "/news", headers={"Accept-Language": locale}
            )
            assert response.status_code == 200
            assert response.json()["items"][0]["title"] == "First title"
        assert calls == []

        news.title = "Updated title"
        news.title_en = "Updated title"
        await db_session.commit()
        await news_cache_version.increment(cache)
        response = await async_client.get("/news", headers={"Accept-Language": "en"})
        assert response.status_code == 200
        assert response.json()["items"][0]["title"] == "Updated title"
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_mutation_during_warmup_does_not_publish_stale_news(
    async_client, db_session
):
    class DelayedListWrite(MemoryCache):
        def __init__(self):
            super().__init__()
            self.write_started = asyncio.Event()
            self.release_write = asyncio.Event()
            self.delay_first = True

        async def set(self, key, payload, ttl=None):
            if key.startswith("news:list:") and self.delay_first:
                self.delay_first = False
                self.write_started.set()
                await self.release_write.wait()
            return await super().set(key, payload, ttl)

    cache = DelayedListWrite()
    await news_cache_version.increment(cache)
    news = models.News(title="Before", content="Content")
    db_session.add(news)
    await db_session.commit()

    task = asyncio.create_task(_run_warmup(cache))
    try:
        await asyncio.wait_for(cache.write_started.wait(), timeout=10)
        news.title = "After"
        await db_session.commit()
        await news_cache_version.increment(cache)
    finally:
        cache.release_write.set()
        await task

    await _assert_current_news(cache, async_client, "After")


@pytest.mark.asyncio
async def test_delayed_cold_generation_read_cannot_resurrect_old_snapshot(
    async_client, db_session
):
    class DelayedGenerationRead(MemoryCache):
        def __init__(self):
            super().__init__()
            self.read_started = asyncio.Event()
            self.release_read = asyncio.Event()
            self.delay_first = True

        async def get(self, key):
            entry = await super().get(key)
            if key == news_cache_version.generation_key and self.delay_first:
                self.delay_first = False
                self.read_started.set()
                await self.release_read.wait()
            return entry

    cache = DelayedGenerationRead()
    news = models.News(title="Old snapshot", content="Content")
    db_session.add(news)
    await db_session.commit()
    news_id = news.id

    async def establish_old_snapshot(_cache, warmup_db):
        await warmup_db.execute(text("BEGIN"))
        await warmup_db.execute(select(models.News).where(models.News.id == news_id))

    task = asyncio.create_task(_run_warmup(cache, establish_old_snapshot))
    try:
        await asyncio.wait_for(cache.read_started.wait(), timeout=10)
        async with database.async_session() as writer:
            await writer.execute(
                update(models.News)
                .where(models.News.id == news_id)
                .values(title="New committed title")
            )
            await writer.commit()
        await news_cache_version.increment(cache)
    finally:
        cache.release_read.set()
        await task

    await _assert_current_news(cache, async_client, "New committed title")


@pytest.mark.asyncio
async def test_warmup_does_not_publish_a_snapshot_older_than_the_generation(
    async_client, db_session
):
    cache = MemoryCache()
    news = models.News(title="Old snapshot", content="Content")
    db_session.add(news)
    await db_session.commit()
    news_id = news.id

    async def establish_old_snapshot_and_mutate(_cache, warmup_db):
        await warmup_db.execute(text("BEGIN"))
        await warmup_db.execute(select(models.News).where(models.News.id == news_id))
        async with database.async_session() as writer:
            await writer.execute(
                update(models.News)
                .where(models.News.id == news_id)
                .values(title="New committed title")
            )
            await writer.commit()
        await news_cache_version.increment(cache)

    await _run_warmup(cache, establish_old_snapshot_and_mutate)
    await _assert_current_news(cache, async_client, "New committed title")
