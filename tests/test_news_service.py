from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import models
from app.schemas import schemas
from app.schemas.dtos.news import NewsDTO, NewsListingDTO
from app.services.news_service import NewsService


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.db = AsyncMock()
    repo.db.commit = AsyncMock()
    repo.db.refresh = AsyncMock()
    # Mock return values for methods to avoid awaiting None
    repo.list_news.return_value = []
    return repo


@pytest.fixture
def mock_vector_service():
    vs = AsyncMock()
    vs.get_embedding.return_value = [0.1, 0.2]
    return vs


@pytest.fixture
def mock_uow(mock_repo):
    uow = AsyncMock()
    uow.news = mock_repo
    uow.session = mock_repo.db
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.commit = AsyncMock()
    uow.flush = AsyncMock()
    uow.rollback = AsyncMock()
    return uow


@pytest.fixture
def news_service(mock_uow, mock_vector_service):
    return NewsService(uow=mock_uow, vector_service=mock_vector_service)


@pytest.mark.asyncio
async def test_list_news(news_service, mock_uow, mock_repo, mock_vector_service):
    # Test with search to trigger vector service
    search_query = "something"

    mock_repo.list_news.return_value = [
        NewsListingDTO(
            news=NewsDTO(
                id=uuid4(),
                title="News",
                content="Content",
                created_at=datetime.now(UTC),
                author_id=uuid4(),
                title_en=None,
                content_en=None,
                image_url=None,
            ),
            likes_count=5,
            comments_count=2,
            is_liked=True,
        )
    ]

    await news_service.list_news(search=search_query)

    mock_vector_service.get_embedding.assert_awaited_once_with(search_query)
    mock_repo.list_news.assert_awaited_once()
    kwargs = mock_repo.list_news.call_args.kwargs
    assert kwargs["search_query"] == search_query
    assert kwargs["query_embedding"] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_create_news(news_service, mock_uow, mock_repo):
    data = schemas.NewsCreate(title="News", content="Content")

    start_event_id = 1
    mock_news = MagicMock(spec=models.News)
    mock_news.id = start_event_id
    mock_news.title = "News"
    mock_repo.create.return_value = mock_news

    result = await news_service.create_news(data)

    mock_repo.create.assert_awaited_once()
    mock_uow.commit.assert_awaited_once()
    assert result == mock_news


@pytest.mark.asyncio
async def test_toggle_like(news_service, mock_uow, mock_repo):
    news_id = 1
    user_id = 2
    mock_repo.toggle_like.return_value = True

    result = await news_service.toggle_like(news_id, user_id)

    mock_repo.toggle_like.assert_awaited_once_with(news_id, user_id)
    mock_uow.commit.assert_awaited_once()
    assert result is True
