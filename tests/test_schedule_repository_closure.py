"""Focused query and factory coverage for schedule repositories."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.models as models
from app.repositories.base import BaseRepository
from app.repositories.schedule_repository import (
    GroupRepository,
    ScheduleRepository,
)
from app.schemas.dtos import GroupDTO, ScheduleDTO


@pytest.mark.asyncio
async def test_group_repository_returns_database_dtos():
    group_id = uuid4()
    row = models.Group(id=group_id, name="Current group")
    database_result = MagicMock()
    database_result.scalars.return_value.all.return_value = [row]
    db = MagicMock(execute=AsyncMock(return_value=database_result))

    result = await GroupRepository(db).list_groups()

    assert [type(item) for item in result] == [GroupDTO]
    assert result[0].id == group_id
    assert result[0].name == "Current group"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("database_rows", "expected_subjects"),
    [([object()], ["Updated Physics"]), ([], [])],
    ids=["updated-in-another-worker", "deleted-in-another-worker"],
)
async def test_schedule_repository_returns_current_database_rows(
    database_rows, expected_subjects
):
    """Each read reflects the database, including changes made by another worker."""

    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
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

    with patch.object(repo, "_to_dto", return_value=current_item) as to_dto:
        rows = await repo.get_by_group(group_id)

    assert [row.subject for row in rows] == expected_subjects
    repo.db.execute.assert_awaited_once()
    if database_rows:
        to_dto.assert_called_once_with(database_rows[0])
    else:
        to_dto.assert_not_called()


@pytest.mark.asyncio
async def test_group_repository_returns_an_empty_database_result():
    database_result = MagicMock()
    database_result.scalars.return_value.all.return_value = []
    db = MagicMock(execute=AsyncMock(return_value=database_result))

    result = await GroupRepository(db).list_groups()

    assert result == []


@pytest.mark.asyncio
async def test_create_records_creator():
    repo = ScheduleRepository(MagicMock())
    payload = {
        "subject": "Independent study",
        "start_time": datetime(2026, 1, 1, 10, 0),
        "end_time": datetime(2026, 1, 1, 11, 0),
    }
    created = object()

    with patch.object(
        BaseRepository, "create", new=AsyncMock(return_value=created)
    ) as base_create:
        result = await repo.create(payload, creator_id="creator-1")

    assert result is created
    base_create.assert_awaited_once()
    created_payload = base_create.await_args.args[0]
    assert created_payload["creator_id"] == "creator-1"


def test_repository_model_and_dto_properties():
    group_repo = GroupRepository(MagicMock())
    schedule_repo = ScheduleRepository(MagicMock())

    assert group_repo.model is models.Group
    assert group_repo.dto_class.__name__ == "GroupDTO"
    assert schedule_repo.model is models.Schedule
    assert schedule_repo.dto_class.__name__ == "ScheduleDTO"


@pytest.mark.asyncio
async def test_group_repository_queries_and_maps():
    repo = GroupRepository(MagicMock())
    group = MagicMock()
    dto = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [group]
    repo.db.execute = AsyncMock(return_value=result)

    with patch.object(repo, "_to_dto", return_value=dto):
        result_dtos = await repo.list_groups()

    assert result_dtos == [dto]
    repo.db.execute.assert_awaited_once()


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
async def test_conflict_candidates_refresh_rows_and_have_no_display_limit():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    dto = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [MagicMock()]
    repo.db.execute = AsyncMock(return_value=result)

    with patch.object(repo, "_to_dto", return_value=dto):
        candidates = await repo.get_conflict_candidates(group_id, "Professor X")

    assert candidates == [dto]
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
async def test_create_without_creator_leaves_creator_unset():
    repo = ScheduleRepository(MagicMock())
    group_id = uuid4()
    payload = {
        "group_id": group_id,
        "subject": "Independent study",
        "start_time": datetime(2026, 1, 1, 10, 0),
        "end_time": datetime(2026, 1, 1, 11, 0),
    }

    with patch.object(
        BaseRepository, "create", new=AsyncMock(return_value="created")
    ) as base_create:
        result = await repo.create(payload)

    assert result == "created"
    created_payload = base_create.await_args.args[0]
    assert created_payload["group_id"] == group_id
    assert "creator_id" not in created_payload


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

    with patch.object(BaseRepository, "create", new=AsyncMock(return_value="created")):
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
