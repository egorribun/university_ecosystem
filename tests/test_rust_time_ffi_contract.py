"""Native time behavior at the Python ABI boundary."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

rust_ext = pytest.importorskip("rust_ext", reason="rust_ext not built")


def test_partition_dates_and_errors_remain_python_compatible() -> None:
    info = rust_ext.get_partition_info("events", 0)
    start = datetime.fromisoformat(info.start_date)
    end = datetime.fromisoformat(info.end_date)
    assert start.tzinfo is UTC
    assert end.tzinfo is UTC
    assert start.day == end.day == 1
    assert start.hour == end.hour == 0
    assert info.start_date.endswith("T00:00:00+00:00")
    assert info.end_date.endswith("T00:00:00+00:00")
    assert rust_ext.is_partition_expired("events_y-10000m01", "events", 0)
    assert not rust_ext.is_partition_expired("events_y-262144m01", "events", 0)
    assert not rust_ext.is_partition_expired("events_y2020m01", "events", 2**100)
    with pytest.raises(TypeError):
        rust_ext.is_partition_expired("events_y2020m01", "events", "30")
    with pytest.raises(ValueError, match="month_offset"):
        rust_ext.get_partition_info("events", 121)


def test_slot_uses_utc_next_weekday_and_preserves_integer_validation() -> None:
    before = datetime.now(UTC).date()
    slot = rust_ext.find_optimal_slot(60, [], [("Sunday", [256, 24, 9])])
    after = datetime.now(UTC).date()
    assert slot is not None
    start = datetime.fromtimestamp(slot.start_time, UTC)
    assert start.date() in {
        today + timedelta(days=(6 - today.weekday()) % 7) for today in (before, after)
    }
    assert (start.hour, start.minute, start.second) == (9, 0, 0)
    assert slot.end_time - slot.start_time == 3_600
    assert slot.weekday == "Sunday"
    with pytest.raises(OverflowError):
        rust_ext.find_optimal_slot(-1, [], [])
    with pytest.raises(OverflowError):
        rust_ext.find_optimal_slot(60, [], [("Sunday", [2**32])])


def test_dst_fold_instants_remain_distinct_through_native_items() -> None:
    zone = ZoneInfo("America/New_York")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    first_start, second_start = int(first.timestamp()), int(second.timestamp())
    assert second_start - first_start == 3_600
    item1 = rust_ext.ScheduleItem("sunday", first_start, first_start + 1_800, "both")
    item2 = rust_ext.ScheduleItem("sunday", second_start, second_start + 1_800, "both")
    assert item1.start_time == first_start
    assert item2.start_time == second_start
    assert rust_ext.detect_conflicts(item1, [item2]) == []
