"""PostgreSQL concurrency regressions for transactional outbox aggregate ordering."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.models.domain_events import StoredEvent
from app.models.failed_outbox_events import FailedOutboxEvent
from app.workers import outbox as outbox_module
from app.workers.outbox import OutboxWorker, PermanentOutboxError

_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _RUN_INTEGRATION_TESTS,
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL outbox ordering regressions",
    ),
]


def _postgres_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = database.engine
    if (
        engine.dialect.name != "postgresql"
        or engine.url.drivername != "postgresql+asyncpg"
    ):
        pytest.fail(
            "outbox ordering concurrency proof requires PostgreSQL via asyncpg",
            pytrace=False,
        )
    return async_sessionmaker(engine, expire_on_commit=False)


def _event(
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
    sequence_number: int | None,
    created_at: datetime,
) -> StoredEvent:
    return StoredEvent(
        id=event_id or uuid.uuid4(),
        event_type="aud265.ordering_probe",
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        aggregate_id_uuid=aggregate_id,
        sequence_number=sequence_number,
        payload={},
        metadata_={},
        status="pending",
        error_count=0,
        created_at=created_at,
    )


async def _stored_events(
    session_factory: async_sessionmaker[AsyncSession],
    *event_ids: uuid.UUID,
) -> dict[uuid.UUID, StoredEvent]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(StoredEvent).where(StoredEvent.id.in_(event_ids))
            )
        ).all()
    return {row.id: row for row in rows}


async def test_locked_predecessor_blocks_successor_but_allows_another_aggregate(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker cannot skip a locked head, even when sequence values have gaps."""
    session_factory = _postgres_session_factory()
    base_time = datetime(2035, 1, 1, tzinfo=UTC)
    aggregate_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
    unrelated_aggregate_id = uuid.UUID("00000000-0000-4000-8000-000000000002")
    head = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        sequence_number=1,
        created_at=base_time,
    )
    successor = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        sequence_number=3,
        created_at=base_time + timedelta(seconds=1),
    )
    db_session.add_all([head, successor])
    await db_session.commit()

    head_locked = asyncio.Event()
    release_head = asyncio.Event()
    first_worker_dispatches: list[uuid.UUID] = []
    second_worker_dispatches: list[uuid.UUID] = []

    async def pause_on_head(event: StoredEvent) -> None:
        first_worker_dispatches.append(event.id)
        if event.id == head.id:
            head_locked.set()
            await release_head.wait()

    async def record_second_worker(event: StoredEvent) -> None:
        second_worker_dispatches.append(event.id)

    monkeypatch.setattr(outbox_module, "async_session", session_factory)
    first_worker = OutboxWorker(batch_size=1)
    second_worker = OutboxWorker(batch_size=1)
    monkeypatch.setattr(first_worker, "_dispatch_event", pause_on_head)
    monkeypatch.setattr(second_worker, "_dispatch_event", record_second_worker)

    first_batch = asyncio.create_task(first_worker.process_batch())
    first_batch_result: int
    try:
        await asyncio.wait_for(head_locked.wait(), timeout=5)
        unrelated = _event(
            aggregate_type="Probe",
            aggregate_id=unrelated_aggregate_id,
            sequence_number=1,
            created_at=base_time,
        )
        db_session.add(unrelated)
        await db_session.commit()

        assert await asyncio.wait_for(second_worker.process_batch(), timeout=5) == 1
        assert second_worker_dispatches == [unrelated.id]
        assert await asyncio.wait_for(second_worker.process_batch(), timeout=5) == 0
        assert second_worker_dispatches == [unrelated.id]
        assert (await _stored_events(session_factory, successor.id))[
            successor.id
        ].processed_at is None
    finally:
        release_head.set()
        first_batch_result = await asyncio.wait_for(first_batch, timeout=5)

    assert first_batch_result == 1
    assert first_worker_dispatches == [head.id]
    assert await asyncio.wait_for(second_worker.process_batch(), timeout=5) == 1
    assert second_worker_dispatches == [unrelated.id, successor.id]
    final_rows = await _stored_events(
        session_factory, head.id, successor.id, unrelated.id
    )
    assert final_rows[head.id].processed_at is not None
    assert final_rows[successor.id].processed_at is not None
    assert final_rows[unrelated.id].processed_at is not None


async def test_batch_orders_nullable_sequence_keys_and_scopes_aggregate_type(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequence, timestamp, and ID ties are stable; type scopes identical IDs."""
    session_factory = _postgres_session_factory()
    base_time = datetime(2035, 1, 2, tzinfo=UTC)
    aggregate_id = uuid.UUID("00000000-0000-4000-8000-000000000003")
    head = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000010"),
        sequence_number=1,
        created_at=base_time,
    )
    same_sequence_same_time = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000011"),
        sequence_number=1,
        created_at=base_time,
    )
    same_sequence_later_time = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        sequence_number=1,
        created_at=base_time + timedelta(seconds=1),
    )
    sequence_gap = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000013"),
        sequence_number=3,
        created_at=base_time + timedelta(seconds=2),
    )
    null_sequence_same_time_lower_id = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000012"),
        sequence_number=None,
        created_at=base_time - timedelta(seconds=1),
    )
    null_sequence_head = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000014"),
        sequence_number=None,
        created_at=base_time - timedelta(seconds=1),
    )
    null_sequence_successor = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000015"),
        sequence_number=None,
        created_at=base_time + timedelta(seconds=3),
    )
    same_id_other_type = _event(
        aggregate_type="ZOtherProbe",
        aggregate_id=aggregate_id,
        event_id=uuid.UUID("00000000-0000-4000-8000-000000000016"),
        sequence_number=None,
        created_at=base_time,
    )
    rows_in_order = [
        head,
        same_sequence_same_time,
        same_sequence_later_time,
        sequence_gap,
        null_sequence_same_time_lower_id,
        null_sequence_head,
        null_sequence_successor,
        same_id_other_type,
    ]
    db_session.add_all(rows_in_order)
    await db_session.commit()

    dispatched: list[uuid.UUID] = []

    async def record_dispatch(event: StoredEvent) -> None:
        dispatched.append(event.id)

    monkeypatch.setattr(outbox_module, "async_session", session_factory)
    worker = OutboxWorker(batch_size=10)
    monkeypatch.setattr(worker, "_dispatch_event", record_dispatch)

    assert await asyncio.wait_for(worker.process_batch(), timeout=5) == 2
    assert set(dispatched) == {head.id, same_id_other_type.id}
    expected_successors = [
        same_sequence_same_time.id,
        same_sequence_later_time.id,
        sequence_gap.id,
        null_sequence_same_time_lower_id.id,
        null_sequence_head.id,
        null_sequence_successor.id,
    ]
    for expected_id in expected_successors:
        assert await asyncio.wait_for(worker.process_batch(), timeout=5) == 1
        assert dispatched[-1] == expected_id
    assert await asyncio.wait_for(worker.process_batch(), timeout=5) == 0

    stored = await _stored_events(
        session_factory, *(event.id for event in rows_in_order)
    )
    assert all(stored[event.id].processed_at is not None for event in rows_in_order)


async def test_successfully_committed_terminal_dlq_releases_successor(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A terminal head stops blocking successors after its DLQ state commits."""
    session_factory = _postgres_session_factory()
    base_time = datetime(2035, 1, 3, tzinfo=UTC)
    aggregate_id = uuid.UUID("00000000-0000-4000-8000-000000000004")
    head = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        sequence_number=10,
        created_at=base_time,
    )
    successor = _event(
        aggregate_type="Probe",
        aggregate_id=aggregate_id,
        sequence_number=11,
        created_at=base_time + timedelta(seconds=1),
    )
    db_session.add_all([head, successor])
    await db_session.commit()

    dispatched: list[uuid.UUID] = []

    async def fail_terminal_head(event: StoredEvent) -> None:
        dispatched.append(event.id)
        if event.id == head.id:
            raise PermanentOutboxError("synthetic terminal delivery failure")

    monkeypatch.setattr(outbox_module, "async_session", session_factory)
    worker = OutboxWorker(batch_size=1, max_retries=1)
    monkeypatch.setattr(worker, "_dispatch_event", fail_terminal_head)

    assert await asyncio.wait_for(worker.process_batch(), timeout=5) == 1
    rows_after_dlq = await _stored_events(session_factory, head.id, successor.id)
    assert rows_after_dlq[head.id].processed_at is not None
    assert rows_after_dlq[successor.id].processed_at is None
    async with session_factory() as session:
        dlq_row = await session.scalar(
            select(FailedOutboxEvent).where(
                FailedOutboxEvent.original_event_id == head.id
            )
        )
    assert dlq_row is not None

    assert await asyncio.wait_for(worker.process_batch(), timeout=5) == 1
    assert dispatched == [head.id, successor.id]
    final_rows = await _stored_events(session_factory, successor.id)
    assert final_rows[successor.id].processed_at is not None
