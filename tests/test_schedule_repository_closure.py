"""Focused cache and factory coverage for schedule repositories."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.models as models
from app.core.cache import schedule_cache
from app.repositories.base import BaseRepository
from app.repositories.schedule_repository import (
    GroupRepository,
    ScheduleRepository,
    get_group_repository,
    get_schedule_repository,
)
from app.schemas.dtos import GroupDTO, ScheduleDTO


@pytest.mark.asyncio
async def test_group_repository_rebuilds_dtos_from_the_cache():
    """A cache hit must return DTOs, not the dicts the cache actually holds.

    The cache stores ``model_dump(mode="json")`` output so orjson can
    serialize it for L2 -- the sibling cache-miss tests below pin that.  These
    tests used to seed a sentinel string and assert it came back untouched,
    which described a pass-through that silently handed every caller ``dict``
    where it read DTO attributes.
    """

    repo = GroupRepository(MagicMock())
    group_id = uuid4()
    cached = [
        GroupDTO(
            id=group_id, name="Group Alpha", created_at=datetime(2026, 1, 1, 9, 0)
        ).model_dump(mode="json")
    ]

    with patch.object(schedule_cache, "get", new=AsyncMock(return_value=cached)):
        result = await repo.list_groups()

    assert [type(item) for item in result] == [GroupDTO]
    assert result[0].id == group_id
    assert result[0].name == "Group Alpha"


@pytest.mark.asyncio
async def test_schedule_repository_rebuilds_dtos_from_the_cache():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    lesson_id = uuid4()
    cached = [
        ScheduleDTO(
            id=lesson_id,
            group_id=group_id,
            weekday="monday",
            start_time=datetime(2026, 1, 1, 9, 0),
            end_time=datetime(2026, 1, 1, 10, 30),
            subject="Physics",
            teacher="Prof. Xavier",
            room="A-101",
        ).model_dump(mode="json")
    ]

    with patch.object(schedule_cache, "get", new=AsyncMock(return_value=cached)):
        result = await repo.get_by_group(group_id)

    assert [type(item) for item in result] == [ScheduleDTO]
    assert result[0].subject == "Physics"
    # The ICS export reads these three; a dict would have yielded None for each
    # and produced an empty calendar.
    assert result[0].weekday == "monday"
    assert result[0].start_time is not None
    assert result[0].end_time is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_kind", ["group", "schedule"])
@pytest.mark.parametrize("cached", [{"items": []}, "invalid-cache-payload", False])
async def test_non_list_cache_hit_returns_empty_collection(repository_kind, cached):
    """Malformed cached containers must not leak mappings or scalars to callers."""

    db = MagicMock(execute=AsyncMock())
    group_id = uuid4()
    with (
        patch.object(schedule_cache, "get", new=AsyncMock(return_value=cached)) as get,
        patch.object(schedule_cache, "set", new=AsyncMock()) as set_cache,
    ):
        if repository_kind == "group":
            result = await GroupRepository(db).list_groups()
            get.assert_awaited_once_with("schedule:groups")
        else:
            result = await ScheduleRepository(db).get_by_group(group_id)
            get.assert_awaited_once_with(f"schedule:group:{group_id}")

    assert result == []
    db.execute.assert_not_awaited()
    set_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_dtos_are_passed_through_untouched():
    """An L1 hit can hand back the DTO objects themselves; do not re-validate."""

    repo = GroupRepository(MagicMock())
    dto = GroupDTO(id=uuid4(), name="Group Beta")

    with patch.object(schedule_cache, "get", new=AsyncMock(return_value=[dto])):
        result = await repo.list_groups()

    assert result[0] is dto


@pytest.mark.asyncio
async def test_create_records_creator_and_invalidates_global_cache():
    repo = ScheduleRepository(MagicMock())
    payload = {
        "subject": "Independent study",
        "start_time": datetime(2026, 1, 1, 10, 0),
        "end_time": datetime(2026, 1, 1, 11, 0),
    }
    created = object()

    with (
        patch.object(
            BaseRepository, "create", new=AsyncMock(return_value=created)
        ) as base_create,
        patch.object(schedule_cache, "delete", new=AsyncMock()) as delete,
    ):
        result = await repo.create(payload, creator_id="creator-1")

    assert result is created
    base_create.assert_awaited_once()
    created_payload = base_create.await_args.args[0]
    assert created_payload["creator_id"] == "creator-1"
    assert delete.await_count == 1
    delete.assert_awaited_once_with("schedule:groups")


def test_repository_factories_bind_database():
    db = MagicMock()

    assert get_group_repository(db).db is db
    assert get_schedule_repository(db).db is db


def test_repository_model_and_dto_properties():
    group_repo = GroupRepository(MagicMock())
    schedule_repo = ScheduleRepository(MagicMock())

    assert group_repo.model is models.Group
    assert group_repo.dto_class.__name__ == "GroupDTO"
    assert schedule_repo.model is models.Schedule
    assert schedule_repo.dto_class.__name__ == "ScheduleDTO"


@pytest.mark.asyncio
async def test_group_repository_cache_miss_queries_and_serializes():
    repo = GroupRepository(MagicMock())
    group = MagicMock()
    dto = MagicMock()
    dto.model_dump.return_value = {"name": "Group Alpha"}
    result = MagicMock()
    result.scalars.return_value.all.return_value = [group]
    repo.db.execute = AsyncMock(return_value=result)

    with (
        patch.object(schedule_cache, "get", new=AsyncMock(return_value=None)),
        patch.object(schedule_cache, "set", new=AsyncMock()) as set_cache,
        patch.object(repo, "_to_dto", return_value=dto),
    ):
        result_dtos = await repo.list_groups()

    assert result_dtos == [dto]
    set_cache.assert_awaited_once_with("schedule:groups", [{"name": "Group Alpha"}])


@pytest.mark.asyncio
async def test_schedule_repository_cache_miss_queries_and_serializes():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    item = MagicMock()
    dto = MagicMock()
    dto.model_dump.return_value = {"subject": "Physics"}
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    repo.db.execute = AsyncMock(return_value=result)

    with (
        patch.object(schedule_cache, "get", new=AsyncMock(return_value=None)),
        patch.object(schedule_cache, "set", new=AsyncMock()) as set_cache,
        patch.object(repo, "_to_dto", return_value=dto),
    ):
        result_dtos = await repo.get_by_group(group_id)

    assert result_dtos == [dto]
    set_cache.assert_awaited_once_with(
        f"schedule:group:{group_id}", [{"subject": "Physics"}]
    )


@pytest.mark.asyncio
async def test_schedule_repository_get_by_teacher_queries_and_maps():
    repo = ScheduleRepository(MagicMock())
    item = MagicMock()
    dto = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    repo.db.execute = AsyncMock(return_value=result)

    with patch.object(repo, "_to_dto", return_value=dto):
        result_dtos = await repo.get_by_teacher("Professor X")

    assert result_dtos == [dto]
    repo.db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_with_group_id_without_creator_invalidates_group_cache():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    payload = {
        "group_id": group_id,
        "subject": "Independent study",
        "start_time": datetime(2026, 1, 1, 10, 0),
        "end_time": datetime(2026, 1, 1, 11, 0),
    }

    with (
        patch.object(BaseRepository, "create", new=AsyncMock(return_value="created")),
        patch.object(schedule_cache, "delete", new=AsyncMock()) as delete,
    ):
        result = await repo.create(payload)

    assert result == "created"
    assert [entry.args[0] for entry in delete.await_args_list] == [
        f"schedule:group:{group_id}",
        "schedule:groups",
    ]


@pytest.mark.asyncio
async def test_create_accepts_model_dump_input():
    repo = ScheduleRepository(MagicMock())

    class Payload:
        def model_dump(self):
            return {
                "subject": "Independent study",
                "start_time": datetime(2026, 1, 1, 10, 0),
                "end_time": datetime(2026, 1, 1, 11, 0),
            }

    with (
        patch.object(BaseRepository, "create", new=AsyncMock(return_value="created")),
        patch.object(schedule_cache, "delete", new=AsyncMock()),
    ):
        result = await repo.create(Payload())

    assert result == "created"
