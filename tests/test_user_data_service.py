from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import models
from app.services.user.data_service import UserDataService


@pytest.mark.asyncio
async def test_export_user_data():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_repo = AsyncMock()
    mock_audit = AsyncMock()

    service = UserDataService(mock_db, mock_repo, mock_audit)

    # Mock user with relationships
    mock_user = MagicMock(spec=models.User)
    mock_user.id = 1
    mock_user.sessions = [MagicMock(id=101)]
    mock_user.notifications = [MagicMock(id=201)]
    mock_user.mfa_challenges = [MagicMock(id=301)]
    mock_user.totp_enrollments = [MagicMock(id=401)]

    mock_repo.get_full_user_data.return_value = mock_user

    mock_request = MagicMock()

    with (
        patch("app.services.user.data_service.attach_pending_email", AsyncMock()),
        patch(
            "app.services.user.data_service.schemas.UserOut.from_orm"
        ) as mock_from_orm,
        patch(
            "app.services.user.data_service.export_access_logs",
            AsyncMock(return_value=[]),
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
        mock_repo.get_full_user_data.assert_called_once_with(1)
        mock_audit.log.assert_called_once()
