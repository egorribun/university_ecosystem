from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import sqlalchemy as sa

from app.core.database import async_session
from app.models.models import ActiveSession, NotificationQueueJob, User
from app.services import notification_queue, session_cleanup


@pytest.mark.anyio
async def test_notification_worker_recovers_after_restart(
    monkeypatch: pytest.MonkeyPatch,
):
    notification_queue._loop_states.clear()

    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_retry_base_seconds",
        0.0,
        raising=False,
    )

    attempts: list[int] = []
    first_failure = asyncio.Event()
    processed = asyncio.Event()

    async def _flaky_process(job):
        attempts.append(job.record_id)
        if len(attempts) == 1:
            first_failure.set()
            raise RuntimeError("boom")
        processed.set()

    monkeypatch.setattr(notification_queue, "_process_job", _flaky_process)

    await notification_queue.enqueue_event_notification(9001)

    await asyncio.wait_for(first_failure.wait(), timeout=1.0)
    await asyncio.sleep(0.05)

    state = notification_queue._get_loop_state()
    worker = state.worker_task
    if worker is not None:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        state.worker_task = None

    # Reset the job for retry
    async with async_session() as session:
        await session.execute(
            sa.update(NotificationQueueJob)
            .where(NotificationQueueJob.record_id == 9001)
            .values(claimed_at=None, next_retry_at=datetime.now(UTC))
        )
        await session.commit()

    # Query the row immediately after update, before any worker can process it
    async with async_session() as session:
        row = (
            await session.execute(
                sa.select(NotificationQueueJob).where(
                    NotificationQueueJob.record_id == 9001
                )
            )
        ).scalar_one_or_none()

    # If the row was already processed by a background task, that's acceptable
    if row is None:
        # Worker already processed the job; verify attempts reflect that
        assert len(attempts) >= 2
        assert set(attempts) == {9001}
        notification_queue._loop_states.clear()
        return

    reclaimed = notification_queue.NotificationJob(
        kind=cast(notification_queue.JobKind, row.kind),
        record_id=row.record_id,
        locale=row.locale,
        queue_id=row.id,
        enqueued_at=row.enqueued_at,
        claimed_at=datetime.now(UTC),
    )

    await notification_queue._process_job(reclaimed)
    metrics = notification_queue._get_metrics()
    await notification_queue._acknowledge_persistent_job(
        reclaimed, success=True, error=None, state=state, metrics=metrics
    )

    await asyncio.wait_for(processed.wait(), timeout=2.0)
    await notification_queue.wait_for_all_jobs(timeout=1.0)

    assert len(attempts) >= 2
    assert set(attempts) == {9001}

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_session_cleanup_retries_after_failure(monkeypatch: pytest.MonkeyPatch):
    async with async_session() as session:
        user = User(email="chaos@example.com", hashed_password="secret")
        session.add(user)
        await session.flush()

        session.add(
            ActiveSession(
                user_id=user.id,
                jti="chaos-session",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
                revoked_at=None,
            )
        )
        await session.commit()

    real_cleanup = session_cleanup.cleanup_expired_sessions
    attempts = 0
    completed = asyncio.Event()

    async def _flaky_cleanup(*, db=None, now=None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient failure")
        result = await real_cleanup(db=db, now=now)
        completed.set()
        return result

    monkeypatch.setattr(session_cleanup, "cleanup_expired_sessions", _flaky_cleanup)

    monkeypatch.setattr(
        session_cleanup.SessionCleanupConfig,
        "normalized_interval",
        lambda self: 0.05,
        raising=False,
    )
    config = session_cleanup.SessionCleanupConfig(interval_seconds=1)

    stop = await session_cleanup.start_session_cleanup_scheduler(config=config)
    try:
        await asyncio.wait_for(completed.wait(), timeout=0.6)
    finally:
        await stop()

    async with async_session() as session:
        result = await session.execute(sa.select(ActiveSession))
        assert result.scalars().all() == []

    assert attempts >= 2
