"""Date-less inputs preserve offsets without inferring DST or weekdays."""

from datetime import UTC, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

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


@pytest.mark.parametrize("field", ["start_time", "end_time"])
@pytest.mark.parametrize("zone_name", ["America/New_York", "Europe/Berlin"])
def test_time_with_date_dependent_zone_remains_semantically_naive(
    field: str, zone_name: str
) -> None:
    value = time(11, 15, tzinfo=ZoneInfo(zone_name))
    assert value.utcoffset() is None
    item = ScheduleItemInternal(
        weekday="Monday",
        start_time=time(10),
        end_time=time(12),
        parity="both",
    ).model_copy(update={field: value})

    native = ScheduleOptimizerService()._to_rust_item(item)

    assert getattr(native, field) == 11 * 3600 + 15 * 60
    assert native.weekday == "Monday"


@pytest.mark.parametrize("field", ["start_time", "end_time"])
@pytest.mark.parametrize(
    "value",
    [
        time(1, tzinfo=timezone(timedelta(hours=3))),
        time(23, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
def test_offset_time_cannot_silently_move_to_another_weekday(
    field: str, value: time
) -> None:
    item = ScheduleItemInternal(
        weekday="Monday",
        start_time=time(10),
        end_time=time(12),
        parity="odd",
    ).model_copy(update={field: value})

    with pytest.raises(ValueError, match="crosses a UTC day"):
        ScheduleOptimizerService()._to_rust_item(item)


@pytest.mark.parametrize("offset_hours,hour", [(3, 1), (-3, 23)])
def test_dated_datetime_conversion_and_explicit_weekday_are_unchanged(
    offset_hours: int, hour: int
) -> None:
    start = datetime(
        2026, 7, 6, hour, tzinfo=timezone(timedelta(hours=offset_hours))
    )
    end = start + timedelta(minutes=30)
    item = ScheduleItemInternal(
        weekday="Monday",
        start_time=start,
        end_time=end,
        parity="odd",
    )

    native = ScheduleOptimizerService()._to_rust_item(item)

    assert native.start_time == int(start.timestamp())
    assert native.end_time == int(end.timestamp())
    assert native.weekday == "Monday"
    assert native.parity == "odd"


def test_dated_zoneinfo_keeps_its_real_summer_offset() -> None:
    start = datetime(2026, 7, 6, 11, tzinfo=ZoneInfo("Europe/Berlin"))
    item = ScheduleItemInternal(
        weekday="Monday",
        start_time=start,
        end_time=start + timedelta(hours=1),
        parity="both",
    )

    native = ScheduleOptimizerService()._to_rust_item(item)

    assert native.start_time == int(start.timestamp())
    assert native.start_time % 86400 == 9 * 3600


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["single", "batch", "slot"])
async def test_midnight_time_rejection_propagates_through_optimizer_operations(
    operation: str,
) -> None:
    item = ScheduleItemInternal(
        weekday="Monday",
        start_time=time(1, tzinfo=timezone(timedelta(hours=3))),
        end_time=time(2, tzinfo=timezone(timedelta(hours=3))),
        parity="both",
    )
    optimizer = ScheduleOptimizerService()

    with pytest.raises(ValueError, match="crosses a UTC day"):
        if operation == "single":
            await optimizer.detect_conflicts(item, [])
        elif operation == "batch":
            await optimizer.batch_detect_conflicts([item])
        else:
            await optimizer.find_optimal_slot(60, [item], ["Monday"])


def test_time_conversion_uses_explicit_offset_not_an_invented_date() -> None:
    class DateSensitiveZone(tzinfo):
        def utcoffset(self, dt: datetime | None) -> timedelta:
            return timedelta(hours=3 if dt is None else 7)

        def dst(self, dt: datetime | None) -> timedelta:
            return timedelta(0)

    item = ScheduleItemInternal(
        weekday="Monday",
        start_time=time(11, tzinfo=DateSensitiveZone()),
        end_time=time(12, tzinfo=DateSensitiveZone()),
        parity="both",
    )

    native = ScheduleOptimizerService()._to_rust_item(item)

    assert native.start_time == 8 * 3600
    assert native.end_time == 9 * 3600
    assert native.weekday == "Monday"
