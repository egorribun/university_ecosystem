from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import models
from app.schemas import schemas
from app.services.notification_templates import (
    ScenarioContext,
    render_notification_template,
)


def test_notification_templates_scenarios():
    # 1. News
    data = {"headline": "Test News", "summary": "Sum", "id": 1}
    res = render_notification_template("news.new", data, locale="en")
    assert "Test News" in res["title"]

    # 2. Events
    data = {"title": "Test Event", "id": 1, "location": "Loc"}
    res = render_notification_template("events.new", data, locale="ru")
    assert "Test Event" in res["title"]

    # 3. Schedule change
    data = {
        "subject": "Math",
        "summary": "Changed",
        "date": "2023-10-10",
        "time": "10:00",
    }
    res = render_notification_template("schedule.change", data, locale="ru")
    assert "Math" in res["title"]
    assert "Changed" in res["body"]

    # 4. Schedule reminder
    data = {"subject": "Phys", "starts_at": "2023-10-10T10:00:00Z"}
    res = render_notification_template("schedule.reminder", data, locale="en")
    assert "Phys" in res["title"]


def test_scenario_context_logic():
    ctx = ScenarioContext({"a": 1, "data": {"b": 2}})
    assert ctx.get("a") == 1
    assert ctx.get("b") == 2
    assert ctx.get_text("a") == "1"


@pytest.mark.asyncio
async def test_user_service_basics():
    from app.services.user_service import UserService

    audit = MagicMock()
    notifications = AsyncMock()
    db = AsyncMock()
    repo = AsyncMock()
    service = UserService(db, repo, audit, notifications)
    user = models.User(id=1, email="u@e.com")
    user.avatar_url = None
    user.cover_url = None
    request = MagicMock()

    # Mock repo.get to return user
    repo.get.return_value = user
    # Mock db.execute to return a mock result
    # We use MagicMock for the result because scalars() is a
    # synchronous call in SQLAlchemy
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    # update_user_profile
    data = schemas.UserProfileUpdate(full_name="New Name")
    with patch("app.services.user_service.resolve_locale", return_value="en"):
        await service.update_user_profile(user, data, request)
        assert user.full_name == "New Name"

    # delete_avatar
    user.avatar_url = "/path/to/img"
    with (
        patch(
            "app.services.user_service.delete_static_file", new_callable=AsyncMock
        ) as m_del,
        patch(
            "app.services.user_service.ensure_mfa_relationships_loaded",
            new_callable=AsyncMock,
        ),
    ):
        await service.delete_avatar(user)
        assert user.avatar_url is None
        m_del.assert_called_once()


@pytest.mark.asyncio
async def test_auth_service_basics():
    from app.services.auth_service import AuthService

    audit = MagicMock()
    db = AsyncMock()
    service = AuthService(db, audit)
    user = models.User(id=1, email="u@e.com", hashed_password="old_hash")
    request = MagicMock()

    # Mock for revoke_sessions_matching
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    # Change password
    data = schemas.UserPasswordChangeIn(
        current_password="old", new_password="newpassword123"
    )
    with (
        patch("app.services.auth_service.verify_password") as m_verify,
        patch("app.services.auth_service.get_password_hash", return_value="new_hash"),
        patch("app.services.auth_service.resolve_locale", return_value="en"),
    ):
        m_verify.side_effect = [True, False]
        await service.change_password(user, data, request)
        assert user.hashed_password == "new_hash"
        db.commit.assert_called()


@pytest.mark.asyncio
async def test_partition_management_logic():
    from app.services.partition_manager import ensure_partitions_exist

    with patch("app.services.partition_manager.engine") as m_engine:
        conn = AsyncMock()
        conn.dialect.name = "postgresql"
        # Mocking the async context manager engine.connect()
        m_engine.connect.return_value.__aenter__.return_value = conn

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        conn.execute.return_value = mock_result

        await ensure_partitions_exist()
        assert conn.execute.called
