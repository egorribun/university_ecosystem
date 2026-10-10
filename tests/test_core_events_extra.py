from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.core.event_dlq import DeadLetterQueue
from app.core.events import DomainEvent


@dataclass
class DummyEvent(DomainEvent):
    event_type = "dummy.event"
    some_value: str = "test"


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
