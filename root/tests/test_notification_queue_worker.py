import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from prometheus_client import REGISTRY
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core import observability
from app.core.database import Base, async_session
from app.models.models import NotificationQueueJob
from app.services import notification_queue


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_alembic_config(tmp_path: Path) -> tuple[Config, str, str | None]:
    db_path = tmp_path / "queue-migration.sqlite"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    sync_url = f"sqlite:///{db_path}"
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", async_url)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    return config, sync_url, previous_url


@pytest.fixture(autouse=True)
def _force_persistent_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_in_memory_only",
        False,
        raising=False,
    )


@pytest.mark.anyio
async def test_shutdown_notification_queue_completes_jobs(
    monkeypatch: pytest.MonkeyPatch,
):
    processed_ids: list[int] = []
    processed_event = asyncio.Event()

    async def _fake_process(job):
        processed_ids.append(job.record_id)
        processed_event.set()

    monkeypatch.setattr(notification_queue, "_process_job", _fake_process)

    await notification_queue.enqueue_event_notification(42)

    await asyncio.wait_for(processed_event.wait(), timeout=1.0)
    await notification_queue.wait_for_all_jobs(timeout=1.0)

    state = notification_queue._get_loop_state()
    assert state.worker_task is not None
    assert not state.worker_task.done()

    await notification_queue.shutdown_notification_queue()

    assert processed_ids == [42]
    assert state.queue.empty()
    assert state.worker_task is None or state.worker_task.done()


@pytest.mark.anyio
async def test_shutdown_notification_queue_does_not_leak_tasks(
    monkeypatch: pytest.MonkeyPatch,
):
    processed_event = asyncio.Event()

    async def _fake_process(job):
        processed_event.set()

    monkeypatch.setattr(notification_queue, "_process_job", _fake_process)

    await notification_queue.enqueue_news_notification(77)

    await asyncio.wait_for(processed_event.wait(), timeout=1.0)
    await notification_queue.wait_for_all_jobs(timeout=1.0)

    await notification_queue.shutdown_notification_queue()
    await asyncio.sleep(0)

    worker_tasks = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task()
        and task.get_name() == notification_queue._WORKER_TASK_NAME
    ]
    assert not worker_tasks


def _metric_value(name: str) -> float | None:
    return REGISTRY.get_sample_value(name)


@pytest.mark.anyio
async def test_notification_queue_records_drops_when_saturated(
    monkeypatch: pytest.MonkeyPatch,
):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()
    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_in_memory_only",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_max_size",
        1,
        raising=False,
    )

    async def _no_worker() -> None:
        return None

    monkeypatch.setattr(notification_queue, "_ensure_worker", _no_worker)

    await notification_queue.enqueue_event_notification(1)
    await notification_queue.enqueue_event_notification(2)

    state = notification_queue._get_loop_state()
    assert state.queue.qsize() == 1
    assert [job.record_id for job in list(state.queue._queue)] == [2]

    assert _metric_value("notification_queue_size") == pytest.approx(1.0)
    assert _metric_value("notification_queue_dropped_jobs_total") == pytest.approx(1.0)

    await notification_queue.reset_testing_state()
    await notification_queue.shutdown_notification_queue()
    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_notification_queue_records_processing_latency(
    monkeypatch: pytest.MonkeyPatch,
):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()

    async def _fake_process(job):
        await asyncio.sleep(0.01)

    monkeypatch.setattr(notification_queue, "_process_job", _fake_process)

    await notification_queue.enqueue_event_notification(5)

    await notification_queue.wait_for_all_jobs(timeout=1.0)
    await notification_queue.shutdown_notification_queue()

    count = _metric_value("notification_queue_processing_latency_seconds_count")
    total = _metric_value("notification_queue_processing_latency_seconds_sum")
    assert count == pytest.approx(1.0)
    assert total is not None and total > 0
    assert _metric_value("notification_queue_size") == pytest.approx(0.0)

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_persistent_queue_persists_and_clears_jobs(
    monkeypatch: pytest.MonkeyPatch,
):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()

    processed_event = asyncio.Event()

    async def _fake_process(job):
        assert job.queue_id is not None
        async with async_session() as session:
            record = await session.get(NotificationQueueJob, job.queue_id)
            assert record is not None
            assert record.claimed_at is not None
        processed_event.set()

    monkeypatch.setattr(notification_queue, "_process_job", _fake_process)

    await notification_queue.enqueue_event_notification(101)

    await asyncio.wait_for(processed_event.wait(), timeout=1.0)
    await notification_queue.wait_for_all_jobs(timeout=1.0)

    async with async_session() as session:
        result = await session.execute(select(NotificationQueueJob.id))
        assert result.first() is None

    assert _metric_value("notification_queue_size") == pytest.approx(0.0)

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_persistent_queue_deduplicates_jobs(monkeypatch: pytest.MonkeyPatch):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()

    async def _noop_worker() -> None:
        return None

    monkeypatch.setattr(notification_queue, "_ensure_worker", _noop_worker)

    await notification_queue.enqueue_news_notification(202)
    await notification_queue.enqueue_news_notification(202)

    async with async_session() as session:
        result = await session.execute(select(NotificationQueueJob.record_id))
        rows = result.fetchall()
    assert [row[0] for row in rows] == [202]

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_persistent_queue_retries_failed_jobs(monkeypatch: pytest.MonkeyPatch):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()

    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_retry_base_seconds",
        0.0,
        raising=False,
    )

    attempts: list[int] = []
    processed_event = asyncio.Event()

    async def _process(job):
        attempts.append(job.record_id)
        if len(attempts) == 1:
            raise RuntimeError("boom")
        processed_event.set()

    monkeypatch.setattr(notification_queue, "_process_job", _process)

    await notification_queue.enqueue_news_notification(303)

    await asyncio.wait_for(processed_event.wait(), timeout=1.0)
    await notification_queue.wait_for_all_jobs(timeout=1.0)

    assert attempts == [303, 303]

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_persistent_queue_applies_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()

    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_retry_base_seconds",
        0.05,
        raising=False,
    )
    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_max_attempts",
        3,
        raising=False,
    )

    attempt_times: list[float] = []
    first_attempt = asyncio.Event()
    processed_event = asyncio.Event()

    async def _process(job):
        attempt_times.append(asyncio.get_running_loop().time())
        if len(attempt_times) == 1:
            first_attempt.set()
            raise RuntimeError("boom")
        processed_event.set()

    monkeypatch.setattr(notification_queue, "_process_job", _process)

    await notification_queue.enqueue_event_notification(404)

    await asyncio.wait_for(first_attempt.wait(), timeout=1.0)
    await asyncio.sleep(0.01)

    async with async_session() as session:
        result = await session.execute(
            select(NotificationQueueJob).where(NotificationQueueJob.record_id == 404)
        )
        record = result.scalar_one()
        assert record.next_retry_at is not None
        now = datetime.now(timezone.utc)
        next_retry = record.next_retry_at
        if next_retry.tzinfo is None:
            next_retry = next_retry.replace(tzinfo=timezone.utc)
        assert next_retry > now
        assert record.last_error == "boom"
        assert not record.dead_lettered

    await asyncio.wait_for(processed_event.wait(), timeout=1.0)
    await notification_queue.wait_for_all_jobs(timeout=1.0)

    assert len(attempt_times) == 2
    interval = attempt_times[1] - attempt_times[0]
    assert interval >= 0.04
    assert _metric_value("notification_queue_failed_jobs_total") == pytest.approx(0.0)

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_persistent_queue_dead_letters_poison_jobs(
    monkeypatch: pytest.MonkeyPatch,
):
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()
    notification_queue._loop_states.clear()

    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_retry_base_seconds",
        0.01,
        raising=False,
    )
    monkeypatch.setattr(
        notification_queue.settings,
        "notifications_queue_max_attempts",
        3,
        raising=False,
    )

    attempts: list[int] = []

    async def _process(job):
        attempts.append(job.record_id)
        raise RuntimeError("poison pill")

    monkeypatch.setattr(notification_queue, "_process_job", _process)

    await notification_queue.enqueue_event_notification(505)

    async def _wait_for_dead_lettered() -> NotificationQueueJob:
        while True:
            async with async_session() as session:
                result = await session.execute(
                    select(NotificationQueueJob).where(
                        NotificationQueueJob.record_id == 505
                    )
                )
                record = result.scalar_one_or_none()
            if record and record.dead_lettered:
                return record
            await asyncio.sleep(0.01)

    record = await asyncio.wait_for(_wait_for_dead_lettered(), timeout=2.0)

    assert record.dead_lettered is True
    assert record.attempts == 3
    assert record.next_retry_at is None
    assert record.last_error == "poison pill"
    assert len(attempts) == 3

    await asyncio.sleep(0.05)
    assert len(attempts) == 3

    assert _metric_value("notification_queue_failed_jobs_total") == pytest.approx(1.0)

    await notification_queue.wait_for_all_jobs(timeout=1.0)

    notification_queue._loop_states.clear()


@pytest.mark.anyio
async def test_notification_queue_pending_index_migration(tmp_path: Path) -> None:
    config, sync_url, previous_url = _make_alembic_config(tmp_path)
    def _prepare_schema() -> None:
        engine = sa.create_engine(sync_url)
        try:
            Base.metadata.create_all(engine)
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "DROP INDEX IF EXISTS ix_notification_queue_jobs_pending_claim"
                    )
                )
        finally:
            engine.dispose()

    await asyncio.to_thread(_prepare_schema)
    try:
        await asyncio.to_thread(command.upgrade, config, "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url

    def _inspect_indexes() -> set[str]:
        engine = sa.create_engine(sync_url)
        try:
            inspector = sa.inspect(engine)
            indexes = inspector.get_indexes("notification_queue_jobs")
            return {index["name"] for index in indexes}
        finally:
            engine.dispose()

    index_names = await asyncio.to_thread(_inspect_indexes)
    assert "ix_notification_queue_jobs_pending_claim" in index_names


@pytest.mark.anyio
async def test_persistent_queue_claims_next_job_from_large_backlog() -> None:
    await notification_queue.reset_testing_state()
    metrics = observability.get_notification_queue_metrics()
    metrics.reset()

    now = datetime.now(timezone.utc)

    async with async_session() as session:
        bulk_jobs = [
            NotificationQueueJob(
                kind="event",
                record_id=1000 + index,
                locale="ru",
                enqueued_at=now - timedelta(seconds=300 + index),
                next_retry_at=now + timedelta(minutes=5),
            )
            for index in range(500)
        ]
        session.add_all(bulk_jobs)

        ready_job = NotificationQueueJob(
            kind="news",
            record_id=9999,
            locale="en",
            enqueued_at=now - timedelta(minutes=10),
            next_retry_at=now - timedelta(seconds=1),
        )
        session.add(ready_job)

        fallback_job = NotificationQueueJob(
            kind="event",
            record_id=5000,
            locale=None,
            enqueued_at=now + timedelta(minutes=10),
            next_retry_at=None,
        )
        session.add(fallback_job)

        await session.commit()

    try:
        job = await notification_queue._claim_next_persistent_job()
        assert job is not None
        assert job.kind == "news"
        assert job.record_id == 9999
        assert job.queue_id is not None

        async with async_session() as session:
            stored = await session.get(NotificationQueueJob, job.queue_id)
            assert stored is not None
            assert stored.claimed_at is not None

    finally:
        await notification_queue.reset_testing_state()
