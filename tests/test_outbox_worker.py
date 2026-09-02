import asyncio
import contextlib
import uuid

import pytest
from sqlalchemy import select

from app.models.domain_events import StoredEvent
from app.workers.outbox import OutboxWorker


@pytest.fixture(autouse=True)
def mock_outbox_session(db_session, monkeypatch):
    """Binds all async_session calls in this test module to the test's db_session transaction."""

    @contextlib.asynccontextmanager
    async def mock_async_session():
        yield db_session

    monkeypatch.setattr("app.workers.outbox.async_session", mock_async_session)
    monkeypatch.setattr("app.core.database.async_session", mock_async_session)


@pytest.mark.asyncio
async def test_outbox_worker_process_batch(db_session):
    worker = OutboxWorker()
    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="UserCreated",
        aggregate_type="User",
        aggregate_id="123",
        aggregate_id_uuid=uuid.uuid4(),
        sequence_number=1,
        payload={"user_id": "123", "email": "test@example.com"},
        metadata_={"correlation_id": "test-corr"},
    )
    db_session.add(se)
    await db_session.flush()

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
    await db_session.flush()

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
    await db_session.flush()

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
    await db_session.flush()

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
async def test_outbox_worker_run_stop(monkeypatch):
    # Use a very small poll interval for testing
    worker = OutboxWorker(poll_interval=0.01)

    async def mock_listen():
        # Mock listen loop that does nothing
        while worker._is_running:
            await asyncio.sleep(0.01)

    monkeypatch.setattr(worker, "_listen_loop", mock_listen)

    # Start in task
    task = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.02)
    assert worker._is_running is True

    # Trigger notification callback to cover _on_notification
    worker._on_notification()
    assert worker._wakeup_event.is_set()

    # Stop
    await worker.stop()
    # Give it a moment to exit the loop
    await asyncio.wait_for(task, timeout=1.0)
    assert worker._is_running is False


@pytest.mark.asyncio
async def test_outbox_worker_unknown_event_type(db_session, monkeypatch):
    worker = OutboxWorker()
    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="NonExistentEvent",
        aggregate_type="test_agg",
        aggregate_id="789",
        payload={"foo": "bar"},
        error_count=0,
    )
    db_session.add(se)
    await db_session.flush()

    processed_count = await worker.process_batch()
    assert processed_count == 1

    from app.core.database import async_session

    async with async_session() as db:
        result = await db.get(StoredEvent, event_id)
        assert result.error_count == 1
        assert result.processed_at is not None


@pytest.mark.asyncio
async def test_outbox_worker_dispatch_exception(db_session, monkeypatch):
    worker = OutboxWorker()
    event_id = uuid.uuid4()
    se = StoredEvent(
        id=event_id,
        event_type="UserCreated",
        aggregate_type="User",
        aggregate_id="123",
        payload={"user_id": "123", "email": "test@example.com"},
        error_count=0,
    )
    db_session.add(se)
    await db_session.flush()

    async def mock_publish_fail(*args, **kwargs):
        raise ValueError("Publish failed")

    monkeypatch.setattr("app.core.events.event_bus.publish", mock_publish_fail)

    processed_count = await worker.process_batch()
    assert processed_count == 1

    from app.core.database import async_session

    async with async_session() as db:
        result = await db.get(StoredEvent, event_id)
        assert result.error_count == 1
        assert "Publish failed" in result.last_error


@pytest.mark.asyncio
async def test_outbox_worker_listen_loop_exceptions(monkeypatch):
    import asyncpg

    worker = OutboxWorker(poll_interval=0.01)
    worker._is_running = True

    attempts = 0

    async def mock_connect_fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("Mock connection error")
        worker._is_running = False
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncpg, "connect", mock_connect_fail)

    async def mock_sleep(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    await worker._listen_loop()
    assert attempts == 2


@pytest.mark.asyncio
async def test_outbox_worker_main(monkeypatch):
    from unittest.mock import AsyncMock

    import app.workers.outbox
    from app.workers.outbox import main

    monkeypatch.setattr("app.core.database.init_database", lambda: None)

    async def mock_wait_db(*args, **kwargs):
        pass

    monkeypatch.setattr("app.core.database.wait_db", mock_wait_db)

    async def mock_register():
        pass

    monkeypatch.setattr("app.core.events.register_event_listeners", mock_register)
    monkeypatch.setattr(
        "app.services.event_handlers.configure_event_handlers", lambda: None
    )

    mock_run = AsyncMock()
    mock_stop = AsyncMock()
    monkeypatch.setattr(OutboxWorker, "run_forever", mock_run)
    monkeypatch.setattr(OutboxWorker, "stop", mock_stop)

    async def mock_wait_signals(stop_event):
        stop_event.set()

    monkeypatch.setattr(app.workers.outbox, "_wait_for_signals", mock_wait_signals)

    await main()
    mock_run.assert_called_once()
    mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_signals(monkeypatch):
    import signal

    from app.workers.outbox import _wait_for_signals

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    handlers = {}

    def mock_add_handler(sig, handler):
        handlers[sig] = handler

    monkeypatch.setattr(loop, "add_signal_handler", mock_add_handler)

    wait_task = asyncio.create_task(_wait_for_signals(stop_event))
    await asyncio.sleep(0.01)

    # If add_signal_handler is not implemented (e.g. on Windows), loop is bypassed
    # and signal.signal fallback is used, so SIGTERM might not be in handlers.
    # Let's handle both paths.
    if signal.SIGTERM in handlers:
        handlers[signal.SIGTERM]()
        await asyncio.wait_for(wait_task, timeout=1.0)
        assert stop_event.is_set()
    else:
        # Clean up task
        wait_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await wait_task


@pytest.mark.asyncio
async def test_wait_for_signals_not_implemented(monkeypatch):
    import signal

    from app.workers.outbox import _wait_for_signals

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def mock_add_handler(sig, handler):
        raise NotImplementedError()

    monkeypatch.setattr(loop, "add_signal_handler", mock_add_handler)

    signal_handlers = {}

    def mock_signal(sig, handler):
        signal_handlers[sig] = handler
        return None

    monkeypatch.setattr(signal, "signal", mock_signal)

    wait_task = asyncio.create_task(_wait_for_signals(stop_event))
    await asyncio.sleep(0.01)

    assert signal.SIGTERM in signal_handlers
    signal_handlers[signal.SIGTERM](None, None)

    await asyncio.wait_for(wait_task, timeout=1.0)
    assert stop_event.is_set()
