from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import models
from app.schemas import schemas
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_update_user_profile_decomposed_fields():
    # Setup
    db = AsyncMock(spec=AsyncSession)
    audit = MagicMock()
    notifications = MagicMock()
    service = UserService(db, audit, notifications)

    user = models.User(id=1, email="test@example.com")
    db.get.return_value = user

    update_data = schemas.UserProfileUpdate(
        about="New about", institute="New institute", timezone="Europe/Moscow"
    )
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_res
    request = MagicMock()

    # Execute
    updated_user = await service.update_user_profile(user, update_data, request)

    # Verify
    assert updated_user.profile_detail.about == "New about"
    assert updated_user.education_path.institute == "New institute"
    assert updated_user.preferences.timezone == "Europe/Moscow"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_profile_email_change():
    # Setup
    db = AsyncMock(spec=AsyncSession)
    audit = MagicMock()
    notifications = MagicMock()
    service = UserService(db, audit, notifications)

    user = models.User(id=1, email="old@example.com")
    db.get.return_value = user

    # Mock email uniqueness check
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_result

    update_data = schemas.UserProfileUpdate(email="new@example.com")
    request = MagicMock()

    # Execute
    updated_user = await service.update_user_profile(user, update_data, request)

    # Verify
    assert updated_user.email == "new@example.com"
    db.commit.assert_called_once()
