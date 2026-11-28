from unittest.mock import AsyncMock, call, patch

from app.core import event_dlq
from app.core.events import EventBus, UserCreated


async def test_in_memory_dlq_add_and_remove_only_log_event_types() -> None:
    queue = event_dlq.DeadLetterQueue()
    event = UserCreated()

    with (
        patch.object(event_dlq.logger, "warning") as warning,
        patch.object(event_dlq.logger, "info") as info,
    ):
        await queue.add(event, RuntimeError("synthetic storage detail"))
        assert await queue.remove(event.event_id)

    assert queue.size == 0
    warning.assert_called_once_with(
        "Event added to DLQ",
        event_type=event.event_type,
        error_type="RuntimeError",
    )
    info.assert_called_once_with("Event removed from DLQ", event_type=event.event_type)


async def test_manual_dlq_replay_logs_outcomes_without_record_data() -> None:
    queue = event_dlq.DeadLetterQueue()
    first, second = UserCreated(), UserCreated()
    await queue.add(first, RuntimeError("initial"))
    await queue.add(second, RuntimeError("initial"))
    bus = AsyncMock(spec=EventBus)
    bus.publish.side_effect = [None, ConnectionError("synthetic transport detail")]

    with (
        patch.object(event_dlq.logger, "info") as info,
        patch.object(event_dlq.logger, "error") as error,
    ):
        assert await queue.replay(bus) == (1, 1)

    assert [item.event for item in await queue.get_all()] == [second]
    error.assert_called_once_with(
        "DLQ replay failed", event_type=second.event_type, error_type="ConnectionError"
    )
    assert info.call_args_list == [
        call("DLQ event replayed successfully", event_type=first.event_type),
        call("DLQ replay complete: %d succeeded, %d failed", 1, 1),
    ]


async def test_terminal_dlq_replay_failure_logs_type_and_retry_count() -> None:
    queue = event_dlq.DeadLetterQueue()
    event = UserCreated()
    await queue.add(event, RuntimeError("initial"))
    bus = AsyncMock(spec=EventBus)
    bus.publish.side_effect = OSError("synthetic transport detail")

    with patch.object(event_dlq.logger, "error") as error:
        assert await queue.auto_replay(
            bus=bus, max_retries=1, base_backoff=0, jitter=0, rate_limit_delay=0
        ) == (0, 1)

    assert queue.size == 0
    error.assert_called_once_with(
        "Event permanently failed DLQ replay",
        event_type=event.event_type,
        retry_count=1,
        error_type="OSError",
    )
