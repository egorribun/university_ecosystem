from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.core.container import get_schedule_handler
from app.core.database import get_db
from app.main import app
from app.models import models


@pytest.fixture
def mock_user():
    user = MagicMock(spec=models.User)
    user.id = 1
    user.role = "admin"
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Mock for sched = await db.get(models.Schedule, schedule_id)
    mock_sched = MagicMock(spec=models.Schedule)
    mock_sched.id = 1
    mock_sched.group_id = 101
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
            "id": 1,
            "group_id": 101,
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


@pytest.mark.asyncio
async def test_schedule_api_coverage(mock_user, mock_db, mock_schedule_handler):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_schedule_handler] = lambda: mock_schedule_handler

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as ac:
            # Test get schedule
            res = await ac.get("/api/v1/schedule/101")
            assert res.status_code == 200
            assert res.headers["ETag"] == "sched-etag"

            # Test get schedule 304 Not Modified
            mock_schedule_handler.handle.return_value.not_modified = True
            res = await ac.get(
                "/api/v1/schedule/101", headers={"If-None-Match": "sched-etag"}
            )
            assert res.status_code == 304

            # Test update schedule
            res = await ac.patch("/api/v1/schedule/1", json={"teacher": "New Teacher"})
            assert res.status_code == 200

            # Test delete schedule
            res = await ac.delete("/api/v1/schedule/1")
            assert res.status_code == 200
            assert res.json() == {"ok": True}
    finally:
        app.dependency_overrides.clear()
