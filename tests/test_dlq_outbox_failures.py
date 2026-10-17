"""Operator view and requeue for outbox events that exhausted their retries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api import dlq
from app.models.domain_events import StoredEvent
from app.models.failed_outbox_events import FailedOutboxEvent
from tests.conftest import call_injected


async def _dead_letter(
    db, *, event_type: str = "news.created", resolved: bool = False
) -> tuple[StoredEvent, FailedOutboxEvent]:
    now = datetime.now(UTC)
    stored = StoredEvent(
        event_type=event_type,
        aggregate_type="News",
        aggregate_id=str(uuid.uuid4()),
        payload={"k": "v"},
        status="failed",
        error_count=5,
        last_error="boom",
        processed_at=now,
    )
    db.add(stored)
    await db.flush()
    failure = FailedOutboxEvent(
        original_event_id=stored.id,
        event_type=event_type,
        aggregate_type="News",
        aggregate_id=stored.aggregate_id,
        payload={"k": "v"},
        error_message="boom " * 100,
        retry_count=5,
        failed_at=now,
        resolved_at=now if resolved else None,
    )
    db.add(failure)
    await db.flush()
    return stored, failure


@pytest.mark.asyncio
async def test_unresolved_count_ignores_resolved_failures(db_session):
    await _dead_letter(db_session)
    await _dead_letter(db_session, resolved=True)
    assert await dlq._count_unresolved_outbox_failures(db_session) == 1


@pytest.mark.asyncio
async def test_list_outbox_failures_hides_resolved_by_default(db_session):
    _, open_failure = await _dead_letter(db_session)
    await _dead_letter(db_session, resolved=True)

    default = await call_injected(
        dlq.list_outbox_failures,
        include_resolved=False,
        limit=20,
        _=None,
        provides={"AsyncDatabaseSession": db_session},
    )
    everything = await call_injected(
        dlq.list_outbox_failures,
        include_resolved=True,
        limit=50,
        _=None,
        provides={"AsyncDatabaseSession": db_session},
    )

    assert default.total == 1
    assert default.failures[0].id == str(open_failure.id)
    assert len(default.failures[0].error_message) == 200
    assert default.failures[0].resolved_at is None
    assert everything.total == 2
    assert {item.resolved_at is None for item in everything.failures} == {True, False}


@pytest.mark.asyncio
async def test_requeue_restores_original_event_and_resolves_failure(db_session):
    stored, failure = await _dead_letter(db_session)

    result = await call_injected(
        dlq.requeue_outbox_failure,
        failure.id,
        locale="en",
        _=None,
        provides={"AsyncDatabaseSession": db_session},
    )

    assert result == {"success": True, "event_type": "news.created"}
    await db_session.refresh(stored)
    await db_session.refresh(failure)
    assert stored.processed_at is None
    assert stored.error_count == 0
    assert stored.last_error is None
    assert stored.status == "pending"
    assert failure.resolved_at is not None
    assert failure.resolution_note == "requeued by administrator"


async def _requeue(db_session, failure_id):
    return await call_injected(
        dlq.requeue_outbox_failure,
        failure_id,
        locale="en",
        _=None,
        provides={"AsyncDatabaseSession": db_session},
    )


@pytest.mark.asyncio
async def test_requeue_unknown_failure_is_404(db_session):
    with pytest.raises(HTTPException) as error:
        await _requeue(db_session, uuid.uuid4())
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_requeue_resolved_failure_is_conflict(db_session):
    _, failure = await _dead_letter(db_session, resolved=True)
    with pytest.raises(HTTPException) as error:
        await _requeue(db_session, failure.id)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_requeue_of_shredded_mfa_event_is_conflict(db_session):
    stored, failure = await _dead_letter(
        db_session, event_type="auth.mfa_email.requested"
    )
    with pytest.raises(HTTPException) as error:
        await _requeue(db_session, failure.id)
    assert error.value.status_code == 409
    await db_session.refresh(stored)
    assert stored.processed_at is not None


@pytest.mark.asyncio
async def test_requeue_without_original_event_is_404(db_session):
    stored, failure = await _dead_letter(db_session)
    await db_session.delete(stored)
    await db_session.flush()
    with pytest.raises(HTTPException) as error:
        await _requeue(db_session, failure.id)
    assert error.value.status_code == 404
    unresolved = (
        await db_session.execute(
            select(FailedOutboxEvent).where(FailedOutboxEvent.id == failure.id)
        )
    ).scalar_one()
    assert unresolved.resolved_at is None
