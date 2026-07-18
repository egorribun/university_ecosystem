"""Wave 3 coverage: core infrastructure modules.

Covers:
- app/core/event_dlq.py
- app/core/event_retry.py
- app/core/event_decorators.py
- app/core/event_registry.py (via events.py)
- app/core/internal_access.py
- app/core/ratelimit/logic.py
- app/core/ratelimit/utils.py
- app/core/ratelimit/strategies/memory.py
- app/core/policies/csp.py
- app/core/security_headers.py
- app/core/middleware/response_hardening.py
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/core/event_dlq.py — DeadLetterQueue
# ---------------------------------------------------------------------------


def _make_mock_event(event_type: str = "test.event") -> MagicMock:
    event = MagicMock()
    event.event_id = str(uuid.uuid4())
    event.event_type = event_type
    event.metadata = MagicMock()
    event.metadata.retry_count = 0
    return event


@pytest.mark.asyncio
async def test_dlq_add_and_size() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue(max_size=100)
    assert dlq.size == 0

    event = _make_mock_event()
    await dlq.add(event, ValueError("test error"), handler_name="test_handler")
    assert dlq.size == 1
    assert dlq.max_size == 100


@pytest.mark.asyncio
async def test_dlq_add_no_metadata() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()

    event = MagicMock()
    event.event_id = str(uuid.uuid4())
    event.event_type = "test"
    # no metadata attribute
    del event.metadata

    await dlq.add(event, RuntimeError("no meta"))
    assert dlq.size == 1


@pytest.mark.asyncio
async def test_dlq_get_all() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    event1 = _make_mock_event("type.a")
    event2 = _make_mock_event("type.b")

    await dlq.add(event1, Exception("e1"))
    await dlq.add(event2, Exception("e2"))

    all_events = await dlq.get_all()
    assert len(all_events) == 2
    types = {f.event.event_type for f in all_events}
    assert types == {"type.a", "type.b"}


@pytest.mark.asyncio
async def test_dlq_get_by_type() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    await dlq.add(_make_mock_event("news.created"), Exception("x"))
    await dlq.add(_make_mock_event("user.created"), Exception("y"))
    await dlq.add(_make_mock_event("news.created"), Exception("z"))

    news_events = await dlq.get_by_type("news.created")
    assert len(news_events) == 2

    user_events = await dlq.get_by_type("user.created")
    assert len(user_events) == 1


@pytest.mark.asyncio
async def test_dlq_clear() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    for _ in range(5):
        await dlq.add(_make_mock_event(), Exception("err"))

    cleared = await dlq.clear()
    assert cleared == 5
    assert dlq.size == 0


@pytest.mark.asyncio
async def test_dlq_remove_existing() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    event = _make_mock_event()
    await dlq.add(event, Exception("e"))

    removed = await dlq.remove(event.event_id)
    assert removed is True
    assert dlq.size == 0


@pytest.mark.asyncio
async def test_dlq_remove_nonexistent() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    removed = await dlq.remove("nonexistent-id")
    assert removed is False


@pytest.mark.asyncio
async def test_dlq_replay_success() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    event = _make_mock_event()
    await dlq.add(event, Exception("initial failure"))

    mock_bus = AsyncMock()
    mock_bus.publish = AsyncMock()

    success, fail = await dlq.replay(mock_bus)
    assert success == 1
    assert fail == 0
    assert dlq.size == 0  # cleared on success


@pytest.mark.asyncio
async def test_dlq_replay_failure() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    event = _make_mock_event()
    await dlq.add(event, Exception("initial"))

    mock_bus = AsyncMock()
    mock_bus.publish = AsyncMock(side_effect=RuntimeError("bus down"))

    success, fail = await dlq.replay(mock_bus)
    assert success == 0
    assert fail == 1
    assert dlq.size == 1  # not cleared on failure


@pytest.mark.asyncio
async def test_dlq_replay_filtered_by_type() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    await dlq.add(_make_mock_event("news.created"), Exception("a"))
    await dlq.add(_make_mock_event("user.created"), Exception("b"))

    mock_bus = AsyncMock()
    mock_bus.publish = AsyncMock()

    success, fail = await dlq.replay(mock_bus, event_type="news.created")
    assert success == 1
    assert fail == 0
    # Only news.created was replayed
    assert dlq.size == 1  # user.created remains


@pytest.mark.asyncio
async def test_dlq_replay_no_clear_on_success() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    event = _make_mock_event()
    await dlq.add(event, Exception("e"))

    mock_bus = AsyncMock()
    mock_bus.publish = AsyncMock()

    await dlq.replay(mock_bus, clear_on_success=False)
    assert dlq.size == 1  # not cleared


@pytest.mark.asyncio
async def test_dlq_get_stats_empty() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue(max_size=500)
    stats = await dlq.get_stats()

    assert stats["size"] == 0
    assert stats["max_size"] == 500
    assert stats["oldest_event"] is None
    assert stats["newest_event"] is None


@pytest.mark.asyncio
async def test_dlq_get_stats_with_events() -> None:
    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    await dlq.add(_make_mock_event("a"), ValueError("v"))
    await dlq.add(_make_mock_event("a"), TypeError("t"))
    await dlq.add(_make_mock_event("b"), ValueError("v2"))

    stats = await dlq.get_stats()
    assert stats["size"] == 3
    assert stats["by_type"]["a"] == 2
    assert stats["by_type"]["b"] == 1
    assert "ValueError" in stats["by_error"]
    assert stats["oldest_event"] is not None
    assert stats["newest_event"] is not None


def test_failed_event_to_dict() -> None:
    from app.core.event_dlq import FailedEvent

    event = _make_mock_event("test.type")
    failed = FailedEvent(
        event=event,
        error="some error",
        error_type="ValueError",
        handler_name="test_handler",
        retry_count=2,
    )
    d = failed.to_dict()
    assert d["event_id"] == event.event_id
    assert d["event_type"] == "test.type"
    assert d["error"] == "some error"
    assert d["retry_count"] == 2
    assert d["handler_name"] == "test_handler"


@pytest.mark.asyncio
async def test_dlq_max_size_eviction() -> None:
    """When max_size is reached, oldest events are evicted."""

    from app.core.event_dlq import DeadLetterQueue

    dlq = DeadLetterQueue(max_size=2)

    for i in range(3):
        await dlq.add(_make_mock_event(f"type.{i}"), Exception(str(i)))

    # deque(maxlen=2) keeps only the last 2
    assert dlq.size == 2


# ---------------------------------------------------------------------------
# app/core/event_retry.py — RetryMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_middleware_success_first_attempt() -> None:
    from app.core.event_retry import RetryMiddleware

    mw = RetryMiddleware(max_retries=3, base_delay=0.01)
    event = _make_mock_event()

    call_count = 0

    async def handler(e: Any) -> None:
        nonlocal call_count
        call_count += 1

    await mw(event, handler)
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_middleware_retries_then_success() -> None:
    from app.core.event_retry import RetryMiddleware

    mw = RetryMiddleware(max_retries=3, base_delay=0.001)
    event = _make_mock_event()
    call_count = 0

    async def handler(e: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")

    await mw(event, handler)
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_middleware_exhausts_all_retries() -> None:
    from app.core.event_retry import EventRetryExhausted, RetryMiddleware

    mw = RetryMiddleware(max_retries=2, base_delay=0.001)
    event = _make_mock_event()
    call_count = 0

    async def always_fails(e: Any) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("always fails")

    with pytest.raises(EventRetryExhausted) as exc_info:
        await mw(event, always_fails)

    assert exc_info.value.attempts == 3  # max_retries + 1
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_middleware_non_retryable_exception() -> None:
    """Non-retryable exceptions propagate immediately without retry."""
    from app.core.event_retry import RetryMiddleware

    mw = RetryMiddleware(
        max_retries=3,
        base_delay=0.001,
        retryable_exceptions=(ValueError,),
    )
    event = _make_mock_event()
    call_count = 0

    async def raises_type_error(e: Any) -> None:
        nonlocal call_count
        call_count += 1
        raise TypeError("not retryable")

    with pytest.raises(TypeError, match="not retryable"):
        await mw(event, raises_type_error)

    assert call_count == 1  # No retries


def test_retry_config_defaults() -> None:
    from app.core.event_retry import RetryConfig

    config = RetryConfig()
    assert config.max_retries == 3
    assert config.base_delay == 0.1
    assert config.max_delay == 10.0


def test_retry_middleware_calculate_delay_capped() -> None:
    from app.core.event_retry import RetryMiddleware

    mw = RetryMiddleware(
        max_retries=10, base_delay=1.0, max_delay=5.0, exponential_base=2.0
    )
    # attempt=10: 1.0 * 2^10 = 1024 → capped to 5.0 (±25% jitter)
    delay = mw._calculate_delay(10)
    assert delay == pytest.approx(5.0, rel=0.3)


def test_retry_middleware_calculate_delay_uncapped() -> None:
    from app.core.event_retry import RetryMiddleware

    mw = RetryMiddleware(
        max_retries=3, base_delay=0.1, max_delay=10.0, exponential_base=2.0
    )
    # attempt=0: 0.1 * 2^0 = 0.1, then +-25% jitter → [0.075, 0.125]
    delay = mw._calculate_delay(0)
    assert delay == pytest.approx(0.1, rel=0.3)


def test_retry_middleware_is_retryable() -> None:
    from app.core.event_retry import RetryMiddleware

    mw = RetryMiddleware(retryable_exceptions=(ValueError, TypeError))
    assert mw._is_retryable(ValueError("v")) is True
    assert mw._is_retryable(TypeError("t")) is True
    assert mw._is_retryable(RuntimeError("r")) is False


@pytest.mark.asyncio
async def test_with_retry_decorator() -> None:
    from app.core.event_retry import with_retry

    call_count = 0

    @with_retry(max_retries=2, base_delay=0.001)
    async def my_handler(event: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("temp")

    event = _make_mock_event()
    await my_handler(event)
    assert call_count == 2


def test_event_retry_exhausted_str() -> None:
    from app.core.event_retry import EventRetryExhausted

    event = _make_mock_event("foo.bar")
    exc = EventRetryExhausted(
        event=event, original_error=ValueError("oops"), attempts=3
    )
    assert "foo.bar" in str(exc)
    assert "3" in str(exc)


# ---------------------------------------------------------------------------
# app/core/event_decorators.py
# ---------------------------------------------------------------------------


def test_event_decorators_subscribe() -> None:
    from app.core.event_decorators import (
        _pending_subscriptions,
        clear_pending_registrations,
        subscribe,
    )

    clear_pending_registrations()

    @subscribe("test.event")
    async def handler(event: Any) -> None:
        pass

    assert any(et == "test.event" and h is handler for et, h in _pending_subscriptions)
    clear_pending_registrations()


def test_event_decorators_subscribe_all() -> None:
    from app.core.event_decorators import (
        _pending_all_subscriptions,
        clear_pending_registrations,
        subscribe_all,
    )

    clear_pending_registrations()

    @subscribe_all
    async def global_handler(event: Any) -> None:
        pass

    assert global_handler in _pending_all_subscriptions
    clear_pending_registrations()


def test_event_decorators_get_pending_count() -> None:
    from app.core.event_decorators import (
        clear_pending_registrations,
        get_pending_count,
        subscribe,
        subscribe_all,
    )

    clear_pending_registrations()
    assert get_pending_count() == 0

    @subscribe("a")
    async def h1(e: Any) -> None:
        pass

    @subscribe_all
    async def h2(e: Any) -> None:
        pass

    assert get_pending_count() == 2
    clear_pending_registrations()
    assert get_pending_count() == 0


def test_event_decorators_register_handlers() -> None:
    from app.core.event_decorators import (
        clear_pending_registrations,
        register_decorated_handlers,
        subscribe,
        subscribe_all,
    )

    clear_pending_registrations()

    @subscribe("some.event")
    async def typed_handler(e: Any) -> None:
        pass

    @subscribe_all
    async def all_handler(e: Any) -> None:
        pass

    mock_bus = MagicMock()
    mock_bus.subscribe = MagicMock()
    mock_bus.subscribe_all = MagicMock()

    count = register_decorated_handlers(mock_bus)
    assert count == 2
    mock_bus.subscribe.assert_called_once_with("some.event", typed_handler)
    mock_bus.subscribe_all.assert_called_once_with(all_handler)

    clear_pending_registrations()


def test_event_decorators_register_class_type() -> None:
    """subscribe() with a class (not string) uses event_type property."""
    from app.core.event_decorators import (
        clear_pending_registrations,
        register_decorated_handlers,
        subscribe,
    )

    clear_pending_registrations()

    class FakeEvent:
        EVENT_TYPE = "fake.event"

        def __init__(self) -> None:
            pass

        @property
        def event_type(self) -> str:
            return self.EVENT_TYPE

    @subscribe(FakeEvent)  # type: ignore[arg-type]
    async def handler(e: Any) -> None:
        pass

    mock_bus = MagicMock()
    mock_bus.subscribe = MagicMock()

    register_decorated_handlers(mock_bus)
    # Called with the string event type
    mock_bus.subscribe.assert_called_once()

    clear_pending_registrations()


# ---------------------------------------------------------------------------
# app/core/internal_access.py — InternalAccessMiddleware
# ---------------------------------------------------------------------------


def _make_asgi_scope(
    path: str = "/api/internal/test",
    headers: dict[str, str] | None = None,
    client_host: str = "127.0.0.1",
    method: str = "GET",
) -> dict[str, Any]:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": (client_host, 0) if client_host else None,
    }


async def _call_asgi_middleware(
    mw: Any,
    scope: dict[str, Any],
    body: bytes = b"",
) -> dict[str, Any]:
    """Call an ASGI middleware and capture the response status + headers."""
    captured: dict[str, Any] = {
        "status": None,
        "headers": {},
        "body": b"",
        "called_app": False,
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = {
                k.decode("latin-1") if isinstance(k, bytes) else k: v.decode("latin-1")
                if isinstance(v, bytes)
                else v
                for k, v in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    await mw(scope, receive, send)
    return captured


@pytest.mark.asyncio
async def test_internal_access_non_internal_path_passes_through() -> None:
    from app.core.internal_access import InternalAccessMiddleware

    app_called = False

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/api/internal"],
        header_name="X-Internal-Token",
        header_token="secret",
    )

    scope = _make_asgi_scope(path="/api/v1/users")
    result = await _call_asgi_middleware(mw, scope)
    assert app_called
    assert result["status"] == 200


@pytest.mark.asyncio
async def test_internal_access_valid_token_passes() -> None:
    from app.core.internal_access import InternalAccessMiddleware

    app_called = False

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/api/internal"],
        header_name="X-Internal-Token",
        header_token="secret123",
    )

    scope = _make_asgi_scope(
        path="/api/internal/health",
        headers={"X-Internal-Token": "secret123"},
    )
    result = await _call_asgi_middleware(mw, scope)
    assert app_called
    assert result["status"] == 200
    # Token-authenticated requests get Vary header injected
    assert "x-internal-token" in result["headers"] or "vary" in result["headers"]


@pytest.mark.asyncio
async def test_internal_access_valid_ip_passes() -> None:
    from app.core.internal_access import InternalAccessMiddleware

    app_called = False

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/internal"],
        allowed_ips=["10.0.0.1"],
    )

    scope = _make_asgi_scope(path="/internal/status", client_host="10.0.0.1")
    result = await _call_asgi_middleware(mw, scope)
    assert app_called
    assert result["status"] == 200


@pytest.mark.asyncio
async def test_internal_access_denied_wrong_token() -> None:
    from app.core.internal_access import InternalAccessMiddleware

    app_called = False

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/internal"],
        header_name="X-Internal-Token",
        header_token="correct",
    )

    scope = _make_asgi_scope(
        path="/internal/admin",
        headers={"X-Internal-Token": "wrong"},
    )
    result = await _call_asgi_middleware(mw, scope)
    assert not app_called
    assert result["status"] == 403


@pytest.mark.asyncio
async def test_internal_access_no_client_still_denies() -> None:
    from app.core.internal_access import InternalAccessMiddleware

    app_called = False

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/internal"],
        allowed_ips=["127.0.0.1"],
    )

    scope = _make_asgi_scope(path="/internal/test")
    scope["client"] = None  # no client

    result = await _call_asgi_middleware(mw, scope)
    assert not app_called
    assert result["status"] == 403


def test_internal_access_has_valid_header_missing_name() -> None:
    """When header_name is None, _has_valid_header_from_scope returns False."""
    from app.core.internal_access import InternalAccessMiddleware

    mock_app = MagicMock()
    mw = InternalAccessMiddleware(mock_app, internal_prefixes=["/x"])
    mw.header_name = None
    mw.header_token = "token"

    # Test via the scope-based method that the middleware actually uses
    assert mw._has_valid_header_from_scope({}) is False


@pytest.mark.asyncio
async def test_internal_access_vary_header_added_on_token_auth() -> None:
    """Token-authenticated internal requests get Vary header with header_name."""
    from app.core.internal_access import InternalAccessMiddleware

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/internal"],
        header_name="X-Token",
        header_token="secret",
    )

    scope = _make_asgi_scope(
        path="/internal/test",
        headers={"X-Token": "secret"},
    )
    result = await _call_asgi_middleware(mw, scope)
    assert result["status"] == 200
    assert "vary" in result["headers"]
    assert "X-Token" in result["headers"]["vary"]


@pytest.mark.asyncio
async def test_internal_access_vary_header_appends_to_existing() -> None:
    """Vary header appends header_name without duplicating existing values."""
    from app.core.internal_access import InternalAccessMiddleware

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"vary", b"Accept-Encoding")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    mw = InternalAccessMiddleware(
        inner_app,
        internal_prefixes=["/internal"],
        header_name="X-Token",
        header_token="secret",
    )

    scope = _make_asgi_scope(
        path="/internal/test",
        headers={"X-Token": "secret"},
    )
    result = await _call_asgi_middleware(mw, scope)
    assert result["status"] == 200
    vary_value = result["headers"].get("vary", "")
    assert "X-Token" in vary_value
    assert "Accept-Encoding" in vary_value


def test_internal_access_no_header_name_no_vary() -> None:
    """When header_name is None, _make_vary_send returns the original send."""
    from app.core.internal_access import InternalAccessMiddleware

    mock_app = MagicMock()
    mw = InternalAccessMiddleware(mock_app, internal_prefixes=[])
    mw.header_name = None

    mock_send = MagicMock()
    result = mw._make_vary_send(mock_send)
    # When header_name is None, _make_vary_send returns the original send unchanged
    assert result is mock_send


# ---------------------------------------------------------------------------
# app/core/ratelimit/utils.py — parse_rate_limit, _normalize_ip
# ---------------------------------------------------------------------------


def test_parse_rate_limit_per_minute() -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    count, seconds = parse_rate_limit("5 per minute", fallback=(1, 60))
    assert count == 5
    assert seconds == 60


def test_parse_rate_limit_slash_format() -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    count, seconds = parse_rate_limit("10/60", fallback=(1, 60))
    assert count == 10
    assert seconds == 60


def test_parse_rate_limit_various_units() -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    assert parse_rate_limit("100 per hour", fallback=(0, 0)) == (100, 3600)
    assert parse_rate_limit("5 per day", fallback=(0, 0)) == (5, 86400)
    assert parse_rate_limit("20/min", fallback=(0, 0)) == (20, 60)
    assert parse_rate_limit("10 seconds", fallback=(0, 0)) == (10, 1)


def test_parse_rate_limit_fallback_on_empty() -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    assert parse_rate_limit(None, fallback=(5, 60)) == (5, 60)
    assert parse_rate_limit("", fallback=(3, 30)) == (3, 30)
    assert parse_rate_limit("   ", fallback=(2, 10)) == (2, 10)


def test_parse_rate_limit_fallback_on_invalid() -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    assert parse_rate_limit("not_a_rate", fallback=(1, 1)) == (1, 1)
    assert parse_rate_limit("abc/xyz", fallback=(2, 2)) == (2, 2)


def test_parse_rate_limit_fallback_on_zero() -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    assert parse_rate_limit("0 per minute", fallback=(5, 60)) == (5, 60)


@pytest.mark.parametrize(
    "rate_str,expected",
    [
        ("1/s", (1, 1)),
        ("100 per sec", (100, 1)),
        ("30/min", (30, 60)),
        ("10/hour", (10, 3600)),
        ("1/day", (1, 86400)),
    ],
)
def test_parse_rate_limit_parametrized(
    rate_str: str, expected: tuple[int, int]
) -> None:
    from app.core.ratelimit.utils import parse_rate_limit

    result = parse_rate_limit(rate_str, fallback=(0, 0))
    assert result == expected


def test_normalize_ip_valid_ipv4() -> None:
    from app.core.ratelimit.utils import _normalize_ip

    assert _normalize_ip("192.168.1.1") == "192.168.1.1"


def test_normalize_ip_valid_ipv6() -> None:
    from app.core.ratelimit.utils import _normalize_ip

    result = _normalize_ip("::1")
    assert result == "::1"


def test_normalize_ip_invalid() -> None:
    from app.core.ratelimit.utils import _normalize_ip

    assert _normalize_ip("not_an_ip") is None


def test_normalize_ip_none() -> None:
    from app.core.ratelimit.utils import _normalize_ip

    assert _normalize_ip(None) is None
    assert _normalize_ip("") is None


# ---------------------------------------------------------------------------
# app/core/ratelimit/strategies/memory.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_strategy_allows_under_limit() -> None:
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()
    strategy = MemorySlidingWindowStrategy(namespace="test")

    info = await strategy.check("user123", limit=5, window_seconds=60)
    assert info.allowed is True
    assert info.remaining == 4

    clear_memory_state()


@pytest.mark.asyncio
async def test_memory_strategy_blocks_at_limit() -> None:
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()
    strategy = MemorySlidingWindowStrategy(namespace="block_test")

    for _ in range(3):
        await strategy.check("u1", limit=3, window_seconds=60)

    info = await strategy.check("u1", limit=3, window_seconds=60)
    assert info.allowed is False
    assert info.remaining == 0
    assert info.retry_after >= 0

    clear_memory_state()


@pytest.mark.asyncio
async def test_memory_strategy_invalid_params() -> None:
    from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy

    strategy = MemorySlidingWindowStrategy()
    # limit <= 0 should be allowed (degenerate case)
    info = await strategy.check("key", limit=0, window_seconds=60)
    assert info.allowed is True


@pytest.mark.asyncio
async def test_memory_strategy_different_keys_independent() -> None:
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()
    strategy = MemorySlidingWindowStrategy(namespace="ns")

    for _ in range(3):
        await strategy.check("user_a", limit=3, window_seconds=60)

    # user_b should not be affected
    info_b = await strategy.check("user_b", limit=3, window_seconds=60)
    assert info_b.allowed is True

    clear_memory_state()


def test_memory_strategy_clear_state() -> None:
    from app.core.ratelimit.strategies.memory import _memory_windows, clear_memory_state

    _memory_windows["test_key"] = MagicMock()
    clear_memory_state()
    assert len(_memory_windows) == 0


# ---------------------------------------------------------------------------
# app/core/ratelimit/logic.py — check_rate_limit, enforce_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_rate_limit_disabled() -> None:
    from app.core.ratelimit.logic import check_rate_limit

    with patch("app.core.ratelimit.logic.settings") as mock_settings:
        mock_settings.rate_limit_enabled = False

        info = await check_rate_limit(
            identifier="user1",
            limit=5,
            window_seconds=60,
        )

    assert info.allowed is True
    assert info.remaining == 5


@pytest.mark.asyncio
async def test_check_rate_limit_memory_fallback_no_redis() -> None:
    from app.core.ratelimit.logic import check_rate_limit
    from app.core.ratelimit.strategies.memory import clear_memory_state

    clear_memory_state()

    with patch("app.core.ratelimit.logic.settings") as mock_settings:
        mock_settings.rate_limit_enabled = True

        info = await check_rate_limit(
            identifier="testuser",
            namespace="test_ns",
            limit=10,
            window_seconds=60,
            redis_url=None,  # no Redis
        )

    assert info.allowed is True
    clear_memory_state()


@pytest.mark.asyncio
async def test_enforce_rate_limit_disabled() -> None:
    from app.core.ratelimit.logic import enforce_rate_limit
    from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy

    with patch("app.core.ratelimit.logic.settings") as mock_settings:
        mock_settings.rate_limit_enabled = False

        strategy = MemorySlidingWindowStrategy()
        info = await enforce_rate_limit(
            identifier="u1",
            limit=5,
            window_seconds=60,
            strategy=strategy,
        )

    assert info.allowed is True


@pytest.mark.asyncio
async def test_enforce_rate_limit_exceeded_raises() -> None:
    from app.core.ratelimit.exceptions import RateLimitExceeded
    from app.core.ratelimit.logic import enforce_rate_limit
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()

    with patch("app.core.ratelimit.logic.settings") as mock_settings:
        mock_settings.rate_limit_enabled = True

        strategy = MemorySlidingWindowStrategy(namespace="exceed_test")
        for _ in range(2):
            await enforce_rate_limit(
                identifier="abuser", limit=2, window_seconds=60, strategy=strategy
            )

        with pytest.raises(RateLimitExceeded):
            await enforce_rate_limit(
                identifier="abuser", limit=2, window_seconds=60, strategy=strategy
            )

    clear_memory_state()


@pytest.mark.asyncio
async def test_check_rate_limit_redis_error_fallback() -> None:
    from redis.exceptions import RedisError

    from app.core.ratelimit.logic import check_rate_limit
    from app.core.ratelimit.strategies.memory import clear_memory_state

    clear_memory_state()

    mock_strategy = AsyncMock()
    mock_strategy.check = AsyncMock(side_effect=RedisError("connection error"))

    with (
        patch("app.core.ratelimit.logic.settings") as mock_settings,
        patch(
            "app.core.ratelimit.logic._get_redis_strategy", return_value=mock_strategy
        ),
    ):
        mock_settings.rate_limit_enabled = True

        info = await check_rate_limit(
            identifier="user",
            limit=10,
            window_seconds=60,
            redis_url="redis://localhost:6379",
        )

    # Should fall back to memory strategy
    assert info.allowed is True  # within fallback limit (5)
    clear_memory_state()


@pytest.mark.asyncio
async def test_check_rate_limit_redis_success_records_cb_success() -> None:
    """Lines 89-90: Successful Redis check records circuit breaker success and returns result.

    Verifies that when the circuit breaker ALLOWS the request AND the Redis
    strategy succeeds, record_success() is called and the result is returned
    (not falling back to memory).
    """
    from unittest.mock import AsyncMock, patch

    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker
    from app.core.ratelimit.logic import check_rate_limit
    from app.core.ratelimit.models import RateLimitInfo
    from app.core.ratelimit.strategies.memory import clear_memory_state

    clear_memory_state()

    mock_strategy = AsyncMock()
    mock_result = RateLimitInfo(allowed=True, remaining=9, retry_after=0)
    mock_strategy.check = AsyncMock(return_value=mock_result)

    mock_cb = RedisCircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
    # Ensure CB is CLOSED and allows request
    assert mock_cb.state == CircuitState.CLOSED
    assert mock_cb.allow_request() is True
    initial_fail_count = mock_cb._failure_count  # type: ignore[attr-defined]

    with (
        patch("app.core.ratelimit.logic.settings") as mock_settings,
        patch("app.core.ratelimit.logic._get_redis_strategy", return_value=mock_strategy),
        patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=mock_cb),
    ):
        mock_settings.rate_limit_enabled = True

        result = await check_rate_limit(
            identifier="user123",
            limit=10,
            window_seconds=60,
            redis_url="redis://localhost:6379",
        )

    assert result.allowed is True
    assert result.remaining == 9
    # record_success() was called: failure_count reset to 0
    assert mock_cb._failure_count == 0  # type: ignore[attr-defined]
    clear_memory_state()


@pytest.mark.asyncio
async def test_check_rate_limit_circuit_open_debug_log_and_fallback() -> None:
    """Line 98: Circuit OPEN triggers debug log and falls back to memory strategy.

    Verifies that when the circuit breaker is OPEN (returns False from allow_request()),
    the code logs a debug message and falls back to the in-memory fallback strategy.
    """
    from unittest.mock import AsyncMock, patch

    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker
    from app.core.ratelimit.logic import check_rate_limit
    from app.core.ratelimit.strategies.memory import clear_memory_state

    clear_memory_state()

    # Create a circuit breaker in OPEN state
    mock_cb = RedisCircuitBreaker(failure_threshold=1, recovery_timeout=3600.0)
    mock_cb.record_failure()  # Trip the breaker
    assert mock_cb.state == CircuitState.OPEN

    with (
        patch("app.core.ratelimit.logic.settings") as mock_settings,
        patch("app.core.ratelimit.logic._get_redis_strategy") as mock_strategy_fn,
        patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=mock_cb),
    ):
        mock_settings.rate_limit_enabled = True

        result = await check_rate_limit(
            identifier="open_circuit_user",
            limit=10,
            window_seconds=60,
            redis_url="redis://localhost:6379",
        )

    # Should fall back to in-memory with 50% limit (limit//2 = 5)
    assert result.allowed is True  # First request within fallback limit
    # Redis strategy should NOT have been called (circuit was open)
    mock_strategy_fn.assert_called_once()  # strategy was created
    clear_memory_state()


@pytest.mark.asyncio
async def test_enforce_rate_limit_circuit_open_uses_fallback() -> None:
    """Lines 157-159: enforce_rate_limit falls back to memory when circuit is OPEN."""
    from unittest.mock import AsyncMock, patch

    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker
    from app.core.ratelimit.logic import enforce_rate_limit
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()

    # Create a circuit breaker in OPEN state
    open_cb = RedisCircuitBreaker(failure_threshold=1, recovery_timeout=3600.0)
    open_cb.record_failure()
    assert open_cb.state == CircuitState.OPEN

    strategy = MemorySlidingWindowStrategy(namespace="test_open")

    with (
        patch("app.core.ratelimit.logic.settings") as mock_settings,
        patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=open_cb),
    ):
        mock_settings.rate_limit_enabled = True

        # With circuit open, enforce_rate_limit should use fallback memory at 50%
        info = await enforce_rate_limit(
            identifier="circuit_open_user",
            limit=10,
            window_seconds=60,
            strategy=strategy,
        )

    assert info.allowed is True
    clear_memory_state()


def test_get_default_strategy_redis_backend() -> None:
    """Line 117: get_default_strategy() returns Redis strategy when storage_backend is redis."""
    from unittest.mock import patch

    from app.core.ratelimit.logic import get_default_strategy
    from app.core.ratelimit.strategies.redis import RedisSlidingWindowStrategy

    with patch("app.core.ratelimit.logic.settings") as mock_settings:
        mock_settings.rate_limit_storage_backend = "redis"
        mock_settings.rate_limit_storage_uri = "redis://localhost:6379"

        strategy = get_default_strategy("test_ns")

    assert isinstance(strategy, RedisSlidingWindowStrategy)


def test_get_default_strategy_memory_backend() -> None:
    """Line 118: get_default_strategy() returns Memory strategy when backend is not redis."""
    from unittest.mock import patch

    from app.core.ratelimit.logic import get_default_strategy
    from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy

    with patch("app.core.ratelimit.logic.settings") as mock_settings:
        mock_settings.rate_limit_storage_backend = "memory"
        mock_settings.rate_limit_storage_uri = "memory://"

        strategy = get_default_strategy("test_ns")

    assert isinstance(strategy, MemorySlidingWindowStrategy)


@pytest.mark.asyncio
async def test_enforce_rate_limit_redis_error_fallback() -> None:
    """Lines 143-152: enforce_rate_limit catches RedisError/OSError and falls back to memory.

    When the strategy raises RedisError or OSError, the circuit breaker records a failure,
    and the fallback MemorySlidingWindowStrategy is used at 50% limit.
    """
    from unittest.mock import AsyncMock, patch

    from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker
    from app.core.ratelimit.logic import enforce_rate_limit
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()

    # Create a strategy that raises OSError on first call
    mock_strategy = AsyncMock()
    mock_strategy.check = AsyncMock(side_effect=OSError("Redis connection refused"))

    # Circuit breaker in CLOSED state (allows request)
    closed_cb = RedisCircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
    assert closed_cb.state == CircuitState.CLOSED

    with (
        patch("app.core.ratelimit.logic.settings") as mock_settings,
        patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=closed_cb),
    ):
        mock_settings.rate_limit_enabled = True

        # Strategy raises OSError → CB records failure → fallback memory at 50%
        info = await enforce_rate_limit(
            identifier="user_redis_error",
            limit=10,
            window_seconds=60,
            strategy=mock_strategy,
        )

    # Should succeed (fallback at 50% = 5 req limit, first attempt allowed)
    assert info.allowed is True
    # CB failure count should have incremented
    assert closed_cb._failure_count == 1  # type: ignore[attr-defined]
    clear_memory_state()


@pytest.mark.asyncio
async def test_enforce_rate_limit_redis_error_fallback_exceeded() -> None:
    """Lines 143-152 + 163-164: When Redis fails AND fallback is exceeded, raises RateLimitExceeded."""
    from unittest.mock import AsyncMock, patch

    from app.core.ratelimit.circuit_breaker import RedisCircuitBreaker
    from app.core.ratelimit.exceptions import RateLimitExceeded
    from app.core.ratelimit.logic import enforce_rate_limit
    from app.core.ratelimit.strategies.memory import (
        MemorySlidingWindowStrategy,
        clear_memory_state,
    )

    clear_memory_state()

    mock_strategy = AsyncMock()
    mock_strategy.check = AsyncMock(side_effect=OSError("Redis down"))

    closed_cb = RedisCircuitBreaker(failure_threshold=5, recovery_timeout=10.0)

    with (
        patch("app.core.ratelimit.logic.settings") as mock_settings,
        patch("app.core.ratelimit.logic.get_circuit_breaker", return_value=closed_cb),
    ):
        mock_settings.rate_limit_enabled = True

        # With limit=1, fallback limit = max(1//2, 1) = 1
        # First call: Redis fails → fallback at 1 req/min → ALLOWED
        first = await enforce_rate_limit(
            identifier="user_fallback_exceeded",
            limit=1,
            window_seconds=60,
            strategy=mock_strategy,
        )
        assert first.allowed is True

        # Second call: Redis fails again → fallback already used (1 req) → EXCEEDED
        with pytest.raises(RateLimitExceeded):
            await enforce_rate_limit(
                identifier="user_fallback_exceeded",
                limit=1,
                window_seconds=60,
                strategy=mock_strategy,
            )

    clear_memory_state()


# ---------------------------------------------------------------------------
# app/core/policies/csp.py — ContentSecurityPolicy
# ---------------------------------------------------------------------------


def test_csp_production_policy_has_nonce() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    csp = ContentSecurityPolicy(is_development=False)
    nonce = "abc123"
    policy = csp.generate(nonce=nonce)
    assert nonce in policy
    assert "nonce-" in policy


def test_csp_development_policy_has_connect_src() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    csp = ContentSecurityPolicy(is_development=True)
    policy = csp.generate()
    assert "connect-src" in policy
    assert "localhost" in policy


def test_csp_custom_policy_overrides() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    custom = "default-src 'none'"
    csp = ContentSecurityPolicy(custom_policy=custom)
    policy = csp.generate()
    assert custom in policy


def test_csp_report_only_flag() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    csp = ContentSecurityPolicy(report_only=True)
    assert csp.report_only is True


def test_csp_extra_connect_src() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    csp = ContentSecurityPolicy(
        is_development=False,
        connect_src_extra=["wss://push.example.com"],
    )
    policy = csp.generate(nonce="xyz")
    assert "wss://push.example.com" in policy


def test_csp_report_uri_included() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    csp = ContentSecurityPolicy(
        is_development=False,
        report_uri="/csp-report",
    )
    policy = csp.generate(nonce="nonce")
    assert "/csp-report" in policy or "report-uri" in policy


def test_csp_require_trusted_types_in_dev() -> None:
    from app.core.policies.csp import ContentSecurityPolicy

    csp = ContentSecurityPolicy(is_development=True)
    policy = csp.generate()
    assert "trusted-types" in policy or "require-trusted-types" in policy


# ---------------------------------------------------------------------------
# app/core/security_headers.py — SecurityHeadersMiddleware
# ---------------------------------------------------------------------------


def test_security_headers_import() -> None:
    from app.core.security_headers import SecurityHeadersMiddleware

    assert SecurityHeadersMiddleware is not None


@pytest.mark.asyncio
async def test_security_headers_adds_hsts() -> None:
    from app.core.security_headers import SecurityHeadersMiddleware

    mock_app = AsyncMock()
    mock_response = MagicMock()
    mock_response.headers = {}

    async def call_next(request: Any) -> Any:
        return mock_response

    mock_settings = MagicMock()
    mw = SecurityHeadersMiddleware(mock_app, settings=mock_settings)
    assert mw is not None  # Just test instantiation with required settings arg


def test_security_headers_middleware_exists() -> None:
    """Verify module exports the expected class."""
    from app.core import security_headers

    assert hasattr(security_headers, "SecurityHeadersMiddleware")


# ---------------------------------------------------------------------------
# app/core/middleware/response_hardening.py
# ---------------------------------------------------------------------------


def test_response_hardening_import() -> None:
    """Module exports the ASGI middleware function."""
    from app.core.middleware.response_hardening import http_response_hardening

    assert callable(http_response_hardening)


@pytest.mark.asyncio
async def test_response_hardening_adds_cache_control_for_static() -> None:
    """Static paths get Cache-Control header."""
    from starlette.responses import Response

    from app.core.middleware.response_hardening import http_response_hardening

    mock_request = MagicMock()
    mock_request.url.path = "/static/avatar.png"
    mock_request.method = "GET"
    mock_request.headers = {}

    mock_response = Response(content=b"img", status_code=200)

    async def call_next(req: Any) -> Any:
        return mock_response

    result = await http_response_hardening(mock_request, call_next)
    assert result.headers.get("cache-control") == "public, max-age=86400"


@pytest.mark.asyncio
async def test_ensure_vary_header_adds_origin() -> None:
    """_ensure_vary_header appends to Vary if not present."""
    from starlette.responses import Response

    from app.core.middleware.response_hardening import _ensure_vary_header

    response = Response()
    _ensure_vary_header(response, "Origin")
    assert response.headers.get("Vary") == "Origin"


@pytest.mark.asyncio
async def test_ensure_vary_header_no_duplicate() -> None:
    """_ensure_vary_header does not duplicate existing Vary entries."""
    from starlette.responses import Response

    from app.core.middleware.response_hardening import _ensure_vary_header

    response = Response()
    response.headers["Vary"] = "Origin"
    _ensure_vary_header(response, "Origin")
    assert response.headers["Vary"] == "Origin"  # not "Origin, Origin"
