"""Targeted closure tests for the final one-branch backend modules."""

import asyncio
import builtins
import importlib
from dataclasses import dataclass
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.responses import Response

from app.core.event_registry import reconstruct_event, register_event
from app.core.events import DomainEvent
from app.core.middleware.response_hardening import http_response_hardening


@register_event
@dataclass
class _ClosureRegisteredEvent(DomainEvent):
    value: str = "default"


def test_event_registry_reconstructs_payload_without_unknown_keys():
    event = reconstruct_event(
        "_ClosureRegisteredEvent",
        {"value": "valid"},
    )

    assert isinstance(event, _ClosureRegisteredEvent)
    assert event.value == "valid"


def test_reset_mfa_audit_without_extra_payload():
    from app.management.reset_mfa import _audit_cli

    with patch("app.management.reset_mfa.audit_logger") as audit_logger:
        _audit_cli("users.mfa.reset", user_id=1, reason="admin_reset")

    audit_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_reset_mfa_changed_without_notification():
    from app.management import reset_mfa

    user = MagicMock(id=1)
    stats = SimpleNamespace(changed=True, totp_deleted=1, challenges_revoked=0)
    session = MagicMock()
    session.get = AsyncMock(return_value=user)
    session.commit = AsyncMock()

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    with (
        patch.object(reset_mfa, "async_session", return_value=SessionContext()),
        patch.object(
            reset_mfa.mfa, "reset_user_mfa", new=AsyncMock(return_value=stats)
        ),
        patch.object(reset_mfa, "_audit_cli") as audit_cli,
    ):
        result_user, result_stats = await reset_mfa._reset_user_mfa(
            user_id=1,
            email=None,
            notify=False,
        )

    assert result_user is user
    assert result_stats is stats
    audit_cli.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_ics_omits_content_language_without_locale():
    import uuid

    from app.routers import schedule

    group_id = uuid.uuid4()
    group = SimpleNamespace(id=group_id, name="Group A")
    db = MagicMock()
    db.get = AsyncMock(return_value=group)
    schedule_service = MagicMock()
    schedule_service.get_schedule = AsyncMock(return_value=[])
    request = MagicMock()

    with (
        patch.object(schedule, "resolve_locale", return_value=None),
        patch.object(schedule, "generate_schedule_ics", return_value="BEGIN:VCALENDAR"),
    ):
        response = await schedule.download_schedule_ics(
            request,
            schedule_service,
            group=group_id,
            db=db,
        )

    assert response.headers.get("content-language") is None


@pytest.mark.asyncio
async def test_notifications_stop_does_not_clear_replaced_scheduler_task():
    import app.workers.notifications as workers

    workers._scheduler_task = None
    stop = await workers.start_notifications_scheduler(
        poll_seconds=60,
        window_minutes=5,
        max_backoff_seconds=1,
    )
    replacement = asyncio.create_task(asyncio.sleep(60))
    workers._scheduler_task = replacement

    await stop()
    assert workers._scheduler_task is replacement

    replacement.cancel()
    with pytest.raises(asyncio.CancelledError):
        await replacement
    workers._scheduler_task = None


def test_redis_circuit_breaker_deduplicates_and_contains_sync_listener_errors():
    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker

    breaker = RedisCircuitBreaker(failure_threshold=1)
    listener = MagicMock(side_effect=RuntimeError("listener failed"))
    breaker.add_state_listener(listener)
    breaker.add_state_listener(listener)

    breaker._transition(CircuitState.CLOSED, CircuitState.OPEN)

    listener.assert_called_once_with(CircuitState.CLOSED, CircuitState.OPEN)
    assert len(breaker._state_listeners) == 1


def test_redis_circuit_breaker_accepts_sync_listener_without_result():
    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker

    breaker = RedisCircuitBreaker(failure_threshold=1)
    listener = MagicMock(return_value=None)
    breaker.add_state_listener(listener)

    breaker._transition(CircuitState.CLOSED, CircuitState.OPEN)

    listener.assert_called_once_with(CircuitState.CLOSED, CircuitState.OPEN)


@pytest.mark.asyncio
async def test_redis_circuit_breaker_schedules_async_listener():
    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker

    breaker = RedisCircuitBreaker(failure_threshold=1)
    listener = AsyncMock()
    breaker.add_state_listener(listener)

    breaker._transition(CircuitState.CLOSED, CircuitState.OPEN)
    await asyncio.sleep(0)

    listener.assert_awaited_once_with(CircuitState.CLOSED, CircuitState.OPEN)


def test_redis_circuit_breaker_runs_async_listener_without_loop():
    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker

    breaker = RedisCircuitBreaker(failure_threshold=1)
    listener = AsyncMock()
    breaker.add_state_listener(listener)

    breaker._transition(CircuitState.CLOSED, CircuitState.OPEN)

    listener.assert_awaited_once_with(CircuitState.CLOSED, CircuitState.OPEN)


@pytest.mark.asyncio
async def test_response_hardening_options_without_requested_headers():
    request = MagicMock()
    request.url.path = "/api/v1/health"
    request.method = "OPTIONS"
    request.headers = {}

    async def call_next(_request):
        response = Response(status_code=200)
        response.headers["access-control-allow-origin"] = "https://example.com"
        return response

    response = await http_response_hardening(request, call_next)

    vary = response.headers["Vary"]
    assert "Origin" in vary
    assert "Access-Control-Request-Method" in vary
    assert "Access-Control-Request-Headers" not in vary


def test_middleware_setup_handles_missing_proxy_headers_dependency(monkeypatch):
    setup = importlib.import_module("app.core.middleware.setup")
    original_import = builtins.__import__

    def fail_proxy_headers_import(name, *args, **kwargs):
        if name == "uvicorn.middleware.proxy_headers":
            raise ImportError("proxy headers unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_proxy_headers_import)
    reloaded = importlib.reload(setup)
    try:
        assert reloaded.ProxyHeadersMiddleware is None
    finally:
        importlib.reload(setup)


def test_middleware_setup_skips_endpoint_when_parser_returns_none(monkeypatch):
    from tests.test_middleware_setup import _make_settings

    setup = importlib.import_module("app.core.middleware.setup")
    app = FastAPI()
    settings = _make_settings(rate_limit_enabled=True, rate_limit_news="1/minute")

    def parse_rate_limit(value, *, fallback):
        if value == "1/minute":
            return None, 0
        return 60, 60

    monkeypatch.setattr(setup, "parse_rate_limit", parse_rate_limit)
    setup._configure_rate_limiting(app, settings)

    middleware = next(
        entry
        for entry in app.user_middleware
        if entry.cls.__name__ == "RateLimitMiddleware"
    )
    assert middleware.kwargs["endpoint_limits"] == ()


@pytest.mark.asyncio
async def test_graphql_context_ignores_bearer_payload_without_jti():
    from app.graphql.schema import get_context

    request = MagicMock()
    request.app.dependency_overrides = {}
    request.state.dishka_container.get = AsyncMock(return_value=MagicMock())
    request.headers = {"Authorization": "Bearer token-without-jti"}

    with (
        patch("app.auth.security.decode_token", return_value={"sub": "user-123"}),
        patch(
            "app.services.auth.graphql_token_validator.GraphQLTokenValidator.validate"
        ) as validate,
    ):
        async for context in get_context(request):
            assert context.current_user is None
        validate.assert_not_called()


def test_minio_client_double_checked_lock_returns_racing_instance(monkeypatch):
    import app.services.minio_storage as minio_module

    sentinel = object()

    class RacingLock:
        def __enter__(self):
            minio_module._minio_client = sentinel  # type: ignore[assignment]
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(minio_module, "_minio_client", None)
    monkeypatch.setattr(minio_module, "_minio_client_lock", RacingLock())

    assert minio_module.get_minio_client() is sentinel


def test_push_topics_resolves_settings_when_allowed_topics_omitted(monkeypatch):
    from app.services import push_topics as topics

    configured = SimpleNamespace(
        notifications_allowed_push_topics_list=["News", "alerts"],
        notifications_allowed_push_topics_set=frozenset({"news", "alerts"}),
    )

    assert topics.get_allowed_topics(configured) == ["News", "alerts"]
    assert topics.normalize_topic("NEWS", settings_obj=configured) == "news"

    class User:
        push_topic_preferences = SimpleNamespace(topics=["news"])

    subscription = MagicMock()
    subscription.user = User()
    subscription.topics = None
    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.instance_state",
        lambda _user: (_ for _ in ()).throw(TypeError("detached")),
    )

    assert topics.subscription_supports_topic(
        subscription,
        "news",
        settings_obj=configured,
    )


def test_push_topics_treats_unloaded_preferences_as_unavailable(monkeypatch):
    from app.services import push_topics as topics

    class User:
        push_topic_preferences = SimpleNamespace(topics=["news"])

    class State:
        unloaded: ClassVar[set[str]] = {"push_topic_preferences"}

    subscription = MagicMock()
    subscription.user = User()
    subscription.topics = None
    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.instance_state",
        lambda _user: State(),
    )

    assert topics.subscription_supports_topic(
        subscription,
        "news",
        allowed_topics=["news"],
    )


@pytest.mark.asyncio
async def test_paginate_cursor_skips_filter_when_cursor_decodes_empty():
    from app.utils.pagination import CursorParams, paginate_cursor

    session = AsyncMock()
    stmt = MagicMock()
    stmt.order_by.return_value = stmt
    stmt.limit.return_value = stmt
    cursor_column = MagicMock()
    cursor_column.desc.return_value = cursor_column
    cursor_column.key = "id"
    scalars = MagicMock()
    scalars.all.return_value = []
    session.scalars.return_value = scalars

    await paginate_cursor(
        session,
        stmt,
        cursor_column,
        CursorParams(cursor="not-a-valid-cursor", limit=10),
    )

    stmt.where.assert_not_called()


@pytest.fixture
def standalone_ws_client(monkeypatch):
    import app.services.ws_hub_client as module

    broker = AsyncMock()
    monkeypatch.setattr(
        "app.core.config.settings", MagicMock(ws_hub_internal_secret="secret")
    )
    monkeypatch.setattr("app.core.nats_broker.broker", broker)
    return module.WsHubClient(), broker


@pytest.mark.asyncio
async def test_ws_hub_control_event_retries_then_succeeds(
    standalone_ws_client, monkeypatch
):
    client, broker = standalone_ws_client
    broker.publish.side_effect = [ConnectionError("temporary"), None]
    monkeypatch.setattr("app.services.ws_hub_client.asyncio.sleep", AsyncMock())

    await client.publish_control_event("user-1", action="logout", reason="test")

    assert broker.publish.call_count == 2
    assert broker.publish.call_args_list[-1].args[0] == "ws_hub.control"


@pytest.mark.asyncio
async def test_ws_hub_control_event_records_final_failure(
    standalone_ws_client, monkeypatch
):
    import app.services.ws_hub_client as module

    client, broker = standalone_ws_client
    broker.publish.side_effect = ConnectionError("down")
    monkeypatch.setattr("app.services.ws_hub_client.asyncio.sleep", AsyncMock())
    counter = MagicMock()
    monkeypatch.setattr(module, "_INVALIDATION_FAILURES", counter)

    await client.publish_control_event("user-1")

    assert broker.publish.call_count == 2
    counter.inc.assert_called_once()


def test_ws_hub_client_double_checked_lock_returns_racing_instance(monkeypatch):
    import app.services.ws_hub_client as module

    sentinel = object()

    class RacingLock:
        def __enter__(self):
            module._client = sentinel  # type: ignore[assignment]
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(module, "_client", None)
    monkeypatch.setattr(module, "_client_lock", RacingLock())

    assert module._get_client() is sentinel


@pytest.mark.asyncio
async def test_ws_hub_control_wrapper_delegates(monkeypatch):
    from app.services import ws_hub_client as module

    client = AsyncMock()
    monkeypatch.setattr(module, "_get_client", lambda: client)

    await module.publish_ws_hub_control("user-1", action="logout", reason="test")

    client.publish_control_event.assert_awaited_once_with(
        user_id="user-1",
        action="logout",
        reason="test",
    )
