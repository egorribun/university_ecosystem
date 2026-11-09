from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dlq import list_dlq_jobs
from app.models.dead_letter import DeadLetterJob


@pytest_asyncio.fixture
async def dlq_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(DeadLetterJob.__table__.create)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _job(
    *,
    job_type: str,
    error_message: str | None,
    status: str,
    index: int,
    payload: str = "{}",
) -> DeadLetterJob:
    created = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    return DeadLetterJob(
        job_type=job_type,
        job_hash=uuid.uuid4().hex,
        payload=payload,
        error_message=error_message,
        status=status,
        retry_count=1,
        max_retries=4,
        next_retry_at=created + timedelta(hours=1),
        created_at=created,
        updated_at=created,
    )


async def _list_jobs(
    session: AsyncSession, *, status: str | None = None, limit: int = 20
) -> Any:
    # Invoke the actual handler with its external DI boundary supplied locally.
    handler = cast(Any, list_dlq_jobs).__dishka_orig_func__
    return await handler(db=session, status=status, limit=limit, locale="en", _=None)


@pytest.mark.asyncio
async def test_auth_errors_are_opaque_in_every_status_and_storage_is_unchanged(
    dlq_session: AsyncSession,
) -> None:
    statuses = ("pending", "retrying", "failed", "completed")
    markers = [uuid.uuid4().hex for _ in range(8)]
    jobs = [
        _job(
            job_type="app.tasks.email.send_auth_email",
            error_message=(
                f"https://portal.example.test/reset-password#token={marker}"
                if index % 2 == 0
                else marker
            ),
            payload=json.dumps(
                {
                    "args": [
                        "student@example.test",
                        f"https://portal.example.test/reset-password#token={marker}",
                    ],
                    "kwargs": {},
                }
            ),
            status=statuses[index // 2],
            index=index,
        )
        for index, marker in enumerate(markers)
    ]
    dlq_session.add_all(jobs)
    await dlq_session.commit()
    originals = [(job.id, job.payload, job.error_message) for job in jobs]

    response = await _list_jobs(dlq_session)

    assert response.total == 8
    assert len(response.jobs) == 8
    rendered = response.model_dump_json()
    no_markers = all(marker not in rendered for marker in markers)
    assert no_markers, "auth error output exposed a generated marker"
    opaque_errors = all(
        job.error_message == "Authentication job error details redacted"
        for job in response.jobs
    )
    assert opaque_errors, "auth error details were returned to the admin client"
    original_by_id = {job.id: job for job in jobs}
    metadata_preserved = all(
        listed.job_type == original_by_id[listed.id].job_type
        and listed.job_hash == original_by_id[listed.id].job_hash[:16] + "..."
        and listed.status == original_by_id[listed.id].status
        and listed.retry_count == original_by_id[listed.id].retry_count
        and listed.max_retries == original_by_id[listed.id].max_retries
        and listed.next_retry_at == original_by_id[listed.id].next_retry_at.isoformat()
        and listed.created_at == original_by_id[listed.id].created_at.isoformat()
        and listed.updated_at == original_by_id[listed.id].updated_at.isoformat()
        for listed in response.jobs
    )
    assert metadata_preserved, "auth job metadata changed in the listing"

    for status in statuses:
        filtered = await _list_jobs(dlq_session, status=status)
        assert filtered.total == 2
        assert len(filtered.jobs) == 2
        assert all(job.status == status for job in filtered.jobs)
        filtered_opaque = all(
            job.error_message == "Authentication job error details redacted"
            for job in filtered.jobs
        )
        assert filtered_opaque, "filtered listing exposed auth error details"

    assert not dlq_session.dirty
    dlq_session.expunge_all()
    stored = (await dlq_session.scalars(select(DeadLetterJob))).all()
    unchanged = sorted(
        (job.id, job.payload, job.error_message) for job in stored
    ) == sorted(originals)
    assert unchanged, "listing changed stored payload or error bytes"


@pytest.mark.asyncio
async def test_missing_auth_errors_and_non_auth_diagnostics_keep_existing_behavior(
    dlq_session: AsyncSession,
) -> None:
    marker = uuid.uuid4().hex
    long_error = "delivery diagnostic " + marker * 8
    jobs = [
        _job(
            job_type="app.tasks.email.send_auth_email",
            error_message=None,
            status="failed",
            index=0,
        ),
        _job(
            job_type="app.tasks.email.send_auth_email",
            error_message="",
            status="failed",
            index=1,
        ),
        _job(
            job_type="other.task",
            error_message=long_error,
            status="failed",
            index=2,
        ),
    ]
    dlq_session.add_all(jobs)
    await dlq_session.commit()
    original_errors = [(job.id, job.error_message) for job in jobs]

    response = await _list_jobs(dlq_session, status="failed", limit=2)

    assert response.total == 3
    assert len(response.jobs) == 2
    assert response.jobs[0].job_type == "other.task"
    preserves_truncation = response.jobs[0].error_message == long_error[:200]
    assert preserves_truncation, "non-auth diagnostics or their limit changed"
    assert response.jobs[1].error_message is None

    response = await _list_jobs(dlq_session, status="failed")
    assert all(job.error_message is None for job in response.jobs[1:])
    assert not dlq_session.dirty
    dlq_session.expunge_all()
    stored = (await dlq_session.scalars(select(DeadLetterJob))).all()
    unchanged = sorted((job.id, job.error_message) for job in stored) == sorted(
        original_errors
    )
    assert unchanged, "listing changed an existing error message"
