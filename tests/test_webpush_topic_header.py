"""Web Push replacement topics remain valid independently of application topics."""

from __future__ import annotations

import json
import re
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.notification_contract import CANONICAL_NOTIFICATION_TOPICS
from app.services import webpush as webpush_module


@pytest.fixture
def transport(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, list[dict[str, Any]]]:
    """Record the actual pywebpush boundary without any DNS or network access."""
    sent: list[dict[str, Any]] = []

    def fake_webpush(**kwargs: Any) -> None:
        header = kwargs["headers"].get("Topic")
        if header is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", header):
            error = webpush_module.WebPushException("invalid web push topic")
            error.response = SimpleNamespace(status_code=400)
            raise error
        sent.append(kwargs)

    monkeypatch.setattr(webpush_module, "validate_public_https_url", lambda _url: None)
    monkeypatch.setattr(
        webpush_module, "validate_and_resolve", lambda _url: [("93.184.216.34", 443)]
    )
    monkeypatch.setattr(
        webpush_module, "_create_pinned_webpush_session", lambda *_args: MagicMock()
    )
    monkeypatch.setattr(webpush_module, "webpush", fake_webpush)
    subscription = MagicMock()
    subscription.id = uuid.uuid4()
    subscription.user_id = uuid.uuid4()
    subscription.endpoint = "https://push.example.test/synthetic"
    subscription.p256dh = uuid.uuid4().hex
    subscription.auth = uuid.uuid4().hex
    subscription.user = None
    return subscription, sent


@pytest.mark.parametrize("topic", CANONICAL_NOTIFICATION_TOPICS)
def test_canonical_application_topic_is_deliverable_without_changing_payload(
    transport: tuple[MagicMock, list[dict[str, Any]]], topic: str
) -> None:
    subscription, sent = transport
    result = webpush_module.send_web_push(
        subscription,
        {
            "title": "News",
            "topic": topic,
            "data": {"recipientUserId": str(subscription.user_id)},
        },
    )

    assert result.status == "sent"
    assert len(sent) == 1
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,32}", sent[0]["headers"]["Topic"])
    data = json.loads(sent[0]["data"])["data"]
    assert data["topic"] == topic
    assert data["recipientUserId"] == str(subscription.user_id)


@pytest.mark.parametrize("topic", ["sys-updates", "a" * 32, "UPPER_lower-0123"])
def test_compatible_topic_headers_preserve_existing_values(
    transport: tuple[MagicMock, list[dict[str, Any]]], topic: str
) -> None:
    subscription, sent = transport
    result = webpush_module.send_web_push(subscription, {"title": "T", "topic": topic})

    assert result.status == "sent"
    assert sent[0]["headers"]["Topic"] == topic
    assert json.loads(sent[0]["data"])["data"]["topic"] == topic


def test_invalid_and_reserved_topics_get_stable_distinct_bounded_headers(
    transport: tuple[MagicMock, list[dict[str, Any]]],
) -> None:
    subscription, sent = transport
    topics = [
        "news.published",
        "news.published",
        "events.published",
        "a" * 33,
        "новости",
    ]
    for topic in topics:
        assert (
            webpush_module.send_web_push(
                subscription, {"title": "T", "topic": topic}
            ).status
            == "sent"
        )

    headers = [request["headers"]["Topic"] for request in sent]
    assert headers[0] == headers[1]
    assert len(set(headers[1:])) == len(headers[1:])
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", header) for header in headers)

    # A valid literal in the encoded namespace cannot alias an encoded topic.
    literal_alias = headers[0]
    assert (
        webpush_module.send_web_push(
            subscription, {"title": "T", "topic": literal_alias}
        ).status
        == "sent"
    )
    assert sent[-1]["headers"]["Topic"] != literal_alias
    assert json.loads(sent[-1]["data"])["data"]["topic"] == literal_alias


@pytest.mark.parametrize("topic", [None, ""])
def test_absent_topic_omits_replacement_header(
    transport: tuple[MagicMock, list[dict[str, Any]]], topic: str | None
) -> None:
    subscription, sent = transport
    assert (
        webpush_module.send_web_push(
            subscription, {"title": "T", "topic": topic}
        ).status
        == "sent"
    )
    assert "Topic" not in sent[0]["headers"]


def test_provider_failure_still_reports_the_real_status(
    transport: tuple[MagicMock, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    subscription, _sent = transport
    error = webpush_module.WebPushException("provider unavailable")
    error.response = SimpleNamespace(status_code=503)
    provider = MagicMock(side_effect=error)
    monkeypatch.setattr(webpush_module, "webpush", provider)

    result = webpush_module.send_web_push(
        subscription, {"title": "T", "topic": "news.published"}
    )

    assert result.status == "error"
    assert result.status_code == 503
    provider.assert_called_once()
