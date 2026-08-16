from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.dead_letter_queue as dlq_module
from app.models.dead_letter import JobStatus
from app.workers.dead_letter_queue import (
    DeadLetterQueue,
    register_circuit_breaker_db_dlq_listener,
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
    assert "handler" in job.error_message.lower()


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


def test_circuit_listener_ignores_non_recovery_and_no_running_loop() -> None:
    circuit_breaker = MagicMock()
    register_circuit_breaker_db_dlq_listener(circuit_breaker, MagicMock())
    listener = circuit_breaker.add_state_listener.call_args.args[0]

    listener(None, SimpleNamespace(name="OPEN"))
    with patch.object(
        dlq_module.asyncio, "get_running_loop", side_effect=RuntimeError("no loop")
    ):
        listener(None, "CLOSED")


@pytest.mark.asyncio
async def test_circuit_listener_contains_background_replay_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    circuit_breaker = MagicMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(
        side_effect=OSError("database unavailable")
    )
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    register_circuit_breaker_db_dlq_listener(circuit_breaker, session_factory)
    listener = circuit_breaker.add_state_listener.call_args.args[0]

    tasks: list[asyncio.Task[None]] = []
    running_loop = asyncio.get_running_loop()

    class CapturingLoop:
        def create_task(self, coroutine: object) -> asyncio.Task[None]:
            task = running_loop.create_task(coroutine)  # type: ignore[arg-type]
            tasks.append(task)
            return task

    monkeypatch.setattr(dlq_module.asyncio, "get_running_loop", lambda: CapturingLoop())
    listener(None, SimpleNamespace(name="HALF_OPEN"))
    await tasks[0]

    assert tasks[0].exception() is None
    assert not dlq_module._worker_dlq_tasks
