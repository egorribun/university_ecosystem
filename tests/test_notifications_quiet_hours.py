"""Tests for ``app.services.notifications.quiet_hours``.

The module is the canonical Do-Not-Disturb gate consumed by both
the notifications scheduler and the webpush delivery path. We
exercise the time-window arithmetic exhaustively (normal window,
midnight-straddle window, equal start/end sentinel, missing fields,
DND off) and the payload-mutation behaviour of
``prepare_push_payload_for_user``.

We construct user mocks via ``SimpleNamespace`` rather than building
real ORM instances — quiet-hours is a pure-data function and never
issues queries.
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace

import pytest

from app.services.notifications.quiet_hours import (
    is_user_in_quiet_hours,
    prepare_push_payload_for_user,
)


def _user_with_dnd(
    *,
    enabled: bool,
    start: time | None = None,
    end: time | None = None,
) -> SimpleNamespace:
    """Build a User-shaped object with ``preferences.dnd_*`` attributes."""
    prefs = SimpleNamespace(
        dnd_enabled=enabled,
        dnd_start=start,
        dnd_end=end,
    )
    return SimpleNamespace(preferences=prefs)


# ── 1. is_user_in_quiet_hours — short-circuits ───────────────────────────────


class TestIsUserInQuietHours:
    def test_no_user_returns_false(self) -> None:
        """No user object → not in quiet hours (anonymous senders never gated)."""
        assert is_user_in_quiet_hours(None) is False

    def test_user_without_preferences_returns_false(self) -> None:
        """A user with no preferences is never in quiet hours."""
        user = SimpleNamespace(preferences=None)
        assert is_user_in_quiet_hours(user) is False

    def test_dnd_disabled_returns_false(self) -> None:
        user = _user_with_dnd(enabled=False, start=time(0, 0), end=time(23, 59))
        assert is_user_in_quiet_hours(user, now_time=time(2, 0)) is False

    def test_dnd_enabled_no_window_means_always_quiet(self) -> None:
        """Enabling DND with no window = quiet 24/7 (admin sentinel)."""
        user = _user_with_dnd(enabled=True)
        assert is_user_in_quiet_hours(user, now_time=time(13, 0)) is True


# ── 2. is_user_in_quiet_hours — same-day window (start < end) ────────────────


class TestSameDayWindow:
    @pytest.fixture
    def user(self) -> SimpleNamespace:
        return _user_with_dnd(enabled=True, start=time(13, 0), end=time(15, 0))

    def test_inside_window(self, user: SimpleNamespace) -> None:
        assert is_user_in_quiet_hours(user, now_time=time(14, 0)) is True

    def test_at_start_inclusive(self, user: SimpleNamespace) -> None:
        assert is_user_in_quiet_hours(user, now_time=time(13, 0)) is True

    def test_at_end_exclusive(self, user: SimpleNamespace) -> None:
        """The window is half-open: ``start <= now < end`` — end-time is allowed."""
        assert is_user_in_quiet_hours(user, now_time=time(15, 0)) is False

    def test_before_window(self, user: SimpleNamespace) -> None:
        assert is_user_in_quiet_hours(user, now_time=time(12, 59)) is False

    def test_after_window(self, user: SimpleNamespace) -> None:
        assert is_user_in_quiet_hours(user, now_time=time(15, 1)) is False


# ── 3. is_user_in_quiet_hours — midnight-straddle window (start > end) ──────


class TestMidnightStraddleWindow:
    @pytest.fixture
    def user(self) -> SimpleNamespace:
        # 22:00 → 07:00 next day — typical sleep schedule.
        return _user_with_dnd(enabled=True, start=time(22, 0), end=time(7, 0))

    def test_late_evening_inside(self, user: SimpleNamespace) -> None:
        assert is_user_in_quiet_hours(user, now_time=time(22, 0)) is True
        assert is_user_in_quiet_hours(user, now_time=time(23, 30)) is True

    def test_early_morning_inside(self, user: SimpleNamespace) -> None:
        """Times before the wraparound end-point are still quiet."""
        assert is_user_in_quiet_hours(user, now_time=time(0, 0)) is True
        assert is_user_in_quiet_hours(user, now_time=time(5, 0)) is True
        # Half-open boundary — at the end-time itself we are no longer quiet.
        assert is_user_in_quiet_hours(user, now_time=time(7, 0)) is False

    def test_daytime_outside(self, user: SimpleNamespace) -> None:
        assert is_user_in_quiet_hours(user, now_time=time(13, 0)) is False
        assert is_user_in_quiet_hours(user, now_time=time(19, 0)) is False


# ── 4. is_user_in_quiet_hours — equal start/end sentinel ────────────────────


class TestEqualStartEndSentinel:
    def test_equal_treats_as_24_hour_quiet(self) -> None:
        user = _user_with_dnd(enabled=True, start=time(8, 0), end=time(8, 0))
        # Any time-of-day reads as 'quiet'.
        for hour in (0, 6, 12, 18, 23):
            assert is_user_in_quiet_hours(user, now_time=time(hour, 0)) is True


# ── 5. prepare_push_payload_for_user — payload mutation gate ─────────────────


class TestPreparePushPayloadForUser:
    def test_no_user_passes_through_unchanged(self) -> None:
        """No user → no DND silencing, payload stays intact."""
        payload = {
            "title": "Hello",
            "options": {"body": "World"},
            "data": {"url": "/x"},
        }
        out = prepare_push_payload_for_user(payload, user=None)
        # Same content, but a fresh dict (not the same object).
        assert out == payload
        assert out is not payload

    def test_no_dnd_passes_through_with_data_clone(self) -> None:
        """User with DND off → payload stays loud, but data dict is cloned."""
        user = _user_with_dnd(enabled=False)
        payload = {"title": "Hi", "data": {"url": "/x"}}
        out = prepare_push_payload_for_user(payload, user=user)
        assert "silent" not in out
        # Payload's data dict is cloned to prevent the caller mutating shared state.
        assert out["data"] is not payload["data"]
        assert out["data"] == payload["data"]

    def test_in_quiet_hours_silences_payload(self) -> None:
        user = _user_with_dnd(enabled=True, start=time(22, 0), end=time(7, 0))
        payload = {
            "title": "Hi",
            "options": {"vibrate": [100, 200]},
            "data": {"url": "/x"},
        }
        # 02:00 is inside 22:00–07:00.
        out = prepare_push_payload_for_user(payload, user=user, now_time=time(2, 0))
        assert out["silent"] is True
        assert out["vibrate"] == []
        assert out["renotify"] is False
        assert out["requireInteraction"] is False
        assert out["data"]["dnd_suppressed"] is True
        # Untouched fields preserved.
        assert out["title"] == "Hi"
        assert out["options"] == {"vibrate": [100, 200]}

    def test_outside_quiet_hours_does_not_set_dnd_flags(self) -> None:
        user = _user_with_dnd(enabled=True, start=time(22, 0), end=time(7, 0))
        payload = {"title": "Hi", "data": {"url": "/x"}}
        # 12:00 is outside the window.
        out = prepare_push_payload_for_user(payload, user=user, now_time=time(12, 0))
        assert "silent" not in out
        assert "vibrate" not in out
        assert "renotify" not in out
        assert "requireInteraction" not in out
        assert "dnd_suppressed" not in out["data"]

    def test_quiet_payload_with_no_data_section_creates_one(self) -> None:
        """When DND is on and the payload had no ``data`` key, one is created."""
        user = _user_with_dnd(enabled=True)
        payload = {"title": "Hi"}  # no data
        out = prepare_push_payload_for_user(payload, user=user, now_time=time(2, 0))
        assert out["silent"] is True
        assert out["data"] == {"dnd_suppressed": True}

    def test_quiet_payload_with_non_dict_data_replaces_it(self) -> None:
        """If ``data`` is not a dict at all, it's replaced with a fresh dict."""
        user = _user_with_dnd(enabled=True)
        payload = {"title": "Hi", "data": "not-a-dict"}
        out = prepare_push_payload_for_user(payload, user=user, now_time=time(2, 0))
        assert out["data"] == {"dnd_suppressed": True}

    def test_does_not_mutate_input_payload(self) -> None:
        """The function must NOT mutate the caller's payload dict."""
        user = _user_with_dnd(enabled=True)
        data = {"url": "/x"}
        payload = {"title": "Hi", "data": data}
        prepare_push_payload_for_user(payload, user=user, now_time=time(2, 0))
        assert "dnd_suppressed" not in data  # caller's dict untouched
        assert "silent" not in payload  # caller's dict untouched

    def test_data_section_with_mapping_protocol_cloned_to_dict(self) -> None:
        """A ``Mapping``-shaped data section becomes a regular dict."""
        from collections import OrderedDict

        user = _user_with_dnd(enabled=False)
        payload = {"title": "Hi", "data": OrderedDict([("k", 1)])}
        out = prepare_push_payload_for_user(payload, user=user)
        assert isinstance(out["data"], dict)
        assert out["data"] == {"k": 1}
