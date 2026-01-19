"""Tests for notifications_retention service.

Coverage targets:
- NotificationsRetentionConfig: interval and retention normalization
- start_notifications_retention_scheduler: disabled case, scheduler creation
"""

from unittest.mock import patch

import pytest

from app.services.notifications_retention import (
    NotificationsRetentionConfig,
    start_notifications_retention_scheduler,
)

# ============================================================
# NotificationsRetentionConfig tests
# ============================================================


def test_notifications_retention_config_default():
    """Test default config values."""
    config = NotificationsRetentionConfig()
    assert config.retention_days == 90
    assert config.interval_seconds == 86_400
    assert config.normalized_retention_days() == 90
    assert config.normalized_interval() == 86_400


def test_notifications_retention_config_custom():
    """Test custom config values."""
    config = NotificationsRetentionConfig(retention_days=30, interval_seconds=3600)
    assert config.normalized_retention_days() == 30
    assert config.normalized_interval() == 3600


def test_notifications_retention_config_min_interval():
    """Test interval is clamped to minimum 300 seconds."""
    config = NotificationsRetentionConfig(interval_seconds=100)
    assert config.normalized_interval() == 300


def test_notifications_retention_config_zero_interval():
    """Test zero interval is clamped to 300."""
    config = NotificationsRetentionConfig(interval_seconds=0)
    assert config.normalized_interval() == 300


def test_notifications_retention_config_negative_interval():
    """Test negative interval is clamped to 300."""
    config = NotificationsRetentionConfig(interval_seconds=-100)
    assert config.normalized_interval() == 300


def test_notifications_retention_config_zero_retention():
    """Test zero retention days."""
    config = NotificationsRetentionConfig(retention_days=0)
    assert config.normalized_retention_days() == 0


def test_notifications_retention_config_negative_retention():
    """Test negative retention days is clamped to 0."""
    config = NotificationsRetentionConfig(retention_days=-10)
    assert config.normalized_retention_days() == 0


# ============================================================
# start_notifications_retention_scheduler tests
# ============================================================


@pytest.mark.asyncio
async def test_start_scheduler_disabled():
    """Test scheduler is disabled when retention_days is 0."""
    config = NotificationsRetentionConfig(retention_days=0)

    stop_fn = await start_notifications_retention_scheduler(config=config)

    assert callable(stop_fn)
    # Calling stop should not raise
    await stop_fn()


@pytest.mark.asyncio
async def test_start_scheduler_default():
    """Test scheduler starts with default config."""
    with patch(
        "app.services.notifications_retention.cleanup_stale_notifications",
        return_value=(10, 5),
    ):
        stop_fn = await start_notifications_retention_scheduler(
            config=NotificationsRetentionConfig(interval_seconds=100000)
        )

    assert callable(stop_fn)
    await stop_fn()
