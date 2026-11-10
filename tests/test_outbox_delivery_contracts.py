"""Delivery order and retry admission use persisted outbox state."""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

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
    # Each query selects at most one pending head per aggregate, even when the
    # batch has room for more rows. The next poll drains the newly eligible head.
    assert await worker.process_batch() == 1
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
    ordinary_retry = user_created(
        created_at=timestamp,
        error_count=1,
        aggregate_id=uuid.UUID("00000000-0000-4000-8000-00000000000a"),
    )
    fresh = user_created(
        created_at=timestamp + timedelta(seconds=1),
        aggregate_id=uuid.UUID("00000000-0000-4000-8000-00000000000b"),
    )
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
    # The immutable scheduling key is now (created_at, stored row ID), not
    # aggregate ID. Keep the ordinary competitor ahead of the retry in that
    # key so the second poll still proves reserved membership preemption.
    first.id = uuid.UUID(int=1)
    competing.id = uuid.UUID(int=2)
    retry.id = uuid.UUID(int=3)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 2, 20])
@pytest.mark.parametrize("worker_count", [1, 2])
async def test_deferred_heads_rotate_without_starving_independent_mfa(
    db_session, outbox_bus, monkeypatch, batch_size, worker_count
):
    from app.core.events import DurableEventDeferred

    log = MagicMock()
    monkeypatch.setattr("app.workers.outbox._deferred_logger", log)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    messages = [
        StoredEvent(
            id=uuid.uuid4(),
            event_type="chat.message_sent",
            aggregate_type="Message",
            aggregate_id=str(uuid.UUID(int=index + 1)),
            sequence_number=1,
            payload={},
            created_at=timestamp,
            error_count=0,
        )
        for index in range(3 * batch_size)
    ]
    successor = StoredEvent(
        id=uuid.uuid4(),
        event_type="chat.message_sent",
        aggregate_type="Message",
        aggregate_id=messages[0].aggregate_id,
        sequence_number=2,
        payload={},
        created_at=timestamp,
        error_count=0,
    )
    mfa = StoredEvent(
        id=uuid.uuid4(),
        event_type="auth.mfa_email.requested",
        aggregate_type="MfaChallenge",
        aggregate_id=str(uuid.uuid4()),
        payload={},
        created_at=timestamp,
        error_count=0,
    )
    db_session.add_all([*messages, successor, mfa])
    await db_session.flush()
    delivered = []
    attempted = []
    disconnected = True

    async def dispatch(event):
        attempted.append(event.id)
        if event.aggregate_type == "Message" and disconnected:
            raise DurableEventDeferred()
        delivered.append(event.id)

    workers = [OutboxWorker(batch_size=batch_size) for _ in range(worker_count)]
    for worker in workers:
        monkeypatch.setattr(worker, "_dispatch_event", dispatch)
    for index in range(4 * worker_count):
        await workers[index % worker_count].process_batch()
    assert delivered == [mfa.id]
    assert successor.id not in attempted
    assert log.info.call_count == len(attempted) - 1
    for call in log.info.call_args_list:
        assert call.args == ("outbox_event_deferred",)
        assert set(call.kwargs) == {"stored_event_id"}
        assert call.kwargs["stored_event_id"] in {str(row.id) for row in messages}
    assert set(row.id for row in messages) <= set(attempted)
    for row in messages:
        await db_session.refresh(row)
        assert row.processed_at is None
        assert row.error_count == 0
        assert row.last_error is None

    disconnected = False
    # A replacement worker starts with no cursor and still drains persisted rows.
    replacement = OutboxWorker(batch_size=batch_size)
    monkeypatch.setattr(replacement, "_dispatch_event", dispatch)
    for _ in range(5):
        await replacement.process_batch()
    assert set(delivered) == {row.id for row in [*messages, successor, mfa]}
    assert len(delivered) == len(messages) + 2
    assert delivered.index(messages[0].id) < delivered.index(successor.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 2, 20])
async def test_new_message_ingress_does_not_starve_older_mfa(
    db_session, outbox_bus, monkeypatch, batch_size
):
    from app.core.events import DurableEventDeferred

    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    mfa = StoredEvent(
        id=uuid.uuid4(),
        event_type="auth.mfa_email.requested",
        aggregate_type="MfaChallenge",
        aggregate_id=str(uuid.uuid4()),
        payload={},
        created_at=timestamp,
        error_count=0,
    )
    db_session.add(mfa)
    delivered = []

    async def dispatch(event):
        if event.aggregate_type == "Message":
            raise DurableEventDeferred()
        delivered.append(event.id)

    worker = OutboxWorker(batch_size=batch_size)
    monkeypatch.setattr(worker, "_dispatch_event", dispatch)
    for poll in range(8):
        db_session.add_all(
            StoredEvent(
                id=uuid.uuid4(),
                event_type="chat.message_sent",
                aggregate_type="Message",
                aggregate_id=str(uuid.UUID(int=1 + poll * batch_size + index)),
                payload={},
                created_at=timestamp + timedelta(seconds=1 + poll),
                error_count=0,
            )
            for index in range(batch_size)
        )
        await db_session.flush()
        await worker.process_batch()
    assert delivered == [mfa.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("late_kind", ["mfa", "causal_successor"])
async def test_bounded_sweep_revisits_old_keys_during_continuous_ingress(
    db_session, outbox_bus, monkeypatch, late_kind
):
    from app.core.events import DurableEventDeferred

    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    def message(index, *, created_at, sequence_number=1, aggregate_id=None):
        return StoredEvent(
            id=uuid.UUID(int=100 + index),
            event_type="chat.message_sent",
            aggregate_type="Message",
            aggregate_id=aggregate_id or str(uuid.UUID(int=100 + index)),
            sequence_number=sequence_number,
            payload={},
            created_at=created_at,
            error_count=0,
        )

    predecessor = message(0, created_at=timestamp)
    guard = message(1, created_at=timestamp + timedelta(seconds=1))
    db_session.add_all([predecessor, guard])
    await db_session.flush()
    recovered = False
    delivered = []

    async def dispatch(event):
        if event.id == predecessor.id and not recovered:
            raise DurableEventDeferred()
        if event.id not in {predecessor.id, late.id}:
            raise DurableEventDeferred()
        delivered.append(event.id)

    late = message(
        2,
        created_at=timestamp - timedelta(seconds=1),
        sequence_number=2,
        aggregate_id=predecessor.aggregate_id,
    )
    if late_kind == "mfa":
        late.event_type = "auth.mfa_email.requested"
        late.aggregate_type = "MfaChallenge"
        late.aggregate_id = str(uuid.uuid4())

    worker = OutboxWorker(batch_size=1)
    monkeypatch.setattr(worker, "_dispatch_event", dispatch)
    assert await worker.process_batch() == 0
    # Simulate an older transaction becoming visible after the cursor passed
    # its key; alternatively, this row is a successor with an older timestamp.
    db_session.add(late)
    await db_session.flush()
    recovered = True
    for poll in range(12):
        db_session.add(
            message(3 + poll, created_at=timestamp + timedelta(seconds=2 + poll))
        )
        await db_session.flush()
        await worker.process_batch()
    assert predecessor.id in delivered
    assert late.id in delivered
    assert len(delivered) == 2
    if late_kind == "causal_successor":
        assert delivered.index(predecessor.id) < delivered.index(late.id)
    for row in (predecessor, late):
        await db_session.refresh(row)
        assert row.processed_at is not None
        assert row.error_count == 0
        assert row.last_error is None


@pytest.mark.asyncio
async def test_fresh_membership_failure_consumes_ordinary_sweep_slot(
    db_session, outbox_bus
):
    async def fail(_event):
        raise RuntimeError("membership unavailable")

    outbox_bus.subscribe(ChatParticipantRemoved.EVENT_TYPE, fail)
    row = membership_retry(created_at=datetime(2026, 1, 1, tzinfo=UTC), error_count=0)
    db_session.add(row)
    await db_session.flush()
    worker = OutboxWorker(batch_size=1)
    assert await worker.process_batch() == 0
    assert row.error_count == 1
    assert worker._ordinary_sweep_remaining is None
    assert worker._ordinary_cursor is None


@pytest.mark.asyncio
async def test_failed_commit_does_not_advance_cursor_or_sweep_budget(
    db_session, outbox_bus, monkeypatch
):
    row = user_created(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    db_session.add(row)
    await db_session.flush()
    worker = OutboxWorker(batch_size=1)
    cursor = (datetime(2025, 1, 1, tzinfo=UTC), uuid.UUID(int=1))
    worker._ordinary_cursor = cursor
    worker._ordinary_sweep_remaining = 7
    monkeypatch.setattr(worker, "_dispatch_event", AsyncMock())
    monkeypatch.setattr(
        db_session, "commit", AsyncMock(side_effect=RuntimeError("commit failed"))
    )
    with pytest.raises(RuntimeError, match="commit failed"):
        await worker.process_batch()
    assert worker._ordinary_cursor == cursor
    assert worker._ordinary_sweep_remaining == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_fails", [False, True])
async def test_empty_snapshot_resets_scheduling_only_after_commit(
    db_session, outbox_bus, monkeypatch, commit_fails
):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    worker = OutboxWorker(batch_size=1)
    cursor = (timestamp, uuid.UUID(int=1))
    worker._ordinary_cursor = cursor
    worker._ordinary_sweep_remaining = 1_000_000
    if commit_fails:
        monkeypatch.setattr(
            db_session, "commit", AsyncMock(side_effect=RuntimeError("commit failed"))
        )
        with pytest.raises(RuntimeError, match="commit failed"):
            await worker.process_batch()
        assert worker._ordinary_cursor == cursor
        assert worker._ordinary_sweep_remaining == 1_000_000
        return

    assert await worker.process_batch() == 0
    assert worker._ordinary_cursor is None
    assert worker._ordinary_sweep_remaining is None
    # Another worker drained the old backlog. A refill with an older key must
    # not inherit a large stale sweep while newer messages keep arriving.
    older = user_created(created_at=timestamp - timedelta(seconds=1))
    db_session.add(older)
    delivered = []

    async def dispatch(event):
        from app.core.events import DurableEventDeferred

        if event.id != older.id:
            raise DurableEventDeferred()
        delivered.append(event.id)

    monkeypatch.setattr(worker, "_dispatch_event", dispatch)
    for poll in range(3):
        db_session.add(user_created(created_at=timestamp + timedelta(seconds=1 + poll)))
        await db_session.flush()
        await worker.process_batch()
    assert delivered == [older.id]
