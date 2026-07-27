"""Branch closure tests for NewsService no-op cleanup paths."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.news_service import NewsService


def _service():
    repo = AsyncMock()
    uow = AsyncMock()
    uow.news = repo
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    return NewsService(uow, AsyncMock()), repo


@pytest.mark.asyncio
async def test_get_news_returns_none_without_enrichment():
    service, repo = _service()
    repo.get_with_interactions.return_value = (0, False)
    repo.get.return_value = None

    assert await service.get_news(uuid4()) is None


@pytest.mark.asyncio
async def test_delete_news_commits_without_static_image_cleanup():
    service, repo = _service()
    news = MagicMock()
    news.image_url = None
    repo.get.return_value = news

    assert await service.delete_news(uuid4()) is True
    service.uow.commit.assert_awaited_once()
