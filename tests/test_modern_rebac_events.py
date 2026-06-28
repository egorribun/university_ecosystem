import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from app.api.deps import get_current_user, get_db, get_event_service
from app.api.deps.auth import get_permission_checker
from app.main import app


@pytest.mark.asyncio
async def test_update_event_rebac_allowed(async_client, user_factory):
    """Verify that update_event allows access when PermissionChecker returns True."""
    user = await user_factory()
    event_id = uuid.uuid4()

    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_session.get.return_value = MagicMock(
        id=event_id, created_by=uuid.uuid4(), image_url=None
    )
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_result.scalar.return_value = 0
    mock_session.execute.return_value = mock_result

    mock_event_service = AsyncMock()
    mock_event_service.update_event.return_value = MagicMock(
        id=event_id, image_url=None
    )
    import datetime

    event_out_mock = {
        "id": event_id,
        "title": "Updated Title",
        "starts_at": datetime.datetime.now(datetime.UTC),
        "ends_at": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
        "created_by": str(uuid.uuid4()),
        "created_at": datetime.datetime.now(datetime.UTC),
        "is_active": True,
        "participant_count": 0,
        "files": [],
    }
    mock_event_service.serialize_event = MagicMock(return_value=event_out_mock)

    from app.auth.rbac import PermissionChecker

    mock_checker = AsyncMock(spec=PermissionChecker)
    mock_checker.check_permission.return_value = True

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_event_service] = lambda: mock_event_service
    app.dependency_overrides[get_permission_checker] = lambda: mock_checker

    try:
        with patch("app.api.events.delete_static_file", new_callable=AsyncMock):
            response = await async_client.patch(
                f"/events/{event_id}", json={"title": "Updated Title"}
            )

            assert response.status_code == 200
            mock_checker.check_permission.assert_called_once()
    finally:
        # Cleaned up by conftest
        pass


@pytest.mark.asyncio
async def test_update_event_rebac_denied(async_client, user_factory):
    """Verify that update_event denies access when PermissionChecker returns False."""
    user = await user_factory()
    event_id = uuid.uuid4()

    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_session.get.return_value = MagicMock(
        id=event_id, created_by=uuid.uuid4(), image_url=None
    )
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_result.scalar.return_value = 0
    mock_session.execute.return_value = mock_result

    from app.auth.rbac import PermissionChecker

    mock_checker = AsyncMock(spec=PermissionChecker)
    mock_checker.check_permission.return_value = False

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session
    app.dependency_overrides[get_permission_checker] = lambda: mock_checker

    try:
        response = await async_client.patch(
            f"/events/{event_id}", json={"title": "Updated Title"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_checker.check_permission.assert_called_once()
        assert response.headers["Content-Type"] == "application/problem+json"
    finally:
        # Cleaned up by conftest
        pass
