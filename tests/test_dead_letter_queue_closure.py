from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.dead_letter import JobStatus
from app.workers.dead_letter_queue import (
    DeadLetterQueue,
)


def _job(*, retry_count: int = 0, max_retries: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        job_type="sync_record",
        job_hash="hash-value",
        payload='{"record_id": 42}',
        status=JobStatus.PENDING.value,
        retry_count=retry_count,
        max_retries=max_retries,
        next_retry_at=None,
        error_message=None,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_replay_without_handler_fails_safely_instead_of_losing_job() -> None:
    session = AsyncMock()
    queue = DeadLetterQueue(session)
    job = _job()
    queue.get_jobs_ready_for_retry = AsyncMock(side_effect=[[job], []])

    success, failed = await queue.auto_replay_jobs(
        handler=None,
        rate_limit_delay=0,
    )

    assert (success, failed) == (0, 1)
    assert job.status == JobStatus.PENDING.value
    assert job.error_message == (
        "No DB DLQ replay handler is configured for job type 'sync_record'"
    )


@pytest.mark.asyncio
async def test_circuit_breaker_denial_halts_replay_without_refetching() -> None:
    session = AsyncMock()
    queue = DeadLetterQueue(session)
    queue.get_jobs_ready_for_retry = AsyncMock(return_value=[_job()])
    queue.mark_job_retrying = AsyncMock()
    circuit_breaker = MagicMock()
    circuit_breaker.state.name = "CLOSED"
    circuit_breaker.allow_request.return_value = False

    assert await queue.auto_replay_jobs(
        handler=AsyncMock(),
        circuit_breaker=circuit_breaker,
        max_batches=3,
        rate_limit_delay=0,
    ) == (0, 0)

    queue.get_jobs_ready_for_retry.assert_awaited_once_with(limit=10)
    queue.mark_job_retrying.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_skips_when_lock_is_held_unless_forced() -> None:
    session = AsyncMock()
    queue = DeadLetterQueue(session)
    lock = DeadLetterQueue._replay_lock
    await lock.acquire()
    try:
        assert await queue.auto_replay_jobs(handler=AsyncMock()) == (0, 0)
    finally:
        lock.release()
    queue.get_jobs_ready_for_retry = AsyncMock(return_value=[])
    assert await queue.auto_replay_jobs(handler=AsyncMock(), force=True) == (0, 0)


@pytest.mark.asyncio
async def test_open_circuit_and_zero_batches_stop_without_querying() -> None:
    queue = DeadLetterQueue(AsyncMock())
    queue.get_jobs_ready_for_retry = AsyncMock(return_value=[])
    circuit_breaker = MagicMock()
    circuit_breaker.state.name = "OPEN"

    assert await queue.auto_replay_jobs(
        handler=AsyncMock(), circuit_breaker=circuit_breaker
    ) == (0, 0)
    queue.get_jobs_ready_for_retry.assert_not_awaited()

    assert await queue.auto_replay_jobs(handler=AsyncMock(), max_batches=0) == (0, 0)


@pytest.mark.asyncio
async def test_replay_records_circuit_success_and_permanent_failure() -> None:
    session = AsyncMock()
    queue = DeadLetterQueue(session)
    successful = _job()
    permanent = _job(retry_count=2, max_retries=3)
    queue.get_jobs_ready_for_retry = AsyncMock(
        side_effect=[[successful, permanent], []]
    )
    circuit_breaker = MagicMock()
    circuit_breaker.state.name = "CLOSED"
    circuit_breaker.allow_request.return_value = True

    async def handler(job_type: str, payload: dict[str, object]) -> None:
        if payload["record_id"] == 42 and job_type == "sync_record":
            if successful.status == JobStatus.COMPLETED.value:
                raise OSError("permanent downstream failure")

    success, failed = await queue.auto_replay_jobs(
        handler=handler,
        circuit_breaker=circuit_breaker,
        rate_limit_delay=0,
    )

    assert (success, failed) == (1, 1)
    assert permanent.status == JobStatus.FAILED.value
    assert permanent.next_retry_at is None
    circuit_breaker.record_success.assert_called_once_with()
    circuit_breaker.record_failure.assert_called_once_with()


@pytest.mark.asyncio
async def test_replay_continues_to_followup_batches_after_successful_batch() -> None:
    session = AsyncMock()
    queue = DeadLetterQueue(session)
    first = _job()
    second = _job()
    queue.get_jobs_ready_for_retry = AsyncMock(side_effect=[[first], [second], []])
    handler = AsyncMock()

    assert await queue.auto_replay_jobs(handler=handler, rate_limit_delay=0) == (2, 0)

    assert handler.await_count == 2
    assert queue.get_jobs_ready_for_retry.await_count == 3
    assert all(
        call.kwargs == {"limit": 10}
        for call in queue.get_jobs_ready_for_retry.await_args_list
    )


@pytest.mark.asyncio
async def test_replay_flushes_after_each_completed_batch() -> None:
    session = AsyncMock()
    queue = DeadLetterQueue(session)
    queue.mark_job_retrying = AsyncMock()
    queue.mark_job_completed = AsyncMock()
    queue.get_jobs_ready_for_retry = AsyncMock(side_effect=[[_job()], [_job()], []])

    result = await queue.auto_replay_jobs(handler=AsyncMock(), rate_limit_delay=0)

    assert result == (2, 0)
    assert session.flush.await_count == 2
