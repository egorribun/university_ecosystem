import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.repositories.news_repository import NewsRepository, get_news_repository


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    # execute is async, but returns a Result object which has sync methods
    # (all, scalars, etc)
    # By default AsyncMock returns AsyncMock children, so result.all() becomes async
    # We fix this by making the return value of execute a MagicMock
    db.execute.return_value = MagicMock()
    return db


@pytest.fixture
def news_repo(mock_db):
    return NewsRepository(mock_db)


@pytest.mark.asyncio
async def test_get_published(news_repo, mock_db):
    from app.core.cache import news_cache

    await news_cache.invalidate_prefix("news:published")

    now = datetime.now(UTC)
    id1, id2 = uuid.uuid4(), uuid.uuid4()

    mock_news1 = MagicMock()
    mock_news1.id = id1
    mock_news1.title = "title1"
    mock_news1.content = "content1"
    mock_news1.created_at = now
    mock_news1.author_id = None
    mock_news1.title_en = None
    mock_news1.content_en = None
    mock_news1.image_url = None

    mock_news2 = MagicMock()
    mock_news2.id = id2
    mock_news2.title = "title2"
    mock_news2.content = "content2"
    mock_news2.created_at = now
    mock_news2.author_id = None
    mock_news2.title_en = None
    mock_news2.content_en = None
    mock_news2.image_url = None

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_news1, mock_news2]
    mock_db.execute.return_value = mock_result

    result = await news_repo.get_published(skip=0, limit=10)

    assert len(result) == 2
    assert result[0].id == id1
    assert result[1].id == id2
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search(news_repo, mock_db):
    id1 = uuid.uuid4()
    mock_news = MagicMock()
    mock_news.id = id1
    mock_news.title = "found"
    mock_news.content = "content"
    mock_news.created_at = datetime.now(UTC)
    mock_news.author_id = None
    mock_news.title_en = None
    mock_news.content_en = None
    mock_news.image_url = None

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_news]
    mock_db.execute.return_value = mock_result

    result = await news_repo.search("test")

    assert len(result) == 1
    assert result[0].title == "found"


@pytest.mark.asyncio
async def test_list_news_basic(news_repo, mock_db):
    id1 = uuid.uuid4()
    mock_news = MagicMock()
    mock_news.id = id1
    mock_news.title = "news"
    mock_news.content = "content"
    mock_news.created_at = datetime.now(UTC)
    mock_news.author_id = None
    mock_news.title_en = None
    mock_news.content_en = None
    mock_news.image_url = None

    # 1. News items result
    res_news = MagicMock()
    res_news.scalars.return_value.all.return_value = [mock_news]

    # 2. Likes count result
    res_likes = MagicMock()
    res_likes.all.return_value = [(id1, 1)]

    # 3. Comments count result
    res_comments = MagicMock()
    res_comments.all.return_value = [(id1, 2)]

    mock_db.execute.side_effect = [res_news, res_likes, res_comments]

    result = await news_repo.list_news()
    assert len(result) == 1
    assert result[0].news.id == id1
    assert result[0].likes_count == 1
    assert result[0].comments_count == 2
    assert result[0].is_liked is False


@pytest.mark.asyncio
async def test_list_news_cursor(news_repo, mock_db):
    cursor_created_at = datetime.now(UTC)
    item_created_at = cursor_created_at - timedelta(seconds=1)
    item_id = uuid.uuid4()
    mock_news = MagicMock()
    mock_news.id = item_id
    mock_news.title = "after cursor"
    mock_news.content = "content"
    mock_news.created_at = item_created_at
    mock_news.author_id = None
    mock_news.title_en = None
    mock_news.content_en = None
    mock_news.image_url = None

    res_news = MagicMock()
    res_news.scalars.return_value.all.return_value = [mock_news]
    res_likes = MagicMock()
    res_likes.all.return_value = [(item_id, 3)]
    res_comments = MagicMock()
    res_comments.all.return_value = [(item_id, 2)]
    mock_db.execute.side_effect = [res_news, res_likes, res_comments]

    result = await news_repo.list_news(
        cursor=(cursor_created_at, uuid.uuid4()),
    )

    assert len(result) == 1
    assert result[0].news.id == item_id
    assert result[0].news.title == "after cursor"
    assert result[0].likes_count == 3
    assert result[0].comments_count == 2
    assert result[0].is_liked is False
    assert result[0].ranked is False
    assert result[0].distance is None
    assert mock_db.execute.call_count == 3


@pytest.mark.asyncio
async def test_list_news_search_semantic(news_repo, mock_db):
    item_id = uuid.uuid4()
    mock_news = MagicMock()
    mock_news.id = item_id
    mock_news.title = "semantic match"
    mock_news.content = "content"
    mock_news.created_at = datetime.now(UTC)
    mock_news.author_id = None
    mock_news.title_en = None
    mock_news.content_en = None
    mock_news.image_url = None

    res_news = MagicMock()
    res_news.all.return_value = [(mock_news, 0.25)]
    res_likes = MagicMock()
    res_likes.all.return_value = []
    res_comments = MagicMock()
    res_comments.all.return_value = []
    mock_db.execute.side_effect = [res_news, res_likes, res_comments]

    with patch.object(settings, "semantic_search_enabled", True):
        result = await news_repo.list_news(
            search_query="test",
            query_embedding=[0.1],
        )

    assert len(result) == 1
    assert result[0].news.id == item_id
    assert result[0].news.title == "semantic match"
    assert result[0].ranked is True
    assert result[0].distance == 0.25
    assert result[0].likes_count == 0
    assert result[0].comments_count == 0
    assert mock_db.execute.call_count == 3


@pytest.mark.asyncio
async def test_list_news_search_text(news_repo, mock_db):
    item_id = uuid.uuid4()
    mock_news = MagicMock()
    mock_news.id = item_id
    mock_news.title = "text match"
    mock_news.content = "content"
    mock_news.created_at = datetime.now(UTC)
    mock_news.author_id = None
    mock_news.title_en = None
    mock_news.content_en = None
    mock_news.image_url = None

    res_news = MagicMock()
    res_news.scalars.return_value.all.return_value = [mock_news]
    res_likes = MagicMock()
    res_likes.all.return_value = [(item_id, 1)]
    res_comments = MagicMock()
    res_comments.all.return_value = [(item_id, 4)]
    mock_db.execute.side_effect = [res_news, res_likes, res_comments]

    with patch.object(settings, "semantic_search_enabled", False):
        result = await news_repo.list_news(search_query="test")

    assert len(result) == 1
    assert result[0].news.id == item_id
    assert result[0].news.title == "text match"
    assert result[0].ranked is False
    assert result[0].distance is None
    assert result[0].likes_count == 1
    assert result[0].comments_count == 4
    assert mock_db.execute.call_count == 3


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
    # INSERT ON CONFLICT DO NOTHING inserts new row -> rowcount=1 -> returns True
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result

    result = await news_repo.toggle_like(1, 123)

    assert result is True
    mock_db.execute.assert_called()


@pytest.mark.asyncio
async def test_toggle_like_remove(news_repo, mock_db):
    # INSERT ON CONFLICT DO NOTHING hits conflict -> rowcount=0 -> delete and return False
    mock_insert_result = MagicMock()
    mock_insert_result.rowcount = 0
    mock_delete_result = MagicMock()
    mock_db.execute.side_effect = [mock_insert_result, mock_delete_result]

    result = await news_repo.toggle_like(1, 123)

    assert result is False
    assert mock_db.execute.call_count == 2


def test_get_news_repository_factory():
    db = MagicMock()
    repo = get_news_repository(db)
    assert isinstance(repo, NewsRepository)
    assert repo.db == db
