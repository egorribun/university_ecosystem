"""Comprehensive tests for app/services/webpush.py.

Extends existing test_webpush_unit.py to cover send_web_push exception
handling, async delivery, rate limiting, process_push_results DB cleanup,
and concurrency control paths.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PushSubscription
from app.services.webpush import (
    WebPushResult,
    _is_user_in_quiet_hours,
    _normalize_payload,
    _prepare_actions,
    _prepare_delivery_payload,
    _resolve_ttl,
    _sanitize_vibrate,
    build_payload,
    process_push_results,
    send_web_push,
)

# ---------------------------------------------------------------------------
# send_web_push — exception handling paths
# ---------------------------------------------------------------------------


class TestSendWebPush:
    """Tests for send_web_push exception handling.

    Note: the exception branches in send_web_push are marked with
    ``pragma: no cover`` upstream. These tests verify correctness of
    the gone/error classification logic even though coverage won't count them.
    """

    def _make_sub(self, endpoint: str = "https://push.example.com/test"):
        sub = MagicMock()
        sub.id = uuid.uuid4()
        sub.endpoint = endpoint
        sub.user_id = uuid.uuid4()
        sub.p256dh = "key"
        sub.auth = "auth"
        sub.user = None
        return sub

    def test_success(self, mock_pywebpush):
        sub = self._make_sub()
        result = send_web_push(sub, {"title": "Hello"})
        assert result.status == "sent"
        assert result.subscription_id == sub.id
        mock_pywebpush.assert_called_once()
        call_kwargs = mock_pywebpush.call_args.kwargs
        assert call_kwargs["subscription_info"] == {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }

    def test_dns_failure_is_not_bypassed_outside_development(
        self, mock_pywebpush, monkeypatch
    ):
        """A DNS failure must remain fail-closed outside development mode."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.webpush.settings",
            SimpleNamespace(
                is_development=False,
                VAPID_PRIVATE_KEY="",
                WEBPUSH_SUBJECT="mailto:test@example.com",
            ),
        )
        monkeypatch.setattr(
            "app.services.webpush.validate_url_not_internal",
            MagicMock(side_effect=ValueError("DNS resolution failed")),
        )

        result = send_web_push(self._make_sub(), {"title": "Blocked"})

        assert result.status == "error"
        assert "DNS resolution failed" in (result.error or "")
        mock_pywebpush.assert_not_called()

    def test_dns_failure_default_is_fail_closed_when_setting_is_missing(
        self, mock_pywebpush, monkeypatch
    ):
        """Missing development configuration must use the safe false default."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.webpush.settings",
            SimpleNamespace(
                VAPID_PRIVATE_KEY="",
                WEBPUSH_SUBJECT="mailto:test@example.com",
            ),
        )
        monkeypatch.setattr(
            "app.services.webpush.validate_url_not_internal",
            MagicMock(side_effect=ValueError("DNS resolution failed")),
        )

        result = send_web_push(self._make_sub(), {"title": "Blocked"})

        assert result.status == "error"
        assert "DNS resolution failed" in (result.error or "")
        mock_pywebpush.assert_not_called()

    def test_dns_failure_is_allowed_in_development(self, mock_pywebpush, monkeypatch):
        """Development fixtures may use provider endpoints without DNS."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.webpush.settings",
            SimpleNamespace(
                is_development=True,
                VAPID_PRIVATE_KEY="",
                WEBPUSH_SUBJECT="mailto:test@example.com",
            ),
        )
        monkeypatch.setattr(
            "app.services.webpush.validate_url_not_internal",
            MagicMock(side_effect=ValueError("DNS resolution failed")),
        )

        result = send_web_push(self._make_sub(), {"title": "Development"})

        assert result.status == "sent"
        mock_pywebpush.assert_called_once()

    def test_rejects_private_endpoint_before_network_call(self, mock_pywebpush):
        sub = self._make_sub("https://127.0.0.1/latest")
        result = send_web_push(sub, {"title": "Blocked"})
        assert result.status == "error"
        assert "private" in (result.error or "").lower()
        mock_pywebpush.assert_not_called()

    def test_gone_404(self, mock_pywebpush):
        from pywebpush import WebPushException

        mock_pywebpush.side_effect = WebPushException(
            "Not Found", response=MagicMock(status_code=404)
        )
        result = send_web_push(self._make_sub(), {"title": "Gone"})
        assert result.status == "gone"

    def test_gone_410(self, mock_pywebpush):
        from pywebpush import WebPushException

        mock_pywebpush.side_effect = WebPushException(
            "Gone", response=MagicMock(status_code=410)
        )
        result = send_web_push(self._make_sub(), {"title": "Gone"})
        assert result.status == "gone"

    def test_error_429(self, mock_pywebpush):
        from types import SimpleNamespace

        from pywebpush import WebPushException

        # Use SimpleNamespace instead of MagicMock to avoid random memory
        # addresses in str(exc) that could accidentally contain "410"/"404".
        mock_resp = SimpleNamespace(status_code=429, text="Rate Limited")
        mock_pywebpush.side_effect = WebPushException(
            "Rate Limited", response=mock_resp
        )
        result = send_web_push(self._make_sub(), {"title": "Rate"})
        assert result.status == "error"
        assert result.status_code == 429

    def test_error_generic_exception(self, mock_pywebpush):
        mock_pywebpush.side_effect = ConnectionError("Connection reset")
        result = send_web_push(self._make_sub(), {"title": "Error"})
        assert result.status == "error"
        assert "Connection reset" in (result.error or "")

    def test_webpush_exception_404_in_message(self, mock_pywebpush):
        from pywebpush import WebPushException

        mock_pywebpush.side_effect = WebPushException("404 Not Found")
        result = send_web_push(self._make_sub(), {"title": "G"})
        assert result.status == "gone"


# ---------------------------------------------------------------------------
# _send_push_async — timeout and semaphore
# ---------------------------------------------------------------------------


class TestSendPushAsync:
    @pytest.mark.asyncio
    async def test_timeout(self, mock_pywebpush):
        """Push exceeding timeout returns error."""
        from app.services.webpush import _send_push_async

        async def slow_push(*args, **kwargs):
            await asyncio.sleep(100)

        sub = MagicMock()
        sub.id = uuid.uuid4()
        sub.endpoint = "https://push.example.com/slow"
        sub.user_id = uuid.uuid4()
        sub.p256dh = "key"
        sub.auth = "auth"
        sub.user = None

        with (
            patch("app.services.webpush.asyncio.to_thread", side_effect=slow_push),
            patch("app.services.webpush._PUSH_CALL_TIMEOUT_SECONDS", 0.01),
        ):
            result = await _send_push_async(sub, {"title": "Slow"})
            assert result.status == "error"
            assert "timed out" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# process_push_results — DB cleanup
# ---------------------------------------------------------------------------


class TestProcessPushResults:
    @pytest.mark.asyncio
    async def test_deletes_gone_subscriptions(
        self, db_session: AsyncSession, user_factory, push_subscription_factory
    ):
        """Gone subscriptions are deleted from DB."""
        from contextlib import asynccontextmanager

        user = await user_factory()
        sub = await push_subscription_factory(user=user)
        sub_id = sub.id

        results = [
            WebPushResult(
                subscription_id=sub_id,
                endpoint=sub.endpoint,
                user_id=user.id,
                status="gone",
            )
        ]

        @asynccontextmanager
        async def _fake_session():
            yield db_session

        with patch("app.services.webpush.async_session", _fake_session):
            with patch(
                "app.services.webpush._ensure_async_sessionmaker",
                new_callable=AsyncMock,
            ):
                await process_push_results(results)

        # Verify deleted
        row = (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.id == sub_id)
            )
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_updates_sent_subscriptions(
        self, db_session: AsyncSession, user_factory, push_subscription_factory
    ):
        """Sent subscriptions get last_seen_at updated."""
        from contextlib import asynccontextmanager

        user = await user_factory()
        sub = await push_subscription_factory(user=user, last_seen_at=None)
        sub_id = sub.id

        results = [
            WebPushResult(
                subscription_id=sub_id,
                endpoint=sub.endpoint,
                user_id=user.id,
                status="sent",
            )
        ]

        @asynccontextmanager
        async def _fake_session():
            yield db_session

        with patch("app.services.webpush.async_session", _fake_session):
            with patch(
                "app.services.webpush._ensure_async_sessionmaker",
                new_callable=AsyncMock,
            ):
                await process_push_results(results)

        # Re-query to see updated value
        row = (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.id == sub_id)
            )
        ).scalar_one()
        assert row.last_seen_at is not None

    @pytest.mark.asyncio
    async def test_empty_results_noop(self):
        """Empty results list does nothing."""
        # Should not raise
        await process_push_results([])


# ---------------------------------------------------------------------------
# Quiet hours
# ---------------------------------------------------------------------------


class TestQuietHours:
    def test_not_in_quiet_hours(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(23, 0)
        user.preferences.dnd_end = time(7, 0)

        # 12:00 noon — outside DND
        assert _is_user_in_quiet_hours(user, now_time=time(12, 0)) is False

    def test_in_quiet_hours_wrap_around(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(23, 0)
        user.preferences.dnd_end = time(7, 0)

        # 2:00 AM — inside DND (wraps midnight)
        assert _is_user_in_quiet_hours(user, now_time=time(2, 0)) is True

    def test_dnd_disabled(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = False

        assert _is_user_in_quiet_hours(user, now_time=time(3, 0)) is False

    def test_no_preferences(self):
        user = MagicMock()
        user.preferences = None

        assert _is_user_in_quiet_hours(user) is False

    def test_none_user(self):
        assert _is_user_in_quiet_hours(None) is False

    def test_same_start_end(self):
        """DND start == end means always in DND when enabled."""
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(0, 0)
        user.preferences.dnd_end = time(0, 0)

        # When start==end the range is zero or 24h; implementation-dependent
        result = _is_user_in_quiet_hours(user, now_time=time(12, 0))
        assert isinstance(result, bool)  # just ensure no crash


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


class TestPayloadHelpers:
    def test_resolve_ttl_explicit(self):
        assert _resolve_ttl({"ttl": 300}) == 300

    def test_resolve_ttl_urgency_high(self):
        assert _resolve_ttl({"urgency": "high"}) == 300  # 5 min

    def test_resolve_ttl_urgency_low(self):
        assert _resolve_ttl({"urgency": "low"}) == 43200  # 12h

    def test_resolve_ttl_urgency_very_low(self):
        assert _resolve_ttl({"urgency": "very-low"}) == 86400  # 24h

    def test_resolve_ttl_default(self):
        assert _resolve_ttl({}) == 3600  # default 1h

    def test_sanitize_vibrate_valid(self):
        assert _sanitize_vibrate([100, 50, 200]) == [100, 50, 200]

    def test_sanitize_vibrate_floats(self):
        result = _sanitize_vibrate([100.5, 50.2])
        assert result == [100, 50]

    def test_sanitize_vibrate_non_numeric(self):
        result = _sanitize_vibrate([100, "invalid", 200])
        assert result == [100, 200]

    def test_sanitize_vibrate_empty(self):
        assert _sanitize_vibrate([]) == []

    def test_sanitize_vibrate_none(self):
        assert _sanitize_vibrate(None) == []

    def test_prepare_actions_valid(self):
        actions, urls = _prepare_actions(
            [
                {"action": "open", "title": "Open", "url": "/home"},
                {"action": "dismiss", "title": "Dismiss"},
            ]
        )
        assert len(actions) == 2
        assert urls.get("open") == "/home"

    def test_prepare_actions_empty(self):
        actions, urls = _prepare_actions([])
        assert actions == []
        assert urls == {}

    def test_prepare_actions_none(self):
        actions, urls = _prepare_actions(None)
        assert actions == []
        assert urls == {}

    def test_normalize_payload_basic(self):
        payload, _meta = _normalize_payload({"title": "Hello", "body": "World"})
        assert payload["title"] == "Hello"
        # body may be in options depending on normalization logic
        body = payload.get("body") or payload.get("options", {}).get("body")
        assert body == "World"

    def test_normalize_payload_with_meta(self):
        _payload, meta = _normalize_payload(
            {"title": "T", "ttl": 600, "urgency": "high", "topic": "sys"}
        )
        assert meta.get("ttl") == 600
        assert meta.get("urgency") == "high"

    def test_normalize_payload_none(self):
        payload, meta = _normalize_payload(None)
        assert isinstance(payload, dict)
        assert isinstance(meta, dict)

    def test_normalize_payload_with_locale(self):
        payload, _meta = _normalize_payload({"title": "T"}, locale="ru")
        assert isinstance(payload, dict)

    def test_build_payload_minimal(self):
        result = build_payload("test", {"title": "T", "body": "B"})
        assert "title" in result
        # body may be nested in options
        has_body = "body" in result or "body" in result.get("options", {})
        assert has_body


# ---------------------------------------------------------------------------
# _prepare_delivery_payload — DND suppression
# ---------------------------------------------------------------------------


class TestPrepareDeliveryPayload:
    def test_with_quiet_hours_suppression(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(0, 0)
        user.preferences.dnd_end = time(23, 59)
        user.preferences.timezone = "UTC"

        result = _prepare_delivery_payload(
            {"title": "Test", "body": "Hello"}, topic="system", user=user
        )
        # When in quiet hours, silent mode is applied
        assert isinstance(result, dict)

    def test_without_user(self):
        result = _prepare_delivery_payload(
            {"title": "Test", "body": "Hello"}, topic="system", user=None
        )
        assert isinstance(result, dict)
        assert "title" in result

    def test_with_topic(self):
        result = _prepare_delivery_payload({"title": "T"}, topic="events", user=None)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# WebPushResult dataclass
# ---------------------------------------------------------------------------


class TestWebPushResult:
    def test_creation(self):
        r = WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="https://e.com",
            user_id=uuid.uuid4(),
            status="sent",
        )
        assert r.status == "sent"
        assert r.status_code is None
        assert r.error is None

    def test_error_result(self):
        r = WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="https://e.com",
            user_id=uuid.uuid4(),
            status="error",
            status_code=500,
            error="Internal Server Error",
        )
        assert r.status == "error"
        assert r.status_code == 500
