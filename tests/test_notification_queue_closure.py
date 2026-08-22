"""Closure tests for the NATS-backed notification queue compatibility API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
async def test_cleanup_dead_lettered_jobs_deletes_expired_rows():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=2)
    supplied_now = datetime(2026, 8, 17, tzinfo=UTC)

    with patch("app.services.notification_queue.datetime") as datetime_type:
        datetime_type.now.side_effect = AssertionError(
            "cleanup must honor the supplied timestamp"
        )
        deleted = await queue.cleanup_dead_lettered_jobs(
            7,
            db=db,
            now=supplied_now,
        )

    assert deleted == 2
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
    statement = str(db.execute.await_args.args[0])
    assert "notification_queue_jobs.dead_lettered IS true" in statement
    assert "notification_queue_jobs.enqueued_at <=" in statement


@pytest.mark.asyncio
async def test_cleanup_dead_lettered_jobs_uses_thirty_day_default_retention():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)
    supplied_now = datetime(2026, 8, 17, tzinfo=UTC)

    await queue.cleanup_dead_lettered_jobs(db=db, now=supplied_now)

    statement = db.execute.await_args.args[0]
    bind_values = statement.compile().params
    cutoff = next(
        value for name, value in bind_values.items() if name.startswith("enqueued_at")
    )
    assert cutoff == datetime(2026, 7, 18, tzinfo=UTC)


@pytest.mark.asyncio
async def test_cleanup_dead_lettered_jobs_owns_session_and_validates_retention():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=None)

    with patch.object(queue, "async_session", return_value=context):
        assert (
            await queue.cleanup_dead_lettered_jobs(
                0,
                now=datetime(2026, 8, 17),
            )
            == 0
        )

    context.__aenter__.assert_awaited_once()
    context.__aexit__.assert_awaited_once()
    with pytest.raises(ValueError, match="non-negative"):
        await queue.cleanup_dead_lettered_jobs(-1, db=db)


@pytest.mark.asyncio
async def test_report_failure_updates_queue_metrics():
    record_id = uuid.uuid4()
    metric = MagicMock()

    with (
        patch.object(queue.metrics, "record_notification_failed") as record_metric,
        patch.object(queue, "_queue_metrics", metric),
    ):
        await queue.report_enqueue_failure(
            notification_type="event",
            record_id=record_id,
            error=RuntimeError("queue full"),
            source="test",
        )

    record_metric.assert_called_once_with(
        notification_type="event", reason="enqueue_failure"
    )
    metric.enqueue_failures_total.labels.assert_called_once_with(kind="event")
    metric.enqueue_failures_total.labels.return_value.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_report_failure_survives_optional_metric_errors():
    broken_metric = MagicMock()
    broken_metric.enqueue_failures_total.labels.side_effect = RuntimeError("metrics")

    with (
        patch.object(queue.metrics, "record_notification_failed"),
        patch.object(queue, "_queue_metrics", broken_metric),
        patch.object(queue.logger, "warning") as warning,
    ):
        await queue.report_enqueue_failure(
            notification_type="news",
            record_id=uuid.uuid4(),
            error=OSError("disk"),
            source="test",
        )

    warning.assert_called_once_with(
        "Failed to record metric for enqueue failure", exc_info=True
    )


@pytest.mark.asyncio
async def test_record_failure_without_optional_queue_metrics():
    with (
        patch.object(queue.metrics, "record_notification_failed") as record_metric,
        patch.object(queue, "_queue_metrics", None),
    ):
        await queue.report_enqueue_failure(
            notification_type="event",
            record_id=uuid.uuid4(),
            error=RuntimeError("offline"),
            source="test",
        )

    record_metric.assert_called_once_with(
        notification_type="event", reason="enqueue_failure"
    )


@pytest.mark.asyncio
async def test_enqueue_helpers_report_transport_failures_and_reraise():
    ids = [uuid.uuid4() for _ in range(3)]
    cases = [
        (
            queue.enqueue_event_notification,
            queue.enqueue_event_notification_task,
            (ids[0],),
            {"locale": "en"},
            "event",
            ids[0],
            "enqueue_event_notification",
        ),
        (
            queue.enqueue_news_notification,
            queue.enqueue_news_notification_task,
            (ids[0],),
            {"locale": "ru"},
            "news",
            ids[0],
            "enqueue_news_notification",
        ),
        (
            queue.enqueue_comment_notification,
            queue.enqueue_comment_notification_task,
            tuple(ids),
            {"locale": "en"},
            "comment",
            ids[1],
            "enqueue_comment_notification",
        ),
    ]

    for (
        enqueue,
        task,
        args,
        kwargs,
        expected_kind,
        expected_id,
        expected_source,
    ) in cases:
        transport_error = OSError("nats")
        with (
            patch.object(task, "kick", new=AsyncMock(side_effect=transport_error)),
            patch.object(queue, "report_enqueue_failure", new=AsyncMock()) as report,
            pytest.raises(OSError, match="nats"),
        ):
            await enqueue(*args, **kwargs)
        assert report.await_args.kwargs["notification_type"] == expected_kind
        assert report.await_args.kwargs["record_id"] == expected_id
        assert report.await_args.kwargs["error"] is transport_error
        assert report.await_args.kwargs["source"] == expected_source
