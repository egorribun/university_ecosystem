import pytest

from app.models.models import PushSubscription
from app.services import webpush as webpush_module


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        return None


@pytest.fixture(autouse=True)
def _stub_session(monkeypatch):
    monkeypatch.setattr(webpush_module, "_Session", lambda: _DummySession())


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch):
    class _Settings:
        VAPID_PRIVATE_KEY = "test-private"
        WEBPUSH_SUBJECT = "mailto:test@example.com"

    monkeypatch.setattr(webpush_module, "settings", _Settings())


def _make_subscription() -> PushSubscription:
    subscription = PushSubscription(
        endpoint="https://example.com/subscription",
        p256dh="p256dh-key",
        auth="auth-key",
        user_id=1,
        topics=[],
    )
    subscription.id = 1
    return subscription


@pytest.mark.parametrize(
    ("urgency", "expected_ttl"),
    [
        ("high", 5 * 60),
        ("normal", 60 * 60),
        ("low", 12 * 60 * 60),
        ("very-low", 24 * 60 * 60),
        (None, 60 * 60),
    ],
)
def test_send_web_push_sets_ttl_based_on_urgency(monkeypatch, urgency, expected_ttl):
    captured: dict[str, object] = {}

    def _capture_webpush(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(webpush_module, "webpush", _capture_webpush)
    payload: dict[str, object] = {"title": "Test"}
    if urgency is not None:
        payload["urgency"] = urgency
    result = webpush_module.send_web_push(_make_subscription(), payload)

    assert result.status == "sent"
    assert captured["ttl"] == expected_ttl
    assert captured["headers"]["TTL"] == str(expected_ttl)
    if urgency:
        assert captured["headers"]["Urgency"] == urgency
    else:
        assert "Urgency" not in captured["headers"]


def test_send_web_push_prefers_explicit_ttl(monkeypatch):
    captured: dict[str, object] = {}

    def _capture_webpush(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(webpush_module, "webpush", _capture_webpush)
    payload = {"title": "Test", "ttl": 900, "urgency": "high"}

    result = webpush_module.send_web_push(_make_subscription(), payload)

    assert result.status == "sent"
    assert captured["ttl"] == 900
    assert captured["headers"]["TTL"] == "900"
    assert captured["headers"]["Urgency"] == "high"
