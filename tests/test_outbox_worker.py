import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.models.domain_events import StoredEvent
from app.workers.outbox import OutboxWorker


@pytest.mark.asyncio
async def test_outbox_worker_process_batch(db_session):
    worker = OutboxWorker()

    # Create a stored event (Use a registered event type for HIGH-04)
    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="UserCreated",
        aggregate_type="User",
        aggregate_id="123",
        payload={"user_id": "123", "email": "test@example.com"},
        metadata_={"correlation_id": "test-corr"},
    )
    db_session.add(se)
    await db_session.commit()

    # Process batch
    processed_count = await worker.process_batch()
    assert processed_count == 1

    # Verify it was marked as processed
    # We need a new session to see the commited changes if worker uses its own session
    from app.core.database import async_session

    async with async_session() as db:
        result = await db.get(StoredEvent, event_id)
        assert result.processed_at is not None
        assert result.error_count == 0


@pytest.mark.asyncio
async def test_outbox_worker_error_handling(db_session, monkeypatch):
    worker = OutboxWorker()

    # Create a stored event
    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="fail_event",
        aggregate_type="test_agg",
        aggregate_id="456",
        payload={},
        error_count=0,
    )
    db_session.add(se)
    await db_session.commit()

    # Mock dispatch to fail
    async def mock_fail(*args):
        raise ValueError("Simulated failure")

    monkeypatch.setattr(worker, "_dispatch_event", mock_fail)

    # Process batch
    processed_count = await worker.process_batch()
    assert processed_count == 1

    # Verify error count increased
    from app.core.database import async_session

    async with async_session() as db:
        result = await db.get(StoredEvent, event_id)
        assert result.processed_at is None
        assert result.error_count == 1
        assert "Simulated failure" in result.last_error


@pytest.mark.asyncio
async def test_outbox_worker_dlq_transition(db_session, monkeypatch):
    # Set max_retries = 1 so that a single failure moves it to DLQ
    worker = OutboxWorker(max_retries=1)

    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="fail_event",
        aggregate_type="test_agg",
        aggregate_id="456",
        payload={"key": "val"},
        error_count=0,
    )
    db_session.add(se)
    await db_session.commit()

    async def mock_fail(*args):
        raise ValueError("Critical error")

    monkeypatch.setattr(worker, "_dispatch_event", mock_fail)

    processed_count = await worker.process_batch()
    assert processed_count == 1

    from app.core.database import async_session
    from app.models.failed_outbox_events import FailedOutboxEvent

    async with async_session() as db:
        # Event should be marked as processed (since it was dead-lettered)
        result = await db.get(StoredEvent, event_id)
        assert result.processed_at is not None
        assert result.error_count == 1

        # Check that it exists in FailedOutboxEvent
        dlq_result = await db.execute(
            select(FailedOutboxEvent).where(
                FailedOutboxEvent.original_event_id == event_id
            )
        )
        failed_event = dlq_result.scalar_one()
        assert failed_event is not None
        assert failed_event.event_type == "fail_event"
        assert "Critical error" in failed_event.error_message


@pytest.mark.asyncio
async def test_outbox_worker_metadata_restoration(db_session, monkeypatch):
    worker = OutboxWorker()

    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="UserCreated",
        aggregate_type="User",
        aggregate_id="123",
        payload={"user_id": "123", "email": "test@example.com"},
        metadata_={
            "event_id": str(event_id),
            "correlation_id": "corr-123",
            "user_id": "user-456",
        },
    )
    db_session.add(se)
    await db_session.commit()

    dispatched_events = []

    async def mock_dispatch(event):
        dispatched_events.append(event)

    monkeypatch.setattr("app.core.events.event_bus.publish", mock_dispatch)

    processed_count = await worker.process_batch()
    assert processed_count == 1
    assert len(dispatched_events) == 1

    event = dispatched_events[0]
    assert event.event_id == str(event_id)
    assert event.metadata.correlation_id == "corr-123"
    assert event.metadata.user_id == "user-456"


@pytest.mark.asyncio
async def test_outbox_worker_empty_batch():
    worker = OutboxWorker()
    processed_count = await worker.process_batch()
    assert processed_count == 0


@pytest.mark.asyncio
async def test_outbox_worker_listen_loop(monkeypatch):
    from unittest.mock import AsyncMock

    import asyncpg

    worker = OutboxWorker(poll_interval=0.01)
    worker._is_running = True

    mock_conn = AsyncMock()
    mock_connect = AsyncMock(return_value=mock_conn)
    monkeypatch.setattr(asyncpg, "connect", mock_connect)

    # Let keepalive sleep exit the loop
    async def mock_sleep(seconds):
        worker._is_running = False

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    await worker._listen_loop()

    mock_connect.assert_called_once()
    mock_conn.add_listener.assert_called_once_with(
        worker.CHANNEL, worker._on_notification
    )
    mock_conn.execute.assert_called_once_with("SELECT 1")
    mock_conn.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires PostgreSQL — OutboxWorker uses asyncpg DSN format")
async def test_outbox_worker_run_stop():
    # Use a very small poll interval for testing
    worker = OutboxWorker(poll_interval=0.01)

    # Start in task
    task = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.05)
    assert worker._is_running is True

    # Stop
    await worker.stop()
    # Give it a moment to exit the loop
    await asyncio.wait_for(task, timeout=1.0)
    assert worker._is_running is False
