import datetime as dt

import pytest
from sqlalchemy import select

from app.models.models import Story
from app.services.story_cleanup import cleanup_expired_stories


@pytest.mark.asyncio
async def test_cleanup_expired_stories_removes_expired(db_session, story_factory):
    now = dt.datetime.now(dt.UTC)

    expired = await story_factory(
        title="Expired",
        expires_at=now - dt.timedelta(minutes=10),
        published_at=now - dt.timedelta(hours=1),
    )
    boundary = await story_factory(
        title="Boundary",
        expires_at=now,
        published_at=now - dt.timedelta(hours=2),
    )
    active = await story_factory(
        title="Active",
        expires_at=now + dt.timedelta(hours=1),
        published_at=now - dt.timedelta(minutes=30),
    )

    removed = await cleanup_expired_stories(db=db_session, now=now)
    assert removed == 2

    result = await db_session.execute(select(Story.id))
    remaining = set(result.scalars().all())
    assert remaining == {active.id}
    assert expired.id not in remaining
    assert boundary.id not in remaining
