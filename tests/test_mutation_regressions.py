"""Fast, deterministic contracts for mutation-prone service boundaries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.services.notification_service import NotificationService
from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


def _schedule_item(
    item_id: int,
    *,
    room: str,
    teacher: str,
) -> ScheduleItemInternal:
    return ScheduleItemInternal(
        id=item_id,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
        room=room,
        teacher=teacher,
    )


@pytest.mark.asyncio
async def test_news_enqueue_failure_report_keeps_complete_metadata() -> None:
    service = NotificationService(db=AsyncMock())
    news_id = uuid.uuid4()
    failure = RuntimeError("queue full")
    background = MagicMock(spec=BackgroundTasks)
    background.add_task.side_effect = failure

    with patch(
        "app.services.notification_service.notification_queue.report_enqueue_failure",
        new=AsyncMock(),
    ) as report:
        await service.dispatch_news_created(news_id, "en", background)

    report.assert_awaited_once_with(
        notification_type="news",
        record_id=news_id,
        error=failure,
        source="NotificationService.dispatch_news_created",
    )


def test_uuid_rust_conversion_uses_stable_four_byte_prefix() -> None:
    service = ScheduleOptimizerService()
    item_id = uuid.UUID("12345678-1234-5678-90ab-cdef12345678")
    item = ScheduleItemInternal(
        id=item_id,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )

    rust_item = service._to_rust_item(item)

    expected_id = int.from_bytes(item_id.bytes[:4], "big") & 0x7FFFFFFF
    assert rust_item.id == expected_id


@pytest.mark.asyncio
async def test_batch_conflict_stub_restores_both_domain_metadata() -> None:
    service = ScheduleOptimizerService()
    first = _schedule_item(101, room="101A", teacher="Dr. Smith")
    second = _schedule_item(202, room="202B", teacher="Prof. Jones")

    def return_first_pair(rust_items):
        return [(rust_items[0], rust_items[1])]

    with patch(
        "rust_ext.batch_detect_conflicts",
        side_effect=return_first_pair,
    ):
        conflicts = await service.batch_detect_conflicts([first, second])

    assert len(conflicts) == 1
    returned = {item.id: item for pair in conflicts for item in pair}
    assert returned[101].room == "101A"
    assert returned[101].teacher == "Dr. Smith"
    assert returned[202].room == "202B"
    assert returned[202].teacher == "Prof. Jones"
