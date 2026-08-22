"""Closure tests for the top-level notification service facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks

from app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_dispatch_event_created_schedules_queue_job():
    service = NotificationService(db=AsyncMock())
    background = MagicMock(spec=BackgroundTasks)

    await service.dispatch_event_created(uuid4(), "en", background)

    background.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_event_created_records_runtime_and_os_errors():
    service = NotificationService(db=AsyncMock())
    background = MagicMock()
    background.add_task.side_effect = OSError("queue unavailable")

    with patch(
        "app.services.notification_service.notification_queue.report_enqueue_failure",
        new=AsyncMock(),
    ) as record:
        await service.dispatch_event_created(7, "ru", background)

    record.assert_awaited_once()
    assert (
        record.await_args.kwargs["source"]
        == "NotificationService.dispatch_event_created"
    )
    assert record.await_args.kwargs["record_id"] == 7
    assert isinstance(record.await_args.kwargs["error"], OSError)


@pytest.mark.asyncio
async def test_dispatch_news_and_comment_schedule_jobs():
    service = NotificationService(db=AsyncMock())
    background = MagicMock(spec=BackgroundTasks)
    news_job = AsyncMock()
    comment_job = AsyncMock()

    with (
        patch(
            "app.services.notification_service.notification_queue.enqueue_news_notification",
            news_job,
        ),
        patch(
            "app.services.notification_service.notification_queue.enqueue_comment_notification",
            comment_job,
        ),
    ):
        await service.dispatch_news_created(11, "en", background)
        await service.dispatch_comment_created(12, 13, 14, "ru", background)

    assert background.add_task.call_count == 2
    assert background.add_task.call_args_list[0].args == (news_job, 11)
    assert background.add_task.call_args_list[1].args == (comment_job, 12, 13, 14)


@pytest.mark.asyncio
async def test_dispatch_news_and_comment_swallow_enqueue_errors():
    service = NotificationService(db=AsyncMock())
    background = MagicMock()
    background.add_task.side_effect = RuntimeError("queue full")

    with patch(
        "app.services.notification_service.notification_queue.report_enqueue_failure",
        new=AsyncMock(),
    ) as report:
        await service.dispatch_news_created(1, "en", background)
        await service.dispatch_comment_created(2, 3, 4, "en", background)

    assert [call.kwargs["notification_type"] for call in report.await_args_list] == [
        "news",
        "comment",
    ]
    assert [call.kwargs["source"] for call in report.await_args_list] == [
        "NotificationService.dispatch_news_created",
        "NotificationService.dispatch_comment_created",
    ]


@pytest.mark.asyncio
async def test_send_security_notification_converts_uuid_and_integer_ids():
    service = NotificationService(db=AsyncMock())
    user_id = uuid4()

    with patch(
        "app.services.notification_service.create_notifications_for_users",
        new=AsyncMock(return_value=2),
    ) as create:
        result = await service.send_security_notification([user_id, 5], "Title", "Body")

    assert result == 2
    assert create.await_args.kwargs["user_ids"] == [user_id, UUID(int=5)]
