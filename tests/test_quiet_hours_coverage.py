import pytest
import datetime as dt
from unittest.mock import patch, MagicMock
from app.services.notifications.quiet_hours import is_user_in_quiet_hours, prepare_push_payload_for_user

class MockPreferences:
    def __init__(self, dnd_enabled=False, dnd_start=None, dnd_end=None):
        self.dnd_enabled = dnd_enabled
        self.dnd_start = dnd_start
        self.dnd_end = dnd_end

class MockUser:
    def __init__(self, preferences=None):
        self.preferences = preferences

def test_is_user_in_quiet_hours_disabled():
    # 1. No user
    assert is_user_in_quiet_hours(None) is False

    # 2. No preferences
    user = MockUser(preferences=None)
    assert is_user_in_quiet_hours(user) is False

    # 3. DND disabled
    prefs = MockPreferences(dnd_enabled=False)
    user = MockUser(preferences=prefs)
    assert is_user_in_quiet_hours(user) is False

def test_is_user_in_quiet_hours_no_times():
    # DND enabled but no start/end times
    prefs = MockPreferences(dnd_enabled=True, dnd_start=None, dnd_end=None)
    user = MockUser(preferences=prefs)
    assert is_user_in_quiet_hours(user) is True

def test_is_user_in_quiet_hours_same_times():
    # DND enabled, start == end
    t = dt.time(22, 0)
    prefs = MockPreferences(dnd_enabled=True, dnd_start=t, dnd_end=t)
    user = MockUser(preferences=prefs)
    assert is_user_in_quiet_hours(user) is True

def test_is_user_in_quiet_hours_start_less_than_end():
    # DND start < end (e.g. 9:00 to 17:00)
    start = dt.time(9, 0)
    end = dt.time(17, 0)
    prefs = MockPreferences(dnd_enabled=True, dnd_start=start, dnd_end=end)
    user = MockUser(preferences=prefs)

    # In range
    assert is_user_in_quiet_hours(user, now_time=dt.time(12, 0)) is True
    # Out of range (before)
    assert is_user_in_quiet_hours(user, now_time=dt.time(8, 0)) is False
    # Out of range (after)
    assert is_user_in_quiet_hours(user, now_time=dt.time(18, 0)) is False

def test_is_user_in_quiet_hours_start_greater_than_end():
    # DND start > end (e.g. 22:00 to 6:00)
    start = dt.time(22, 0)
    end = dt.time(6, 0)
    prefs = MockPreferences(dnd_enabled=True, dnd_start=start, dnd_end=end)
    user = MockUser(preferences=prefs)

    # In range (before midnight)
    assert is_user_in_quiet_hours(user, now_time=dt.time(23, 0)) is True
    # In range (after midnight)
    assert is_user_in_quiet_hours(user, now_time=dt.time(2, 0)) is True
    # Out of range
    assert is_user_in_quiet_hours(user, now_time=dt.time(12, 0)) is False

def test_is_user_in_quiet_hours_current_time():
    prefs = MockPreferences(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(6, 0))
    user = MockUser(preferences=prefs)
    
    with patch("app.services.notifications.quiet_hours._current_local_time") as mock_curr:
        mock_curr.return_value = dt.time(23, 0)
        assert is_user_in_quiet_hours(user, now_time=None) is True
        mock_curr.assert_called_once_with(user)

def test_prepare_push_payload_for_user():
    # Quiet hours active
    prefs = MockPreferences(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(6, 0))
    user = MockUser(preferences=prefs)
    
    payload = {
        "title": "Hello",
        "body": "World",
        "data": {"foo": "bar"}
    }
    
    res = prepare_push_payload_for_user(payload, user, now_time=dt.time(23, 0))
    assert res["silent"] is True
    assert res["vibrate"] == []
    assert res["renotify"] is False
    assert res["requireInteraction"] is False
    assert res["data"]["dnd_suppressed"] is True
    assert res["data"]["foo"] == "bar"

    # Quiet hours inactive
    res_inactive = prepare_push_payload_for_user(payload, user, now_time=dt.time(12, 0))
    assert res_inactive.get("silent") is None
    assert res_inactive["data"]["foo"] == "bar"
    assert "dnd_suppressed" not in res_inactive["data"]

    # Silent path when data section is not a Mapping
    payload_no_data = {
        "title": "Hello",
        "body": "World"
    }
    res_no_data = prepare_push_payload_for_user(payload_no_data, user, now_time=dt.time(23, 0))
    assert res_no_data["silent"] is True
    assert res_no_data["data"]["dnd_suppressed"] is True
