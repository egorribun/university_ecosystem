from datetime import UTC, datetime

import pytest
import pytest_asyncio

from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


@pytest_asyncio.fixture
async def optimizer_service():
    service = ScheduleOptimizerService()
    yield service
    await service.close()


@pytest_asyncio.fixture
async def sample_item():
    return ScheduleItemInternal(
        id=1,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
        parity="both",
        room="101A",
        teacher="Dr. Smith",
    )


@pytest.mark.asyncio
async def test_detect_conflicts_success(optimizer_service, sample_item):
    # Same weekday, overlapping time, same parity = conflict
    target = ScheduleItemInternal(
        id=2,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 11, 00, tzinfo=UTC),
        parity="both",
    )
    conflicts = await optimizer_service.detect_conflicts(target, [sample_item])

    assert len(conflicts) == 1
    assert conflicts[0].weekday == sample_item.weekday
    assert conflicts[0].id == 1
    assert conflicts[0].room == "101A"


@pytest.mark.asyncio
async def test_detect_conflicts_no_match(optimizer_service, sample_item):
    # Different weekday = no conflict
    target = ScheduleItemInternal(
        id=3,
        weekday="Tuesday",
        start_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 11, 00, tzinfo=UTC),
        parity="both",
    )
    conflicts = await optimizer_service.detect_conflicts(target, [sample_item])
    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_batch_detect_conflicts(optimizer_service, sample_item):
    target = ScheduleItemInternal(
        id=2,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 11, 00, tzinfo=UTC),
        parity="both",
        room="102B",
    )
    result = await optimizer_service.batch_detect_conflicts([sample_item, target])
    assert len(result) == 1
    a, b = result[0]
    # Check that metadata was correctly restored
    assert a.room == "101A" or b.room == "101A"
    assert a.room == "102B" or b.room == "102B"


@pytest.mark.asyncio
async def test_find_optimal_slot_success(optimizer_service, sample_item):
    result = await optimizer_service.find_optimal_slot(
        90, [sample_item], preferred_weekdays=["Tuesday"]
    )
    assert result is not None
    assert result.weekday == "Tuesday"
    assert result.room == "Auto"
