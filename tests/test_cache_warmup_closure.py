"""Closure tests for fresh news/event cache entries."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.deps.cache import CacheEntry
from app.services import cache_warmup


def _fresh_cache() -> AsyncMock:
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = CacheEntry(payload={}, stored_at=time.time(), etag="fresh")
    return cache


@pytest.mark.asyncio
async def test_warm_news_skips_both_locales_when_entries_are_fresh():
    cache = _fresh_cache()

    with (
        patch("app.api.news._get_news_list_version", AsyncMock(return_value="v1")),
        patch("app.repositories.unit_of_work.uow_from_session"),
        patch("app.core.container.get_vector_service"),
        patch("app.services.news_service.NewsService") as news_service,
    ):
        await cache_warmup._warm_news(cache, MagicMock())

    news_service.return_value.list_news.assert_not_called()
    cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_warm_events_skips_both_locales_when_entries_are_fresh():
    cache = _fresh_cache()

    with patch(
        "app.api.events._get_events_list_version",
        AsyncMock(return_value="v1"),
    ):
        await cache_warmup._warm_events(cache, MagicMock())

    cache.set.assert_not_called()
