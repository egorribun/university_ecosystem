import asyncio

import pytest
from prometheus_client import REGISTRY

from app.core import observability
from app.services import notification_queue


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
