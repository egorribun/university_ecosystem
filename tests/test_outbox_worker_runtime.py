"""Lifecycle and runtime tests for app/workers/outbox.py.

Targets OutboxWorker: stop(), run_forever(), process_batch(), _dispatch_event(),
_move_to_dlq() and _on_notification().
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.outbox import OutboxWorker

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_stored_event(
    event_type: str = "TestEvent",
    payload: dict[str, Any] | None = None,
    error_count: int = 0,
    metadata_: dict[str, Any] | None = None,
    aggregate_id_uuid: uuid.UUID | None = None,
    sequence_number: int | None = None,
):
    se = MagicMock()
    se.id = uuid.uuid4()
    se.event_type = event_type
    se.payload = payload or {}
    se.error_count = error_count
    se.last_error = ""
    se.aggregate_type = "TestAggregate"
    se.aggregate_id = "agg-1"
    se.aggregate_id_uuid = aggregate_id_uuid
    se.sequence_number = sequence_number
    se.metadata_ = metadata_
    se.processed_at = None
    return se


@pytest.fixture
def worker() -> OutboxWorker:
    return OutboxWorker(poll_interval=0.01, batch_size=5, max_retries=3)


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


def test_worker_defaults():
    w = OutboxWorker()
    assert w.poll_interval == 5.0
    assert w.batch_size == 20
    assert w.max_retries == 5
    assert not w._is_running


def test_on_notification_sets_wakeup_event(worker: OutboxWorker):
    assert not worker._wakeup_event.is_set()
    worker._on_notification()
    assert worker._wakeup_event.is_set()


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_sets_is_running_false_and_wakes_event(worker: OutboxWorker):
    worker._is_running = True
    await worker.stop()
    assert not worker._is_running
    assert worker._wakeup_event.is_set()


# ---------------------------------------------------------------------------
# _dispatch_event tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_event_unknown_type(worker: OutboxWorker):
    """Unknown event_type fails closed for process_batch to dead-letter."""
    se = make_stored_event(event_type="NoSuchEvent")
    original_error_count = se.error_count

    with patch("app.core.events._EVENT_REGISTRY", {}):
        with pytest.raises(RuntimeError, match="Unknown outbox event type"):
            await worker._dispatch_event(se)

    assert se.error_count == original_error_count


@pytest.mark.asyncio
async def test_dispatch_event_known_type(worker: OutboxWorker):
    """Known event_type constructs and publishes the event."""

    @dataclasses.dataclass
    class FakeEvent:
        name: str
        event_id: str = "evt-1"
        metadata: Any = None

    se = make_stored_event(
        event_type="FakeEvent",
        payload={"name": "hello"},
        aggregate_id_uuid=uuid.uuid4(),
        sequence_number=1,
    )

    mock_bus = AsyncMock()
    with (
        patch("app.core.events._EVENT_REGISTRY", {"FakeEvent": FakeEvent}),
        patch("app.workers.outbox.event_bus", mock_bus),
    ):
        await worker._dispatch_event(se)

    mock_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_event_with_metadata(worker: OutboxWorker):
    """Metadata is restored on the event if present in the stored event."""

    @dataclasses.dataclass
    class MetaEvent:
        value: int
        event_id: str = "evt-default"
        metadata: Any = None

    se = make_stored_event(
        event_type="MetaEvent",
        payload={"value": 42},
        metadata_={
            "event_id": "restored-id",
            "correlation_id": "corr-1",
            "user_id": "usr-1",
        },
    )

    mock_bus = AsyncMock()
    with (
        patch("app.core.events._EVENT_REGISTRY", {"MetaEvent": MetaEvent}),
        patch("app.workers.outbox.event_bus", mock_bus),
    ):
        await worker._dispatch_event(se)

    mock_bus.publish.assert_called_once()
    published_event: MetaEvent = mock_bus.publish.call_args[0][0]
    assert published_event.event_id == "restored-id"


@pytest.mark.asyncio
async def test_dispatch_event_constructor_raises(worker: OutboxWorker):
    """A direct dispatch failure is re-raised for process_batch to journal."""

    @dataclasses.dataclass
    class BadEvent:
        required: str

        def __post_init__(self) -> None:
            raise ValueError("bad")

    se = make_stored_event(event_type="BadEvent", payload={"required": "x"})

    with (
        patch("app.core.events._EVENT_REGISTRY", {"BadEvent": BadEvent}),
        patch("app.workers.outbox.event_bus", AsyncMock()),
    ):
        with pytest.raises(ValueError):
            await worker._dispatch_event(se)

    assert se.error_count == 0


# ---------------------------------------------------------------------------
# _move_to_dlq tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_to_dlq(worker: OutboxWorker):
    """_move_to_dlq adds a FailedOutboxEvent row and marks the event processed."""
    se = make_stored_event(event_type="TestEvent", error_count=3)
    mock_db = MagicMock()
    mock_db.add = MagicMock()

    mock_failed_event_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.id = uuid.uuid4()
    mock_failed_event_cls.return_value = mock_instance

    with patch(
        "app.models.failed_outbox_events.FailedOutboxEvent",
        mock_failed_event_cls,
    ):
        await worker._move_to_dlq(mock_db, se, "some error")

    mock_db.add.assert_called_once()
    assert se.processed_at is not None  # marked as processed


# ---------------------------------------------------------------------------
# process_batch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_batch_empty_returns_zero(worker: OutboxWorker):
    """process_batch returns 0 when there are no pending events."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_pending_result = MagicMock()
    mock_pending_result.scalar_one.return_value = 0

    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_pending_result])
    mock_db.commit = AsyncMock()

    with patch("app.workers.outbox.async_session") as mock_cm:
        mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await worker.process_batch()

    assert result == 0


@pytest.mark.asyncio
async def test_process_batch_successful_dispatch(worker: OutboxWorker):
    """process_batch dispatches events and commits."""
    se1 = make_stored_event("Evt")
    se2 = make_stored_event("Evt")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [se1, se2]

    mock_pending_result = MagicMock()
    mock_pending_result.scalar_one.return_value = 2

    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_pending_result])
    mock_db.commit = AsyncMock()

    with (
        patch("app.workers.outbox.async_session") as mock_cm,
        patch.object(worker, "_dispatch_event", new_callable=AsyncMock),
    ):
        mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await worker.process_batch()

    assert result == 2
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_process_batch_dispatch_failure_increments_error(worker: OutboxWorker):
    """When dispatch fails below max_retries, error_count is incremented."""
    worker.max_retries = 3
    se = make_stored_event("Evt", error_count=0)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [se]

    mock_pending_result = MagicMock()
    mock_pending_result.scalar_one.return_value = 1

    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_pending_result])
    mock_db.commit = AsyncMock()

    async def dispatch_fail(event: Any) -> None:
        raise RuntimeError("boom")

    with (
        patch("app.workers.outbox.async_session") as mock_cm,
        patch.object(worker, "_dispatch_event", side_effect=dispatch_fail),
    ):
        mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await worker.process_batch()

    assert result == 1
    assert se.error_count == 1


@pytest.mark.asyncio
async def test_process_batch_dispatch_failure_hits_dlq_at_max_retries(
    worker: OutboxWorker,
):
    """When dispatch fails and error_count >= max_retries, event goes to DLQ."""
    worker.max_retries = 2
    se = make_stored_event("Evt", error_count=1)  # One away from max

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [se]

    mock_pending_result = MagicMock()
    mock_pending_result.scalar_one.return_value = 1

    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_pending_result])
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def dispatch_fail(event: Any) -> None:
        raise RuntimeError("boom")

    mock_failed_event = MagicMock()
    mock_failed_event.id = uuid.uuid4()

    with (
        patch("app.workers.outbox.async_session") as mock_cm,
        patch.object(worker, "_dispatch_event", side_effect=dispatch_fail),
        patch(
            "app.models.failed_outbox_events.FailedOutboxEvent",
            return_value=mock_failed_event,
        ),
    ):
        mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await worker.process_batch()

    assert result == 1
    mock_db.add.assert_called_once()  # DLQ row added


# ---------------------------------------------------------------------------
# run_forever tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_forever_cancels_cleanly(worker: OutboxWorker):
    """run_forever should catch CancelledError and shut down listen_task."""
    call_count = 0

    async def mock_process_batch() -> int:
        nonlocal call_count
        call_count += 1
        raise asyncio.CancelledError

    worker.process_batch = mock_process_batch  # type: ignore[method-assign]

    # _listen_loop will try to connect to a real DB — mock it out
    async def mock_listen_loop() -> None:
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    with patch.object(worker, "_listen_loop", side_effect=mock_listen_loop):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()


@pytest.mark.asyncio
async def test_run_forever_handles_exception_in_loop(worker: OutboxWorker):
    """Non-CancelledError exception in process_batch should be caught and loop continues."""
    call_count = 0

    async def mock_process_batch() -> int:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("transient error")
        # On second call, cancel the loop
        raise asyncio.CancelledError

    async def mock_listen_loop() -> None:
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    worker.process_batch = mock_process_batch  # type: ignore[method-assign]

    with (
        patch.object(worker, "_listen_loop", side_effect=mock_listen_loop),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()

    assert call_count >= 2  # both iterations happened


@pytest.mark.asyncio
async def test_run_forever_processed_equals_or_exceeds_batch_size(worker: OutboxWorker):
    """When processed >= batch_size, run_forever should immediately loop without waiting on wakeup_event."""
    worker.batch_size = 2
    call_count = 0

    async def mock_process_batch() -> int:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return 2  # processed = batch_size, should not wait!
        # Cancel on second call to break the loop
        raise asyncio.CancelledError

    worker.process_batch = mock_process_batch  # type: ignore[method-assign]

    async def mock_listen_loop() -> None:
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    # Spy on _wakeup_event.wait
    mock_wait = AsyncMock()
    worker._wakeup_event.wait = mock_wait  # type: ignore[method-assign]

    with (
        patch.object(worker, "_listen_loop", side_effect=mock_listen_loop),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()

    # The wakeup wait should NOT be called on the first loop iteration!
    assert call_count >= 2
    mock_wait.assert_not_called()
