"""Tests for story_cleanup service.

Coverage targets:
- StoryCleanupConfig: interval normalization
- cleanup_expired_stories: with patched delete
- start_story_cleanup_scheduler: scheduler creation/stop
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.story_cleanup import (
    StoryCleanupConfig,
    cleanup_expired_stories,
    start_story_cleanup_scheduler,
)

# ============================================================
# StoryCleanupConfig tests
# ============================================================


def test_story_cleanup_config_default():
    """Test default config values."""
    config = StoryCleanupConfig()
    assert config.interval_seconds == 86_400
    assert config.normalized_interval() == 86_400


def test_story_cleanup_config_custom():
    """Test custom interval."""
    config = StoryCleanupConfig(interval_seconds=3600)
    assert config.normalized_interval() == 3600


def test_story_cleanup_config_min_interval():
    """Test interval is clamped to minimum 60 seconds."""
    config = StoryCleanupConfig(interval_seconds=10)
    assert config.normalized_interval() == 60


def test_story_cleanup_config_zero():
    """Test zero interval is clamped to 60."""
    config = StoryCleanupConfig(interval_seconds=0)
    assert config.normalized_interval() == 60


def test_story_cleanup_config_negative():
    """Test negative interval is clamped to 60."""
    config = StoryCleanupConfig(interval_seconds=-100)
    assert config.normalized_interval() == 60


# ============================================================
# cleanup_expired_stories tests
# ============================================================


@pytest.mark.asyncio
async def test_cleanup_expired_stories_with_db():
    """Test cleanup with injected db session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_db.execute.return_value = mock_result

    result = await cleanup_expired_stories(db=mock_db, now=datetime.now(UTC))

    assert result == 5
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_expired_stories_no_deleted():
    """Test cleanup when no stories deleted."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute.return_value = mock_result

    result = await cleanup_expired_stories(db=mock_db, now=datetime.now(UTC))

    assert result == 0


@pytest.mark.asyncio
async def test_cleanup_expired_stories_naive_datetime():
    """Test cleanup handles naive datetime."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.rowcount = 2
    mock_db.execute.return_value = mock_result

    naive_now = datetime.now()  # noqa: DTZ005  # Naive datetime
    result = await cleanup_expired_stories(db=mock_db, now=naive_now)

    assert result == 2


@pytest.mark.asyncio
async def test_cleanup_expired_stories_creates_session():
    """Test cleanup creates session when none provided."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_db.execute.return_value = mock_result

    with patch("app.services.story_cleanup.async_session") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = mock_db
        mock_factory.return_value.__aexit__.return_value = None

        result = await cleanup_expired_stories()

    assert result == 3


# ============================================================
# start_story_cleanup_scheduler tests
# ============================================================


@pytest.mark.asyncio
async def test_start_story_cleanup_scheduler_returns_stop():
    """Test scheduler returns a callable stop function."""
    with patch("app.services.story_cleanup.cleanup_expired_stories", return_value=0):
        stop_fn = await start_story_cleanup_scheduler(
            config=StoryCleanupConfig(interval_seconds=100000)
        )

    assert callable(stop_fn)
    await stop_fn()
