"""Batch accounting must preserve every deferred durable event."""

import contextlib
import uuid

import pytest

from app.core.events import DurableEventDeferred, EventBus
from app.models.domain_events import StoredEvent
from app.workers.outbox import OutboxWorker


@pytest.mark.asyncio
async def test_multiple_durable_deferrals_are_excluded_from_completed_batch_count(
    db_session, monkeypatch
):
    # The worker must see flushed rows in this test's uncommitted transaction.
    # This is the same session binding used by test_outbox_worker.py.
    @contextlib.asynccontextmanager
    async def shared_session():
        yield db_session

    monkeypatch.setattr("app.workers.outbox.async_session", shared_session)
    monkeypatch.setattr("app.core.database.async_session", shared_session)
    user_ids = [str(uuid.uuid4()) for _ in range(3)]
    rows = [
        StoredEvent(
            id=uuid.uuid4(),
            event_type="user.created",
            aggregate_type="User",
            aggregate_id=user_id,
            payload={"user_id": user_id, "email": "user@example.test"},
            error_count=0,
        )
        for user_id in user_ids
    ]
    db_session.add_all(rows)
    await db_session.flush()
    deferred_users = set(user_ids[:2])
    delivered_users = []
    bus = EventBus()

    async def handler(event):
        if event.user_id in deferred_users:
            raise DurableEventDeferred()
        delivered_users.append(event.user_id)

    bus.subscribe("user.created", handler)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    worker = OutboxWorker(batch_size=3)

    assert await worker.process_batch() == 1
    assert delivered_users == [user_ids[2]]
    for index, row in enumerate(rows):
        await db_session.refresh(row)
        assert (row.processed_at is None) is (index < 2)
        assert row.error_count == 0
        assert row.last_error is None

    # Repeated polling of the two live leases must still report no completion.
    assert await worker.process_batch() == 0
    assert delivered_users == [user_ids[2]]
