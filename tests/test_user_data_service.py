from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import models
from app.services.user.data_service import UserDataService


@pytest.mark.asyncio
async def test_export_user_data():
    mock_repo = AsyncMock()
    mock_audit = AsyncMock()

    service = UserDataService(mock_repo, mock_audit)

    # Mock user (lightweight)
    mock_user = MagicMock(spec=models.User)
    mock_user.id = 1

    # Mock granular data returns
    mock_repo.get.return_value = mock_user
    mock_repo.get_user_sessions.return_value = [MagicMock(id=101)]
    mock_repo.get_user_notifications.return_value = [MagicMock(id=201)]
    mock_repo.get_user_mfa_challenges.return_value = [MagicMock(id=301)]
    mock_repo.get_user_totp_enrollments.return_value = [MagicMock(id=401)]

    mock_request = MagicMock()

    with (
        patch("app.services.user.data_service.attach_pending_email", AsyncMock()),
        patch(
            "app.services.user.data_service.schemas.UserOut.from_orm"
        ) as mock_from_orm,
        patch(
            "app.services.user.data_service.export_access_logs",
            AsyncMock(return_value=[]),
            # Mock log attributes to prevent AttributeError on getattr
        ),
        patch("app.services.user.data_service.log_data_access", AsyncMock()),
    ):
        mock_from_orm.return_value.model_dump.return_value = {
            "id": 1,
            "email": "test@example.com",
        }

        result = await service.export_user_data(mock_user, mock_request)

        assert result.profile["id"] == 1
        assert len(result.sessions) == 1
        assert len(result.notifications) == 1

        # Verify granular calls
        mock_repo.get.assert_called_once_with(1)
        mock_repo.get_user_sessions.assert_called_once_with(1, limit=1000)
        mock_repo.get_user_notifications.assert_called_once_with(1, limit=1000)
        mock_audit.log.assert_called_once()
