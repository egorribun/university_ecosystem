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
    cleanup_expired_stories,
)

# ============================================================
# StoryCleanupConfig tests
# ============================================================


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

    naive_now = datetime.now()  # Naive datetime
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
