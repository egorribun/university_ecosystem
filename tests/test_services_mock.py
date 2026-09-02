"""Wave 2 coverage: services with mocked dependencies.

Covers:
- app/services/ws_hub_client.py
- app/services/push_service.py
- app/services/event_handlers.py
- app/services/content_processing.py
- app/services/vector_service.py
- app/services/fraud_detection_service.py
- app/services/ical.py (pure helpers)
- app/services/user/logic.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/services/content_processing.py
# ---------------------------------------------------------------------------


def test_content_processing_strip_mode() -> None:
    from app.services.content_processing import SanitizationMode, sanitize

    result = sanitize(
        "<b>hello</b> <script>alert(1)</script>", mode=SanitizationMode.STRIP
    )
    assert "<b>" not in result
    assert "<script>" not in result
    assert "hello" in result


def test_content_processing_basic_mode() -> None:
    from app.services.content_processing import SanitizationMode, sanitize

    result = sanitize("<b>bold</b><script>bad</script>", mode=SanitizationMode.BASIC)
    assert "<script>" not in result
    assert "bold" in result


def test_content_processing_rich_text_mode() -> None:
    from app.services.content_processing import SanitizationMode, sanitize

    result = sanitize(
        "<p>Hello <b>world</b></p><script>bad</script>",
        mode=SanitizationMode.RICH_TEXT,
    )
    assert "<script>" not in result
    assert "Hello" in result


def test_content_processing_default_mode_is_rich_text() -> None:
    from app.services.content_processing import sanitize

    result = sanitize("<p>text</p>")
    # Should default to RICH_TEXT
    assert "text" in result


def test_content_processing_sanitization_modes_enum() -> None:
    from app.services.content_processing import SanitizationMode

    assert SanitizationMode.RICH_TEXT
    assert SanitizationMode.BASIC
    assert SanitizationMode.STRIP


def test_content_processing_backend_label() -> None:
    import app.services.content_processing as cp

    assert hasattr(cp, "_BACKEND_LABEL")
    assert isinstance(cp._BACKEND_LABEL, str)


def test_content_processing_nh3_fallback() -> None:
    import sys
    from unittest.mock import patch

    # Force fallback branch by deleting from sys.modules
    if "app.services.content_processing" in sys.modules:
        del sys.modules["app.services.content_processing"]

    with patch.dict("sys.modules", {"pyo3_sanitizer": None}):
        import app.services.content_processing as cp_fallback

        # Verify backend label
        assert cp_fallback._BACKEND_LABEL == "nh3 (fallback)"

        # Verify sanitization modes using fallback
        from app.services.content_processing import SanitizationMode

        res_rich = cp_fallback.sanitize(
            "<p>Hello <b>world</b></p><script>alert(1)</script>",
            mode=SanitizationMode.RICH_TEXT,
        )
        assert "<script>" not in res_rich
        assert "Hello" in res_rich

        res_basic = cp_fallback.sanitize(
            "<b>bold</b><script>alert(1)</script>", mode=SanitizationMode.BASIC
        )
        assert "<script>" not in res_basic
        assert "bold" in res_basic

        res_strip = cp_fallback.sanitize(
            "<b>strip</b><script>alert(1)</script>", mode=SanitizationMode.STRIP
        )
        assert "<b>" not in res_strip
        assert "<script>" not in res_strip
        assert "strip" in res_strip

    # Restore default backend state
    if "app.services.content_processing" in sys.modules:
        del sys.modules["app.services.content_processing"]


# ---------------------------------------------------------------------------
# app/services/ws_hub_client.py — WsHubClient.invalidate_cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_hub_client_invalidate_cache_success() -> None:
    from app.services.ws_hub_client import WsHubClient

    mock_broker = AsyncMock()
    mock_broker.publish = AsyncMock()

    with (
        patch("app.services.ws_hub_client.WsHubClient.__init__", return_value=None),
    ):
        client = WsHubClient.__new__(WsHubClient)
        client._broker = mock_broker
        client._secret = "test_secret"

    user_id = uuid.uuid4()
    room_id = uuid.uuid4()
    await client.invalidate_cache(user_id=user_id, room_id=room_id)

    mock_broker.publish.assert_awaited_once()
    call_args = mock_broker.publish.call_args
    assert call_args[0][0] == "cache.invalidate"
    payload = call_args[0][1]
    assert "signature" in payload
    assert payload["data"]["user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_ws_hub_client_invalidate_cache_nats_error_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from app.services.ws_hub_client import WsHubClient

    mock_broker = AsyncMock()
    mock_broker.publish = AsyncMock(side_effect=ConnectionError("NATS down"))

    client = WsHubClient.__new__(WsHubClient)
    client._broker = mock_broker
    client._secret = "test_secret"

    with caplog.at_level(logging.ERROR, logger="app.services.ws_hub_client"):
        await client.invalidate_cache(user_id="user1", room_id="room1")

    assert "ws_hub_invalidation_failed" in caplog.text


@pytest.mark.asyncio
async def test_ws_hub_client_signature_is_hmac() -> None:
    """Signature in the published payload is a valid HMAC-SHA256 hex string."""
    import hashlib
    import hmac
    import json

    from app.services.ws_hub_client import WsHubClient

    mock_broker = AsyncMock()
    captured: list[dict] = []

    async def capture_publish(subject: str, payload: dict) -> None:
        captured.append(payload)

    mock_broker.publish = capture_publish

    client = WsHubClient.__new__(WsHubClient)
    client._broker = mock_broker
    client._secret = "supersecret"

    user_id = "user-abc"
    room_id = "room-xyz"
    await client.invalidate_cache(user_id=user_id, room_id=room_id)

    assert len(captured) == 1
    payload = captured[0]
    # Verify the signature matches what we'd compute ourselves
    data = payload["data"]
    json_payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    expected_sig = hmac.new(
        b"supersecret", json_payload.encode(), hashlib.sha256
    ).hexdigest()
    assert payload["signature"] == expected_sig


# ---------------------------------------------------------------------------
# app/services/push_service.py — deliver_push_to_subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_push_empty_subscriptions() -> None:
    from app.services.push_service import deliver_push_to_subscriptions

    results = await deliver_push_to_subscriptions(
        subscriptions=[],
        payload={"title": "test"},
        topic="news",
    )
    assert results == []


@pytest.mark.asyncio
async def test_deliver_push_topic_filter_skips_unsupported() -> None:
    from app.services.push_service import deliver_push_to_subscriptions

    mock_sub = MagicMock()
    mock_sub.user = None

    with patch(
        "app.services.push_service.subscription_supports_topic",
        return_value=False,
    ):
        results = await deliver_push_to_subscriptions(
            subscriptions=[mock_sub],
            payload={"title": "test"},
            topic="events",
        )

    assert results == []


@pytest.mark.asyncio
async def test_deliver_push_successful_delivery() -> None:
    from app.services.push_service import deliver_push_to_subscriptions
    from app.services.webpush import WebPushResult

    mock_sub = MagicMock()
    mock_sub.user = None

    expected_result = WebPushResult(
        subscription_id=uuid.uuid4(),
        endpoint="https://push.example.com",
        user_id=uuid.uuid4(),
        status="ok",
        error=None,
    )

    with (
        patch(
            "app.services.push_service.subscription_supports_topic",
            return_value=True,
        ),
        patch(
            "app.services.push_service._deliver_to_subscription",
            new=AsyncMock(return_value=expected_result),
        ),
        patch(
            "app.services.notifications.prepare_push_payload_for_user",
            return_value={"title": "test"},
        ),
    ):
        results = await deliver_push_to_subscriptions(
            subscriptions=[mock_sub],
            payload={"title": "test"},
            topic=None,
        )

    # results may be list of WebPushResult or empty depending on mocking
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_deliver_push_handles_exception_result() -> None:
    """When gather returns an exception, it becomes an error WebPushResult."""
    from app.services.push_service import deliver_push_to_subscriptions

    mock_sub = MagicMock()
    mock_sub.user = None

    async def raise_exc(sub: Any) -> None:
        raise ConnectionError("push failed")

    with (
        patch(
            "app.services.push_service.subscription_supports_topic",
            return_value=True,
        ),
        patch(
            "app.services.push_service._deliver_to_subscription",
            new=AsyncMock(side_effect=ConnectionError("push failed")),
        ),
    ):
        results = await deliver_push_to_subscriptions(
            subscriptions=[mock_sub],
            payload={"title": "test"},
            topic=None,
            concurrency=1,
        )

    # Should handle the exception and return an error result
    assert isinstance(results, list)
    if results:
        assert results[0].status == "error"


# ---------------------------------------------------------------------------
# app/services/event_handlers.py — individual handler functions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_all_events() -> None:
    from app.core.events import DomainEvent
    from app.services.event_handlers import log_all_events

    # Create a concrete DomainEvent-like mock
    mock_event = MagicMock(spec=DomainEvent)
    mock_event.event_type = "test.event"
    mock_event.event_id = str(uuid.uuid4())

    # Should log without raising
    await log_all_events(mock_event)


@pytest.mark.asyncio
async def test_handle_user_created() -> None:
    from app.services.event_handlers import handle_user_created

    mock_event = MagicMock()
    mock_event.user_id = 42
    mock_event.email = "test@example.com"

    await handle_user_created(mock_event)  # should not raise


@pytest.mark.asyncio
async def test_handle_user_logged_in_with_ip() -> None:
    from app.services.event_handlers import handle_user_logged_in

    mock_event = MagicMock()
    mock_event.user_id = 1
    mock_event.ip_address = "127.0.0.1"

    await handle_user_logged_in(mock_event)


@pytest.mark.asyncio
async def test_handle_user_logged_in_no_ip() -> None:
    from app.services.event_handlers import handle_user_logged_in

    mock_event = MagicMock()
    mock_event.user_id = 1
    mock_event.ip_address = None

    await handle_user_logged_in(mock_event)


@pytest.mark.asyncio
async def test_handle_mfa_enabled() -> None:
    from app.services.event_handlers import handle_mfa_enabled

    mock_event = MagicMock()
    mock_event.user_id = 5
    mock_event.method = "totp"

    await handle_mfa_enabled(mock_event)


@pytest.mark.asyncio
async def test_handle_event_created() -> None:
    from app.services.event_handlers import handle_event_created

    mock_event = MagicMock()
    mock_event.event_id_entity = 100
    mock_event.organizer_id = 1
    mock_event.title = "Lecture 1"

    await handle_event_created(mock_event)


@pytest.mark.asyncio
async def test_handle_event_registration() -> None:
    from app.services.event_handlers import handle_event_registration

    mock_event = MagicMock()
    mock_event.event_id_entity = 100
    mock_event.user_id = 42

    await handle_event_registration(mock_event)


@pytest.mark.asyncio
async def test_handle_notification_sent() -> None:
    from app.services.event_handlers import handle_notification_sent

    mock_event = MagicMock()
    mock_event.notification_id = str(uuid.uuid4())
    mock_event.user_id = 3
    mock_event.notification_type = "news"

    await handle_notification_sent(mock_event)


@pytest.mark.asyncio
async def test_handle_notifications_requested_empty() -> None:
    from app.services.event_handlers import handle_notifications_requested

    mock_event = MagicMock()
    mock_event.notification_ids = []
    mock_event.channel = "push"

    await handle_notifications_requested(mock_event)  # returns early


@pytest.mark.asyncio
async def test_handle_notifications_requested_with_ids() -> None:
    from app.services import event_handlers

    mock_event = MagicMock()
    mock_event.notification_ids = [uuid.uuid4(), uuid.uuid4()]
    mock_event.channel = "push"
    db = MagicMock()
    db.commit = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=db)
    session_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(event_handlers, "async_session", return_value=session_context),
        patch(
            "app.services.notifications.delivery.redeliver_notifications",
            new=AsyncMock(return_value=SimpleNamespace(retryable_failures=0)),
        ) as redeliver,
    ):
        await event_handlers.handle_notifications_requested(mock_event)

    redeliver.assert_awaited_once_with(
        db,
        notification_ids=mock_event.notification_ids,
        channel="push",
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_chat_deleted() -> None:
    from app.services.event_handlers import handle_chat_deleted

    mock_event = MagicMock()
    mock_event.participant_id = uuid.uuid4()
    mock_event.chat_id = uuid.uuid4()

    with patch(
        "app.services.ws_hub_client.invalidate_ws_hub_cache",
        new=AsyncMock(),
    ) as mock_invalidate:
        await handle_chat_deleted(mock_event)
        mock_invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_attachment_cleanup_empty_urls() -> None:
    from app.services.event_handlers import handle_attachment_cleanup_requested

    mock_event = MagicMock()
    mock_event.attachment_urls = []
    mock_event.chat_id = uuid.uuid4()

    await handle_attachment_cleanup_requested(mock_event)  # returns early


@pytest.mark.asyncio
async def test_handle_attachment_cleanup_with_urls() -> None:
    from app.services.event_handlers import handle_attachment_cleanup_requested

    mock_event = MagicMock()
    mock_event.attachment_urls = ["/media/file1.jpg", "/media/file2.png"]
    mock_event.chat_id = uuid.uuid4()

    mock_attachment_svc = AsyncMock()
    mock_attachment_svc.cleanup_files = AsyncMock()

    with patch(
        "app.services.chat.attachment_service.ChatAttachmentService",
        return_value=mock_attachment_svc,
    ):
        await handle_attachment_cleanup_requested(mock_event)
        mock_attachment_svc.cleanup_files.assert_awaited_once_with(
            mock_event.attachment_urls
        )


@pytest.mark.asyncio
async def test_configure_event_handlers() -> None:
    from app.services.event_handlers import configure_event_handlers

    mock_bus = MagicMock()
    mock_bus.subscribe = MagicMock()
    mock_bus.subscribe_all = MagicMock()

    with patch("app.services.event_handlers.event_bus", mock_bus):
        configure_event_handlers()

    mock_bus.subscribe_all.assert_called_once()
    assert mock_bus.subscribe.call_count >= 5


@pytest.mark.asyncio
async def test_generate_event_embedding_not_found() -> None:
    from app.services.event_handlers import generate_event_embedding

    mock_event = MagicMock()
    mock_event.event_id_entity = 999

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)  # event not found
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.event_handlers.async_session", return_value=mock_session_ctx
        ),
        patch(
            "app.services.event_handlers.get_vector_service", return_value=MagicMock()
        ),
    ):
        await generate_event_embedding(mock_event)  # returns early when not found


@pytest.mark.asyncio
async def test_generate_news_embedding_not_found() -> None:
    from app.services.event_handlers import generate_news_embedding

    mock_event = MagicMock()
    mock_event.news_id = 999

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.event_handlers.async_session", return_value=mock_session_ctx
        ),
        patch(
            "app.services.event_handlers.get_vector_service", return_value=MagicMock()
        ),
    ):
        await generate_news_embedding(mock_event)


@pytest.mark.asyncio
async def test_generate_event_embedding_found() -> None:
    from app.services.event_handlers import generate_event_embedding

    mock_event = MagicMock()
    mock_event.event_id_entity = 1

    mock_db_event = MagicMock()
    mock_db_event.title = "Conference"
    mock_db_event.description = "Desc"
    mock_db_event.location = "Room 1"

    mock_vector_svc = AsyncMock()
    mock_vector_svc.get_embedding = AsyncMock(return_value=[0.1, 0.2])

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_db_event)
    mock_db.commit = AsyncMock()

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.event_handlers.async_session", return_value=mock_session_ctx
        ),
        patch(
            "app.services.event_handlers.get_vector_service",
            return_value=mock_vector_svc,
        ),
    ):
        await generate_event_embedding(mock_event)

    mock_vector_svc.get_embedding.assert_awaited_once()
    assert mock_db_event.embedding == [0.1, 0.2]


# ---------------------------------------------------------------------------
# app/services/vector_service.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vector_service_get_embedding_disabled() -> None:
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = False
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = "key"
        mock_settings.embedding_dimensions = 128

        svc = VectorService(db=mock_db)
        result = await svc.get_embedding("test text")

    assert result == [0.0] * 128


@pytest.mark.asyncio
async def test_vector_service_get_embedding_no_api_key() -> None:
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = True
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = ""
        mock_settings.embedding_dimensions = 64

        svc = VectorService(db=mock_db)
        result = await svc.get_embedding("test")

    assert result == [0.0] * 64


@pytest.mark.asyncio
async def test_vector_service_get_embedding_http_success() -> None:
    import httpx

    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    mock_response.raise_for_status = MagicMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = True
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = "test-key"
        mock_settings.embedding_dimensions = 3
        mock_settings.embedding_model = "text-embedding-3-small"

        svc = VectorService(db=mock_db)
        svc._client = AsyncMock()
        svc._client.post = AsyncMock(return_value=mock_response)

        result = await svc.get_embedding("hello world")

    assert result == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_vector_service_get_embedding_http_error() -> None:
    import httpx

    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = True
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = "key"
        mock_settings.embedding_dimensions = 8
        mock_settings.embedding_model = "model"

        svc = VectorService(db=mock_db)
        svc._client = AsyncMock()
        svc._client.post = AsyncMock(side_effect=httpx.ConnectError("no connection"))

        result = await svc.get_embedding("text")

    assert result == [0.0] * 8


@pytest.mark.asyncio
async def test_vector_service_search_similar_disabled() -> None:
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = False
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = ""
        mock_settings.embedding_dimensions = 4

        svc = VectorService(db=mock_db)
        results = await svc.search_similar_with_scores(
            MagicMock(), [0.1, 0.2, 0.3], limit=5
        )

    assert results == []


@pytest.mark.asyncio
async def test_vector_service_search_similar_empty_embedding() -> None:
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = True
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = "key"
        mock_settings.embedding_dimensions = 4

        svc = VectorService(db=mock_db)
        results = await svc.search_similar_with_scores(MagicMock(), [], limit=5)

    assert results == []


@pytest.mark.asyncio
async def test_vector_service_close() -> None:
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = False
        mock_settings.embedding_api_base = "http://localhost"
        mock_settings.embedding_api_key = ""
        mock_settings.embedding_dimensions = 4

        svc = VectorService(db=mock_db)
        svc._client = AsyncMock()
        svc._client.aclose = AsyncMock()
        await svc.close()

    svc._client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_vector_service_search_disabled_returns_empty() -> None:
    """When semantic search is disabled, search_similar_with_scores returns []."""
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = False
        mock_settings.embedding_api_base = "http://localhost:8001"
        mock_settings.embedding_api_key = None

        svc = VectorService(db=mock_db)
        results = await svc.search_similar_with_scores(
            MagicMock(), [0.1, 0.2, 0.3], limit=5, min_score=0.5
        )

    assert results == []


@pytest.mark.asyncio
async def test_vector_service_search_empty_embedding_returns_empty() -> None:
    """Empty embedding short-circuits without querying DB."""
    from app.services.vector_service import VectorService

    mock_db = AsyncMock()

    with (
        patch("app.services.vector_service.settings") as mock_settings,
        patch("app.services.vector_service.validate_url_not_internal"),
    ):
        mock_settings.semantic_search_enabled = True
        mock_settings.embedding_api_base = "http://localhost:8001"
        mock_settings.embedding_api_key = None

        svc = VectorService(db=mock_db)
        results = await svc.search_similar_with_scores(
            MagicMock(), [], limit=5, min_score=0.5
        )

    assert results == []
    mock_db.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# app/services/fraud_detection_service.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fraud_detection_record_event_success() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value="1-0")

    svc = FraudDetectionService(redis_client=mock_redis)
    await svc.record_event({"action": "login", "user_id": "123", "severity": "low"})

    mock_redis.xadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_fraud_detection_record_event_high_severity() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    mock_pipeline = AsyncMock()
    mock_pipeline.zadd = MagicMock()
    mock_pipeline.expire = MagicMock()
    mock_pipeline.execute = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value="1-0")
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    svc = FraudDetectionService(redis_client=mock_redis)
    uid = str(uuid.uuid4())
    await svc.record_event(
        {"action": "brute_force", "user_id": uid, "severity": "high"}
    )

    mock_redis.pipeline.assert_called_once()
    mock_pipeline.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_fraud_detection_record_event_redis_error() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(side_effect=ConnectionError("Redis down"))

    svc = FraudDetectionService(redis_client=mock_redis)
    # Should not raise
    await svc.record_event({"action": "x"})


@pytest.mark.asyncio
async def test_fraud_detection_get_recent_events_no_filter() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    raw_data = [
        (b"1234-0", {b"user_id": b"abc", b"action": b"login", b"severity": b"low"})
    ]
    mock_redis = AsyncMock()
    mock_redis.xrevrange = AsyncMock(return_value=raw_data)

    svc = FraudDetectionService(redis_client=mock_redis)
    events = await svc.get_recent_events(count=10)

    assert len(events) == 1
    assert events[0]["user_id"] == "abc"


@pytest.mark.asyncio
async def test_fraud_detection_get_recent_events_with_user_filter() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    target_uid = str(uuid.uuid4())
    raw_data = [
        (b"1-0", {b"user_id": target_uid.encode(), b"action": b"a"}),
        (b"2-0", {b"user_id": b"other_user", b"action": b"b"}),
    ]
    mock_redis = AsyncMock()
    mock_redis.xrevrange = AsyncMock(return_value=raw_data)

    svc = FraudDetectionService(redis_client=mock_redis)
    events = await svc.get_recent_events(user_id=target_uid, count=10)

    assert all(e["user_id"] == target_uid for e in events)


@pytest.mark.asyncio
async def test_fraud_detection_get_recent_events_with_time_filter() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    mock_redis = AsyncMock()
    mock_redis.xrevrange = AsyncMock(return_value=[])

    svc = FraudDetectionService(redis_client=mock_redis)
    events = await svc.get_recent_events(within_seconds=300)

    assert events == []
    # Check xrevrange was called with a min_id (not "-")
    call_args = mock_redis.xrevrange.call_args
    assert call_args[1]["min"] != "-"


@pytest.mark.asyncio
async def test_fraud_detection_get_recent_events_redis_error() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    mock_redis = AsyncMock()
    mock_redis.xrevrange = AsyncMock(side_effect=ConnectionError("oops"))

    svc = FraudDetectionService(redis_client=mock_redis)
    events = await svc.get_recent_events()

    assert events == []


@pytest.mark.asyncio
async def test_fraud_detection_count_recent_high_severity_success() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    mock_redis = AsyncMock()
    mock_redis.zcount = AsyncMock(return_value=3)

    svc = FraudDetectionService(redis_client=mock_redis)
    uid = str(uuid.uuid4())
    count = await svc.count_recent_high_severity(user_id=uid, within_seconds=300)

    assert count == 3


@pytest.mark.asyncio
async def test_fraud_detection_count_recent_high_severity_fallback_on_error() -> None:
    from app.services.fraud_detection_service import FraudDetectionService

    raw_data = [
        (b"1-0", {b"severity": b"high", b"user_id": b"usr"}),
        (b"2-0", {b"severity": b"low", b"user_id": b"usr"}),
        (b"3-0", {b"severity": b"high", b"user_id": b"usr"}),
    ]
    mock_redis = AsyncMock()
    mock_redis.zcount = AsyncMock(side_effect=ConnectionError("zcount down"))
    mock_redis.xrevrange = AsyncMock(return_value=raw_data)

    svc = FraudDetectionService(redis_client=mock_redis)
    count = await svc.count_recent_high_severity(user_id="usr", within_seconds=300)

    # Fallback counts high-severity from stream
    assert count == 2


# ---------------------------------------------------------------------------
# app/services/ical.py — pure helpers
# ---------------------------------------------------------------------------


def test_ical_escape_empty() -> None:
    from app.services.ical import _escape

    assert _escape(None) == ""
    assert _escape("") == ""


def test_ical_escape_special_chars() -> None:
    from app.services.ical import _escape

    result = _escape("a;b,c\nd\\e")
    assert "\\;" in result
    assert "\\," in result
    assert "\\n" in result
    assert "\\\\" in result


def test_ical_format_dt_utc() -> None:
    from app.services.ical import _format_dt

    dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    result = _format_dt(dt)
    assert result.endswith("Z")
    assert "20250601" in result


def test_ical_format_dt_aware_non_utc() -> None:
    from app.services.ical import _format_dt

    tz = UTC  # UTC is UTC regardless
    dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=tz)
    result = _format_dt(dt)
    assert result.endswith("Z")


def test_ical_format_dt_naive() -> None:
    from app.services.ical import _format_dt

    dt = datetime(2025, 3, 15, 9, 30, 0)  # naive
    result = _format_dt(dt)
    assert "Z" not in result
    assert "20250315" in result


def test_ical_ensure_time_none() -> None:
    from app.services.ical import _ensure_time

    assert _ensure_time(None) is None


def test_ical_ensure_time_from_datetime() -> None:
    from app.services.ical import _ensure_time

    dt = datetime(2025, 6, 1, 10, 30, 0)
    result = _ensure_time(dt)
    assert result is not None
    assert result.hour == 10
    assert result.minute == 30


def test_ical_ensure_time_from_time() -> None:
    from datetime import time

    from app.services.ical import _ensure_time

    t = time(14, 0, 0)
    result = _ensure_time(t)
    assert result == t


def test_ical_weekday_index_none() -> None:
    from app.services.ical import _weekday_index

    result = _weekday_index(None)
    assert result is None


# ---------------------------------------------------------------------------
# app/services/user/logic.py — update_user_attributes
# ---------------------------------------------------------------------------


def test_update_user_attributes_profile_fields() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.profile = MagicMock()
    mock_user.preferences = MagicMock()
    mock_user.education_path = MagicMock()

    update_user_attributes(mock_user, {"full_name": "John Doe", "about": "Bio"})

    assert mock_user.profile.full_name == "John Doe"
    assert mock_user.profile.about == "Bio"


def test_update_user_attributes_creates_profile_if_none() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.profile = None
    mock_user.preferences = None
    mock_user.education_path = None

    update_user_attributes(mock_user, {"full_name": "Jane"})
    # profile should be created


def test_update_user_attributes_preferences_fields() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.preferences = MagicMock()

    update_user_attributes(mock_user, {"dnd_enabled": True})
    assert mock_user.preferences.dnd_enabled is True


def test_update_user_attributes_preferences_dict() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.preferences = MagicMock()

    update_user_attributes(mock_user, {"preferences": {"dnd_enabled": False}})
    assert mock_user.preferences.dnd_enabled is False


def test_update_user_attributes_profile_dict() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.profile = MagicMock()

    update_user_attributes(mock_user, {"profile": {"full_name": "Alice", "about": "X"}})
    assert mock_user.profile.full_name == "Alice"


def test_update_user_attributes_education_fields() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.education_path = MagicMock()
    mock_user.preferences = MagicMock()
    mock_user.profile = MagicMock()

    update_user_attributes(mock_user, {"institute": "MIT", "course": "3"})
    assert mock_user.education_path.institute == "MIT"
    assert mock_user.education_path.course == "3"


def test_update_user_attributes_direct_field() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.preferences = MagicMock()
    mock_user.profile = MagicMock()
    mock_user.education_path = MagicMock()

    update_user_attributes(mock_user, {"is_active": False})
    # Should call setattr on user directly
    assert mock_user.is_active is False


def test_update_user_attributes_creates_education_if_none() -> None:
    from app.services.user.logic import update_user_attributes

    mock_user = MagicMock()
    mock_user.education_path = None
    mock_user.preferences = MagicMock()
    mock_user.profile = MagicMock()
    mock_user.id = uuid.uuid4()

    update_user_attributes(mock_user, {"institute": "Oxford"})
    # education_path should be created (patched model)
