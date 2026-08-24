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


@pytest.mark.timeout(5)
def test_unique_id_allocator_keeps_surrogate_mapping(optimizer_service) -> None:
    item = ScheduleItemInternal(
        id=uuid.UUID("018f0000-0000-7000-8000-000000000001"),
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )

    rust_items, rust_id_map = optimizer_service._to_rust_items_with_unique_ids([item])

    assert [rust_item.id for rust_item in rust_items] == [2_147_483_647]
    assert rust_id_map == {2_147_483_647: item}


@pytest.mark.asyncio
async def test_batch_conflicts_restore_both_metadata_with_native_pair(
    optimizer_service,
) -> None:
    first = ScheduleItemInternal(
        id=101,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
        room="101A",
        teacher="Dr. Smith",
    )
    second = first.model_copy(
        update={
            "id": 202,
            "room": "202B",
            "teacher": "Prof. Jones",
        }
    )

    def return_first_pair(rust_items):
        return [(rust_items[0], rust_items[1])]

    with patch(
        "rust_ext.batch_detect_conflicts",
        side_effect=return_first_pair,
    ):
        conflicts = await optimizer_service.batch_detect_conflicts([first, second])

    assert len(conflicts) == 1
    returned = {item.id: item for pair in conflicts for item in pair}
    assert returned[101].room == "101A"
    assert returned[101].teacher == "Dr. Smith"
    assert returned[202].room == "202B"
    assert returned[202].teacher == "Prof. Jones"


def test_reconstruct_conflict_item_restores_original_metadata(
    optimizer_service, sample_item
) -> None:
    native_item = MagicMock()
    reconstructed = sample_item.model_copy(update={"id": None})

    with patch.object(
        optimizer_service, "_from_rust_item", return_value=reconstructed
    ) as from_rust_item:
        result = optimizer_service._reconstruct_conflict_item(
            (native_item, sample_item)
        )

    from_rust_item.assert_called_once_with(native_item, "101A", "Dr. Smith")
    assert result is reconstructed
    assert result.id == sample_item.id


def test_reconstruct_conflict_item_keeps_unknown_native_identity(optimizer_service):
    native_item = MagicMock()
    reconstructed = ScheduleItemInternal(
        id=None,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )

    with patch.object(
        optimizer_service, "_from_rust_item", return_value=reconstructed
    ) as from_rust_item:
        result = optimizer_service._reconstruct_conflict_item((native_item, None))

    from_rust_item.assert_called_once_with(native_item, None, None)
    assert result is reconstructed
    assert result.id is None


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
@pytest.mark.integration
async def test_batch_detect_conflicts(optimizer_service, sample_item):
    target = ScheduleItemInternal(
        id=2,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 11, 00, tzinfo=UTC),
        parity="both",
        room="102B",
        teacher="Prof. Jones",
    )
    result = await optimizer_service.batch_detect_conflicts([sample_item, target])
    assert len(result) == 1
    a, b = result[0]
    # Check that metadata and original identifiers were correctly restored.
    returned = {item.id: item for item in (a, b)}
    assert returned[1].room == "101A"
    assert returned[1].teacher == "Dr. Smith"
    assert returned[2].room == "102B"
    assert returned[2].teacher == "Prof. Jones"


@pytest.mark.asyncio
@pytest.mark.timeout(5)
@pytest.mark.integration
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

    rust_items, _ = optimizer_service._to_rust_items_with_unique_ids([first, second])
    assert [item.id for item in rust_items] == [2_147_483_647, 2_147_483_646]

    integer_item = first.model_copy(update={"id": 42})
    _, rust_id_map = optimizer_service._to_rust_items_with_unique_ids([integer_item])
    assert rust_id_map[42] is integer_item

    max_id = 2_147_483_647
    occupied_a = first.model_copy(update={"id": max_id})
    occupied_b = second.model_copy(update={"id": max_id - 1})
    occupied_c = first.model_copy(update={"id": max_id - 2})
    uuid_a = first.model_copy(
        update={"id": uuid.UUID("018f0000-0000-7000-8000-000000000003")}
    )
    uuid_b = second.model_copy(
        update={"id": uuid.UUID("018f0000-0000-7000-8000-000000000004")}
    )
    rust_items, _ = optimizer_service._to_rust_items_with_unique_ids(
        [occupied_a, occupied_b, occupied_c, uuid_a, uuid_b]
    )
    assert [item.id for item in rust_items] == [
        max_id,
        max_id - 1,
        max_id - 2,
        max_id - 3,
        max_id - 4,
    ]


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
    u_id = uuid.UUID("12345678-1234-5678-90ab-cdef12345678")
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
    assert optimizer_service._uuid_to_rust_id(u_id) == expected_id


@pytest.mark.asyncio
async def test_detect_conflicts_restores_teacher_metadata(optimizer_service) -> None:
    target = ScheduleItemInternal(
        id=1,
        weekday="Monday",
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        parity="both",
    )
    existing = target.model_copy(
        update={"id": 2, "room": "101A", "teacher": "Dr. Smith"}
    )

    conflicts = await optimizer_service.detect_conflicts(target, [existing])

    assert len(conflicts) == 1
    assert conflicts[0].id == existing.id
    assert conflicts[0].room == existing.room
    assert conflicts[0].teacher == existing.teacher


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
