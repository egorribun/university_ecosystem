"""Exercise the real DLQ worker/admin retry interleaving on PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dlq import retry_dlq_job
from app.core.localization import translate
from app.models import DeadLetterJob, JobStatus
from app.workers.dead_letter_queue import DeadLetterQueue, compute_job_hash
from tests.conftest import call_injected

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for PostgreSQL concurrency coverage",
    ),
]


async def _wait_for_admin_lock_wait(
    observer: AsyncSession, admin_pid: int, worker_pid: int
) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 3.0
    while (remaining := deadline - loop.time()) > 0:
        query = await asyncio.wait_for(
            observer.scalar(
                text(
                    "SELECT query FROM pg_stat_activity "
                    "WHERE pid = :admin_pid AND state = 'active' "
                    "AND wait_event_type = 'Lock' "
                    "AND :worker_pid = ANY(pg_blocking_pids(pid))"
                ),
                {"admin_pid": admin_pid, "worker_pid": worker_pid},
            ),
            timeout=remaining,
        )
        # pg_stat_activity must be observed in a fresh transaction each time.
        await observer.rollback()
        if query:
            return str(query)
        await asyncio.sleep(min(0.02, max(0.0, deadline - loop.time())))
    raise AssertionError("Admin retry did not wait on the replay worker's row lock")


@pytest.mark.asyncio
async def test_retry_completed_job_waits_for_worker_and_preserves_state(db_session):
    assert db_session.bind.dialect.name == "postgresql"
    now = datetime.now(UTC)
    due_at = now - timedelta(minutes=1)
    eligible = select(DeadLetterJob.id).where(
        DeadLetterJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRYING.value]),
        DeadLetterJob.next_retry_at <= now,
    )
    assert list((await db_session.scalars(eligible)).all()) == [], (
        "The integration database must have no pre-existing due DLQ jobs"
    )
    job_type = "dlq.retry-race"
    payload = {"regression_id": uuid4().hex}
    job = DeadLetterJob(
        job_type=job_type,
        job_hash=compute_job_hash(job_type, payload),
        payload=json.dumps(payload),
        error_message="Regression seed",
        retry_count=2,
        max_retries=5,
        status=JobStatus.PENDING.value,
        next_retry_at=due_at,
        created_at=due_at,
        updated_at=due_at,
    )
    db_session.add(job)
    await db_session.flush()
    job_id = job.id
    await db_session.commit()
    assert list((await db_session.scalars(eligible)).all()) == [job_id]
    await db_session.rollback()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    worker = session_factory()
    admin = session_factory()
    admin_task: asyncio.Task[Any] | None = None
    primary_error: BaseException | None = None

    try:
        isolation = await worker.scalar(text("SHOW transaction_isolation"))
        assert isolation == "read committed"
        stale_admin_job = await admin.get(DeadLetterJob, job_id)
        assert stale_admin_job is not None
        assert stale_admin_job.status == JobStatus.PENDING.value
        assert stale_admin_job.retry_count == 2
        admin_pid = int(await admin.scalar(text("SELECT pg_backend_pid()")))
        worker_pid = int(await worker.scalar(text("SELECT pg_backend_pid()")))
        assert admin_pid != worker_pid

        handler_calls: list[tuple[str, dict[str, Any]]] = []

        async def successful_handler(
            received_type: str, received_payload: dict[str, Any]
        ) -> None:
            handler_calls.append((received_type, received_payload))

        replay_result = await asyncio.wait_for(
            DeadLetterQueue(worker).auto_replay_jobs(
                successful_handler,
                batch_size=1,
                max_batches=1,
                rate_limit_delay=0,
            ),
            timeout=5,
        )
        assert replay_result == (1, 0)
        assert handler_calls == [(job_type, payload)]
        worker_job = await worker.get(DeadLetterJob, job_id)
        assert worker_job is not None
        assert worker_job.status == JobStatus.COMPLETED.value
        assert worker_job.retry_count == 3
        assert worker_job.next_retry_at == due_at
        worker_updated_at = worker_job.updated_at
        assert worker_updated_at != due_at

        async def invoke_retry() -> Any:
            try:
                return await call_injected(
                    retry_dlq_job,
                    job_id=job_id,
                    provides={"AsyncDatabaseSession": admin},
                    locale="en",
                    _=None,
                )
            except HTTPException as exc:
                return exc

        admin_task = asyncio.create_task(invoke_retry())
        waiting_query = await _wait_for_admin_lock_wait(
            db_session, admin_pid, worker_pid
        )
        normalized_query = " ".join(waiting_query.lower().split())
        # A blocked UPDATE would be too late: the decision must follow a
        # locking SELECT that refreshes the stale admin identity-map object.
        assert normalized_query.startswith("select")
        assert "dead_letter_jobs" in normalized_query
        assert "for update" in normalized_query

        await worker.commit()
        response = await asyncio.wait_for(admin_task, timeout=5)
        admin_task = None
        assert isinstance(response, HTTPException)
        assert response.status_code == 409
        assert response.detail == translate("errors.dlq.already_resolved", locale="en")
        expected = (JobStatus.COMPLETED.value, 3, due_at, worker_updated_at)
        assert (
            stale_admin_job.status,
            stale_admin_job.retry_count,
            stale_admin_job.next_retry_at,
            stale_admin_job.updated_at,
        ) == expected

        await admin.rollback()
        await db_session.rollback()
        persisted = await db_session.scalar(
            select(DeadLetterJob)
            .where(DeadLetterJob.id == job_id)
            .execution_options(populate_existing=True)
        )
        assert persisted is not None
        assert (
            persisted.status,
            persisted.retry_count,
            persisted.next_retry_at,
            persisted.updated_at,
        ) == expected
    except BaseException as error:
        primary_error = error
        raise
    finally:
        # Release the worker first, then drain the admin and close both sessions.
        # Cleanup failures remain visible even when an assertion already failed.
        cleanup_errors: list[BaseException] = []
        try:
            await asyncio.wait_for(worker.rollback(), timeout=5)
        except BaseException as error:
            cleanup_errors.append(error)
        if admin_task is not None:
            try:
                await asyncio.wait_for(admin_task, timeout=5)
            except BaseException as error:
                if error is not primary_error:
                    cleanup_errors.append(error)
        for session in (admin, worker):
            try:
                await asyncio.wait_for(session.close(), timeout=5)
            except BaseException as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            errors = (
                [primary_error] if primary_error is not None else []
            ) + cleanup_errors
            raise BaseExceptionGroup("DLQ interleaving test cleanup failed", errors)
