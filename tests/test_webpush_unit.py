from datetime import time

from app.services.webpush import (
    _is_user_in_quiet_hours,
    _normalize_payload,
    _prepare_actions,
    _resolve_ttl,
    _sanitize_vibrate,
    build_payload,
)


def test_sanitize_vibrate():
    assert _sanitize_vibrate([100, 200.5, "invalid"]) == [100, 200]
    assert _sanitize_vibrate(None) == []
    assert _sanitize_vibrate("not-a-list") == []


def test_is_user_in_quiet_hours():
    class MockUser:
        def __init__(self, dnd_enabled=False, dnd_start=None, dnd_end=None):
            self.preferences = type(
                "Prefs",
                (),
                {
                    "dnd_enabled": dnd_enabled,
                    "dnd_start": dnd_start,
                    "dnd_end": dnd_end,
                },
            )

    # DND disabled
    user_off = MockUser(dnd_enabled=False)
    assert _is_user_in_quiet_hours(user_off, now_time=time(12, 0)) is False

    # DND enabled, simple range 22:00 - 08:00
    user_on = MockUser(dnd_enabled=True, dnd_start=time(22, 0), dnd_end=time(8, 0))
    assert _is_user_in_quiet_hours(user_on, now_time=time(23, 0)) is True
    assert _is_user_in_quiet_hours(user_on, now_time=time(7, 0)) is True
    assert _is_user_in_quiet_hours(user_on, now_time=time(12, 0)) is False

    # DND enabled, range within day 14:00 - 16:00
    user_mid = MockUser(dnd_enabled=True, dnd_start=time(14, 0), dnd_end=time(16, 0))
    assert _is_user_in_quiet_hours(user_mid, now_time=time(15, 0)) is True
    assert _is_user_in_quiet_hours(user_mid, now_time=time(13, 0)) is False


def test_resolve_ttl():
    assert _resolve_ttl({"ttl": 500}) == 500
    assert _resolve_ttl({"urgency": "high"}) == 300  # 5 min
    assert _resolve_ttl({"urgency": "very-low"}) == 86400  # 24h
    assert _resolve_ttl({}) == 3600  # Default 1h


def test_prepare_actions():
    raw = [
        {"action": "yes", "title": "Yes", "icon": "check.png", "url": "/confirm"},
        {"action": "no", "title": "No"},
    ]
    actions, urls = _prepare_actions(raw)
    assert len(actions) == 2
    assert actions[0]["action"] == "yes"
    assert urls["yes"] == "/confirm"
    assert "icon" in actions[0]
    assert "url" not in actions[0]  # URL goes to data


def test_normalize_payload_basic():
    raw = {"title": "Hello", "body": "World", "icon": "icon.png", "_meta": {"ttl": 123}}
    payload, meta = _normalize_payload(raw)
    assert payload["title"] == "Hello"
    assert payload["options"]["body"] == "World"
    assert payload["options"]["icon"] == "icon.png"
    assert meta["ttl"] == 123


def test_normalize_payload_with_options():
    raw = {"options": {"body": "Overridden", "tag": "my-tag"}, "data": {"key": "val"}}
    payload, _ = _normalize_payload(raw)
    assert payload["options"]["body"] == "Overridden"
    assert payload["data"]["key"] == "val"


def test_build_payload_integration():
    # Tests the high-level build_payload which uses templates
    data = {"title": "Custom Title", "body": "Custom Body", "urgency": "high"}
    result = build_payload("test_type", data)
    assert result["title"] == "Custom Title"
    assert result["options"]["body"] == "Custom Body"
    assert result["_meta"]["urgency"] == "high"


def test_prepare_delivery_payload_minimal(monkeypatch):
    import app.services.push_topics as pt
    from app.services.webpush import _prepare_delivery_payload

    # Mock settings to allow test-topic
    class MockSettings:
        notifications_allowed_push_topics_set = frozenset(["test-topic"])

    monkeypatch.setattr(pt, "app_settings", MockSettings())

    payload = {"title": "Test"}
    prepared = _prepare_delivery_payload(payload, topic="test-topic", user=None)
    assert prepared["title"] == "Test"
    assert prepared["_meta"]["topic"] == "test-topic"
    assert "options" in prepared


def test_prepare_delivery_payload_with_user_quiet_hours(monkeypatch):
    import app.services.webpush as wp
    from app.services.webpush import _prepare_delivery_payload

    class MockUser:
        def __init__(self):
            self.id = "user-123"
            self.preferences = type(
                "Prefs",
                (),
                {
                    "dnd_enabled": True,
                    "dnd_start": None,  # Always in quiet hours if start/end missing but enabled
                    "dnd_end": None,
                    "timezone": "UTC",
                },
            )

    # Mock quiet hours to always True
    monkeypatch.setattr(wp, "_is_user_in_quiet_hours", lambda u: True)

    payload = {"title": "Hello", "body": "Secret"}
    user = MockUser()
    prepared = _prepare_delivery_payload(payload, topic="t", user=user)

    assert prepared["title"] == "Hello"
    assert prepared["options"]["silent"] is True
    assert prepared["data"]["dnd_suppressed"] is True


def test_process_push_results_cleanup(monkeypatch):
    import uuid
    from unittest.mock import AsyncMock, MagicMock

    from app.services.webpush import WebPushResult, process_push_results

    # Mock database session
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    monkeypatch.setattr("app.services.webpush.async_session", mock_session_factory)

    u1 = uuid.uuid4()
    u2 = uuid.uuid4()

    results = [
        WebPushResult(
            subscription_id=u1,
            endpoint="e1",
            user_id=uuid.uuid4(),
            status="gone",
            status_code=404,
        ),
        WebPushResult(
            subscription_id=u2,
            endpoint="e2",
            user_id=uuid.uuid4(),
            status="gone",
            status_code=410,
        ),
        WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="e3",
            user_id=uuid.uuid4(),
            status="sent",
            status_code=201,
        ),
    ]

    import asyncio

    asyncio.run(process_push_results(results))

    # Verify that sessions was called
    assert mock_session.execute.call_count >= 1
