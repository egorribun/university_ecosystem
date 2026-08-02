"""Branch closure tests for NewsService no-op cleanup paths."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.dtos.news import NewsDTO, NewsListingDTO
from app.services.news_service import NewsService
from app.utils.pagination import encode_datetime_cursor


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


def _listing(created_at: datetime, news_id):
    return NewsListingDTO(
        news=NewsDTO(
            id=news_id,
            title="News",
            content="Content",
            created_at=created_at,
            author_id=uuid4(),
            title_en=None,
            content_en=None,
            image_url=None,
        ),
        likes_count=1,
        comments_count=2,
        is_liked=False,
    )


@pytest.mark.asyncio
async def test_list_news_uses_cursor_and_builds_next_cursor():
    service, repo = _service()
    first_id, second_id = uuid4(), uuid4()
    first_time = datetime(2026, 1, 2, tzinfo=UTC)
    second_time = datetime(2026, 1, 1, tzinfo=UTC)
    repo.list_news.return_value = [
        _listing(first_time, first_id),
        _listing(second_time, second_id),
    ]
    cursor = encode_datetime_cursor(second_time, str(second_id))

    result = await service.list_news(limit=1, cursor=cursor)

    assert result.has_more is True
    assert result.next_cursor is not None
    assert repo.list_news.call_args.kwargs["cursor"] == (second_time, str(second_id))


@pytest.mark.asyncio
async def test_list_news_suppresses_malformed_decoded_cursor():
    service, repo = _service()
    repo.list_news.return_value = []

    with patch("app.utils.pagination.decode_datetime_cursor", return_value=object()):
        result = await service.list_news(limit=1, cursor="malformed")

    assert result.next_cursor is None
    assert repo.list_news.call_args.kwargs["cursor"] is None


@pytest.mark.asyncio
async def test_list_news_ignores_cursor_without_decoded_value():
    service, repo = _service()
    repo.list_news.return_value = []

    with patch("app.utils.pagination.decode_datetime_cursor", return_value=None):
        result = await service.list_news(limit=1, cursor="not-decodable")

    assert result.has_more is False
    assert repo.list_news.call_args.kwargs["cursor"] is None
