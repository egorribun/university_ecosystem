"""Closure tests for the NATS-backed notification queue compatibility API."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import notification_queue as queue


@pytest.mark.asyncio
async def test_enqueue_event_and_news_convert_integer_ids():
    event_id = uuid.uuid4()
    news_id = uuid.uuid4()

    with patch.object(
        queue.enqueue_event_notification_task, "kick", new=AsyncMock()
    ) as event_kick:
        await queue.enqueue_event_notification(event_id.int, locale="ru")
    with patch.object(
        queue.enqueue_news_notification_task, "kick", new=AsyncMock()
    ) as news_kick:
        await queue.enqueue_news_notification(news_id.int, locale="en")

    event_kick.assert_awaited_once_with(event_id, locale="ru")
    news_kick.assert_awaited_once_with(news_id, locale="en")


@pytest.mark.asyncio
async def test_enqueue_comment_converts_all_integer_ids():
    ids = [uuid.uuid4() for _ in range(3)]

    with patch.object(
        queue.enqueue_comment_notification_task, "kick", new=AsyncMock()
    ) as comment_kick:
        await queue.enqueue_comment_notification(
            ids[0].int, ids[1].int, ids[2].int, locale="ru"
        )

    comment_kick.assert_awaited_once_with(*ids, locale="ru")


@pytest.mark.asyncio
async def test_cleanup_scheduler_and_wait_are_noops():
    config = queue.DeadLetterCleanupConfig(retention_days=7, interval_seconds=60)

    assert await queue.cleanup_dead_lettered_jobs(config.retention_days) == 0
    stop = await queue.start_dead_letter_cleanup_scheduler(config)
    assert await stop() is None
    assert await queue.wait_for_all_jobs(timeout=0.01) is None
    assert await queue.shutdown_notification_queue() is None


@pytest.mark.asyncio
async def test_record_failure_updates_queue_metrics():
    job = queue.NotificationJob(kind="event", record_id=uuid.uuid4())
    metric = MagicMock()

    with (
        patch.object(queue.metrics, "record_notification_failed") as record_metric,
        patch.object(queue, "_queue_metrics", metric),
    ):
        await queue.record_enqueue_failure(job, RuntimeError("queue full"), "test")

    records = await queue.get_failed_enqueue_records()
    assert records[-1].job is job
    assert records[-1].error == "queue full"
    assert records[-1].source == "test"
    record_metric.assert_called_once_with(
        notification_type="event", reason="enqueue_failure"
    )
    metric.enqueue_failures_total.labels.assert_called_once_with(kind="event")
    metric.enqueue_failures_total.labels.return_value.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_record_failure_survives_metric_errors_and_state_can_reset():
    job = queue.NotificationJob(kind="news", record_id=uuid.uuid4())
    broken_metric = MagicMock()
    broken_metric.enqueue_failures_total.labels.side_effect = RuntimeError("metrics")

    with (
        patch.object(queue.metrics, "record_notification_failed"),
        patch.object(queue, "_queue_metrics", broken_metric),
    ):
        await queue.record_enqueue_failure(job, OSError("disk"), "test")

    assert (await queue.get_failed_enqueue_records())[-1].error == "disk"
    await queue.reset_testing_state()
    assert await queue.get_failed_enqueue_records() == []
