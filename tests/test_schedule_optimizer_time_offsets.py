"""Offset-aware time inputs use the same UTC contract as datetime inputs."""

from datetime import UTC, datetime, time, timedelta, timezone

import pytest

from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


@pytest.mark.parametrize("offset_minutes", [None, 0, 180, -330])
def test_time_and_datetime_inputs_have_identical_native_instants(
    offset_minutes: int | None,
) -> None:
    zone = (
        None
        if offset_minutes is None
        else timezone(timedelta(minutes=offset_minutes))
    )
    start = time(11, 15, tzinfo=zone)
    end = time(12, 45, tzinfo=zone)
    time_item = ScheduleItemInternal(
        weekday="Monday",
        start_time=start,
        end_time=end,
        parity="both",
    )
    datetime_item = time_item.model_copy(
        update={
            "start_time": datetime.combine(datetime(1970, 1, 1).date(), start),
            "end_time": datetime.combine(datetime(1970, 1, 1).date(), end),
        }
    )
    optimizer = ScheduleOptimizerService()

    native_time = optimizer._to_rust_item(time_item)
    native_datetime = optimizer._to_rust_item(datetime_item)

    assert native_time.start_time == native_datetime.start_time
    assert native_time.end_time == native_datetime.end_time
    offset_seconds = (offset_minutes or 0) * 60
    assert native_time.start_time == 11 * 3600 + 15 * 60 - offset_seconds
    assert native_time.end_time == 12 * 3600 + 45 * 60 - offset_seconds


@pytest.mark.asyncio
@pytest.mark.integration
async def test_time_offset_cannot_hide_single_or_batch_conflicts() -> None:
    optimizer = ScheduleOptimizerService()
    existing = ScheduleItemInternal(
        id=1,
        weekday="Monday",
        start_time=time(11, tzinfo=timezone(timedelta(hours=3))),
        end_time=time(12, tzinfo=timezone(timedelta(hours=3))),
        parity="both",
        room="101",
        teacher="Synthetic Teacher",
    )
    target = ScheduleItemInternal(
        id=2,
        weekday="Monday",
        start_time=time(8, 30, tzinfo=UTC),
        end_time=time(9, 30, tzinfo=UTC),
        parity="both",
    )

    conflicts = await optimizer.detect_conflicts(target, [existing])
    pairs = await optimizer.batch_detect_conflicts([target, existing])

    assert [item.id for item in conflicts] == [1]
    assert conflicts[0].room == "101"
    assert conflicts[0].teacher == "Synthetic Teacher"
    assert len(pairs) == 1
    assert {item.id for item in pairs[0]} == {1, 2}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_optimal_slot_respects_offset_aware_time_occupancy() -> None:
    existing = ScheduleItemInternal(
        weekday="Monday",
        start_time=time(11, tzinfo=timezone(timedelta(hours=3))),
        end_time=time(12, tzinfo=timezone(timedelta(hours=3))),
        parity="both",
    )

    suggested = await ScheduleOptimizerService().find_optimal_slot(
        60, [existing], preferred_weekdays=["Monday"]
    )

    assert suggested is not None
    assert suggested.weekday == "Monday"
    assert suggested.start_time.hour == 9
    assert suggested.end_time.hour == 10
