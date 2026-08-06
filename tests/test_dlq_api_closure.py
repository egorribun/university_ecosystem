"""Closure tests for DLQ replay target routing and defensive branches."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import dlq


async def test_trigger_dlq_replay_rejects_unknown_target():
    with pytest.raises(HTTPException) as exc_info:
        await dlq.trigger_dlq_replay(
            request=dlq.DLQReplayRequest(target="unknown"),
            db=AsyncMock(),
            locale="en",
            _=MagicMock(),
        )

    assert exc_info.value.status_code == 400


async def test_trigger_dlq_replay_can_run_in_memory_target_only():
    in_memory = MagicMock()
    in_memory.auto_replay = AsyncMock(return_value=(3, 1))
    db = AsyncMock()

    with patch.object(dlq, "in_memory_dlq", in_memory):
        response = await dlq.trigger_dlq_replay(
            request=dlq.DLQReplayRequest(target="in_memory", batch_size=4, force=True),
            db=db,
            locale="en",
            _=MagicMock(),
        )

    assert response.success is False
    assert response.in_memory_replayed == 3
    assert response.db_replayed == 0
    db.commit.assert_not_awaited()


async def test_trigger_dlq_replay_can_run_database_target_only():
    db = AsyncMock()
    db_dlq = MagicMock()
    db_dlq.auto_replay_jobs = AsyncMock(return_value=(2, 0))
    circuit_breaker = MagicMock()
    in_memory = MagicMock()

    with (
        patch.object(dlq, "in_memory_dlq", in_memory),
        patch.object(dlq, "DeadLetterQueue", return_value=db_dlq),
        patch.object(dlq, "get_circuit_breaker", return_value=circuit_breaker),
    ):
        response = await dlq.trigger_dlq_replay(
            request=dlq.DLQReplayRequest(target="db", batch_size=5),
            db=db,
            locale="en",
            _=MagicMock(),
        )

    assert response.success is True
    assert response.db_replayed == 2
    in_memory.auto_replay.assert_not_called()
    db.commit.assert_awaited_once()


async def test_retry_dlq_job_rejects_missing_job():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await dlq.retry_dlq_job(
            job_id=42,
            db=db,
            locale="en",
            _=MagicMock(),
        )

    assert exc_info.value.status_code == 404
