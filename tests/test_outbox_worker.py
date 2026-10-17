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
async def test_outbox_worker_process_batch(db_session, monkeypatch):
    from app.core.events import EventBus

    bus = EventBus()

    async def handle_user_created(_event):
        return None

    bus.subscribe("user.created", handle_user_created)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
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
async def test_chat_participant_removed_retries_past_dlq_limit_without_blocking_batch(
    db_session, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.core.events import ChatParticipantRemoved, EventBus
    from app.models.failed_outbox_events import FailedOutboxEvent

    bus = EventBus()
    revoke_id = uuid.uuid4()
    healthy_id = uuid.uuid4()
    revoke_user_id = uuid.uuid4()
    healthy_user_id = uuid.uuid4()
    dispatched_ids: list[str] = []

    async def handle_participant_removed(event):
        dispatched_ids.append(event.event_id)
        if event.user_id == str(revoke_user_id):
            raise RuntimeError("JetStream is temporarily unavailable")

    bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, handle_participant_removed)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    worker = OutboxWorker(max_retries=1, batch_size=1)
    created_at = datetime.now(UTC)

    revoke_event = StoredEvent(
        id=revoke_id,
        event_type=ChatParticipantRemoved.EVENT_TYPE,
        aggregate_type="Chat",
        aggregate_id=str(uuid.uuid4()),
        aggregate_id_uuid=None,
        sequence_number=None,
        payload={"chat_id": str(uuid.uuid4()), "user_id": str(revoke_user_id)},
        created_at=created_at - timedelta(seconds=1),
    )
    healthy_event = StoredEvent(
        id=healthy_id,
        event_type=ChatParticipantRemoved.EVENT_TYPE,
        aggregate_type="Chat",
        aggregate_id=str(uuid.uuid4()),
        aggregate_id_uuid=None,
        sequence_number=None,
        payload={"chat_id": str(uuid.uuid4()), "user_id": str(healthy_user_id)},
        created_at=created_at,
    )
    db_session.add_all([revoke_event, healthy_event])
    await db_session.flush()

    assert await worker.process_batch() == 0

    revoke_state = await db_session.get(StoredEvent, revoke_id)
    healthy_state = await db_session.get(StoredEvent, healthy_id)
    assert revoke_state is not None
    assert healthy_state is not None
    assert revoke_state.processed_at is None
    assert revoke_state.error_count == 1
    assert healthy_state.processed_at is None
    failed_event = await db_session.scalar(
        select(FailedOutboxEvent).where(
            FailedOutboxEvent.original_event_id == revoke_id
        )
    )
    assert failed_event is None

    assert await worker.process_batch() == 1

    healthy_state = await db_session.get(StoredEvent, healthy_id)
    assert healthy_state is not None
    assert healthy_state.processed_at is not None

    assert await worker.process_batch() == 0

    refreshed_revoke_state = await db_session.get(StoredEvent, revoke_id)
    assert refreshed_revoke_state is not None
    assert refreshed_revoke_state.processed_at is None
    assert refreshed_revoke_state.error_count == 2
    assert dispatched_ids.count(str(revoke_id)) == 2
    assert dispatched_ids.count(str(healthy_id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 3])
async def test_chat_participant_removed_retry_progresses_during_sustained_first_attempt_arrivals(
    db_session, monkeypatch, batch_size
):
    from app.core.events import ChatParticipantRemoved, EventBus
    from app.models.failed_outbox_events import FailedOutboxEvent

    bus = EventBus()
    revoke_id = uuid.uuid4()
    retry_event_ids: list[str] = []
    normal_event_ids: list[str] = []
    worker = OutboxWorker(max_retries=1, batch_size=batch_size)

    def make_user_created_event() -> StoredEvent:
        event_id = uuid.uuid4()
        return StoredEvent(
            id=event_id,
            event_type="UserCreated",
            aggregate_type="User",
            aggregate_id=str(event_id),
            aggregate_id_uuid=event_id,
            sequence_number=1,
            payload={"user_id": str(event_id), "email": "test@example.com"},
        )

    async def handle_participant_removed(event):
        retry_event_ids.append(event.event_id)
        raise RuntimeError("JetStream is temporarily unavailable")

    async def handle_user_created(event):
        normal_event_ids.append(event.event_id)
        # Keep a fresh first-attempt event available after every ordinary
        # dispatch, modeling a sustained arrival stream.
        db_session.add(make_user_created_event())
        await db_session.flush()
        raise RuntimeError("The ordinary event is also temporarily unavailable")

    bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, handle_participant_removed)
    bus.subscribe("user.created", handle_user_created)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)

    revoke_event = StoredEvent(
        id=revoke_id,
        event_type=ChatParticipantRemoved.EVENT_TYPE,
        aggregate_type="Chat",
        aggregate_id=str(uuid.uuid4()),
        aggregate_id_uuid=None,
        sequence_number=None,
        payload={"chat_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
        error_count=1,
    )
    db_session.add(revoke_event)
    db_session.add_all(make_user_created_event() for _ in range(batch_size))
    await db_session.flush()

    batch_results = [await worker.process_batch() for _ in range(6)]

    assert retry_event_ids, (
        "a continuous stream of first attempts starved the revoke retry"
    )
    assert retry_event_ids == [str(revoke_id)] * len(retry_event_ids)
    assert len(normal_event_ids) == len(set(normal_event_ids))
    if batch_size == 1:
        assert len(retry_event_ids) >= 3
        assert len(normal_event_ids) >= 3
        assert batch_results == [1, 0, 1, 0, 1, 0]
    else:
        assert len(retry_event_ids) == 6
        assert len(normal_event_ids) >= (batch_size - 1) * 6
        assert batch_results == [batch_size - 1] * 6

    retry_state = await db_session.get(StoredEvent, revoke_id)
    assert retry_state is not None
    assert retry_state.processed_at is None
    assert retry_state.error_count == 1 + len(retry_event_ids)
    assert (
        await db_session.scalar(
            select(FailedOutboxEvent).where(
                FailedOutboxEvent.original_event_id == revoke_id
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_membership_retry_progresses_during_continuous_membership_first_attempts(
    db_session, monkeypatch
):
    from app.core.events import ChatParticipantRemoved, EventBus
    from app.models.failed_outbox_events import FailedOutboxEvent

    bus = EventBus()
    retry_id = uuid.uuid4()
    seen_event_ids = {str(retry_id)}
    first_attempt_ids: list[str] = []
    retry_attempt_ids: list[str] = []
    worker = OutboxWorker(max_retries=1, batch_size=1)

    def make_membership_event() -> StoredEvent:
        event_id = uuid.uuid4()
        return StoredEvent(
            id=event_id,
            event_type=ChatParticipantRemoved.EVENT_TYPE,
            aggregate_type="Chat",
            aggregate_id=str(event_id),
            aggregate_id_uuid=None,
            sequence_number=None,
            payload={"chat_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
        )

    async def handle_participant_removed(event):
        if event.event_id in seen_event_ids:
            retry_attempt_ids.append(event.event_id)
        else:
            seen_event_ids.add(event.event_id)
            first_attempt_ids.append(event.event_id)
            db_session.add(make_membership_event())
            await db_session.flush()
        raise RuntimeError("JetStream is temporarily unavailable")

    bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, handle_participant_removed)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    db_session.add(
        StoredEvent(
            id=retry_id,
            event_type=ChatParticipantRemoved.EVENT_TYPE,
            aggregate_type="Chat",
            aggregate_id=str(uuid.uuid4()),
            aggregate_id_uuid=None,
            sequence_number=None,
            payload={"chat_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
            error_count=1,
        )
    )
    db_session.add(make_membership_event())
    await db_session.flush()

    for _ in range(8):
        await worker.process_batch()

    assert retry_attempt_ids, "new membership first attempts starved a revocation retry"
    assert retry_attempt_ids.count(str(retry_id)) >= 3
    assert len(first_attempt_ids) >= 3
    retry_state = await db_session.get(StoredEvent, retry_id)
    assert retry_state is not None
    assert retry_state.error_count >= 4
    assert retry_state.processed_at is None
    assert (
        await db_session.scalar(
            select(FailedOutboxEvent).where(
                FailedOutboxEvent.original_event_id == retry_id
            )
        )
        is None
    )


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

    async def mock_dispatch(event, *, durable=False):
        assert durable is True
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
@pytest.mark.parametrize("payload_event_id", [None, "payload-event-id"])
async def test_outbox_retry_uses_stored_id_without_explicit_event_metadata(
    monkeypatch,
    payload_event_id,
):
    worker = OutboxWorker()
    stored_id = uuid.uuid4()
    event = StoredEvent(
        id=stored_id,
        event_type="UserCreated",
        aggregate_type="User",
        aggregate_id="123",
        payload={
            "user_id": "123",
            "email": "test@example.com",
            **({"event_id": payload_event_id} if payload_event_id else {}),
        },
        metadata_={},
    )
    dispatched_ids = []

    async def capture(published, *, durable=False):
        assert durable is True
        dispatched_ids.append(published.event_id)

    monkeypatch.setattr("app.workers.outbox.event_bus.publish", capture)
    await worker._dispatch_event(event)
    await worker._dispatch_event(event)
    expected_id = payload_event_id or str(stored_id)
    assert dispatched_ids == [expected_id, expected_id]


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
async def test_outbox_worker_heartbeat_without_path_returns():
    await OutboxWorker()._heartbeat_loop()


@pytest.mark.asyncio
async def test_outbox_worker_heartbeat_runs_until_shutdown(tmp_path, monkeypatch):
    heartbeat_path = tmp_path / "worker.heartbeat"
    worker = OutboxWorker(heartbeat_path=heartbeat_path, heartbeat_interval=0.001)

    async def mock_listen():
        while worker._is_running:
            await asyncio.sleep(0.001)

    async def mock_process_batch():
        while not heartbeat_path.exists():
            await asyncio.sleep(0)
        await worker.stop()
        return 0

    monkeypatch.setattr(worker, "_listen_loop", mock_listen)
    monkeypatch.setattr(worker, "process_batch", mock_process_batch)

    await worker.run_forever()

    assert heartbeat_path.exists()


def test_outbox_module_cli_guard_invokes_main(monkeypatch):
    import runpy
    from pathlib import Path

    run_calls = []

    def capture_run(coroutine):
        run_calls.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", capture_run)
    script = Path(__file__).resolve().parents[1] / "app" / "workers" / "outbox.py"

    runpy.run_path(str(script), run_name="__main__")

    assert len(run_calls) == 1


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
async def test_durable_outbox_handler_failure_retries_without_pii(
    db_session, monkeypatch, caplog
):
    worker = OutboxWorker()
    event_id = uuid.uuid4()
    db_session.add(
        StoredEvent(
            id=event_id,
            event_type="user.created",
            aggregate_type="User",
            aggregate_id="123",
            payload={"user_id": "123", "email": "user@example.test"},
            error_count=0,
        )
    )
    await db_session.flush()

    from app.core.events import EventBus

    bus = EventBus()
    attempts = 0

    async def handler(_event):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("recipient user@example.test, code 123456")

    bus.subscribe("user.created", handler)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)

    assert await worker.process_batch() == 1
    from app.core.database import async_session

    async with async_session() as db:
        stored = await db.get(StoredEvent, event_id)
        assert stored is not None
        assert stored.processed_at is None
        assert stored.error_count == 1
        assert "Durable event handler failed" in stored.last_error
        assert "user@example.test" not in stored.last_error
        assert "123456" not in stored.last_error
    assert "user@example.test" not in caplog.text
    assert "123456" not in caplog.text

    assert await worker.process_batch() == 1
    async with async_session() as db:
        stored = await db.get(StoredEvent, event_id)
        assert stored is not None
        assert stored.processed_at is not None
        assert stored.error_count == 1
    assert attempts == 2


@pytest.mark.asyncio
async def test_durable_outbox_deferral_preserves_retry_budget_and_pending_event(
    db_session, monkeypatch
):
    from app.core.events import DurableEventDeferred, EventBus

    worker = OutboxWorker(batch_size=1)
    event_id = uuid.uuid4()
    db_session.add(
        StoredEvent(
            id=event_id,
            event_type="user.created",
            aggregate_type="User",
            aggregate_id="123",
            payload={"user_id": "123", "email": "user@example.test"},
            error_count=0,
        )
    )
    await db_session.flush()
    bus = EventBus()
    attempts = 0

    async def handler(_event):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise DurableEventDeferred()

    bus.subscribe("user.created", handler)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)

    assert await worker.process_batch() == 0
    from app.core.database import async_session

    async with async_session() as db:
        stored = await db.get(StoredEvent, event_id)
        assert stored is not None
        assert stored.processed_at is None
        assert stored.error_count == 0
        assert stored.last_error is None

    assert await worker.process_batch() == 1
    async with async_session() as db:
        stored = await db.get(StoredEvent, event_id)
        assert stored is not None
        assert stored.processed_at is not None
        assert stored.error_count == 0
    assert attempts == 2


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
