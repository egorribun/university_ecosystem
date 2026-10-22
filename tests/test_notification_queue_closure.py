"""Closure tests for the NATS-backed notification queue compatibility API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import notification_queue as queue


@pytest.mark.asyncio
async def test_cleanup_dead_lettered_jobs_deletes_expired_rows():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=2)
    supplied_now = datetime(2026, 8, 17, tzinfo=UTC)

    with (
        patch("app.services.notification_queue.datetime") as datetime_type,
        patch.object(queue.logger, "info") as info,
    ):
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
    info.assert_called_once_with(
        "Removed %s expired notification queue dead letters",
        2,
    )


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
async def test_cleanup_dead_lettered_jobs_normalizes_non_utc_offsets():
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)

    await queue.cleanup_dead_lettered_jobs(
        7,
        db=db,
        now=datetime(2026, 8, 17, 3, tzinfo=timezone(timedelta(hours=3))),
    )

    cutoff = next(
        value
        for name, value in db.execute.await_args.args[0].compile().params.items()
        if name.startswith("enqueued_at")
    )
    assert cutoff == datetime(2026, 8, 10, tzinfo=UTC)


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
    error = RuntimeError("queue full")
    metric = MagicMock()

    with (
        patch.object(queue.metrics, "record_notification_failed") as record_metric,
        patch.object(queue, "_queue_metrics", metric),
        patch.object(queue.logger, "error") as error_log,
    ):
        await queue.report_enqueue_failure(
            notification_type="event",
            record_id=record_id,
            error=error,
            source="test",
        )

    error_log.assert_called_once_with(
        "Failed to enqueue %s notification for ID %s (source=%s): %s",
        "event",
        record_id,
        "test",
        error,
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


def test_enqueue_wrappers_are_removed_from_the_queue_module():
    """AUD-198: live notifications come from the durable outbox; NATS wrappers that dropped work are gone."""
    for name in (
        "enqueue_event_notification",
        "enqueue_news_notification",
        "enqueue_comment_notification",
    ):
        assert not hasattr(queue, name)
