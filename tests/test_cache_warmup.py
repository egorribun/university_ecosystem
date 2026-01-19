"""Tests for cache_warmup service.

Coverage targets:
- _is_entry_fresh: various max_age scenarios
- _schedule_cache_key: key format
- _period_days_from_key: parsing various formats
- warm_cache: disabled, cache not enabled paths
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.cache_warmup import (
    _is_entry_fresh,
    _period_days_from_key,
    _schedule_cache_key,
    warm_cache,
)

# ============================================================
# _is_entry_fresh tests
# ============================================================


def test_is_entry_fresh_max_age_zero():
    """Test entry is always fresh when max_age <= 0."""
    entry = MagicMock()
    entry.stored_at = time.time() - 1000000  # Very old

    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_max_age_seconds = 0
        result = _is_entry_fresh(entry)

    assert result is True


def test_is_entry_fresh_max_age_negative():
    """Test entry is always fresh when max_age is negative."""
    entry = MagicMock()
    entry.stored_at = time.time() - 1000000

    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_max_age_seconds = -100
        result = _is_entry_fresh(entry)

    assert result is True


def test_is_entry_fresh_within_max_age():
    """Test entry is fresh when within max_age."""
    entry = MagicMock()
    entry.stored_at = time.time() - 30  # 30 seconds ago

    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_max_age_seconds = 60
        result = _is_entry_fresh(entry)

    assert result is True


def test_is_entry_fresh_expired():
    """Test entry is stale when past max_age."""
    entry = MagicMock()
    entry.stored_at = time.time() - 120  # 2 minutes ago

    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_max_age_seconds = 60
        result = _is_entry_fresh(entry)

    assert result is False


# ============================================================
# _schedule_cache_key tests
# ============================================================


def test_schedule_cache_key_format():
    """Test cache key format for schedule."""
    result = _schedule_cache_key(123)
    assert result == "schedule:group:123"


def test_schedule_cache_key_zero():
    """Test cache key with zero group id."""
    result = _schedule_cache_key(0)
    assert result == "schedule:group:0"


# ============================================================
# _period_days_from_key tests
# ============================================================


def test_period_days_from_key_valid():
    """Test parsing valid period key."""
    assert _period_days_from_key("7d") == 7
    assert _period_days_from_key("30d") == 30
    assert _period_days_from_key("365d") == 365


def test_period_days_from_key_uppercase():
    """Test parsing uppercase period key."""
    assert _period_days_from_key("7D") == 7
    assert _period_days_from_key("30D") == 30


def test_period_days_from_key_with_whitespace():
    """Test parsing period key with whitespace."""
    assert _period_days_from_key("  7d  ") == 7


def test_period_days_from_key_invalid():
    """Test parsing invalid period key."""
    assert _period_days_from_key("invalid") is None
    assert _period_days_from_key("7") is None
    assert _period_days_from_key("d") is None
    assert _period_days_from_key("") is None
    assert _period_days_from_key("abcd") is None


def test_period_days_from_key_none():
    """Test parsing None period key."""
    assert _period_days_from_key(None) is None


# ============================================================
# warm_cache tests
# ============================================================


@pytest.mark.asyncio
async def test_warm_cache_disabled():
    """Test warm_cache returns early when disabled."""
    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_enabled = False
        await warm_cache()
        # Should not raise


@pytest.mark.asyncio
async def test_warm_cache_cache_disabled():
    """Test warm_cache returns when cache backend is disabled."""
    mock_cache = MagicMock()
    mock_cache.enabled = False

    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_enabled = True
        with patch("app.services.cache_warmup.get_cache", return_value=mock_cache):
            await warm_cache()
            # Should not raise
