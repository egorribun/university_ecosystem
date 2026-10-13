"""Focused cache and factory coverage for schedule repositories."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ConfigDict

import app.models as models
from app.core.cache import schedule_cache
from app.repositories.base import BaseRepository
from app.repositories.schedule_repository import (
    GroupRepository,
    ScheduleRepository,
    _restore_cached,
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
@pytest.mark.parametrize(
    ("database_rows", "expected_subjects"),
    [([object()], ["Updated Physics"]), ([], [])],
    ids=["updated-in-another-worker", "deleted-in-another-worker"],
)
async def test_schedule_repository_ignores_stale_process_cache(
    database_rows, expected_subjects
):
    """A stale worker-local value must not replace the current database result."""

    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    old_item = ScheduleDTO(
        id=uuid4(),
        group_id=group_id,
        weekday="monday",
        start_time=datetime(2026, 1, 1, 9, 0),
        end_time=datetime(2026, 1, 1, 10, 30),
        subject="Old Physics",
        teacher="Prof. Xavier",
        room="A-101",
    )
    current_item = ScheduleDTO(
        id=uuid4(),
        group_id=group_id,
        weekday="monday",
        start_time=datetime(2026, 1, 1, 9, 0),
        end_time=datetime(2026, 1, 1, 10, 30),
        subject="Updated Physics",
        teacher="Prof. Xavier",
        room="A-101",
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = database_rows
    repo.db.execute = AsyncMock(return_value=result)

    with (
        patch.object(
            schedule_cache,
            "get",
            new=AsyncMock(return_value=[old_item.model_dump(mode="json")]),
        ) as cache_get,
        patch.object(schedule_cache, "set", new=AsyncMock()) as cache_set,
        patch.object(repo, "_to_dto", return_value=current_item) as to_dto,
    ):
        rows = await repo.get_by_group(group_id)

    assert [row.subject for row in rows] == expected_subjects
    repo.db.execute.assert_awaited_once()
    cache_get.assert_not_awaited()
    cache_set.assert_not_awaited()
    if database_rows:
        to_dto.assert_called_once_with(database_rows[0])
    else:
        to_dto.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [{"items": []}, "invalid-cache-payload", False])
async def test_non_list_group_cache_hit_returns_empty_collection(cached):
    """Malformed group-cache containers must not leak mappings or scalars."""

    db = MagicMock(execute=AsyncMock())
    with (
        patch.object(schedule_cache, "get", new=AsyncMock(return_value=cached)) as get,
        patch.object(schedule_cache, "set", new=AsyncMock()) as set_cache,
    ):
        result = await GroupRepository(db).list_groups()
        get.assert_awaited_once_with("schedule:groups")

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


def test_cached_instances_preserve_identity_with_revalidating_model() -> None:
    """The generic cache helper must not replace already-created DTOs."""

    class RevalidatingGroupDTO(GroupDTO):
        model_config = ConfigDict(revalidate_instances="always")

    dto = RevalidatingGroupDTO(id=uuid4(), name="Group Gamma")
    payload = {"id": uuid4(), "name": "Group Delta"}

    # This real Pydantic policy rebuilds even a valid existing instance.
    assert RevalidatingGroupDTO.model_validate(dto) is not dto

    result = _restore_cached(RevalidatingGroupDTO, [dto, payload])

    assert result[0] is dto
    assert result[0].name == "Group Gamma"
    assert result[1].id == payload["id"]
    assert result[1].name == "Group Delta"
    assert isinstance(result[1], RevalidatingGroupDTO)


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
async def test_schedule_repository_queries_without_process_cache():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    item = MagicMock()
    dto = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    repo.db.execute = AsyncMock(return_value=result)

    with (
        patch.object(
            schedule_cache, "get", new=AsyncMock(return_value=None)
        ) as cache_get,
        patch.object(schedule_cache, "set", new=AsyncMock()) as cache_set,
        patch.object(repo, "_to_dto", return_value=dto),
    ):
        result_dtos = await repo.get_by_group(group_id)

    assert result_dtos == [dto]
    repo.db.execute.assert_awaited_once()
    cache_get.assert_not_awaited()
    cache_set.assert_not_awaited()


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
async def test_schedule_mutation_lock_is_transaction_scoped_and_postgres_only():
    postgres_db = MagicMock()
    postgres_db.get_bind.return_value.dialect.name = "postgresql"
    postgres_db.execute = AsyncMock()
    postgres_repo = ScheduleRepository(postgres_db)

    await postgres_repo.lock_schedule_mutations()

    postgres_db.execute.assert_awaited_once()
    statement, parameters = postgres_db.execute.await_args.args
    assert "pg_advisory_xact_lock" in str(statement)
    assert "pg_advisory_lock(" not in str(statement)
    assert parameters == {
        "namespace": "university_ecosystem.schedule",
        "operation": "mutation",
    }

    sqlite_db = MagicMock()
    sqlite_db.get_bind.return_value.dialect.name = "sqlite"
    sqlite_db.execute = AsyncMock()
    await ScheduleRepository(sqlite_db).lock_schedule_mutations()
    sqlite_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_row_read_refreshes_identity_map_and_takes_row_lock():
    repo = ScheduleRepository(MagicMock())
    schedule_id = uuid4()
    orm_item = MagicMock()
    dto = MagicMock()
    repo.db.get = AsyncMock(return_value=orm_item)

    with patch.object(repo, "_to_dto", return_value=dto):
        result = await repo.get_for_update_fresh(schedule_id)

    assert result is dto
    repo.db.get.assert_awaited_once_with(
        models.Schedule,
        schedule_id,
        with_for_update=True,
        populate_existing=True,
    )


@pytest.mark.asyncio
async def test_conflict_candidates_bypass_cache_and_have_no_display_limit():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    dto = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [MagicMock()]
    repo.db.execute = AsyncMock(return_value=result)

    with (
        patch.object(schedule_cache, "get", new=AsyncMock()) as cache_get,
        patch.object(repo, "_to_dto", return_value=dto),
    ):
        candidates = await repo.get_conflict_candidates(group_id, "Professor X")

    assert candidates == [dto]
    cache_get.assert_not_awaited()
    repo.db.execute.assert_awaited_once()
    statement = str(repo.db.execute.await_args.args[0])
    assert (
        repo.db.execute.await_args.args[0]._execution_options["populate_existing"]
        is True
    )
    assert "schedule.group_id" in statement
    assert "schedule.teacher" in statement
    assert " OR " in statement
    assert "LIMIT" not in statement.upper()


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


@pytest.mark.asyncio
async def test_conflict_candidates_accept_multiple_teacher_names():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    dto = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [MagicMock()]
    repo.db.execute = AsyncMock(return_value=result)

    with patch.object(repo, "_to_dto", return_value=dto):
        candidates = await repo.get_conflict_candidates(
            group_id, ("Professor X", "Professor Y")
        )

    assert candidates == [dto]
    statement = str(repo.db.execute.await_args.args[0])
    assert "schedule.group_id" in statement
    assert "schedule.teacher IN" in statement
    assert " OR " in statement
    assert "LIMIT" not in statement.upper()
