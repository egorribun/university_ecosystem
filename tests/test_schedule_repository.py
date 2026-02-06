import uuid
from datetime import UTC, datetime

import pytest

from app.models import models
from app.repositories.schedule_repository import GroupRepository, ScheduleRepository


@pytest.mark.asyncio
async def test_group_repository_list_groups(db_session):
    repo = GroupRepository(db_session)

    # Create sample groups
    g_id1 = uuid.uuid4()
    g_id2 = uuid.uuid4()
    group1 = models.Group(id=g_id1, name="Group Alpha")
    group2 = models.Group(id=g_id2, name="Group Beta")
    db_session.add(group1)
    db_session.add(group2)
    await db_session.flush()

    # Test list_groups
    groups = await repo.list_groups()
    assert len(groups) >= 2
    assert any(g.name == "Group Alpha" for g in groups)
    assert any(g.name == "Group Beta" for g in groups)


@pytest.mark.asyncio
async def test_schedule_repository_get_by_group(db_session):
    group_id = uuid.uuid4()
    repo = ScheduleRepository(db_session)

    # Create sample group and schedule
    group = models.Group(id=group_id, name="Test Group Repo")
    db_session.add(group)

    item = models.Schedule(
        id=uuid.uuid4(),
        group_id=group_id,
        subject="Mathematics",
        weekday="1",
        start_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 11, 30, tzinfo=UTC),
        parity="both",
        lesson_type="lecture",
    )
    db_session.add(item)
    await db_session.flush()

    # Test get_by_group
    schedule = await repo.get_by_group(group_id)
    assert len(schedule) == 1
    assert schedule[0].subject == "Mathematics"


@pytest.mark.asyncio
async def test_schedule_repository_get_by_teacher(db_session):
    repo = ScheduleRepository(db_session)
    teacher_name = "Professor X"

    item = models.Schedule(
        id=uuid.uuid4(),
        group_id=uuid.uuid4(),
        subject="Telepathy 101",
        weekday="2",
        start_time=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, 15, 30, tzinfo=UTC),
        parity="even",
        teacher=teacher_name,
        lesson_type="seminar",
    )
    db_session.add(item)
    await db_session.flush()

    # Test get_by_teacher
    items = await repo.get_by_teacher(teacher_name)
    assert len(items) == 1
    assert items[0].subject == "Telepathy 101"


@pytest.mark.asyncio
async def test_schedule_repository_create_ensures_utc(db_session):
    repo = ScheduleRepository(db_session)
    group_id = uuid.uuid4()

    # Create with naive datetimes
    data = {
        "group_id": group_id,
        "subject": "Chemistry",
        "weekday": "3",
        "start_time": datetime(2026, 1, 1, 10, 0),  # noqa: DTZ001
        "end_time": datetime(2026, 1, 1, 11, 30),  # noqa: DTZ001
        "parity": "odd",
        "lesson_type": "lab",
        "teacher": "Lab Prof",
        "room": "L1",
    }

    # This should trigger _ensure_utc in create override
    # We pass a dict to avoid Pydantic validation until inside create
    item = await repo.create(data)

    # SQLite might not preserve tzinfo after refresh
    if "sqlite" not in str(db_session.bind.url):
        assert item.start_time.tzinfo is not None
        assert item.start_time.utcoffset().total_seconds() == 0
    assert item.subject == "Chemistry"
