"""Real-DB tests for NewsRepository comment + interaction methods.

The existing ``test_news_repository_coverage.py`` exercises the list/search/cache
paths against a mocked session. This file complements it with the
comment-CRUD + ``get_interactions`` methods, which are clearer to assert against
the real SQLite ``db_session`` (the ``comments_stmt`` join + coalesce shaping is
fiddly to mock). ``news`` / ``news_comments`` / ``news_likes`` are auto-created
via create_all. Real users come from ``user_factory``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models as models
from app.core.events import register_event_listeners
from app.models.domain_events import StoredEvent
from app.repositories.news_repository import NewsRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.news_service import NewsService


@pytest.fixture
def news_repo_db(db_session: AsyncSession) -> NewsRepository:
    return NewsRepository(db_session)


async def _add_news(db: AsyncSession, *, title: str = "Title", content: str = "Body"):
    news = models.News(title=title, content=content)
    db.add(news)
    await db.flush()
    return news


@pytest.mark.asyncio
async def test_comment_crud_and_get(news_repo_db, db_session, user_factory):
    user = await user_factory()
    news = await _add_news(db_session)

    comment = await news_repo_db.create_comment(news.id, user.id, "Hello")
    assert comment.content == "Hello"

    fetched = await news_repo_db.get_comment(comment.id)
    assert fetched is not None
    assert fetched.content == "Hello"

    updated = await news_repo_db.update_comment(comment, "Edited")
    assert updated.content == "Edited"

    await news_repo_db.delete_comment(comment)
    await db_session.flush()
    assert await news_repo_db.get_comment(comment.id) is None


@pytest.mark.asyncio
async def test_get_interactions_with_like_and_comment(
    news_repo_db, db_session, user_factory
):
    user = await user_factory()
    news = await _add_news(db_session, title="Interactive")
    await news_repo_db.create_comment(news.id, user.id, "Nice piece")
    db_session.add(models.NewsLike(news_id=news.id, user_id=user.id))
    await db_session.flush()

    dto = await news_repo_db.get_interactions(news.id, current_user_id=user.id)
    assert dto.likes_count == 1
    assert dto.is_liked is True
    assert dto.comments_count == 1
    assert len(dto.comments) == 1

    # Anonymous viewer → is_liked False branch (no current_user_id).
    anon = await news_repo_db.get_interactions(news.id)
    assert anon.likes_count == 1
    assert anon.is_liked is False


@pytest.mark.asyncio
async def test_get_interactions_empty_news(news_repo_db, db_session):
    news = await _add_news(db_session, title="Quiet")
    dto = await news_repo_db.get_interactions(news.id)
    assert dto.likes_count == 0
    assert dto.comments_count == 0
    assert dto.comments == []


@pytest.mark.asyncio
async def test_list_news_marks_user_liked(news_repo_db, db_session, user_factory):
    user = await user_factory()
    news = await _add_news(db_session, title="Listed")
    db_session.add(models.NewsLike(news_id=news.id, user_id=user.id))
    await db_session.flush()

    listing = await news_repo_db.list_news(current_user_id=user.id)
    assert len(listing) >= 1
    target = next(item for item in listing if item.news.id == news.id)
    assert target.likes_count == 1
    # current_user_id branch populates is_liked_map.
    assert target.is_liked is True


@pytest.mark.asyncio
async def test_update_persists_headline_in_news_updated_outbox_event(
    db_session: AsyncSession,
) -> None:
    await register_event_listeners()
    news = models.News(title="Original headline", content="Article body")
    db_session.add(news)
    await db_session.flush()

    updated_title = "Updated headline"
    updated = await NewsRepository(db_session).update(news.id, {"title": updated_title})
    assert updated is not None
    assert updated.title == updated_title

    await db_session.commit()
    event = await db_session.scalar(
        select(StoredEvent).where(
            StoredEvent.aggregate_type == "News",
            StoredEvent.aggregate_id == str(news.id),
            StoredEvent.event_type == "news.updated",
        )
    )

    assert event is not None
    assert event.payload["news_id"] == str(news.id)
    assert event.payload["title"] == updated_title


@pytest.mark.asyncio
async def test_comment_service_commits_create_and_edit_across_sessions(
    db_session: AsyncSession,
    user_factory,
):
    user = await user_factory()
    news = await _add_news(db_session, title="Durable comments")
    user_id = user.id
    news_id = news.id
    await db_session.commit()

    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with sessions() as writer:
        service = NewsService(uow_from_session(writer), AsyncMock())
        created = await service.create_comment(news_id, user_id, "Committed comment")
        comment_id = created.id

    async with sessions() as reader:
        persisted = await reader.scalar(
            select(models.NewsComment).where(models.NewsComment.id == comment_id)
        )
        assert persisted is not None
        assert persisted.content == "Committed comment"

    async with sessions() as writer:
        service = NewsService(uow_from_session(writer), AsyncMock())
        updated = await service.update_comment(comment_id, user_id, "Committed edit")
        assert updated.content == "Committed edit"

    async with sessions() as reader:
        persisted = await reader.scalar(
            select(models.NewsComment).where(models.NewsComment.id == comment_id)
        )
        assert persisted is not None
        assert persisted.content == "Committed edit"
