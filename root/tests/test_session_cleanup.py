"""Tests for session_cleanup service.

Tests focus on the cleanup scheduler and config, avoiding SQLAlchemy clause issues.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.session_cleanup import (
    SessionCleanupConfig,
    cleanup_expired_sessions,
    start_session_cleanup_scheduler,
)


# ============================================================
# SessionCleanupConfig tests
# ============================================================


def test_session_cleanup_config_default():
    """Test default config values."""
    config = SessionCleanupConfig()
    assert config.interval_seconds == 900
    assert config.normalized_interval() == 900


def test_session_cleanup_config_custom():
    """Test custom interval."""
    config = SessionCleanupConfig(interval_seconds=120)
    assert config.normalized_interval() == 120


def test_session_cleanup_config_min_interval():
    """Test interval is clamped to minimum 30 seconds."""
    config = SessionCleanupConfig(interval_seconds=10)
    assert config.normalized_interval() == 30


def test_session_cleanup_config_zero_interval():
    """Test zero interval is clamped to 30."""
    config = SessionCleanupConfig(interval_seconds=0)
    assert config.normalized_interval() == 30


def test_session_cleanup_config_negative():
    """Test negative interval is clamped to 30."""
    config = SessionCleanupConfig(interval_seconds=-100)
    assert config.normalized_interval() == 30


# ============================================================
# cleanup_expired_sessions tests (with patched delete function)
# ============================================================


@pytest.mark.anyio
async def test_cleanup_expired_sessions_with_db():
    """Test cleanup with injected db session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch(
        "app.services.session_cleanup.delete_sessions_matching",
        return_value=5
    ) as mock_delete:
        result = await cleanup_expired_sessions(
            db=mock_db, now=datetime.now(UTC)
        )

    assert result == 5
    mock_delete.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.anyio
async def test_cleanup_expired_sessions_no_deleted():
    """Test cleanup when no sessions deleted."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch(
        "app.services.session_cleanup.delete_sessions_matching",
        return_value=0
    ):
        result = await cleanup_expired_sessions(
            db=mock_db, now=datetime.now(UTC)
        )

    assert result == 0


@pytest.mark.anyio
async def test_cleanup_expired_sessions_creates_own_session():
    """Test cleanup creates session when none provided."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch("app.services.session_cleanup.async_session") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = mock_db
        mock_factory.return_value.__aexit__.return_value = None

        with patch(
            "app.services.session_cleanup.delete_sessions_matching",
            return_value=2
        ):
            result = await cleanup_expired_sessions()

    assert result == 2


# ============================================================
# start_session_cleanup_scheduler tests
# ============================================================


@pytest.mark.anyio
async def test_start_session_cleanup_scheduler_returns_stop_function():
    """Test scheduler returns a callable stop function."""
    with patch(
        "app.services.session_cleanup.cleanup_expired_sessions",
        return_value=0
    ):
        stop_fn = await start_session_cleanup_scheduler(
            config=SessionCleanupConfig(interval_seconds=100000)
        )

    assert callable(stop_fn)

    # Clean up by stopping the scheduler
    await stop_fn()



