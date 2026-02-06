import asyncio
import uuid

import pytest

from app.models.domain_events import StoredEvent
from app.workers.outbox import OutboxWorker


@pytest.mark.asyncio
async def test_outbox_worker_process_batch(db_session):
    worker = OutboxWorker()

    # Create a stored event
    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="test_event",
        aggregate_type="test_agg",
        aggregate_id="123",
        payload={"foo": "bar"},
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
