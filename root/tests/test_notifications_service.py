import datetime as dt

from app.models.models import User
from app.services.notifications import (
    is_user_in_quiet_hours,
    prepare_push_payload_for_user,
)


def test_is_user_in_quiet_hours_crosses_midnight():
    user = User(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(7, 0))
    assert is_user_in_quiet_hours(user, now_time=dt.time(23, 15)) is True
    assert is_user_in_quiet_hours(user, now_time=dt.time(6, 45)) is True
    assert is_user_in_quiet_hours(user, now_time=dt.time(12, 0)) is False


def test_prepare_push_payload_applies_silent_mode():
    payload = {"title": "Test", "data": {"foo": "bar"}}
    user = User(dnd_enabled=True, dnd_start=dt.time(21, 0), dnd_end=dt.time(6, 0))

    result = prepare_push_payload_for_user(payload, user, now_time=dt.time(22, 30))

    assert result is not payload
    assert result["silent"] is True
    assert result["vibrate"] == []
    assert result["renotify"] is False
    assert result["requireInteraction"] is False
    assert result["data"]["foo"] == "bar"
    assert result["data"]["dnd_suppressed"] is True
    assert "silent" not in payload


def test_prepare_push_payload_keeps_original_when_outside_interval():
    payload = {"title": "Test outside", "data": {"foo": "bar"}}
    user = User(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(7, 0))

    result = prepare_push_payload_for_user(payload, user, now_time=dt.time(15, 0))

    assert "silent" not in result
    assert result["data"]["foo"] == "bar"
    assert "dnd_suppressed" not in result["data"]
