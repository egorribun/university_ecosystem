import uuid
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from httpx import ASGITransport, AsyncClient

import app.models as models
from app.api.deps import get_current_user
from app.core.container import get_read_schedule_handler
from app.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.core.database import get_db
from app.cqrs.bus import CommandBus, QueryBus
from app.main import app


@pytest.fixture
def mock_user():
    user = MagicMock(spec=models.User)
    user.id = uuid.uuid4()
    user.role = "admin"
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Mock for sched = await db.get(models.Schedule, schedule_id)
    mock_sched = MagicMock(spec=models.Schedule)
    mock_sched.id = uuid.uuid4()
    mock_sched.group_id = uuid.uuid4()
    mock_sched.subject = "Test Subject"
    mock_sched.weekday = "1"
    mock_sched.start_time = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    mock_sched.end_time = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    mock_sched.teacher = "Test Teacher"
    mock_sched.room = "101"
    mock_sched.parity = "both"
    mock_sched.lesson_type = "lecture"
    db.get.return_value = mock_sched
    return db


@pytest.fixture
def mock_schedule_handler():
    handler = AsyncMock()
    result = MagicMock()
    result.payload = [
        {
            "id": str(uuid.uuid4()),
            "group_id": str(uuid.uuid4()),
            "subject": "Test Subject",
            "weekday": "1",
            "start_time": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            "end_time": datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
            "teacher": "Test Teacher",
            "room": "101",
            "parity": "both",
            "lesson_type": "lecture",
        }
    ]
    result.etag = "sched-etag"
    result.not_modified = False
    handler.handle.return_value = result
    return handler


@pytest.fixture
def mock_schedule_service():
    service = AsyncMock()

    # Mock create
    mock_created = MagicMock(spec=models.Schedule)
    mock_created.id = uuid.uuid4()
    mock_created.group_id = uuid.uuid4()
    mock_created.subject = "Test Subject"
    mock_created.weekday = "1"
    mock_created.start_time = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    mock_created.end_time = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    mock_created.teacher = "Test Teacher"
    mock_created.room = "101"
    mock_created.parity = "both"
    mock_created.lesson_type = "lecture"
    mock_created.lesson_type_display = "Lecture"
    service.create_schedule.return_value = mock_created

    # Mock update
    mock_updated = MagicMock(spec=models.Schedule)
    mock_updated.id = uuid.uuid4()
    mock_updated.group_id = uuid.uuid4()
    mock_updated.subject = "Test Subject"
    mock_updated.weekday = "1"
    mock_updated.start_time = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    mock_updated.end_time = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    mock_updated.teacher = "New Teacher"
    mock_updated.room = "101"
    mock_updated.parity = "both"
    mock_updated.lesson_type = "lecture"
    mock_updated.lesson_type_display = "Lecture"
    service.get_by_id.return_value = mock_updated
    service.update_schedule.return_value = mock_updated

    # Mock delete
    service.delete_schedule.return_value = True

    return service


@pytest.mark.asyncio
async def test_schedule_api_coverage(
    mock_user, mock_db, mock_schedule_handler, mock_schedule_service
):
    # We override get_schedule_service dependency
    from app.api.deps import get_schedule_service

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_schedule_service] = lambda: mock_schedule_service
    app.dependency_overrides[get_read_schedule_handler] = lambda: mock_schedule_handler
    # We also keep get_db override if needed by other deps,
    # but schedule endpoints now use service
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_query_bus = AsyncMock(spec=QueryBus)
    mock_query_bus.execute.side_effect = mock_schedule_handler.handle

    mock_command_bus = AsyncMock(spec=CommandBus)

    async def mock_command_bus_execute(command):
        if command.__class__.__name__ == "CreateScheduleCommand":
            return await mock_schedule_service.create_schedule(
                user=mock_user, data=command.data
            )
        elif command.__class__.__name__ == "UpdateScheduleCommand":
            return await mock_schedule_service.update_schedule(
                user=mock_user, schedule_id=command.schedule_id, data=command.data
            )
        elif command.__class__.__name__ == "DeleteScheduleCommand":
            return await mock_schedule_service.delete_schedule(
                user=mock_user, schedule_id=command.schedule_id
            )
        return None

    mock_command_bus.execute.side_effect = mock_command_bus_execute

    class TestProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def query_bus(self) -> QueryBus:
            return cast(QueryBus, mock_query_bus)

        @provide(scope=Scope.REQUEST)
        def command_bus(self) -> CommandBus:
            return cast(CommandBus, mock_command_bus)

    original_container = getattr(app.state, "dishka_container", None)
    app.state.dishka_container = make_async_container(TestProvider())

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            csrf_response = await ac.get("/api/v1/auth/csrf-cookie")
            assert csrf_response.status_code == 200
            csrf_token = ac.cookies.get(CSRF_COOKIE_NAME)
            assert csrf_token
            ac.headers[CSRF_HEADER_NAME] = csrf_token

            gid = str(uuid.uuid4())
            # Test get schedule (uses handler)
            res = await ac.get(f"/api/v1/schedule/{gid}")
            assert res.status_code == 200
            assert res.headers["ETag"] == "sched-etag"

            # Test get schedule 304 Not Modified
            mock_schedule_handler.handle.return_value.not_modified = True
            res = await ac.get(
                f"/api/v1/schedule/{gid}", headers={"If-None-Match": "sched-etag"}
            )
            assert res.status_code == 304

            sid = str(uuid.uuid4())
            # Test update schedule
            res = await ac.patch(
                f"/api/v1/schedule/{sid}",
                json={"teacher": "New Teacher", "group_id": str(gid)},
            )
            assert res.status_code == 200
            assert mock_schedule_service.update_schedule.called

            # Test delete schedule
            res = await ac.delete(f"/api/v1/schedule/{sid}")
            assert res.status_code == 200
            assert res.json() == {"ok": True}
    finally:
        # Cleaned up by conftest
        pass
        if hasattr(app.state, "dishka_container"):
            await app.state.dishka_container.close()
        app.state.dishka_container = original_container
