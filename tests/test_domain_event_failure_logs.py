import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.core import events
from app.core.event_dlq import DeadLetterQueue


async def test_handler_failure_logs_class_and_preserves_dlq_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = events.EventBus()
    queue = DeadLetterQueue()
    bus.set_dlq(queue)
    event = events.UserCreated()

    async def failing_handler(_event: events.DomainEvent) -> None:
        raise ValueError("synthetic private handler detail")

    bus.subscribe(event.event_type, failing_handler)
    with caplog.at_level(logging.ERROR, logger=events.__name__):
        await bus.publish(event)

    (failed,) = await queue.get_all()
    assert failed.event is event
    assert failed.handler_name == "failing_handler"
    assert failed.error_type == "ValueError"
    assert "synthetic private handler detail" not in caplog.text
    (record,) = [
        entry
        for entry in caplog.records
        if entry.name == events.__name__ and entry.levelno == logging.ERROR
    ]
    payload = vars(record)["msg"]
    assert isinstance(payload, dict)
    assert payload["message"] == "Domain event handler failed"
    assert payload["event_type"] == event.event_type
    assert payload["handler_name"] == "failing_handler"
    assert payload["error_type"] == "ValueError"


async def test_double_failure_logs_both_classes_without_record_data() -> None:
    bus = events.EventBus()
    queue = AsyncMock(spec=DeadLetterQueue)
    queue.add.side_effect = OSError("synthetic private DLQ detail")
    bus.set_dlq(queue)
    event = events.UserCreated()
    handler_error = ValueError("synthetic private handler detail")

    async def failing_handler(_event: events.DomainEvent) -> None:
        raise handler_error

    bus.subscribe(event.event_type, failing_handler)
    with patch.object(events.logger, "critical") as critical:
        await bus.publish(event)

    queue.add.assert_awaited_once_with(event, handler_error, "failing_handler")
    critical.assert_called_once_with(
        "DOMAIN EVENT LOST: Both handler and DLQ failed",
        handler_error_type="ValueError",
        dlq_error_type="OSError",
        event_type=event.event_type,
        handler_name="failing_handler",
    )
