"""Tests for Enhanced Domain Events System.

Tests for:
- EventMetadata
- Decorator-based subscriptions
- Middleware pipeline
- Retry mechanism
- Dead Letter Queue
"""

from unittest.mock import AsyncMock

import pytest

from app.core.event_decorators import (
    clear_pending_registrations,
    get_pending_count,
    register_decorated_handlers,
    subscribe,
    subscribe_all,
)
from app.core.event_dlq import DeadLetterQueue, FailedEvent
from app.core.event_retry import (
    EventRetryExhausted,
    RetryMiddleware,
    with_retry,
)
from app.core.events import (
    DomainEvent,
    EventBus,
    EventMetadata,
    UserCreated,
)

# ============================================================
# EventMetadata Tests
# ============================================================


def test_event_metadata_defaults():
    """Test EventMetadata has correct defaults."""
    metadata = EventMetadata()

    assert metadata.correlation_id is None
    assert metadata.causation_id is None
    assert metadata.user_id is None
    assert metadata.source == "app"
    assert metadata.retry_count == 0
    assert metadata.max_retries == 3


def test_event_metadata_custom_values():
    """Test EventMetadata with custom values."""
    metadata = EventMetadata(
        correlation_id="corr-123",
        causation_id="cause-456",
        user_id=42,
        source="test",
        retry_count=2,
        max_retries=5,
    )

    assert metadata.correlation_id == "corr-123"
    assert metadata.causation_id == "cause-456"
    assert metadata.user_id == 42
    assert metadata.source == "test"
    assert metadata.retry_count == 2
    assert metadata.max_retries == 5


def test_domain_event_has_metadata():
    """Test DomainEvent includes metadata field."""
    event = UserCreated(user_id=1, email="test@example.com")

    assert event.metadata is not None
    assert isinstance(event.metadata, EventMetadata)
    assert event.metadata.source == "app"


def test_domain_event_custom_metadata():
    """Test DomainEvent with custom metadata."""
    metadata = EventMetadata(correlation_id="test-123", user_id=1)
    event = UserCreated(user_id=1, email="test@example.com", metadata=metadata)

    assert event.metadata.correlation_id == "test-123"
    assert event.metadata.user_id == 1


# ============================================================
# Decorator Tests
# ============================================================


def test_subscribe_decorator_registers_handler():
    """Test @subscribe decorator adds handler to pending list."""
    clear_pending_registrations()

    @subscribe("test.event")
    async def test_handler(event: DomainEvent) -> None:
        pass

    assert get_pending_count() == 1


def test_subscribe_all_decorator_registers_handler():
    """Test @subscribe_all decorator adds handler to pending list."""
    clear_pending_registrations()

    @subscribe_all
    async def test_handler(event: DomainEvent) -> None:
        pass

    assert get_pending_count() == 1


@pytest.mark.asyncio
async def test_register_decorated_handlers():
    """Test decorated handlers are registered with the bus."""
    clear_pending_registrations()
    bus = EventBus()

    @subscribe("user.created")
    async def handle_user(event: DomainEvent) -> None:
        pass

    @subscribe_all
    async def log_all(event: DomainEvent) -> None:
        pass

    count = register_decorated_handlers(bus)

    assert count == 2
    assert bus.get_handler_count("user.created") == 2  # specific + all
    assert len(bus._all_handlers) == 1


def test_clear_pending_registrations():
    """Test clearing pending registrations."""
    clear_pending_registrations()

    @subscribe("test.event")
    async def handler(event: DomainEvent) -> None:
        pass

    assert get_pending_count() == 1
    clear_pending_registrations()
    assert get_pending_count() == 0


# ============================================================
# Enhanced EventBus Tests
# ============================================================


@pytest.mark.asyncio
async def test_event_bus_middleware():
    """Test middleware is executed around handlers."""
    bus = EventBus()
    execution_order: list[str] = []

    async def middleware(
        event: DomainEvent,
        next_handler,
    ) -> None:
        execution_order.append("middleware_before")
        await next_handler(event)
        execution_order.append("middleware_after")

    async def handler(event: DomainEvent) -> None:
        execution_order.append("handler")

    bus.add_middleware(middleware)
    bus.subscribe("user.created", handler)

    event = UserCreated(user_id=1, email="test@example.com")
    await bus.publish(event)

    assert execution_order == ["middleware_before", "handler", "middleware_after"]


@pytest.mark.asyncio
async def test_event_bus_middleware_chain():
    """Test multiple middleware execute in correct order."""
    bus = EventBus()
    order: list[str] = []

    async def mw1(event: DomainEvent, next_handler) -> None:
        order.append("mw1_before")
        await next_handler(event)
        order.append("mw1_after")

    async def mw2(event: DomainEvent, next_handler) -> None:
        order.append("mw2_before")
        await next_handler(event)
        order.append("mw2_after")

    async def handler(event: DomainEvent) -> None:
        order.append("handler")

    bus.add_middleware(mw1)
    bus.add_middleware(mw2)
    bus.subscribe("user.created", handler)

    await bus.publish(UserCreated(user_id=1, email="test@example.com"))

    # First added is outermost
    assert order == [
        "mw1_before",
        "mw2_before",
        "handler",
        "mw2_after",
        "mw1_after",
    ]


@pytest.mark.asyncio
async def test_event_bus_dlq_integration():
    """Test failed handlers send events to DLQ."""
    bus = EventBus()
    dlq = DeadLetterQueue()
    bus.set_dlq(dlq)

    async def failing_handler(event: DomainEvent) -> None:
        raise ValueError("Test error")

    bus.subscribe("user.created", failing_handler)

    event = UserCreated(user_id=1, email="test@example.com")
    await bus.publish(event)

    assert dlq.size == 1
    failed_events = await dlq.get_all()
    assert failed_events[0].event.event_id == event.event_id
    assert failed_events[0].error_type == "ValueError"


def test_event_bus_clear():
    """Test EventBus clear method."""
    bus = EventBus()
    bus.subscribe("test", AsyncMock())
    bus.subscribe_all(AsyncMock())
    bus.add_middleware(AsyncMock())

    bus.clear()

    assert bus.get_handler_count() == 0
    assert len(bus._middleware) == 0


def test_event_bus_unsubscribe_all():
    """Test unsubscribe_all method."""
    bus = EventBus()
    handler = AsyncMock()
    bus.subscribe_all(handler)

    bus.unsubscribe_all(handler)

    assert handler not in bus._all_handlers


# ============================================================
# Retry Middleware Tests
# ============================================================


@pytest.mark.asyncio
async def test_retry_middleware_success():
    """Test RetryMiddleware allows successful calls through."""
    middleware = RetryMiddleware(max_retries=3)
    handler = AsyncMock()
    event = UserCreated(user_id=1, email="test@example.com")

    await middleware(event, handler)

    handler.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_retry_middleware_retries_on_failure():
    """Test RetryMiddleware retries failed calls."""
    middleware = RetryMiddleware(max_retries=2, base_delay=0.01)

    attempts = [0]

    async def failing_then_success(event: DomainEvent) -> None:
        attempts[0] += 1
        if attempts[0] < 2:
            raise ValueError("Temporary failure")

    event = UserCreated(user_id=1, email="test@example.com")
    await middleware(event, failing_then_success)

    assert attempts[0] == 2


@pytest.mark.asyncio
async def test_retry_middleware_exhausts_retries():
    """Test RetryMiddleware raises after max retries."""
    middleware = RetryMiddleware(max_retries=2, base_delay=0.01)

    async def always_fails(event: DomainEvent) -> None:
        raise ValueError("Permanent failure")

    event = UserCreated(user_id=1, email="test@example.com")

    with pytest.raises(EventRetryExhausted) as exc_info:
        await middleware(event, always_fails)

    assert exc_info.value.attempts == 3  # 1 initial + 2 retries
    assert isinstance(exc_info.value.original_error, ValueError)


@pytest.mark.asyncio
async def test_with_retry_decorator():
    """Test @with_retry decorator."""
    attempts = [0]

    @with_retry(max_retries=2, base_delay=0.01)
    async def flaky_handler(event: DomainEvent) -> None:
        attempts[0] += 1
        if attempts[0] < 2:
            raise ValueError("Flaky")

    event = UserCreated(user_id=1, email="test@example.com")
    await flaky_handler(event)

    assert attempts[0] == 2


# ============================================================
# Dead Letter Queue Tests
# ============================================================


@pytest.mark.asyncio
async def test_dlq_add_and_get():
    """Test adding and retrieving failed events."""
    dlq = DeadLetterQueue()
    event = UserCreated(user_id=1, email="test@example.com")
    error = ValueError("Test error")

    await dlq.add(event, error, "test_handler")

    assert dlq.size == 1
    events = await dlq.get_all()
    assert len(events) == 1
    assert events[0].event.event_id == event.event_id
    assert events[0].error == "Test error"
    assert events[0].handler_name == "test_handler"


@pytest.mark.asyncio
async def test_dlq_max_size():
    """Test DLQ respects max size limit."""
    dlq = DeadLetterQueue(max_size=3)

    for i in range(5):
        event = UserCreated(user_id=i, email=f"user{i}@example.com")
        await dlq.add(event, ValueError("error"), None)

    assert dlq.size == 3
    events = await dlq.get_all()
    # Should have the last 3 events (oldest dropped)
    user_ids = [e.event.user_id for e in events]
    assert user_ids == [2, 3, 4]


@pytest.mark.asyncio
async def test_dlq_clear():
    """Test clearing the DLQ."""
    dlq = DeadLetterQueue()
    event = UserCreated(user_id=1, email="test@example.com")
    await dlq.add(event, ValueError("error"), None)

    cleared = await dlq.clear()

    assert cleared == 1
    assert dlq.size == 0


@pytest.mark.asyncio
async def test_dlq_remove():
    """Test removing specific event from DLQ."""
    dlq = DeadLetterQueue()
    event1 = UserCreated(user_id=1, email="test1@example.com")
    event2 = UserCreated(user_id=2, email="test2@example.com")

    await dlq.add(event1, ValueError("error1"), None)
    await dlq.add(event2, ValueError("error2"), None)

    removed = await dlq.remove(event1.event_id)

    assert removed is True
    assert dlq.size == 1
    events = await dlq.get_all()
    assert events[0].event.event_id == event2.event_id


@pytest.mark.asyncio
async def test_dlq_replay():
    """Test replaying events from DLQ."""
    dlq = DeadLetterQueue()
    bus = EventBus()
    handler = AsyncMock()
    bus.subscribe("user.created", handler)

    event = UserCreated(user_id=1, email="test@example.com")
    await dlq.add(event, ValueError("error"), None)

    success, failed = await dlq.replay(bus)

    assert success == 1
    assert failed == 0
    assert dlq.size == 0  # Events cleared after successful replay
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_dlq_get_by_type():
    """Test filtering DLQ by event type."""
    dlq = DeadLetterQueue()
    from app.core.events import UserLoggedIn

    event1 = UserCreated(user_id=1, email="test@example.com")
    event2 = UserLoggedIn(user_id=1)

    await dlq.add(event1, ValueError("error"), None)
    await dlq.add(event2, ValueError("error"), None)

    user_created_events = await dlq.get_by_type("user.created")

    assert len(user_created_events) == 1
    assert user_created_events[0].event.event_type == "user.created"


@pytest.mark.asyncio
async def test_dlq_get_stats():
    """Test DLQ statistics."""
    dlq = DeadLetterQueue()
    event1 = UserCreated(user_id=1, email="test@example.com")
    event2 = UserCreated(user_id=2, email="test2@example.com")

    await dlq.add(event1, ValueError("error"), None)
    await dlq.add(event2, TypeError("type_error"), None)

    stats = await dlq.get_stats()

    assert stats["size"] == 2
    assert "user.created" in stats["by_type"]
    assert stats["by_type"]["user.created"] == 2
    assert "ValueError" in stats["by_error"]
    assert "TypeError" in stats["by_error"]


def test_failed_event_to_dict():
    """Test FailedEvent serialization."""
    event = UserCreated(user_id=1, email="test@example.com")
    failed = FailedEvent(
        event=event,
        error="Test error",
        error_type="ValueError",
        handler_name="test_handler",
    )

    data = failed.to_dict()

    assert data["event_id"] == event.event_id
    assert data["event_type"] == "user.created"
    assert data["error"] == "Test error"
    assert data["error_type"] == "ValueError"
    assert data["handler_name"] == "test_handler"
