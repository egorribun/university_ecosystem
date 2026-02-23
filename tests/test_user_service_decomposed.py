from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import models
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.user_service import UserService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_repo():
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def mock_audit():
    return MagicMock()


@pytest.fixture
def mock_notifications():
    return MagicMock()


@pytest.mark.asyncio
async def test_update_user_profile_decomposed_fields():
    # Setup
    repo = AsyncMock()
    audit = MagicMock()
    notifications = MagicMock()
    service = UserService(repo, audit, notifications)

    user = models.User(id=1, email="test@example.com")
    repo.get.return_value = user

    update_data = schemas.UserProfileUpdate(
        about="New about",
        institute="New institute",
        timezone="Europe/Moscow",
    )
    request = MagicMock()

    # Mock repo methods
    updated_user_mock = MagicMock()
    updated_user_mock.profile.about = "New about"
    updated_user_mock.education_path.institute = "New institute"
    updated_user_mock.preferences.timezone = "Europe/Moscow"
    updated_user_mock.id = 1
    repo._get_orm = AsyncMock(return_value=user)
    repo._to_dto = MagicMock(return_value=updated_user_mock)
    repo.add = MagicMock()
    repo.flush = AsyncMock()
    repo.commit = AsyncMock()

    # Execute
    with patch(
        "app.services.user.profile_service.attach_pending_email",
        side_effect=lambda _db, u: u,
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
    service = UserService(repo, audit, notifications)

    user = models.User(id=1, email="old@example.com")
    repo.get.return_value = user

    # Mock email uniqueness check
    repo.check_email_exists.return_value = False

    update_data = schemas.UserProfileUpdate(email="new@example.com")
    request = MagicMock()

    # Mock repo methods
    updated_user_mock = MagicMock()
    updated_user_mock.email = "new@example.com"
    updated_user_mock.id = 1
    repo._get_orm = AsyncMock(return_value=user)
    repo._to_dto = MagicMock(return_value=updated_user_mock)
    repo.add = MagicMock()
    repo.flush = AsyncMock()
    repo.commit = AsyncMock()

    # Execute
    with patch(
        "app.services.user.profile_service.attach_pending_email",
        side_effect=lambda _db, u: u,
    ):
        updated_user = await service.update_user_profile(user, update_data, request)

    # Verify
    assert updated_user.email == "new@example.com"
    repo.commit.assert_called_once()
