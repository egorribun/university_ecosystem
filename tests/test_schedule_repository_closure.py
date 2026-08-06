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


@pytest.mark.asyncio
async def test_group_repository_returns_cached_groups():
    repo = GroupRepository(MagicMock())

    with patch.object(
        schedule_cache, "get", new=AsyncMock(return_value=["cached-group"])
    ):
        result = await repo.list_groups()

    assert result == ["cached-group"]


@pytest.mark.asyncio
async def test_schedule_repository_returns_cached_items():
    repo = ScheduleRepository(MagicMock())

    with patch.object(
        schedule_cache, "get", new=AsyncMock(return_value=["cached-item"])
    ):
        result = await repo.get_by_group(uuid4())

    assert result == ["cached-item"]


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
