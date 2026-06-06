"""Unit tests for StoryRepository (app/repositories/story_repository.py).

Hermetic against the SQLite test DB (``db_session`` fixture; ``stories`` is
auto-created via create_all — it is NOT partitioned). ``published_at`` /
``expires_at`` / ``created_at`` are set explicitly so the ``before_insert`` listener
(``_set_story_expiration``) never has to fill them, keeping ordering and the
active/expired windows deterministic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stories import Story
from app.repositories.story_repository import StoryRepository, get_story_repository


@pytest.fixture
def repo(db_session: AsyncSession) -> StoryRepository:
    return StoryRepository(db_session)


async def _add_story(
    db: AsyncSession,
    *,
    title: str,
    published_at: datetime,
    expires_at: datetime,
    short_text: str = "body",
    is_active: bool = True,
    created_by: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> Story:
    story = Story(
        title=title,
        short_text=short_text,
        is_active=is_active,
        published_at=published_at,
        expires_at=expires_at,
        created_by=created_by,
        created_at=created_at or published_at,
    )
    db.add(story)
    await db.flush()
    return story


@pytest.mark.asyncio
async def test_get_story_repository_factory_returns_instance(db_session):
    built = get_story_repository(db_session)
    assert isinstance(built, StoryRepository)
    assert built.model is Story
    assert built.dto_class.__name__ == "StoryDTO"


@pytest.mark.asyncio
async def test_get_active_filters_inactive_expired_future_and_orders(repo, db_session):
    now = datetime.now(UTC)
    await _add_story(
        repo.db,
        title="v1",
        published_at=now - timedelta(hours=2),
        expires_at=now + timedelta(hours=10),
    )
    await _add_story(
        repo.db,
        title="v2",
        published_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=10),
    )
    await _add_story(
        repo.db,
        title="inactive",
        is_active=False,
        published_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=10),
    )
    await _add_story(
        repo.db,
        title="expired",
        published_at=now - timedelta(hours=5),
        expires_at=now - timedelta(hours=1),
    )
    await _add_story(
        repo.db,
        title="future",
        published_at=now + timedelta(hours=1),
        expires_at=now + timedelta(hours=10),
    )

    active = await repo.get_active()
    # is_active AND expires_at > now AND published_at <= now, ORDER BY published_at DESC.
    assert [s.title for s in active] == ["v2", "v1"]


@pytest.mark.asyncio
async def test_get_active_respects_skip_and_limit(repo, db_session):
    now = datetime.now(UTC)
    for i in range(3):
        await _add_story(
            repo.db,
            title=f"a{i}",
            published_at=now - timedelta(minutes=i),
            expires_at=now + timedelta(hours=10),
        )
    # published_at DESC → a0 (now-0), a1 (now-1), a2 (now-2). skip=1, limit=1 → a1.
    page = await repo.get_active(skip=1, limit=1)
    assert [s.title for s in page] == ["a1"]


@pytest.mark.asyncio
async def test_get_by_user_filters_and_orders(repo, db_session, user_factory):
    user = await user_factory()
    other = await user_factory()
    now = datetime.now(UTC)
    await _add_story(
        repo.db,
        title="u-old",
        created_by=user.id,
        created_at=now - timedelta(hours=2),
        published_at=now,
        expires_at=now + timedelta(hours=10),
    )
    await _add_story(
        repo.db,
        title="u-new",
        created_by=user.id,
        created_at=now - timedelta(minutes=5),
        published_at=now,
        expires_at=now + timedelta(hours=10),
    )
    await _add_story(
        repo.db,
        title="other",
        created_by=other.id,
        created_at=now,
        published_at=now,
        expires_at=now + timedelta(hours=10),
    )

    rows = await repo.get_by_user(user.id)
    # created_by == user, ORDER BY created_at DESC.
    assert [s.title for s in rows] == ["u-new", "u-old"]


@pytest.mark.asyncio
async def test_count_active_counts_active_nonexpired_including_future_published(
    repo, db_session
):
    now = datetime.now(UTC)
    await _add_story(
        repo.db,
        title="a",
        published_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=10),
    )
    # count_active does NOT filter on published_at, so a future-published active
    # story IS counted (unlike get_active).
    await _add_story(
        repo.db,
        title="future-active",
        published_at=now + timedelta(hours=1),
        expires_at=now + timedelta(hours=10),
    )
    await _add_story(
        repo.db,
        title="expired",
        published_at=now - timedelta(hours=5),
        expires_at=now - timedelta(hours=1),
    )
    await _add_story(
        repo.db,
        title="inactive",
        is_active=False,
        published_at=now,
        expires_at=now + timedelta(hours=10),
    )
    assert await repo.count_active() == 2


@pytest.mark.asyncio
async def test_get_expired_orders_asc_and_limits(repo, db_session):
    now = datetime.now(UTC)
    await _add_story(
        repo.db,
        title="e1",
        published_at=now - timedelta(hours=10),
        expires_at=now - timedelta(hours=3),
    )
    await _add_story(
        repo.db,
        title="e2",
        published_at=now - timedelta(hours=8),
        expires_at=now - timedelta(hours=1),
    )
    await _add_story(
        repo.db,
        title="live",
        published_at=now,
        expires_at=now + timedelta(hours=10),
    )

    rows = await repo.get_expired(limit=10)
    # expires_at <= now, ORDER BY expires_at ASC.
    assert [s.title for s in rows] == ["e1", "e2"]

    limited = await repo.get_expired(limit=1)
    assert [s.title for s in limited] == ["e1"]


@pytest.mark.asyncio
async def test_deactivate_hit_and_miss(repo, db_session):
    now = datetime.now(UTC)
    story = await _add_story(
        repo.db,
        title="d",
        published_at=now,
        expires_at=now + timedelta(hours=10),
    )
    assert await repo.deactivate(story.id) is True
    fetched = await repo.get(story.id)
    assert fetched is not None
    assert fetched.is_active is False
    assert await repo.deactivate(uuid.uuid4()) is False
