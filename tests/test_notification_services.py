"""Tests for notification service submodules:
- app/services/notifications/quiet_hours.py
- app/services/notifications/scheduler.py
- app/services/notifications/stats.py

Goal: bring these 3 modules from ~12-29% to ~85%+.
"""

from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notifications.quiet_hours import (
    is_user_in_quiet_hours,
    prepare_push_payload_for_user,
)

# ===========================================================================
# quiet_hours.py
# ===========================================================================


class TestIsUserInQuietHours:
    def _make_user(self, *, dnd_enabled: bool, dnd_start=None, dnd_end=None, tz="UTC"):
        prefs = MagicMock()
        prefs.dnd_enabled = dnd_enabled
        prefs.dnd_start = dnd_start
        prefs.dnd_end = dnd_end
        prefs.timezone = tz
        user = MagicMock()
        user.preferences = prefs
        return user

    def test_none_user_returns_false(self):
        assert not is_user_in_quiet_hours(None)

    def test_dnd_disabled_returns_false(self):
        user = self._make_user(dnd_enabled=False)
        assert not is_user_in_quiet_hours(user)

    def test_no_preferences_returns_false(self):
        user = MagicMock()
        user.preferences = None
        assert not is_user_in_quiet_hours(user)

    def test_dnd_no_start_end_returns_true(self):
        """DND enabled but no times set = all day DND."""
        user = self._make_user(dnd_enabled=True, dnd_start=None, dnd_end=None)
        assert is_user_in_quiet_hours(user)

    def test_dnd_same_start_end_returns_true(self):
        t = time(10, 0)
        user = self._make_user(dnd_enabled=True, dnd_start=t, dnd_end=t)
        assert is_user_in_quiet_hours(user)

    def test_dnd_daytime_window_inside(self):
        """09:00-17:00 DND; now=12:00 → in quiet hours."""
        user = self._make_user(
            dnd_enabled=True, dnd_start=time(9, 0), dnd_end=time(17, 0)
        )
        assert is_user_in_quiet_hours(user, now_time=time(12, 0))

    def test_dnd_daytime_window_outside(self):
        """09:00-17:00 DND; now=18:00 → not in quiet hours."""
        user = self._make_user(
            dnd_enabled=True, dnd_start=time(9, 0), dnd_end=time(17, 0)
        )
        assert not is_user_in_quiet_hours(user, now_time=time(18, 0))

    def test_dnd_overnight_window_inside(self):
        """22:00-08:00 (overnight); now=23:00 → in quiet hours."""
        user = self._make_user(
            dnd_enabled=True, dnd_start=time(22, 0), dnd_end=time(8, 0)
        )
        assert is_user_in_quiet_hours(user, now_time=time(23, 0))

    def test_dnd_overnight_window_outside(self):
        """22:00-08:00 (overnight); now=12:00 → not in quiet hours."""
        user = self._make_user(
            dnd_enabled=True, dnd_start=time(22, 0), dnd_end=time(8, 0)
        )
        assert not is_user_in_quiet_hours(user, now_time=time(12, 0))

    def test_now_time_resolved_from_user_when_none(self):
        """When now_time is None, the function computes it from user timezone."""
        user = self._make_user(dnd_enabled=True, dnd_start=None, dnd_end=None)
        # No now_time provided — should still work (all-day DND)
        result = is_user_in_quiet_hours(user)
        assert result is True


class TestPreparePushPayloadForUser:
    def _make_user_in_dnd(self):
        prefs = MagicMock()
        prefs.dnd_enabled = True
        prefs.dnd_start = None
        prefs.dnd_end = None
        user = MagicMock()
        user.preferences = prefs
        return user

    def test_no_dnd_returns_payload_unchanged(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = False

        payload = {"title": "Hello", "body": "World"}
        result = prepare_push_payload_for_user(payload, user, now_time=time(12, 0))

        assert result["title"] == "Hello"
        assert "silent" not in result

    def test_dnd_silences_payload(self):
        user = self._make_user_in_dnd()
        payload = {"title": "Alert", "body": "Urgent"}
        result = prepare_push_payload_for_user(payload, user)

        assert result["silent"] is True
        assert result["vibrate"] == []
        assert result["renotify"] is False
        assert result["requireInteraction"] is False

    def test_dnd_sets_dnd_suppressed_in_data(self):
        user = self._make_user_in_dnd()
        payload = {"title": "Alert", "data": {"key": "value"}}
        result = prepare_push_payload_for_user(payload, user)

        assert result["data"]["dnd_suppressed"] is True
        assert result["data"]["key"] == "value"  # original data preserved

    def test_dnd_creates_data_section_if_missing(self):
        user = self._make_user_in_dnd()
        payload = {"title": "Alert"}  # no "data" key
        result = prepare_push_payload_for_user(payload, user)

        assert result["data"]["dnd_suppressed"] is True

    def test_dnd_with_data_as_mapping(self):
        """data can be any Mapping — should be converted to dict."""
        from collections import OrderedDict

        user = self._make_user_in_dnd()
        payload = {"title": "Alert", "data": OrderedDict([("x", 1)])}
        result = prepare_push_payload_for_user(payload, user)

        assert isinstance(result["data"], dict)
        assert result["data"]["dnd_suppressed"] is True

    def test_original_payload_not_mutated(self):
        user = self._make_user_in_dnd()
        original = {"title": "Alert", "data": {"x": 1}}
        prepare_push_payload_for_user(original, user)
        # Original dict should not have "silent" key
        assert "silent" not in original

    def test_none_user_returns_payload_unchanged(self):
        payload = {"title": "Hi"}
        result = prepare_push_payload_for_user(payload, None)
        assert result["title"] == "Hi"
        assert "silent" not in result


# ===========================================================================
# scheduler.py — start_notifications_scheduler proxy
# ===========================================================================


@pytest.mark.asyncio
async def test_start_notifications_scheduler_delegates_to_worker():
    """start_notifications_scheduler should call the worker implementation."""
    from app.services.notifications.scheduler import start_notifications_scheduler

    mock_cancel_fn = MagicMock()

    with patch(
        "app.workers.notifications.start_notifications_scheduler",
        new=AsyncMock(return_value=mock_cancel_fn),
    ) as mock_start:
        result = await start_notifications_scheduler(poll_seconds=10, window_minutes=5)
        mock_start.assert_called_once_with(
            poll_seconds=10,
            window_minutes=5,
            max_backoff_seconds=300,
        )
        assert result is mock_cancel_fn


# ===========================================================================
# stats.py
# ===========================================================================


@pytest.mark.asyncio
async def test_aggregate_notification_delivery_stats_empty():
    from app.services.notifications.stats import aggregate_notification_delivery_stats

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([]))
    db.execute.return_value = mock_result

    with patch("app.services.notifications.stats.select") as mock_select:
        mock_select.return_value = MagicMock()
        result = await aggregate_notification_delivery_stats(db)

    assert result == []


@pytest.mark.asyncio
async def test_aggregate_notification_delivery_stats_with_rows():
    from app.services.notifications.stats import aggregate_notification_delivery_stats

    db = AsyncMock()

    row1 = MagicMock()
    row1._mapping = {
        "channel": "push",
        "status": "delivered",
        "count": 5,
        "delivered": 5,
        "first_attempt_at": None,
        "last_attempt_at": None,
    }
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([row1]))
    db.execute.return_value = mock_result

    with patch("app.services.notifications.stats.select") as mock_select:
        mock_stmt = MagicMock()
        mock_stmt.group_by.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        result = await aggregate_notification_delivery_stats(
            db, since=None, channel=None
        )

    assert len(result) == 1
    assert result[0]["channel"] == "push"
    assert result[0]["count"] == 5


@pytest.mark.asyncio
async def test_aggregate_notification_delivery_stats_with_filters():
    from datetime import UTC, datetime

    from app.services.notifications.stats import aggregate_notification_delivery_stats

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([]))
    db.execute.return_value = mock_result

    since = datetime(2025, 1, 1, tzinfo=UTC)

    with patch("app.services.notifications.stats.select") as mock_select:
        mock_stmt = MagicMock()
        mock_stmt.group_by.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        result = await aggregate_notification_delivery_stats(
            db, since=since, channel="push"
        )

    assert result == []
    # where should be called twice (once for since, once for channel)
    assert mock_stmt.where.call_count == 2
