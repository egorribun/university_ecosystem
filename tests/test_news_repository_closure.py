from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.news_repository import NewsRepository


def _news_item(news_id: uuid.UUID) -> MagicMock:
    item = MagicMock()
    item.id = news_id
    item.title = "News"
    item.content = "Content"
    item.created_at = datetime.now(UTC)
    item.author_id = None
    item.title_en = None
    item.content_en = None
    item.image_url = None
    return item


def _repo() -> tuple[NewsRepository, AsyncMock]:
    db = AsyncMock()
    db.add = MagicMock()
    return NewsRepository(db), db


@pytest.mark.asyncio
async def test_properties_and_list_news_current_user_like():
    repo, db = _repo()
    assert repo.model.__name__ == "News"
    assert repo.dto_class.__name__ == "NewsDTO"

    news_id = uuid.uuid4()
    item = _news_item(news_id)
    news_result = MagicMock()
    news_result.scalars.return_value.all.return_value = [item]
    likes_result = MagicMock()
    likes_result.all.return_value = []
    comments_result = MagicMock()
    comments_result.all.return_value = []
    liked_result = MagicMock()
    liked_result.all.return_value = [(news_id,)]
    db.execute.side_effect = [news_result, likes_result, comments_result, liked_result]

    result = await repo.list_news(current_user_id=uuid.uuid4())
    assert result[0].is_liked is True


@pytest.mark.asyncio
async def test_get_with_interactions_without_user_and_zero_values():
    repo, db = _repo()
    likes = MagicMock()
    likes.scalar.return_value = 0
    liked = MagicMock()
    liked.scalar.return_value = None
    db.execute.side_effect = [likes, liked]
    assert await repo.get_with_interactions(uuid.uuid4()) == (0, False)


@pytest.mark.asyncio
async def test_comment_crud_methods():
    repo, db = _repo()
    comment_id = uuid.uuid4()
    stored = object()
    db.get.return_value = stored
    assert await repo.get_comment(comment_id) is stored

    created = await repo.create_comment(uuid.uuid4(), uuid.uuid4(), "hello")
    assert created.content == "hello"
    db.add.assert_called_once_with(created)
    db.flush.assert_awaited()
    db.refresh.assert_awaited_with(created, ["user"])

    updated = await repo.update_comment(created, "updated")
    assert updated.content == "updated"
    assert db.add.call_count == 2
    db.delete.reset_mock()
    await repo.delete_comment(created)
    db.delete.assert_awaited_once_with(created)


@pytest.mark.asyncio
async def test_get_interactions_with_comments_and_user_like():
    repo, db = _repo()
    comment_id = uuid.uuid4()
    user_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    likes = MagicMock()
    likes.scalar.return_value = 4
    comments = MagicMock()
    comments.all.return_value = [(comment_id, "Great", user_id, "Student", created_at)]
    total = MagicMock()
    total.scalar.return_value = 1
    liked = MagicMock()
    liked.scalar.return_value = uuid.uuid4()
    db.execute.side_effect = [likes, comments, total, liked]

    result = await repo.get_interactions(uuid.uuid4(), user_id, limit=10, offset=2)
    assert result.likes_count == 4
    assert result.is_liked is True
    assert result.comments_count == 1
    assert result.comments[0].content == "Great"

    no_user_likes = MagicMock()
    no_user_likes.scalar.return_value = None
    no_user_comments = MagicMock()
    no_user_comments.all.return_value = []
    no_user_total = MagicMock()
    no_user_total.scalar.return_value = None
    db.execute.side_effect = [no_user_likes, no_user_comments, no_user_total]
    no_user = await repo.get_interactions(uuid.uuid4())
    assert no_user.is_liked is False
    assert no_user.comments_count == 0


@pytest.mark.asyncio
async def test_get_analytics_data_with_date_filters():
    repo, db = _repo()
    result = MagicMock()
    result.fetchall.return_value = [(1, "News")]
    result.keys.return_value = ["id", "title"]
    db.execute.return_value = result
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 2, 1, tzinfo=UTC)
    rows, keys = await repo.get_analytics_data(start, end)
    assert rows == [(1, "News")]
    assert keys == ["id", "title"]

    await repo.get_analytics_data(start_date=start)
    await repo.get_analytics_data(end_date=end)
