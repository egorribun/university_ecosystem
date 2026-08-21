import uuid
from datetime import UTC, datetime, time
from unittest.mock import MagicMock, patch

import pytest

from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


@pytest.fixture
def optimizer_service():
    return ScheduleOptimizerService()


@pytest.fixture
def sample_item():
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
async def test_batch_uuidv7_prefix_collisions_preserve_both_items(
    optimizer_service,
) -> None:
    """UUIDv7 values sharing a timestamp prefix must not overwrite metadata."""
    first = ScheduleItemInternal(
        id=uuid.UUID("018f0000-0000-7000-8000-000000000001"),
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
        room="101A",
    )
    second = first.model_copy(
        update={
            "id": uuid.UUID("018f0000-0000-7000-8000-000000000002"),
            "room": "102B",
        }
    )

    conflicts = await optimizer_service.batch_detect_conflicts([first, second])

    assert len(conflicts) == 1
    returned = {item.id: item.room for pair in conflicts for item in pair}
    assert returned == {first.id: "101A", second.id: "102B"}


@pytest.mark.asyncio
async def test_find_optimal_slot_success(optimizer_service, sample_item):
    result = await optimizer_service.find_optimal_slot(
        90, [sample_item], preferred_weekdays=["Tuesday"]
    )
    assert result is not None
    assert result.weekday == "Tuesday"
    assert result.room == "Auto"


@pytest.mark.asyncio
async def test_uuid_id_conversion(optimizer_service) -> None:
    # Verify UUID id mapping branch
    u_id = uuid.uuid4()
    item = ScheduleItemInternal(
        id=u_id,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )
    rust_item = optimizer_service._to_rust_item(item)
    expected_id = int.from_bytes(u_id.bytes[:4], "big") & 0x7FFFFFFF
    assert rust_item.id == expected_id


@pytest.mark.asyncio
async def test_time_objects_conversion(optimizer_service) -> None:
    # Verify st/et of type time mapping branch
    item = ScheduleItemInternal(
        id=1,
        weekday="Monday",
        start_time=time(9, 30),
        end_time=time(11, 0),
        parity="both",
    )
    rust_item = optimizer_service._to_rust_item(item)
    expected_st = int(
        datetime.combine(
            datetime(1970, 1, 1).date(), time(9, 30), tzinfo=UTC
        ).timestamp()
    )
    expected_et = int(
        datetime.combine(
            datetime(1970, 1, 1).date(), time(11, 0), tzinfo=UTC
        ).timestamp()
    )
    assert rust_item.start_time == expected_st
    assert rust_item.end_time == expected_et


@pytest.mark.asyncio
async def test_detect_conflicts_exception_handling(
    optimizer_service, sample_item
) -> None:
    with patch("rust_ext.detect_conflicts", side_effect=RuntimeError("FFI failed")):
        with pytest.raises(
            RuntimeError, match="Schedule conflict detection unavailable"
        ):
            await optimizer_service.detect_conflicts(sample_item, [sample_item])


@pytest.mark.asyncio
async def test_batch_detect_conflicts_exception_handling(
    optimizer_service, sample_item
) -> None:
    with patch(
        "rust_ext.batch_detect_conflicts", side_effect=RuntimeError("FFI failed")
    ):
        with pytest.raises(
            RuntimeError, match="Schedule batch conflict detection unavailable"
        ):
            await optimizer_service.batch_detect_conflicts([sample_item])


@pytest.mark.asyncio
async def test_find_optimal_slot_fallback_type_error(
    optimizer_service, sample_item
) -> None:
    # Test fallback branch when find_optimal_slot first call raises TypeError
    mock_find = MagicMock()
    mock_find.side_effect = [TypeError("Wrong arguments"), None]

    with patch("rust_ext.find_optimal_slot", mock_find):
        result = await optimizer_service.find_optimal_slot(
            60, [sample_item], ["Monday"]
        )
        assert result is None
        assert mock_find.call_count == 2


@pytest.mark.asyncio
async def test_find_optimal_slot_exception_handling(
    optimizer_service, sample_item
) -> None:
    # Test find_optimal_slot RuntimeError propagation
    with patch("rust_ext.find_optimal_slot", side_effect=RuntimeError("FFI failed")):
        with pytest.raises(RuntimeError, match="FFI failed"):
            await optimizer_service.find_optimal_slot(60, [sample_item], ["Monday"])


@pytest.mark.asyncio
async def test_to_rust_item_other_id_type(optimizer_service) -> None:
    item = ScheduleItemInternal(
        id=None,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )
    rust_item = optimizer_service._to_rust_item(item)
    assert rust_item.id is None
