from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import models
from app.schemas import schemas
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_update_user_profile_decomposed_fields():
    # Setup
    db = AsyncMock()
    repo = AsyncMock()
    audit = MagicMock()
    notifications = MagicMock()
    MagicMock()
    service = UserService(repo, audit, notifications)

    user = models.User(id=1, email="test@example.com")
    repo.get.return_value = user

    update_data = schemas.UserProfileUpdate(
        about="New about", institute="New institute", timezone="Europe/Moscow"
    )
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_res
    request = MagicMock()

    # Mock return value for repo.update
    updated_user_mock = MagicMock()
    updated_user_mock.profile.about = "New about"
    updated_user_mock.education_path.institute = "New institute"
    updated_user_mock.preferences.timezone = "Europe/Moscow"
    repo.update.return_value = updated_user_mock

    # Execute
    with patch(
        "app.services.user.profile_service.attach_pending_email", new_callable=AsyncMock
    ):
        updated_user = await service.update_user_profile(user, update_data, request)

    # Verify
    assert updated_user.profile.about == "New about"
    assert updated_user.education_path.institute == "New institute"
    assert updated_user.preferences.timezone == "Europe/Moscow"
    repo.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_profile_email_change():
    # Setup
    db = AsyncMock()
    repo = AsyncMock()
    audit = MagicMock()
    notifications = MagicMock()
    MagicMock()
    service = UserService(repo, audit, notifications)

    user = models.User(id=1, email="old@example.com")
    repo.get.return_value = user

    # Mock email uniqueness check
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_result
    repo.check_email_exists.return_value = False

    update_data = schemas.UserProfileUpdate(email="new@example.com")
    request = MagicMock()

    # Mock return value for repo.update
    updated_user_mock = MagicMock()
    updated_user_mock.email = "new@example.com"
    repo.update.return_value = updated_user_mock

    # Execute
    with patch(
        "app.services.user.profile_service.attach_pending_email", new_callable=AsyncMock
    ):
        updated_user = await service.update_user_profile(user, update_data, request)

    # Verify
    assert updated_user.email == "new@example.com"
    repo.commit.assert_called_once()
