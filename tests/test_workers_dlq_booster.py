"""Tests for app/workers/dead_letter_queue.py

Covers DeadLetterQueue, compute_job_hash, check_duplicate_job,
mark_job_retrying, mark_job_completed, mark_job_failed, get_queue_stats,
cleanup_completed_jobs. Goal: bring coverage from 27% to ~90%.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.workers.dead_letter_queue import (
    DeadLetterQueue,
    check_duplicate_job,
    compute_job_hash,
)
from app.models.dead_letter import DeadLetterJob, JobStatus


# ---------------------------------------------------------------------------
# compute_job_hash
# ---------------------------------------------------------------------------

def test_compute_job_hash_is_stable():
    h1 = compute_job_hash("SendEmail", {"to": "a@b.com", "subject": "Hi"})
    h2 = compute_job_hash("SendEmail", {"subject": "Hi", "to": "a@b.com"})
    assert h1 == h2  # keys sorted, so same hash


def test_compute_job_hash_differs_on_type():
    h1 = compute_job_hash("SendEmail", {"x": 1})
    h2 = compute_job_hash("SendSMS", {"x": 1})
    assert h1 != h2


def test_compute_job_hash_differs_on_payload():
    h1 = compute_job_hash("Foo", {"a": 1})
    h2 = compute_job_hash("Foo", {"a": 2})
    assert h1 != h2


def test_compute_job_hash_returns_64_hex_chars():
    h = compute_job_hash("T", {})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# check_duplicate_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_duplicate_job_returns_true_when_exists():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "some-id"
    mock_session.execute.return_value = mock_result

    result = await check_duplicate_job(mock_session, "MyJob", {"key": "val"})
    assert result is True


@pytest.mark.asyncio
async def test_check_duplicate_job_returns_false_when_not_exists():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    result = await check_duplicate_job(mock_session, "MyJob", {"key": "val"})
    assert result is False


# ---------------------------------------------------------------------------
# DeadLetterQueue.add_failed_job
# ---------------------------------------------------------------------------

def make_dlq(session: AsyncMock | None = None) -> DeadLetterQueue:
    if session is None:
        session = AsyncMock()
    return DeadLetterQueue(session)


@pytest.mark.asyncio
async def test_add_failed_job_returns_none_on_duplicate():
    session = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = MagicMock()  # duplicate exists
    session.execute.return_value = existing_result

    dlq = make_dlq(session)
    result = await dlq.add_failed_job("MyJob", {"k": "v"}, "error!")
    assert result is None


@pytest.mark.asyncio
async def test_add_failed_job_creates_new_job():
    session = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None  # no duplicate
    session.execute.return_value = existing_result
    session.add = MagicMock()
    session.flush = AsyncMock()

    dlq = make_dlq(session)

    with patch("app.workers.dead_letter_queue.DeadLetterJob") as mock_job_cls:
        mock_instance = MagicMock()
        mock_job_cls.return_value = mock_instance
        result = await dlq.add_failed_job("MyJob", {"k": "v"}, "bad error", max_retries=5)

    session.add.assert_called_once()
    session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# DeadLetterQueue.get_jobs_ready_for_retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_jobs_ready_for_retry_returns_list():
    session = AsyncMock()
    job1 = MagicMock()
    job2 = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [job1, job2]
    session.execute.return_value = result

    dlq = make_dlq(session)
    jobs = await dlq.get_jobs_ready_for_retry(limit=5)
    assert jobs == [job1, job2]


@pytest.mark.asyncio
async def test_get_jobs_ready_for_retry_empty():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    dlq = make_dlq(session)
    jobs = await dlq.get_jobs_ready_for_retry()
    assert jobs == []


# ---------------------------------------------------------------------------
# DeadLetterQueue.mark_job_retrying
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_job_retrying_increments_count_and_flushes():
    session = AsyncMock()
    session.flush = AsyncMock()
    dlq = make_dlq(session)

    job = MagicMock()
    job.retry_count = 0

    await dlq.mark_job_retrying(job)

    assert job.status == JobStatus.RETRYING.value
    assert job.retry_count == 1
    session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# DeadLetterQueue.mark_job_completed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_job_completed_sets_status_and_flushes():
    session = AsyncMock()
    session.flush = AsyncMock()
    dlq = make_dlq(session)

    job = MagicMock()
    job.job_type = "MyJob"
    job.job_hash = "a" * 16
    job.retry_count = 2

    await dlq.mark_job_completed(job)

    assert job.status == JobStatus.COMPLETED.value
    session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# DeadLetterQueue.mark_job_failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_job_failed_permanently_on_max_retries():
    session = AsyncMock()
    session.flush = AsyncMock()
    dlq = make_dlq(session)

    job = MagicMock()
    job.job_type = "MyJob"
    job.job_hash = "b" * 16
    job.retry_count = 3
    job.max_retries = 3

    await dlq.mark_job_failed(job, "unrecoverable error")

    assert job.status == JobStatus.FAILED.value
    assert job.next_retry_at is None
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_mark_job_failed_schedules_retry_below_max_retries():
    session = AsyncMock()
    session.flush = AsyncMock()
    dlq = make_dlq(session)

    job = MagicMock()
    job.job_type = "MyJob"
    job.job_hash = "c" * 16
    job.retry_count = 1
    job.max_retries = 5

    await dlq.mark_job_failed(job, "transient error")

    assert job.status == JobStatus.PENDING.value
    assert job.next_retry_at is not None
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_mark_job_failed_backoff_capped_at_max():
    """With many retries, backoff should be capped at MAX_BACKOFF_SECONDS."""
    session = AsyncMock()
    session.flush = AsyncMock()
    dlq = make_dlq(session)

    job = MagicMock()
    job.job_type = "MyJob"
    job.job_hash = "d" * 16
    job.retry_count = 10   # Large retry count — would overflow without cap
    job.max_retries = 20

    before = datetime.now(UTC)
    await dlq.mark_job_failed(job, "error")
    after = datetime.now(UTC)

    assert job.status == JobStatus.PENDING.value
    assert job.next_retry_at is not None
    # next retry must be at most 1 hour from now
    max_next = after + timedelta(seconds=DeadLetterQueue.MAX_BACKOFF_SECONDS)
    assert job.next_retry_at <= max_next


# ---------------------------------------------------------------------------
# DeadLetterQueue.get_queue_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_queue_stats_aggregates_correctly():
    session = AsyncMock()

    row1 = MagicMock()
    row1.status = JobStatus.PENDING.value
    row1.count = 5

    row2 = MagicMock()
    row2.status = JobStatus.FAILED.value
    row2.count = 2

    result = MagicMock()
    result.__iter__ = MagicMock(return_value=iter([row1, row2]))
    session.execute.return_value = result

    dlq = make_dlq(session)
    stats = await dlq.get_queue_stats()

    assert stats[JobStatus.PENDING.value] == 5
    assert stats[JobStatus.FAILED.value] == 2
    assert stats[JobStatus.RETRYING.value] == 0
    assert stats[JobStatus.COMPLETED.value] == 0


# ---------------------------------------------------------------------------
# DeadLetterQueue.cleanup_completed_jobs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_completed_jobs_returns_deleted_count():
    session = AsyncMock()
    session.flush = AsyncMock()

    delete_result = MagicMock()
    delete_result.rowcount = 7
    session.execute.return_value = delete_result

    dlq = make_dlq(session)
    deleted = await dlq.cleanup_completed_jobs(older_than_days=7)

    assert deleted == 7
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_completed_jobs_returns_zero_when_nothing_deleted():
    session = AsyncMock()
    session.flush = AsyncMock()

    delete_result = MagicMock()
    delete_result.rowcount = 0
    session.execute.return_value = delete_result

    dlq = make_dlq(session)
    deleted = await dlq.cleanup_completed_jobs()
    assert deleted == 0
