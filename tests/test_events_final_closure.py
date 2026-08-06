from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_remaining_domain_event_from_dict_variants():
    from app.core.events import (
        GradeAssigned,
        GradeModified,
        ScheduleCreated,
        ScheduleUpdated,
    )

    for event_class in (ScheduleCreated, ScheduleUpdated, GradeAssigned, GradeModified):
        payload = {"_schema_version": 1, "unknown": "ignored"}
        event = event_class.from_dict(payload)
        assert event.event_type == event_class.EVENT_TYPE
        assert "_schema_version" not in payload


@pytest.mark.asyncio
async def test_event_bus_handler_lifecycle_and_successful_publish():
    from app.core.events import EventBus, UserCreated

    bus = EventBus()
    event = UserCreated(email="events@example.com")
    handler = AsyncMock()
    all_handler = AsyncMock()

    bus.subscribe(event.event_type, handler)
    bus.subscribe_all(all_handler)
    assert bus.get_handler_count(event.event_type) == 2
    assert bus.get_handler_count() == 2

    await bus.publish(event)

    handler.assert_awaited_once_with(event)
    all_handler.assert_awaited_once_with(event)
    bus.unsubscribe(event.event_type, handler)
    bus.unsubscribe_all(all_handler)
    assert bus.get_handler_count() == 0

    bus.subscribe(event.event_type, handler)
    bus.clear()
    assert bus.get_handler_count() == 0


@pytest.mark.asyncio
async def test_event_bus_handler_failure_without_dlq_is_contained():
    from app.core.events import EventBus, UserCreated

    bus = EventBus()
    event = UserCreated(email="events@example.com")

    async def failing_handler(_event):
        raise RuntimeError("handler failure")

    bus.subscribe(event.event_type, failing_handler)
    await bus.publish(event)
