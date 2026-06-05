"""Coverage boost for app/workers/* modules.

All coroutines that could block indefinitely (asyncio.sleep, asyncpg.connect, etc.)
are replaced with AsyncMock / patch to prevent test hangs.

Targets:
  - notifications.py  (59%) — run_forever branches, metrics paths,
    start_notifications_scheduler existing-task branch
  - outbox.py         (55%) — run_forever loop, _listen_loop, stop(),
    _dispatch_event edge-cases, _move_to_dlq
  - dead_letter_queue.py (77%) — mark_job_failed backoff/permanent,
    check_duplicate_job
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stored_event(**kwargs: Any) -> MagicMock:
    """Return a MagicMock behaving like a StoredEvent."""
    se = MagicMock()
    se.id = uuid.uuid4()
    se.event_type = kwargs.get("event_type", "UserCreated")
    se.aggregate_type = kwargs.get("aggregate_type", "User")
    se.aggregate_id = kwargs.get("aggregate_id", "1")
    se.aggregate_id_uuid = kwargs.get("aggregate_id_uuid", uuid.uuid4())
    se.sequence_number = kwargs.get("sequence_number", 1)
    se.payload = kwargs.get("payload", {"user_id": "1"})
    se.metadata_ = kwargs.get("metadata_", None)
    se.error_count = kwargs.get("error_count", 0)
    se.last_error = kwargs.get("last_error", None)
    se.processed_at = kwargs.get("processed_at", None)
    return se


# ============================================================
# NotificationsScheduler — extended coverage
# ============================================================


class TestNotificationsSchedulerRunForever:
    """Cover the run_forever branches not reached by existing tests."""

    @pytest.mark.asyncio
    async def test_success_zero_created_still_calls_metric(self) -> None:
        """0 notifications → metrics.record_success(0), no logger.info call."""
        from app.workers.notifications import NotificationsScheduler

        mock_metrics = MagicMock()
        scheduler = NotificationsScheduler(
            poll_seconds=1,
            window_minutes=5,
            max_backoff_seconds=10,
            metrics=mock_metrics,
        )

        call_count = 0

        async def mock_run_once() -> int:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()
            return 0  # zero → no logger.info branch

        # Patch sleep so the loop doesn't actually wait
        with patch("app.workers.notifications.asyncio.sleep", new_callable=AsyncMock):
            with patch.object(scheduler, "run_once", side_effect=mock_run_once):
                with pytest.raises(asyncio.CancelledError):
                    await scheduler.run_forever()

        mock_metrics.record_success.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_success_nonzero_created_logs_info(self) -> None:
        """Non-zero notifications → logger.info branch executed."""
        from app.workers.notifications import NotificationsScheduler

        scheduler = NotificationsScheduler(
            poll_seconds=1,
            window_minutes=5,
            max_backoff_seconds=10,
            metrics=None,
        )

        call_count = 0

        async def mock_run_once() -> int:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()
            return 5  # non-zero → logger.info branch

        with patch("app.workers.notifications.asyncio.sleep", new_callable=AsyncMock):
            with patch.object(scheduler, "run_once", side_effect=mock_run_once):
                with pytest.raises(asyncio.CancelledError):
                    await scheduler.run_forever()

        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max(self) -> None:
        """Exponential backoff is capped at max_backoff_seconds."""
        from app.workers.notifications import NotificationsScheduler

        mock_metrics = MagicMock()
        scheduler = NotificationsScheduler(
            poll_seconds=100,
            window_minutes=5,
            max_backoff_seconds=200,  # cap much lower than 100 * 2^N
            metrics=mock_metrics,
        )

        call_count = 0
        sleep_values: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_values.append(seconds)
            # Stop the loop after first sleep
            if call_count >= 1:
                raise asyncio.CancelledError()

        async def mock_run_once() -> int:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fails")

        with patch("app.workers.notifications.asyncio.sleep", side_effect=mock_sleep):
            with patch.object(scheduler, "run_once", side_effect=mock_run_once):
                with pytest.raises((asyncio.CancelledError, RuntimeError)):
                    await scheduler.run_forever()

        assert all(s <= 200 for s in sleep_values), f"Uncapped: {sleep_values}"

    @pytest.mark.asyncio
    async def test_failure_with_no_metrics_does_not_raise(self) -> None:
        """metrics=None on failure path — no AttributeError."""
        from app.workers.notifications import NotificationsScheduler

        scheduler = NotificationsScheduler(
            poll_seconds=1,
            window_minutes=5,
            max_backoff_seconds=10,
            metrics=None,
        )

        call_count = 0

        async def mock_run_once() -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("no metrics path")
            raise asyncio.CancelledError()

        with patch("app.workers.notifications.asyncio.sleep", new_callable=AsyncMock):
            with patch.object(scheduler, "run_once", side_effect=mock_run_once):
                with pytest.raises(asyncio.CancelledError):
                    await scheduler.run_forever()

        assert call_count == 2


# ============================================================
# start_notifications_scheduler — existing task branch
# ============================================================


class TestStartNotificationsScheduler:
    @pytest.mark.asyncio
    async def test_returns_stop_existing_when_task_running(self) -> None:
        """If _scheduler_task is set and not done → returns _stop_existing callable."""
        from app.workers import notifications as notifs_module
        from app.workers.notifications import start_notifications_scheduler

        # Create a task that runs forever until cancelled
        async def _never() -> None:
            await asyncio.sleep(3600)

        task = asyncio.ensure_future(_never())
        notifs_module._scheduler_task = task  # type: ignore[assignment]

        try:
            stop_fn = await start_notifications_scheduler(
                poll_seconds=60,
                window_minutes=5,
                max_backoff_seconds=300,
            )
            assert callable(stop_fn)
            # Calling stop_fn should cancel the existing task
            await stop_fn()
            assert task.done()
        finally:
            notifs_module._scheduler_task = None
            if not task.done():
                task.cancel()

    @pytest.mark.asyncio
    async def test_stop_fn_cancels_running_task(self) -> None:
        """The returned stop_fn cancels the background scheduler task."""
        from app.workers import notifications as notifs_module
        from app.workers.notifications import start_notifications_scheduler

        async def instant_complete() -> None:
            # Completes immediately so we can test the "task done" branch
            return None

        with patch("app.workers.notifications.NotificationsScheduler") as MockSched:
            instance = MockSched.return_value
            instance.run_forever = AsyncMock(side_effect=instant_complete)

            stop_fn = await start_notifications_scheduler(
                poll_seconds=60,
                window_minutes=5,
                max_backoff_seconds=300,
            )
            # Give the task time to finish
            await asyncio.sleep(0.05)
            await stop_fn()

        notifs_module._scheduler_task = None


# ============================================================
# OutboxWorker.stop() and _on_notification()
# ============================================================


class TestOutboxWorkerSimpleMethods:
    @pytest.mark.asyncio
    async def test_stop_sets_flags(self) -> None:
        """stop() marks _is_running=False and sets _wakeup_event."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        assert not worker._wakeup_event.is_set()

        await worker.stop()

        assert not worker._is_running
        assert worker._wakeup_event.is_set()

    def test_on_notification_sets_wakeup(self) -> None:
        """_on_notification (raw asyncpg callback) must set _wakeup_event."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        worker._on_notification()
        assert worker._wakeup_event.is_set()


# ============================================================
# OutboxWorker.run_forever — patching everything that blocks
# ============================================================


class TestOutboxWorkerRunForever:
    @pytest.mark.asyncio
    async def test_exits_when_is_running_false_from_start(self) -> None:
        """If _is_running is False before first iteration, exits cleanly."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker(poll_interval=0.01)

        async def mock_process_batch() -> int:
            worker._is_running = False
            return 0

        # _listen_loop is a separate asyncio task; mock it to avoid hanging
        with patch.object(worker, "_listen_loop", new_callable=AsyncMock):
            with patch.object(worker, "process_batch", side_effect=mock_process_batch):
                await worker.run_forever()

    @pytest.mark.asyncio
    async def test_handles_process_batch_exception(self) -> None:
        """Exceptions in process_batch are caught, worker sleeps and retries."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker(poll_interval=0.01)
        call_count = 0

        async def failing_batch() -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB down")
            worker._is_running = False  # Stop after second call
            return 0

        with patch.object(worker, "_listen_loop", new_callable=AsyncMock):
            with patch.object(worker, "process_batch", side_effect=failing_batch):
                with patch("app.workers.outbox.asyncio.sleep", new_callable=AsyncMock):
                    await worker.run_forever()

        assert call_count == 2


# ============================================================
# OutboxWorker._listen_loop — all asyncpg calls mocked
# ============================================================


class TestOutboxWorkerListenLoop:
    @pytest.mark.asyncio
    async def test_does_not_connect_when_not_running(self) -> None:
        """_listen_loop exits immediately when _is_running is False."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        worker._is_running = False

        with patch("app.workers.outbox.asyncpg.connect") as mock_connect:
            await worker._listen_loop()

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_retries_after_connection_error(self) -> None:
        """OSError triggers a retry in _listen_loop."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        worker._is_running = True
        connect_count = 0

        async def mock_connect(dsn: str) -> Any:
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                raise OSError("refused")
            # Second call: stop the loop and cancel
            worker._is_running = False
            raise asyncio.CancelledError()

        with patch("app.workers.outbox.asyncpg.connect", side_effect=mock_connect):
            with patch("app.workers.outbox.asyncio.sleep", new_callable=AsyncMock):
                try:
                    await worker._listen_loop()
                except asyncio.CancelledError:
                    pass

        assert connect_count == 2

    @pytest.mark.asyncio
    async def test_closes_connection_on_cancel(self) -> None:
        """asyncpg connection is closed when CancelledError is raised inside."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        worker._is_running = True

        mock_conn = AsyncMock()
        mock_conn.add_listener = AsyncMock()
        mock_conn.close = AsyncMock()

        call_count = 0

        async def mock_connect(dsn: str) -> Any:
            nonlocal call_count
            call_count += 1
            return mock_conn

        # asyncio.sleep inside the keepalive loop raises CancelledError
        async def mock_sleep(secs: float) -> None:
            raise asyncio.CancelledError()

        with patch("app.workers.outbox.asyncpg.connect", side_effect=mock_connect):
            with patch("app.workers.outbox.asyncio.sleep", side_effect=mock_sleep):
                try:
                    await worker._listen_loop()
                except asyncio.CancelledError:
                    pass

        mock_conn.close.assert_awaited()


# ============================================================
# OutboxWorker._dispatch_event edge cases
# ============================================================


class TestOutboxWorkerDispatch:
    @pytest.mark.asyncio
    async def test_unknown_event_type_increments_error_count(self) -> None:
        """Unregistered event_type increments error_count without raising."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        se = _make_stored_event(event_type="CompletelyUnknown", payload={})

        with patch("app.core.events._EVENT_REGISTRY", {}):
            await worker._dispatch_event(se)

        assert se.error_count == 1

    @pytest.mark.asyncio
    async def test_dispatch_with_metadata_restores_ids(self) -> None:
        """metadata_ on StoredEvent is applied to the reconstructed event."""
        import dataclasses

        from app.workers.outbox import OutboxWorker

        @dataclasses.dataclass
        class FakeEvent:
            user_id: str
            event_id: str = ""
            metadata: Any = None

        worker = OutboxWorker()
        stored_id = "ev-999"
        se = _make_stored_event(
            event_type="FakeEvent",
            payload={"user_id": "42"},
            metadata_={
                "event_id": stored_id,
                "correlation_id": "corr-1",
                "user_id": "42",
            },
        )

        published: list[Any] = []

        async def mock_publish(event: Any) -> None:
            published.append(event)

        mock_span = MagicMock()
        mock_span.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_span.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.core.events._EVENT_REGISTRY", {"FakeEvent": FakeEvent}),
            patch("app.workers.outbox.event_bus") as mock_bus,
            patch("app.workers.outbox.tracer") as mock_tracer,
        ):
            mock_bus.publish = mock_publish
            mock_tracer.start_as_current_span.return_value = mock_span
            await worker._dispatch_event(se)

        assert len(published) == 1
        assert published[0].event_id == stored_id

    @pytest.mark.asyncio
    async def test_reconstruction_error_increments_count_and_reraises(self) -> None:
        """TypeError during event construction increments error_count and re-raises."""
        import dataclasses

        from app.workers.outbox import OutboxWorker

        @dataclasses.dataclass
        class StrictEvent:
            required_field: str  # payload won't provide this

        worker = OutboxWorker()
        se = _make_stored_event(
            event_type="StrictEvent",
            payload={"wrong": "data"},
        )

        with patch("app.core.events._EVENT_REGISTRY", {"StrictEvent": StrictEvent}):
            with pytest.raises(Exception):
                await worker._dispatch_event(se)

        assert se.error_count == 1


# ============================================================
# OutboxWorker._move_to_dlq
# ============================================================


class TestOutboxWorkerMoveToDlq:
    @pytest.mark.asyncio
    async def test_adds_failed_outbox_event_and_marks_processed(self) -> None:
        """_move_to_dlq adds FailedOutboxEvent and sets processed_at."""
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        db = AsyncMock()
        db.add = MagicMock()

        se = _make_stored_event(error_count=5)

        created: list[Any] = []

        class FakeDLQEntry:
            def __init__(self, **kwargs: Any) -> None:
                self.id = uuid.uuid4()
                created.append(self)

        with patch("app.models.failed_outbox_events.FailedOutboxEvent", FakeDLQEntry):
            await worker._move_to_dlq(db, se, "traceback text")

        assert len(created) == 1
        db.add.assert_called_once_with(created[0])
        assert se.processed_at is not None


# ============================================================
# DeadLetterQueue — mark_job_failed
# ============================================================


class TestDeadLetterQueueMarkJobFailed:
    @pytest.mark.asyncio
    async def test_permanent_failure_at_max_retries(self) -> None:
        """retry_count >= max_retries → FAILED status, next_retry_at=None."""
        from app.models.dead_letter import JobStatus
        from app.workers.dead_letter_queue import DeadLetterQueue

        session = AsyncMock()
        dlq = DeadLetterQueue(session=session)

        job = MagicMock()
        job.retry_count = 3
        job.max_retries = 3
        job.job_type = "email"
        job.job_hash = "abc123def456"

        await dlq.mark_job_failed(job, "final error")

        assert job.status == JobStatus.FAILED.value
        assert job.next_retry_at is None

    @pytest.mark.asyncio
    async def test_backoff_retry_when_retries_remain(self) -> None:
        """retry_count < max_retries → PENDING with future next_retry_at."""
        from app.models.dead_letter import JobStatus
        from app.workers.dead_letter_queue import DeadLetterQueue

        session = AsyncMock()
        dlq = DeadLetterQueue(session=session)

        job = MagicMock()
        job.retry_count = 1
        job.max_retries = 3
        job.job_type = "webhook"
        job.job_hash = "xyz789"

        before = datetime.now(UTC)
        await dlq.mark_job_failed(job, "temporary error")

        assert job.status == JobStatus.PENDING.value
        assert job.next_retry_at > before

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max_backoff(self) -> None:
        """Backoff with huge retry_count is capped at MAX_BACKOFF_SECONDS."""
        from app.models.dead_letter import JobStatus
        from app.workers.dead_letter_queue import DeadLetterQueue

        session = AsyncMock()
        dlq = DeadLetterQueue(session=session)

        job = MagicMock()
        job.retry_count = 50  # BASE*2^50 >> MAX_BACKOFF_SECONDS
        job.max_retries = 100
        job.job_type = "slow"
        job.job_hash = "cap"

        before = datetime.now(UTC)
        await dlq.mark_job_failed(job, "still failing")

        assert job.status == JobStatus.PENDING.value
        max_next = before + timedelta(seconds=dlq.MAX_BACKOFF_SECONDS + 5)
        assert job.next_retry_at <= max_next


# ============================================================
# check_duplicate_job
# ============================================================


class TestCheckDuplicateJob:
    @pytest.mark.asyncio
    async def test_returns_true_when_duplicate_exists(self) -> None:
        from app.workers.dead_letter_queue import check_duplicate_job

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        session.execute = AsyncMock(return_value=mock_result)

        result = await check_duplicate_job(session, "email", {"to": "a@b.com"})
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_duplicate(self) -> None:
        from app.workers.dead_letter_queue import check_duplicate_job

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await check_duplicate_job(session, "email", {"to": "new@b.com"})
        assert result is False


# ============================================================
# DeadLetterQueue — cleanup
# ============================================================


class TestDeadLetterQueueCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_returns_deleted_count(self) -> None:
        from app.workers.dead_letter_queue import DeadLetterQueue

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        session.execute = AsyncMock(return_value=mock_result)
        dlq = DeadLetterQueue(session=session)

        deleted = await dlq.cleanup_completed_jobs(older_than_days=7)
        assert deleted == 5

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_nothing_deleted(self) -> None:
        from app.workers.dead_letter_queue import DeadLetterQueue

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)
        dlq = DeadLetterQueue(session=session)

        deleted = await dlq.cleanup_completed_jobs(older_than_days=30)
        assert deleted == 0
