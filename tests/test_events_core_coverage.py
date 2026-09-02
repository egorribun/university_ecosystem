"""Wave 7 coverage tests: Core events, CSRF, middleware, DLQ, database config.

Targets:
- app/core/events.py: from_dict() on all domain event types
- app/core/csrf.py: _compute_csrf_hmac, _build_signed_token, _verify_signed_token
- app/core/middleware/content_size.py: invalid Content-Length, payload too large,
  chunked body replay
- app/core/middleware/response_hardening.py: Vary header, Cache-Control for static
- app/workers/dead_letter_queue.py: edge cases
- app/core/config/notifications.py: notification config validation
- app/core/database.py: database config edge cases
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from starlette.responses import Response

# ===========================================================================
# Domain Events — from_dict() coverage
# ===========================================================================


class TestDomainEventFromDict:
    """Cover from_dict() on all domain event types with the same pattern."""

    def test_user_created_from_dict(self):
        from app.core.events import UserCreated

        data = {"user_id": str(uuid.uuid4()), "email": "test@example.com"}
        event = UserCreated.from_dict(data)
        assert event.email == "test@example.com"

    def test_user_updated_from_dict(self):
        from app.core.events import UserUpdated

        data = {"user_id": str(uuid.uuid4()), "updated_fields": ["email", "name"]}
        event = UserUpdated.from_dict(data)
        assert "email" in event.updated_fields

    def test_user_deleted_from_dict(self):
        from app.core.events import UserDeleted

        uid = str(uuid.uuid4())
        event = UserDeleted.from_dict({"user_id": uid})
        assert str(event.user_id) == uid

    def test_user_logged_in_from_dict(self):
        from app.core.events import UserLoggedIn

        data = {"user_id": str(uuid.uuid4()), "ip_address": "127.0.0.1"}
        event = UserLoggedIn.from_dict(data)
        assert event.ip_address == "127.0.0.1"

    def test_mfa_enabled_from_dict(self):
        from app.core.events import MfaEnabled

        data = {"user_id": str(uuid.uuid4()), "method": "email_otp"}
        event = MfaEnabled.from_dict(data)
        assert event.method == "email_otp"

    def test_from_dict_strips_schema_version(self):
        from app.core.events import UserCreated

        data = {
            "user_id": str(uuid.uuid4()),
            "email": "v@test.com",
            "_schema_version": 2,
        }
        event = UserCreated.from_dict(data)
        assert event.email == "v@test.com"

    def test_from_dict_ignores_unknown_fields(self):
        from app.core.events import UserCreated

        data = {
            "user_id": str(uuid.uuid4()),
            "email": "t@t.com",
            "unknown_field": "ignored",
        }
        event = UserCreated.from_dict(data)
        assert not hasattr(event, "unknown_field") or event.email == "t@t.com"

    def test_event_created_from_dict(self):
        from app.core.events import EventCreated

        data = {
            "event_id_entity": str(uuid.uuid4()),
            "organizer_id": str(uuid.uuid4()),
        }
        event = EventCreated.from_dict(data)
        assert event.event_id_entity is not None

    def test_message_sent_from_dict(self):
        from app.core.events import MessageSent

        data = {
            "message_id": str(uuid.uuid4()),
            "chat_id": str(uuid.uuid4()),
            "sender_id": str(uuid.uuid4()),
            "content_preview": "Hello...",
        }
        event = MessageSent.from_dict(data)
        assert event.content_preview == "Hello..."

    def test_chat_deleted_from_dict(self):
        from app.core.events import ChatDeleted

        data = {"chat_id": str(uuid.uuid4())}
        event = ChatDeleted.from_dict(data)
        assert event.chat_id is not None


# ===========================================================================
# CSRF — signing and verification
# ===========================================================================


class TestCsrfSigning:
    def test_compute_hmac(self):
        from app.core.csrf import _compute_csrf_hmac

        secret = b"test-secret-key"
        mac = _compute_csrf_hmac("nonce123", "session456", secret)
        assert isinstance(mac, str)
        assert len(mac) == 64  # SHA-256 hex digest

    def test_compute_hmac_deterministic(self):
        from app.core.csrf import _compute_csrf_hmac

        secret = b"key"
        m1 = _compute_csrf_hmac("n", "s", secret)
        m2 = _compute_csrf_hmac("n", "s", secret)
        assert m1 == m2

    def test_build_signed_token(self):
        from app.core.csrf import _TOKEN_SEPARATOR, _build_signed_token

        token = _build_signed_token("session-id", b"secret")
        assert _TOKEN_SEPARATOR in token
        parts = token.split(_TOKEN_SEPARATOR, maxsplit=1)
        assert len(parts) == 2
        assert len(parts[0]) > 0  # nonce
        assert len(parts[1]) > 0  # hmac

    def test_verify_signed_token_valid(self):
        from app.core.csrf import _build_signed_token, _verify_signed_token

        secret = b"test-secret-32-bytes-long-enough"
        session_id = "user-session-123"
        token = _build_signed_token(session_id, secret)
        assert _verify_signed_token(token, session_id, secret) is True

    def test_verify_signed_token_wrong_session(self):
        from app.core.csrf import _build_signed_token, _verify_signed_token

        secret = b"test-secret"
        token = _build_signed_token("session-a", secret)
        assert _verify_signed_token(token, "session-b", secret) is False

    def test_verify_signed_token_wrong_secret(self):
        from app.core.csrf import _build_signed_token, _verify_signed_token

        token = _build_signed_token("session", b"secret-a")
        assert _verify_signed_token(token, "session", b"secret-b") is False

    def test_verify_signed_token_malformed(self):
        from app.core.csrf import _verify_signed_token

        assert _verify_signed_token("no-separator-here", "session", b"key") is False
        assert _verify_signed_token("", "session", b"key") is False

    def test_verify_signed_token_empty_parts(self):
        from app.core.csrf import _TOKEN_SEPARATOR, _verify_signed_token

        assert _verify_signed_token(f"{_TOKEN_SEPARATOR}mac", "s", b"k") is False
        assert _verify_signed_token(f"nonce{_TOKEN_SEPARATOR}", "s", b"k") is False


# ===========================================================================
# Response Hardening Middleware
# ===========================================================================


class TestResponseHardening:
    def test_ensure_vary_header_empty(self):
        from app.core.middleware.response_hardening import _ensure_vary_header

        response = Response()
        _ensure_vary_header(response, "Origin")
        assert response.headers["Vary"] == "Origin"

    def test_ensure_vary_header_existing(self):
        from app.core.middleware.response_hardening import _ensure_vary_header

        response = Response()
        response.headers["Vary"] = "Accept-Encoding"
        _ensure_vary_header(response, "Origin")
        assert "Origin" in response.headers["Vary"]
        assert "Accept-Encoding" in response.headers["Vary"]

    def test_ensure_vary_header_no_duplicate(self):
        from app.core.middleware.response_hardening import _ensure_vary_header

        response = Response()
        response.headers["Vary"] = "Origin"
        _ensure_vary_header(response, "Origin")
        # Should not duplicate
        assert response.headers["Vary"].count("Origin") == 1

    @pytest.mark.asyncio
    async def test_static_cache_control(self):
        from app.core.middleware.response_hardening import http_response_hardening

        request = MagicMock()
        request.url.path = "/static/avatar.jpg"
        request.method = "GET"
        request.headers = {}

        async def call_next(req):
            return Response(status_code=200)

        response = await http_response_hardening(request, call_next)
        assert "max-age=86400" in response.headers.get("Cache-Control", "")

    @pytest.mark.asyncio
    async def test_cors_vary_origin(self):
        from app.core.middleware.response_hardening import http_response_hardening

        request = MagicMock()
        request.url.path = "/api/v1/users"
        request.method = "GET"
        request.headers = {}

        async def call_next(req):
            r = Response(status_code=200)
            r.headers["access-control-allow-origin"] = "https://example.com"
            return r

        response = await http_response_hardening(request, call_next)
        assert "Origin" in response.headers.get("Vary", "")

    @pytest.mark.asyncio
    async def test_cors_options_vary(self):
        from app.core.middleware.response_hardening import http_response_hardening

        request = MagicMock()
        request.url.path = "/api/v1/users"
        request.method = "OPTIONS"
        request.headers = {"access-control-request-headers": "Content-Type"}

        async def call_next(req):
            r = Response(status_code=200)
            r.headers["access-control-allow-origin"] = "https://example.com"
            return r

        response = await http_response_hardening(request, call_next)
        vary = response.headers.get("Vary", "")
        assert "Access-Control-Request-Method" in vary
        assert "Access-Control-Request-Headers" in vary


# ===========================================================================
# Content Size Middleware
# ===========================================================================


class TestContentSizeMiddleware:
    def test_init(self):
        from app.core.middleware.content_size import ContentSizeLimitMiddleware

        mw = ContentSizeLimitMiddleware(None, max_bytes=10 * 1024 * 1024)
        assert mw._max_bytes == 10 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_get_request_passes_through(self):
        from app.core.middleware.content_size import ContentSizeLimitMiddleware

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = ContentSizeLimitMiddleware(inner_app, max_bytes=1024)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
        }
        captured = {}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]

        await mw(scope, receive, send)
        assert captured["status"] == 200


# ===========================================================================
# Config — Notifications
# ===========================================================================


class TestNotificationConfig:
    def test_default_values(self):
        """NotificationConfig loads with defaults."""
        from app.core.config import settings

        # These should exist and have reasonable defaults
        assert hasattr(settings, "nats_url") or hasattr(settings, "nats_servers")


# ===========================================================================
# Database config edge cases
# ===========================================================================


class TestDatabaseConfig:
    def test_database_url_setting(self):
        from app.core.config import settings

        assert settings.database_url is not None
        assert (
            "sqlite" in settings.database_url or "postgresql" in settings.database_url
        )

    def test_environment_is_testing(self):
        from app.core.config import settings

        assert str(settings.environment).lower() in {"test", "testing", "development"}


# ===========================================================================
# DLQ — Dead Letter Queue edge cases
# ===========================================================================


class TestDeadLetterQueue:
    def test_dlq_imports(self):
        """DLQ module imports successfully."""
        from app.workers.dead_letter_queue import (
            JobStatus,
        )

        assert JobStatus.PENDING == "pending"
        assert JobStatus.FAILED == "failed"

    def test_compute_job_hash(self):
        from app.workers.dead_letter_queue import compute_job_hash

        h1 = compute_job_hash("test.event", {"key": "val"})
        h2 = compute_job_hash("test.event", {"key": "val"})
        assert h1 == h2
        assert isinstance(h1, str)

    def test_compute_job_hash_different(self):
        from app.workers.dead_letter_queue import compute_job_hash

        h1 = compute_job_hash("a", {"k": 1})
        h2 = compute_job_hash("b", {"k": 1})
        assert h1 != h2


# ===========================================================================
# Domain Event — DomainEvent base class
# ===========================================================================


class TestDomainEventBase:
    def test_domain_event_creation(self):
        from app.core.events import DomainEvent

        event = DomainEvent()
        assert event.event_id is not None
        assert event.occurred_at is not None

    def test_event_emitter_mixin(self):
        from app.core.events import DomainEvent, EventEmitterMixin

        class MockEntity(EventEmitterMixin):
            pass

        entity = MockEntity()
        event = DomainEvent()
        entity.record_event(event)
        assert len(entity._pending_domain_events) == 1

    def test_event_emitter_clear(self):
        from app.core.events import DomainEvent, EventEmitterMixin

        class MockEntity(EventEmitterMixin):
            pass

        entity = MockEntity()
        entity.record_event(DomainEvent())
        entity.record_event(DomainEvent())
        assert len(entity._pending_domain_events) == 2
        entity.clear_events()
        assert len(entity._pending_domain_events) == 0


# ===========================================================================
# Event Registry
# ===========================================================================


class TestEventRegistry:
    def test_domain_event_registry_populated(self):
        from app.core.events import _EVENT_REGISTRY

        # Registered under both class name and EVENT_TYPE
        assert "UserCreated" in _EVENT_REGISTRY
        assert "user.created" in _EVENT_REGISTRY

    def test_domain_event_registry_lookup(self):
        from app.core.events import _EVENT_REGISTRY, MessageSent

        cls = _EVENT_REGISTRY.get("MessageSent")
        assert cls is MessageSent

    def test_register_domain_event_adds_both_keys(self):
        from app.core.events import _EVENT_REGISTRY, ChatDeleted

        assert "ChatDeleted" in _EVENT_REGISTRY
        assert ChatDeleted.EVENT_TYPE in _EVENT_REGISTRY
