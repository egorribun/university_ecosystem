from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.repositories.news_repository import NewsRepository, get_news_repository


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def news_repo(mock_db):
    return NewsRepository(mock_db)


@pytest.mark.asyncio
async def test_get_published(news_repo, mock_db):
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = ["news1", "news2"]
    mock_db.execute.return_value = mock_result

    result = await news_repo.get_published(skip=0, limit=10)

    assert result == ["news1", "news2"]
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_latest(news_repo):
    with patch.object(news_repo, "get_published", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = ["latest"]
        result = await news_repo.get_latest(limit=5)
        assert result == ["latest"]
        mock_get.assert_called_with(skip=0, limit=5)


@pytest.mark.asyncio
async def test_search(news_repo, mock_db):
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = ["found"]
    mock_db.execute.return_value = mock_result

    result = await news_repo.search("test")

    assert result == ["found"]


@pytest.mark.asyncio
async def test_count_total(news_repo, mock_db):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 42
    mock_db.execute.return_value = mock_result

    count = await news_repo.count_total()
    assert count == 42


@pytest.mark.asyncio
async def test_count_total_none(news_repo, mock_db):
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_db.execute.return_value = mock_result

    count = await news_repo.count_total()
    assert count == 0


@pytest.mark.asyncio
async def test_list_news_basic(news_repo, mock_db):
    mock_result = MagicMock()
    mock_result.all.return_value = [("news", 1, 2, False)]
    mock_db.execute.return_value = mock_result

    result = await news_repo.list_news()
    assert len(result) == 1
    assert result[0] == ("news", 1, 2, False)


@pytest.mark.asyncio
async def test_list_news_cursor(news_repo, mock_db):
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    await news_repo.list_news(cursor=(datetime.now(UTC), 1))
    # Verification of complex where clause construction would be implicit by success


@pytest.mark.asyncio
async def test_list_news_search_semantic(news_repo, mock_db):
    with (
        patch.object(settings, "semantic_search_enabled", True),
        patch("app.repositories.news_repository.News") as mock_news,
    ):
        mock_news.embedding.cosine_distance.return_value = 0.0

        await news_repo.list_news(search_query="test", query_embedding=[0.1])
        # Just verify it ran
        mock_db.execute.assert_called()


@pytest.mark.asyncio
async def test_list_news_search_text(news_repo, mock_db):
    with (
        patch.object(settings, "semantic_search_enabled", False),
        patch("app.repositories.news_repository.select"),
        patch("app.repositories.news_repository.or_"),
        patch("app.repositories.news_repository.and_"),
        patch("app.repositories.news_repository.func"),
        patch("app.repositories.news_repository.News") as mock_news,
    ):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        mock_news.title.ilike.return_value = "expr"

        await news_repo.list_news(search_query="test")


@pytest.mark.asyncio
async def test_get_with_interactions(news_repo, mock_db):
    # Mock return values for the two queries
    # Since interactions query happens in one go or multiple?
    # Actually get_with_interactions runs two execute calls

    mock_result1 = MagicMock()
    mock_result1.scalar.return_value = 10

    mock_result2 = MagicMock()
    mock_result2.scalar.return_value = True

    mock_db.execute.side_effect = [mock_result1, mock_result2]

    likes, is_liked = await news_repo.get_with_interactions(1, current_user_id=123)

    assert likes == 10
    assert is_liked is True


@pytest.mark.asyncio
async def test_toggle_like_add(news_repo, mock_db):
    # Mock finding existing like -> None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    result = await news_repo.toggle_like(1, 123)

    assert result is True
    # Should call db.add
    mock_db.add.assert_called()


@pytest.mark.asyncio
async def test_toggle_like_remove(news_repo, mock_db):
    # Mock finding existing like -> present
    mock_like = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_like
    mock_db.execute.return_value = mock_result

    result = await news_repo.toggle_like(1, 123)

    assert result is False
    # Should call db.delete
    mock_db.delete.assert_called_with(mock_like)


def test_get_news_repository_factory():
    db = MagicMock()
    repo = get_news_repository(db)
    assert isinstance(repo, NewsRepository)
    assert repo.db == db
