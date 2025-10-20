import asyncio

import pytest

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
