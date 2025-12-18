"""
Tests for cache_warmup module.

Covers helper functions for cache warming.
"""

import time
from unittest.mock import patch

from app.deps.cache import CacheEntry
from app.services.cache_warmup import (
    _is_entry_fresh,
    _period_days_from_key,
    _schedule_cache_key,
)


class TestIsEntryFresh:
    """Tests for _is_entry_fresh helper."""

    @patch("app.services.cache_warmup.settings")
    def test_returns_true_when_max_age_zero(self, mock_settings):
        """Should return True when max_age is 0 (disabled)."""
        mock_settings.cache_warmup_max_age_seconds = 0
        entry = CacheEntry(etag="abc", payload={}, stored_at=time.time() - 3600)
        assert _is_entry_fresh(entry) is True

    @patch("app.services.cache_warmup.settings")
    def test_returns_true_when_max_age_negative(self, mock_settings):
        """Should return True when max_age is negative."""
        mock_settings.cache_warmup_max_age_seconds = -1
        entry = CacheEntry(etag="abc", payload={}, stored_at=time.time() - 3600)
        assert _is_entry_fresh(entry) is True

    @patch("app.services.cache_warmup.settings")
    def test_returns_true_when_entry_is_fresh(self, mock_settings):
        """Should return True when entry is within max_age."""
        mock_settings.cache_warmup_max_age_seconds = 3600  # 1 hour
        entry = CacheEntry(
            etag="abc", payload={}, stored_at=time.time() - 60
        )  # 1 min old
        assert _is_entry_fresh(entry) is True

    @patch("app.services.cache_warmup.settings")
    def test_returns_false_when_entry_is_stale(self, mock_settings):
        """Should return False when entry exceeds max_age."""
        mock_settings.cache_warmup_max_age_seconds = 300  # 5 min
        entry = CacheEntry(
            etag="abc", payload={}, stored_at=time.time() - 600
        )  # 10 min old
        assert _is_entry_fresh(entry) is False


class TestScheduleCacheKey:
    """Tests for _schedule_cache_key helper."""

    def test_returns_formatted_key(self):
        """Should return properly formatted cache key."""
        assert _schedule_cache_key(123) == "schedule:group:123"
        assert _schedule_cache_key(1) == "schedule:group:1"
        assert _schedule_cache_key(999) == "schedule:group:999"


class TestPeriodDaysFromKey:
    """Tests for _period_days_from_key helper."""

    def test_parses_days_suffix(self):
        """Should parse period keys with 'd' suffix."""
        assert _period_days_from_key("7d") == 7
        assert _period_days_from_key("30d") == 30
        assert _period_days_from_key("90d") == 90
        assert _period_days_from_key("365d") == 365

    def test_handles_uppercase_suffix(self):
        """Should handle uppercase 'D' suffix."""
        assert _period_days_from_key("30D") == 30

    def test_returns_none_for_invalid_format(self):
        """Should return None for invalid formats."""
        assert _period_days_from_key("weekly") is None
        assert _period_days_from_key("month") is None
        assert _period_days_from_key("") is None
        assert _period_days_from_key("abc") is None

    def test_returns_none_for_non_numeric(self):
        """Should return None for non-numeric values."""
        assert _period_days_from_key("abcd") is None
        assert _period_days_from_key("d") is None

    def test_handles_whitespace(self):
        """Should handle whitespace in period key."""
        assert _period_days_from_key(" 7d ") == 7
        assert _period_days_from_key("30d ") == 30
