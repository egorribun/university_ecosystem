"""Direct closure tests for DLQ status and replay orchestration paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

import app.api.dlq as dlq_module
from app.api.deps import get_current_admin_user_from_dishka
from app.api.dlq import DLQReplayRequest, get_dlq_status, trigger_dlq_replay
from app.core.database import get_db
from tests.conftest import build_dishka_app, call_injected, dishka_overrides


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
        patch.object(
            dlq_module,
            "_count_unresolved_outbox_failures",
            new=AsyncMock(return_value=6),
        ),
    ):
        result = await call_injected(
            get_dlq_status, _=None, provides={"AsyncDatabaseSession": db}
        )

    assert result.in_memory_queue_depth == 7
    assert result.outbox_unresolved == 6
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
    broker = MagicMock()

    with (
        patch.object(dlq_module.in_memory_dlq, "auto_replay", new=memory_replay),
        patch.object(dlq_module, "DeadLetterQueue", return_value=db_dlq),
        patch.object(dlq_module, "get_circuit_breaker", return_value=circuit_breaker),
    ):
        all_result = await call_injected(
            trigger_dlq_replay,
            DLQReplayRequest(batch_size=7, force=True, target="all"),
            locale="en",
            _=None,
            provides={"AsyncDatabaseSession": db, "NatsTaskBroker": broker},
        )
        memory_result = await call_injected(
            trigger_dlq_replay,
            DLQReplayRequest(target="in_memory"),
            locale="en",
            _=None,
            provides={"AsyncDatabaseSession": db, "NatsTaskBroker": broker},
        )
        db_result = await call_injected(
            trigger_dlq_replay,
            DLQReplayRequest(target="db"),
            locale="en",
            _=None,
            provides={"AsyncDatabaseSession": db, "NatsTaskBroker": broker},
        )

    assert all_result.success is False
    assert all_result.in_memory_replayed == 2
    assert all_result.db_replayed == 3
    assert memory_result.target == "in_memory"
    assert db_result.target == "db"
    assert memory_replay.await_count == 2
    assert db_dlq.auto_replay_jobs.await_count == 2
    # The DB replay re-enqueues through the broker (a missing handler used to make
    # every replayed job fail with "No DB DLQ replay handler is configured").
    assert db_dlq.auto_replay_jobs.await_args.args == (broker.replay_dead_letter,)
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_trigger_dlq_replay_rejects_unknown_target():
    with pytest.raises(HTTPException) as exc_info:
        await call_injected(
            trigger_dlq_replay,
            DLQReplayRequest(target="unknown"),
            locale="en",
            _=None,
            provides={
                "AsyncDatabaseSession": AsyncMock(),
                "NatsTaskBroker": MagicMock(),
            },
        )

    assert exc_info.value.status_code == 400


def _build_dlq_http_app(db):
    test_app = build_dishka_app(dlq_module.router)
    test_app.dependency_overrides[get_db] = lambda: db
    test_app.dependency_overrides[get_current_admin_user_from_dishka] = (
        lambda: SimpleNamespace(id="admin")
    )
    return test_app


@pytest.mark.asyncio
async def test_cleanup_dlq_rejects_negative_age_but_accepts_zero():
    db = AsyncMock()
    cleanup = AsyncMock(return_value=0)
    queue = MagicMock()
    queue.cleanup_completed_jobs = cleanup
    test_app = _build_dlq_http_app(db)

    with (
        dishka_overrides(test_app),
        patch.object(dlq_module, "DeadLetterQueue", return_value=queue),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://testserver"
        ) as client:
            negative = await client.delete(
                "/admin/dlq/cleanup", params={"older_than_days": -1}
            )
            zero = await client.delete(
                "/admin/dlq/cleanup", params={"older_than_days": 0}
            )

    assert negative.status_code == 422
    assert zero.status_code == 200
    assert zero.json()["older_than_days"] == 0
    cleanup.assert_awaited_once_with(older_than_days=0)


@pytest.mark.asyncio
async def test_replay_dlq_rejects_nonpositive_batch_and_accepts_one():
    db = AsyncMock()
    test_app = _build_dlq_http_app(db)
    replay = AsyncMock(return_value=(0, 0))

    with (
        dishka_overrides(test_app),
        patch.object(dlq_module.in_memory_dlq, "auto_replay", new=replay),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://testserver"
        ) as client:
            zero = await client.post(
                "/admin/dlq/replay",
                json={"batch_size": 0, "target": "in_memory"},
            )
            negative = await client.post(
                "/admin/dlq/replay",
                json={"batch_size": -1, "target": "in_memory"},
            )
            minimum = await client.post(
                "/admin/dlq/replay",
                json={"batch_size": 1, "target": "in_memory"},
            )

    assert zero.status_code == 422
    assert negative.status_code == 422
    assert minimum.status_code == 200
    replay.assert_awaited_once_with(batch_size=1, force=False)
