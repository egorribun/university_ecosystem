"""Direct closure tests for DLQ status and replay orchestration paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.api.dlq as dlq_module
from app.api.dlq import DLQReplayRequest, get_dlq_status, trigger_dlq_replay


@pytest.mark.asyncio
async def test_get_dlq_status_combines_memory_database_and_circuit_breaker_state():
    db = MagicMock()
    db_dlq = MagicMock()
    db_dlq.get_queue_stats = AsyncMock(
        return_value={
            "pending": 2,
            "retrying": 1,
            "failed": 3,
            "completed": 4,
        }
    )
    circuit_breaker = SimpleNamespace(
        state=SimpleNamespace(name="OPEN"), _failure_count=5
    )
    dead_letter_queue_class = MagicMock(return_value=db_dlq)
    dead_letter_queue_class._is_replaying = False

    with (
        patch.object(dlq_module, "DeadLetterQueue", dead_letter_queue_class),
        patch.object(
            dlq_module.in_memory_dlq,
            "get_replay_status",
            new=AsyncMock(
                return_value={"size": 7, "max_size": 50, "is_replaying": False}
            ),
        ),
        patch.object(dlq_module, "get_circuit_breaker", return_value=circuit_breaker),
    ):
        result = await get_dlq_status(db=db, _=None)

    assert result.in_memory_queue_depth == 7
    assert result.db_total_active == 3
    assert result.circuit_breaker_state == "OPEN"
    assert result.circuit_breaker_failures == 5
    assert result.is_replaying is False


@pytest.mark.asyncio
async def test_trigger_dlq_replay_covers_all_and_single_targets():
    db = AsyncMock()
    db_dlq = MagicMock()
    db_dlq.auto_replay_jobs = AsyncMock(return_value=(3, 0))
    circuit_breaker = object()
    memory_replay = AsyncMock(return_value=(2, 1))

    with (
        patch.object(dlq_module.in_memory_dlq, "auto_replay", new=memory_replay),
        patch.object(dlq_module, "DeadLetterQueue", return_value=db_dlq),
        patch.object(dlq_module, "get_circuit_breaker", return_value=circuit_breaker),
    ):
        all_result = await trigger_dlq_replay(
            DLQReplayRequest(batch_size=7, force=True, target="all"),
            db=db,
            locale="en",
            _=None,
        )
        memory_result = await trigger_dlq_replay(
            DLQReplayRequest(target="in_memory"), db=db, locale="en", _=None
        )
        db_result = await trigger_dlq_replay(
            DLQReplayRequest(target="db"), db=db, locale="en", _=None
        )

    assert all_result.success is False
    assert all_result.in_memory_replayed == 2
    assert all_result.db_replayed == 3
    assert memory_result.target == "in_memory"
    assert db_result.target == "db"
    assert memory_replay.await_count == 2
    assert db_dlq.auto_replay_jobs.await_count == 2
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_trigger_dlq_replay_rejects_unknown_target():
    with pytest.raises(HTTPException) as exc_info:
        await trigger_dlq_replay(
            DLQReplayRequest(target="unknown"),
            db=AsyncMock(),
            locale="en",
            _=None,
        )

    assert exc_info.value.status_code == 400
