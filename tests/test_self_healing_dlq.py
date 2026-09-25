"""
Tests for Self-Healing Dead Letter Queue (DLQ) with Circuit Breaker Replay Pattern.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_admin_user
from app.core.database import get_db, get_read_db
from app.core.event_dlq import DeadLetterQueue as InMemoryDLQ
from app.core.events import DomainEvent
from app.core.ratelimit.circuit_breaker import CircuitState, RedisCircuitBreaker
from app.main import app
from app.models.dead_letter import DeadLetterJob, JobStatus
from app.workers.dead_letter_queue import (
    DeadLetterQueue as DBDeadLetterQueue,
)
from app.workers.dead_letter_queue import (
    register_circuit_breaker_db_dlq_listener,
)


@dataclass
class DummyDomainEvent(DomainEvent):
    """Dummy domain event for DLQ testing."""

    EVENT_TYPE: ClassVar[str] = "test.dummy_event"
    data: str = "test_payload"


# ---------------------------------------------------------------------------
# 1. Circuit Breaker Listener Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_add_listener_and_transitions() -> None:
    """Test listener registration and execution on state transitions."""
    # Keep the initial OPEN assertion independent of scheduler load.  A
    # sub-second recovery window can elapse while listener callbacks and
    # pytest/mutmut instrumentation are running, causing ``state`` to perform
    # the expected recovery transition before the assertion is evaluated.
    cb = RedisCircuitBreaker(failure_threshold=2, recovery_timeout=10.0)

    sync_calls: list[tuple[CircuitState, CircuitState]] = []
    async_calls: list[tuple[CircuitState, CircuitState]] = []

    def sync_listener(old_s: CircuitState, new_s: CircuitState) -> None:
        sync_calls.append((old_s, new_s))

    async def async_listener(old_s: CircuitState, new_s: CircuitState) -> None:
        async_calls.append((old_s, new_s))

    def failing_listener(old_s: CircuitState, new_s: CircuitState) -> None:
        raise RuntimeError("Listener error simulation")

    cb.add_state_listener(sync_listener)
    cb.add_state_listener(async_listener)
    cb.add_state_listener(failing_listener)

    # Transition CLOSED -> OPEN
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0)  # Yield until the scheduled async listener runs.

    assert len(sync_calls) == 1
    assert sync_calls[0] == (CircuitState.CLOSED, CircuitState.OPEN)
    assert len(async_calls) == 1
    assert async_calls[0] == (CircuitState.CLOSED, CircuitState.OPEN)

    # Advance the monotonic checkpoint explicitly before observing recovery;
    # this preserves the state-machine assertion without a timing race.
    cb._last_failure_time -= 11.0
    assert cb.state == CircuitState.HALF_OPEN
    await asyncio.sleep(0)

    assert len(sync_calls) == 2
    assert sync_calls[1] == (CircuitState.OPEN, CircuitState.HALF_OPEN)

    # Probe success -> CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    await asyncio.sleep(0)

    assert len(sync_calls) == 3
    assert sync_calls[2] == (CircuitState.HALF_OPEN, CircuitState.CLOSED)


# ---------------------------------------------------------------------------
# 2. In-Memory Domain Event DLQ Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_dlq_auto_replay_success() -> None:
    """Test automated replay of in-memory failed domain events."""
    dlq = InMemoryDLQ(max_size=100)
    mock_bus = AsyncMock()

    event1 = DummyDomainEvent(data="event_1")
    event2 = DummyDomainEvent(data="event_2")

    await dlq.add(event1, ValueError("Error 1"))
    await dlq.add(event2, RuntimeError("Error 2"))
    assert dlq.size == 2

    success, failed = await dlq.auto_replay(bus=mock_bus, batch_size=10)
    assert success == 2
    assert failed == 0
    assert dlq.size == 0
    assert mock_bus.publish.call_count == 2


@pytest.mark.asyncio
async def test_in_memory_dlq_thundering_herd_prevention() -> None:
    """Test that concurrent auto_replay calls do not execute in parallel."""
    dlq = InMemoryDLQ()

    slow_bus = AsyncMock()

    async def slow_publish(event: DomainEvent) -> None:
        await asyncio.sleep(0.1)

    slow_bus.publish.side_effect = slow_publish

    await dlq.add(DummyDomainEvent(data="test"), ValueError("err"))

    # Launch two concurrent auto_replay tasks
    task1 = asyncio.create_task(dlq.auto_replay(bus=slow_bus))
    await asyncio.sleep(0.01)  # Ensure task1 acquires lock

    # Task 2 should return early (0, 0) due to thundering herd lock
    res2 = await dlq.auto_replay(bus=slow_bus)
    res1 = await task1

    assert res2 == (0, 0)
    assert res1 == (1, 0)


@pytest.mark.asyncio
async def test_in_memory_dlq_circuit_breaker_listener_trigger() -> None:
    """Test that circuit breaker state transition triggers automated DLQ replay."""
    cb = RedisCircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
    dlq = InMemoryDLQ()
    mock_bus = AsyncMock()

    dlq.attach_circuit_breaker(cb, mock_bus)
    await dlq.add(DummyDomainEvent(data="auto_trigger"), Exception("fail"))

    # Trip circuit to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Advance the instance's monotonic checkpoint deterministically. A tiny
    # wall-clock timeout makes this assertion flaky on a contended CI worker.
    cb._last_failure_time -= 11.0
    _ = cb.state
    assert cb.state == CircuitState.HALF_OPEN
    await asyncio.sleep(0.05)  # Allow background replay task to run

    # DLQ should have been replayed automatically
    assert dlq.size == 0
    mock_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_in_memory_dlq_exponential_backoff_and_max_retries() -> None:
    """Test retry count increment, exponential backoff, and max retries drop."""
    dlq = InMemoryDLQ()
    failing_bus = AsyncMock()
    failing_bus.publish.side_effect = RuntimeError("Handler still failing")

    event = DummyDomainEvent(data="persistent_failure")
    await dlq.add(event, RuntimeError("initial failure"))

    # First auto_replay attempt with max_retries=2
    success, failed = await dlq.auto_replay(
        bus=failing_bus,
        max_retries=2,
        base_backoff=0.01,
        max_backoff=0.05,
    )
    assert success == 0
    assert failed == 1
    assert dlq.size == 1  # Kept for retry #2

    events = await dlq.get_all()
    assert events[0].retry_count == 1

    # Second auto_replay attempt -> reaches max_retries=2, dropped
    success, failed = await dlq.auto_replay(
        bus=failing_bus,
        max_retries=2,
        base_backoff=0.01,
        max_backoff=0.05,
    )
    assert success == 0
    assert failed == 1
    assert dlq.size == 0  # Dropped from queue after max retries


@pytest.mark.asyncio
async def test_in_memory_dlq_replay_status_metrics() -> None:
    """Test get_replay_status metrics output."""
    dlq = InMemoryDLQ(max_size=500)
    status = await dlq.get_replay_status()

    assert status["size"] == 0
    assert status["max_size"] == 500
    assert status["is_replaying"] is False
    assert status["auto_replay_enabled"] is False


# ---------------------------------------------------------------------------
# 3. DB-Backed DeadLetterJob Worker Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_dlq_auto_replay_jobs_success() -> None:
    """Test automated replay of DB-backed DeadLetterJob records."""
    mock_session = AsyncMock()

    job1 = DeadLetterJob(
        id=1,
        job_type="send_email",
        job_hash="hash1",
        payload=json.dumps({"to": "user@example.com"}),
        status=JobStatus.PENDING.value,
        retry_count=0,
        max_retries=3,
        next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    mock_result_jobs = MagicMock()
    mock_result_jobs.scalars.return_value.all.return_value = [job1]

    mock_result_empty = MagicMock()
    mock_result_empty.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_result_jobs, mock_result_empty]

    executed_jobs: list[tuple[str, dict[str, Any]]] = []

    async def mock_handler(job_type: str, payload: dict[str, Any]) -> None:
        executed_jobs.append((job_type, payload))

    db_dlq = DBDeadLetterQueue(mock_session)
    success, failed = await db_dlq.auto_replay_jobs(handler=mock_handler)

    assert success == 1
    assert failed == 0
    assert len(executed_jobs) == 1
    assert executed_jobs[0][0] == "send_email"
    assert job1.status == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_db_dlq_auto_replay_jobs_failure_and_backoff() -> None:
    """Test failure backoff update for DB-backed jobs."""
    mock_session = AsyncMock()

    job = DeadLetterJob(
        id=2,
        job_type="sync_data",
        job_hash="hash2",
        payload=json.dumps({"item_id": 42}),
        status=JobStatus.PENDING.value,
        retry_count=0,
        max_retries=3,
        next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    mock_result_jobs = MagicMock()
    mock_result_jobs.scalars.return_value.all.return_value = [job]

    mock_result_empty = MagicMock()
    mock_result_empty.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_result_jobs, mock_result_empty]

    async def failing_handler(job_type: str, payload: dict[str, Any]) -> None:
        raise ValueError("Downstream service unreachable")

    db_dlq = DBDeadLetterQueue(mock_session)
    success, failed = await db_dlq.auto_replay_jobs(
        handler=failing_handler,
        base_backoff_seconds=10,
    )

    assert success == 0
    assert failed == 1
    assert job.status == JobStatus.PENDING.value
    assert job.retry_count == 1
    assert job.next_retry_at is not None
    assert "Downstream service unreachable" in (job.error_message or "")


@pytest.mark.asyncio
async def test_db_dlq_circuit_breaker_listener_registration() -> None:
    """Test register_circuit_breaker_db_dlq_listener helper."""
    cb = RedisCircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    handler_mock = AsyncMock()
    register_circuit_breaker_db_dlq_listener(
        cb,
        session_factory=mock_session_factory,
        handler=handler_mock,
    )

    # Trip and recover circuit breaker
    cb.record_failure()
    await asyncio.sleep(0.08)
    _ = cb.state  # Triggers transition to HALF_OPEN

    await asyncio.sleep(0.05)  # Allow background task to execute
    assert mock_session_factory.called
    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4. Admin API Endpoint Tests
# ---------------------------------------------------------------------------


from unittest.mock import patch


def test_admin_dlq_status_and_replay_api_routes() -> None:
    """Test GET /api/v1/admin/dlq/status and POST /api/v1/admin/dlq/replay endpoints."""
    client = TestClient(app)

    # Mock admin dependency and DB sessions
    mock_admin = MagicMock()
    mock_admin.role = "admin"

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.__iter__.return_value = []
    mock_db.execute.return_value = mock_db_result

    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_read_db] = lambda: mock_db

    async def mock_csrf_call(self: Any, scope: Any, receive: Any, send: Any) -> None:
        await self._app(scope, receive, send)

    try:
        with (
            patch(
                "app.core.internal_access.InternalAccessMiddleware._has_valid_header_from_scope",
                return_value=True,
            ),
            patch(
                "app.core.csrf.CSRFMiddleware.__call__",
                new=mock_csrf_call,
            ),
        ):
            # 1. Test GET /api/v1/admin/dlq/status
            res_status = client.get("/api/v1/admin/dlq/status")
            assert res_status.status_code == 200
            data_status = res_status.json()

            assert "in_memory_queue_depth" in data_status
            assert "db_pending" in data_status
            assert "circuit_breaker_state" in data_status
            assert "is_replaying" in data_status

            # 2. Test POST /api/v1/admin/dlq/replay
            res_replay = client.post(
                "/api/v1/admin/dlq/replay",
                json={"batch_size": 10, "force": True, "target": "all"},
            )
            assert res_replay.status_code == 200
            data_replay = res_replay.json()

            assert data_replay["success"] is True
            assert data_replay["target"] == "all"
            assert "in_memory_replayed" in data_replay
            assert "db_replayed" in data_replay
    finally:
        app.dependency_overrides.clear()
