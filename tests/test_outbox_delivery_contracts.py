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


@pytest.mark.asyncio
async def test_batch_counts_only_success_when_multiple_membership_retries_fail(
    db_session, outbox_bus
):
    from sqlalchemy import select

    from app.models.failed_outbox_events import FailedOutboxEvent

    attempted_membership_retries: list[str] = []
    delivered_users: list[str] = []

    async def fail_membership_retry(event):
        attempted_membership_retries.append(event.event_id)
        raise RuntimeError("membership delivery unavailable")

    async def deliver_user_created(event):
        delivered_users.append(event.event_id)

    outbox_bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, fail_membership_retry)
    outbox_bus.subscribe("user.created", deliver_user_created)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    first_retry = membership_retry(created_at=timestamp, error_count=1)
    second_retry = membership_retry(
        created_at=timestamp + timedelta(seconds=1), error_count=1
    )
    successful = user_created(created_at=timestamp + timedelta(seconds=2))
    db_session.add_all([first_retry, second_retry, successful])
    await db_session.flush()

    worker = OutboxWorker(batch_size=3, max_retries=1)
    assert await worker.process_batch() == 1

    retry_ids = sorted((str(first_retry.id), str(second_retry.id)))
    assert sorted(attempted_membership_retries) == retry_ids
    assert delivered_users == [str(successful.id)]

    for retry in (first_retry, second_retry):
        await db_session.refresh(retry)
        assert retry.processed_at is None
        assert retry.error_count == 2
        assert retry.last_error is not None
        assert (
            await db_session.scalar(
                select(FailedOutboxEvent.id).where(
                    FailedOutboxEvent.original_event_id == retry.id
                )
            )
            is None
        )

    await db_session.refresh(successful)
    assert successful.processed_at is not None
    assert successful.error_count == 0


@pytest.mark.asyncio
async def test_singleton_membership_retry_preempts_lower_uuid_ordinary_event(
    db_session, outbox_bus
):
    attempted_membership_retries: list[str] = []
    delivered_users: list[str] = []

    async def fail_membership_retry(event):
        attempted_membership_retries.append(event.event_id)
        raise RuntimeError("membership delivery unavailable")

    async def deliver_user_created(event):
        delivered_users.append(event.event_id)

    outbox_bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, fail_membership_retry)
    outbox_bus.subscribe("user.created", deliver_user_created)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    first_aggregate = uuid.UUID("a1111111-1111-4111-8111-111111111111")
    competing_aggregate = uuid.UUID("b2222222-2222-4222-8222-222222222222")
    retry_aggregate = uuid.UUID("c3333333-3333-4333-8333-333333333333")
    first = user_created(
        created_at=timestamp,
        aggregate_id=first_aggregate,
        sequence_number=1,
    )
    competing = user_created(
        created_at=timestamp,
        aggregate_id=competing_aggregate,
        sequence_number=1,
    )
    retry = membership_retry(created_at=timestamp, error_count=1)
    retry.aggregate_id = str(retry_aggregate)
    retry.aggregate_id_uuid = retry_aggregate
    retry.sequence_number = 1
    retry.payload["chat_id"] = str(retry_aggregate)
    db_session.add_all([first, competing, retry])
    await db_session.flush()

    worker = OutboxWorker(batch_size=1, max_retries=5)
    assert await worker.process_batch() == 1
    assert delivered_users == [str(first.id)]

    assert await worker.process_batch() == 0
    assert attempted_membership_retries == [str(retry.id)]
    assert delivered_users == [str(first.id)]

    await db_session.refresh(first)
    await db_session.refresh(competing)
    await db_session.refresh(retry)
    assert first.processed_at is not None
    assert competing.processed_at is None
    assert competing.error_count == 0
    assert retry.processed_at is None
    assert retry.error_count == 2
