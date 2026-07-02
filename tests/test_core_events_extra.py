from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.event_decorators import (
    clear_pending_registrations,
    get_pending_count,
    register_decorated_handlers,
    subscribe,
    subscribe_all,
)
from app.core.event_dlq import DeadLetterQueue
from app.core.event_registry import reconstruct_event, register_event
from app.core.event_retry import EventRetryExhausted, RetryMiddleware, with_retry
from app.core.events import DomainEvent, EventBus


@dataclass
class DummyEvent(DomainEvent):
    event_type = "dummy.event"
    some_value: str = "test"


@pytest.fixture(autouse=True)
def clear_registrations():
    clear_pending_registrations()
    yield
    clear_pending_registrations()


@pytest.mark.asyncio
async def test_event_decorators():
    @subscribe("test.event")
    async def handle_test(event):
        pass

    @subscribe(DummyEvent)
    async def handle_dummy(event):
        pass

    @subscribe_all
    async def handle_all(event):
        pass

    assert get_pending_count() == 3

    bus = EventBus()
    bus.subscribe = MagicMock()
    bus.subscribe_all = MagicMock()

    count = register_decorated_handlers(bus)
    assert count == 3
    assert bus.subscribe.call_count == 2
    assert bus.subscribe_all.call_count == 1


def test_event_registry():
    @register_event
    @dataclass
    class RegisteredEvent(DomainEvent):
        my_field: str = ""

    assert "RegisteredEvent" in [cls.__name__ for cls in (RegisteredEvent,)]

    payload = {"my_field": "hello", "unknown_field": "dropped"}
    event = reconstruct_event("RegisteredEvent", payload)

    assert isinstance(event, RegisteredEvent)
    assert event.my_field == "hello"
    assert not hasattr(event, "unknown_field")

    with pytest.raises(ValueError, match="Unknown event type"):
        reconstruct_event("UnknownEvent", {})


@pytest.mark.asyncio
async def test_retry_middleware():
    middleware = RetryMiddleware(max_retries=2, base_delay=0.01, max_delay=0.05)

    event = DummyEvent(event_id="123")

    mock_handler = AsyncMock(
        side_effect=[ValueError("fail 1"), ValueError("fail 2"), None]
    )

    # Should succeed on the 3rd attempt (after 2 retries)
    await middleware(event, mock_handler)
    assert mock_handler.call_count == 3

    # Test exhaustion
    mock_handler_exhaust = AsyncMock(side_effect=ValueError("fail forever"))
    with pytest.raises(EventRetryExhausted) as exc_info:
        await middleware(event, mock_handler_exhaust)

    assert exc_info.value.attempts == 3


@pytest.mark.asyncio
async def test_with_retry_decorator():
    mock_handler = AsyncMock(side_effect=[ValueError("fail"), None])

    @with_retry(max_retries=1, base_delay=0.01)
    async def handler(event):
        await mock_handler(event)

    event = DummyEvent(event_id="123")
    await handler(event)
    assert mock_handler.call_count == 2


@pytest.mark.asyncio
async def test_dead_letter_queue():
    dlq = DeadLetterQueue(max_size=10)
    event = DummyEvent(event_id="dlq-1")

    await dlq.add(event, ValueError("test error"), "my_handler")
    assert dlq.size == 1

    events = await dlq.get_all()
    assert len(events) == 1
    assert events[0].event.event_id == "dlq-1"
    assert events[0].error_type == "ValueError"

    # Test get_by_type
    by_type = await dlq.get_by_type("dummy.event")
    assert len(by_type) == 1

    # Test remove
    removed = await dlq.remove("dlq-1")
    assert removed is True
    assert dlq.size == 0

    # Test replay
    bus = AsyncMock()
    bus.publish = AsyncMock()

    await dlq.add(event, ValueError("test error"))
    success, fail = await dlq.replay(bus)

    assert success == 1
    assert fail == 0
    assert dlq.size == 0
    bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_dead_letter_queue_stats():
    dlq = DeadLetterQueue(max_size=10)
    event1 = DummyEvent(event_id="dlq-1")
    event2 = DummyEvent(event_id="dlq-2")

    await dlq.add(event1, ValueError("error 1"))
    await dlq.add(event2, TypeError("error 2"))

    stats = await dlq.get_stats()
    assert stats["size"] == 2
    assert stats["max_size"] == 10
    assert stats["by_type"]["dummy.event"] == 2
    assert stats["by_error"]["ValueError"] == 1
    assert stats["by_error"]["TypeError"] == 1
