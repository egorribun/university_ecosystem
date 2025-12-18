import datetime as dt

import pytest
from sqlalchemy import select

from app.models.models import Story
from app.services.story_cleanup import cleanup_expired_stories, StoryCleanupConfig


class TestStoryCleanupConfig:
    """Tests for StoryCleanupConfig dataclass."""

    def test_default_interval(self):
        """Should have default interval of 86400 seconds (1 day)."""
        config = StoryCleanupConfig()
        assert config.interval_seconds == 86_400

    def test_custom_interval(self):
        """Should accept custom interval."""
        config = StoryCleanupConfig(interval_seconds=3600)
        assert config.interval_seconds == 3600

    def test_normalized_interval_above_minimum(self):
        """Should return interval unchanged when above minimum."""
        config = StoryCleanupConfig(interval_seconds=3600)
        assert config.normalized_interval() == 3600

    def test_normalized_interval_below_minimum(self):
        """Should enforce minimum interval of 60 seconds."""
        config = StoryCleanupConfig(interval_seconds=30)
        assert config.normalized_interval() == 60

    def test_normalized_interval_negative(self):
        """Should return minimum for negative interval."""
        config = StoryCleanupConfig(interval_seconds=-100)
        assert config.normalized_interval() == 60


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
