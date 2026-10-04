"""Delivery order and retry admission use persisted outbox state."""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.events import ChatParticipantRemoved, EventBus
from app.models.domain_events import StoredEvent
from app.workers.outbox import OutboxWorker


@pytest.fixture
def outbox_bus(db_session, monkeypatch):
    @contextlib.asynccontextmanager
    async def session():
        yield db_session

    bus = EventBus()
    monkeypatch.setattr("app.workers.outbox.async_session", session)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    return bus


def user_created(*, created_at, error_count=0, aggregate_id=None, sequence_number=None):
    user_id = aggregate_id or uuid.uuid4()
    return StoredEvent(
        id=uuid.uuid4(),
        event_type="user.created",
        aggregate_type="User",
        aggregate_id=str(user_id),
        aggregate_id_uuid=aggregate_id,
        sequence_number=sequence_number,
        payload={"user_id": str(user_id), "email": "user@example.test"},
        created_at=created_at,
        error_count=error_count,
    )


def membership_retry(*, created_at, error_count):
    chat_id = uuid.uuid4()
    return StoredEvent(
        id=uuid.uuid4(),
        event_type=ChatParticipantRemoved.EVENT_TYPE,
        aggregate_type="Chat",
        aggregate_id=str(chat_id),
        payload={"chat_id": str(chat_id), "user_id": str(uuid.uuid4())},
        created_at=created_at,
        error_count=error_count,
    )


@pytest.mark.asyncio
async def test_singleton_empty_batch_can_resume_delivery(db_session, outbox_bus):
    delivered = []

    async def record(event):
        delivered.append(event.event_id)

    outbox_bus.subscribe("user.created", record)
    worker = OutboxWorker(batch_size=1)
    assert await worker.process_batch() == 0
    row = user_created(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    db_session.add(row)
    await db_session.flush()
    assert await worker.process_batch() == 1
    assert delivered == [str(row.id)]
    await db_session.refresh(row)
    assert row.processed_at is not None
    assert await worker.process_batch() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 2])
async def test_aggregate_sequence_precedes_recording_time(
    db_session, outbox_bus, batch_size
):
    delivered = []

    async def record(event):
        delivered.append(event.event_id)

    outbox_bus.subscribe("user.created", record)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    aggregate_id = uuid.uuid4()
    first = user_created(
        created_at=timestamp + timedelta(seconds=1),
        aggregate_id=aggregate_id,
        sequence_number=1,
    )
    second = user_created(
        created_at=timestamp, aggregate_id=aggregate_id, sequence_number=2
    )
    db_session.add_all([second, first])
    await db_session.flush()
    worker = OutboxWorker(batch_size=batch_size)
    assert await worker.process_batch() == batch_size
    if batch_size == 1:
        await db_session.refresh(second)
        assert second.processed_at is None
        assert await worker.process_batch() == 1
    assert delivered == [str(first.id), str(second.id)]
    for row in (first, second):
        await db_session.refresh(row)
        assert row.processed_at is not None
        assert row.error_count == 0


@pytest.mark.asyncio
async def test_membership_retries_leave_a_slot_for_fresh_delivery(
    db_session, outbox_bus
):
    delivered = []

    async def record(event):
        delivered.append(event.event_id)

    outbox_bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, record)
    outbox_bus.subscribe("user.created", record)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    first_retry = membership_retry(created_at=timestamp, error_count=1)
    second_retry = membership_retry(
        created_at=timestamp + timedelta(seconds=1), error_count=1
    )
    fresh = user_created(created_at=timestamp + timedelta(seconds=2))
    db_session.add_all([first_retry, second_retry, fresh])
    await db_session.flush()
    worker = OutboxWorker(batch_size=2, max_retries=5)
    assert await worker.process_batch() == 2
    assert delivered == [str(first_retry.id), str(fresh.id)]
    await db_session.refresh(second_retry)
    assert second_retry.processed_at is None
    assert second_retry.error_count == 1
    assert await worker.process_batch() == 1
    assert delivered == [str(first_retry.id), str(fresh.id), str(second_retry.id)]


@pytest.mark.asyncio
async def test_ordinary_retry_cannot_take_the_reserved_membership_slot(
    db_session, outbox_bus
):
    delivered = []

    async def record(event):
        delivered.append(event.event_id)

    outbox_bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, record)
    outbox_bus.subscribe("user.created", record)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    ordinary_retry = user_created(created_at=timestamp, error_count=1)
    fresh = user_created(created_at=timestamp + timedelta(seconds=1))
    revoke_retry = membership_retry(
        created_at=timestamp + timedelta(seconds=2), error_count=2
    )
    db_session.add_all([ordinary_retry, fresh, revoke_retry])
    await db_session.flush()
    worker = OutboxWorker(batch_size=2, max_retries=5)
    assert await worker.process_batch() == 2
    assert delivered == [str(revoke_retry.id), str(ordinary_retry.id)]
    await db_session.refresh(fresh)
    assert fresh.processed_at is None
    await db_session.refresh(revoke_retry)
    assert revoke_retry.processed_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_attempts", [1, 2])
async def test_reduced_retry_budget_does_not_redeliver_exhausted_ordinary_events(
    db_session, outbox_bus, prior_attempts
):
    delivered = []
    delivery_available = False

    async def deliver(event):
        if not delivery_available:
            raise ConnectionError("delivery unavailable")
        delivered.append(event.event_id)

    outbox_bus.subscribe("user.created", deliver)
    outbox_bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, deliver)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    ordinary = user_created(created_at=timestamp)
    db_session.add(ordinary)
    await db_session.flush()
    initial_worker = OutboxWorker(max_retries=3)
    for _ in range(prior_attempts):
        assert await initial_worker.process_batch() == 1
    await db_session.refresh(ordinary)
    assert ordinary.error_count == prior_attempts
    assert ordinary.processed_at is None
    last_error = ordinary.last_error
    revoke = membership_retry(
        created_at=timestamp + timedelta(seconds=1), error_count=prior_attempts
    )
    db_session.add(revoke)
    await db_session.flush()
    delivery_available = True
    replacement_worker = OutboxWorker(max_retries=1, batch_size=2)
    assert await replacement_worker.process_batch() == 1
    assert delivered == [str(revoke.id)]
    await db_session.refresh(ordinary)
    assert ordinary.processed_at is None
    assert ordinary.error_count == prior_attempts
    assert ordinary.last_error == last_error
    await db_session.refresh(revoke)
    assert revoke.processed_at is not None
