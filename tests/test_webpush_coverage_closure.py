from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from pywebpush import WebPushException
from sqlalchemy.engine import make_url

from app.services import webpush


def test_build_payload_preserves_timestamp_without_silent_flag() -> None:
    with patch.object(webpush, "render_notification_template", return_value={}):
        payload = webpush.build_payload("news", {"timestamp": "1700000000000"})

    assert payload["options"]["timestamp"] == 1_700_000_000_000


def test_sync_url_preserves_already_synchronous_driver() -> None:
    with (
        patch.object(webpush, "_sync_url_cache", None),
        patch.object(webpush.settings, "database_url", "postgresql://db/app"),
    ):
        assert webpush._get_sync_url() == make_url("postgresql://db/app")


def test_sync_sessionmaker_fast_path_and_double_check() -> None:
    existing = MagicMock()
    with patch.object(webpush, "_Session", existing):
        assert webpush._ensure_sync_sessionmaker() is existing

    lock = MagicMock()

    def initialize_elsewhere() -> None:
        webpush._Session = existing

    lock.__enter__.side_effect = initialize_elsewhere
    with (
        patch.object(webpush, "_Session", None),
        patch.object(webpush, "_sync_init_lock", lock),
        patch.object(webpush, "_initialize_sync_resources") as initialize,
    ):
        assert webpush._ensure_sync_sessionmaker() is existing
    initialize.assert_not_called()


@pytest.mark.asyncio
async def test_async_sessionmaker_fast_path_and_double_check() -> None:
    existing = MagicMock()
    with patch.object(webpush, "_Session", existing):
        assert await webpush._ensure_async_sessionmaker() is existing

    class InitializingLock:
        async def __aenter__(self) -> None:
            webpush._Session = existing

        async def __aexit__(self, *args: object) -> None:
            return None

    with (
        patch.object(webpush, "_Session", None),
        patch.object(webpush, "_async_init_lock", InitializingLock()),
        patch.object(webpush.asyncio, "to_thread") as to_thread,
    ):
        assert await webpush._ensure_async_sessionmaker() is existing
    to_thread.assert_not_called()


def test_normalize_actions_without_urls_in_both_input_shapes() -> None:
    action = {"action": "open", "title": "Open"}
    top_level, _ = webpush._normalize_payload({"actions": [action]})
    nested, _ = webpush._normalize_payload({"options": {"actions": [action]}})

    assert top_level["options"]["actions"] == [action]
    assert nested["options"]["actions"] == [action]
    assert "actionUrls" not in top_level["data"]
    assert "actionUrls" not in nested["data"]


def test_build_payload_merges_input_data_when_template_has_none() -> None:
    with patch.object(
        webpush,
        "render_notification_template",
        return_value={"title": "Template"},
    ):
        payload = webpush.build_payload("news", {"data": {"article": "42"}})

    assert payload["data"]["article"] == "42"


def test_empty_webpush_error_message_is_not_misclassified_as_gone() -> None:
    class EmptyMessageWebPushError(WebPushException):
        def __str__(self) -> str:
            return ""

    subscription = MagicMock(
        id=uuid.uuid4(),
        endpoint="https://push.example.com/subscription",
        p256dh="key",
        auth="auth",
        user_id=None,
        user=None,
    )
    settings = MagicMock(
        VAPID_PRIVATE_KEY="private-key",  # pragma: allowlist secret
        WEBPUSH_SUBJECT="mailto:admin@example.com",
    )
    with (
        patch.object(webpush, "settings", settings),
        patch.object(webpush, "validate_public_https_url"),
        patch.object(webpush, "validate_url_not_internal"),
        patch.object(
            webpush,
            "webpush",
            side_effect=EmptyMessageWebPushError(""),
        ),
    ):
        result = webpush.send_web_push(subscription, {"title": "Hello"})

    assert result.status == "error"
    assert result.error is None
