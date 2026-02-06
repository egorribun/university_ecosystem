import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_update_event_rebac_allowed(async_client, user_factory, db_session):
    """Verify that update_event allows access when PermissionChecker returns True."""
    user = await user_factory()
    event_id = uuid.uuid4()

    # Use dependency_overrides for reliability
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        # Mock PermissionChecker.check_permission to return True
        with patch(
            "app.api.events.PermissionChecker.check_permission", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = True

            # Mock the DB fetch to return an event
            with patch("app.api.events.AsyncSession.get") as mock_get:
                mock_get.return_value = AsyncMock(id=event_id, created_by=uuid.uuid4())

                response = await async_client.patch(
                    f"/events/{event_id}", json={"title": "Updated Title"}
                )

                assert response.status_code in [200, 404]
                mock_check.assert_called_once()
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_update_event_rebac_denied(async_client, user_factory):
    """Verify that update_event denies access when PermissionChecker returns False."""
    user = await user_factory()
    event_id = uuid.uuid4()

    # Use dependency_overrides for reliability
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        # Mock PermissionChecker.check_permission to return False
        with patch(
            "app.api.events.PermissionChecker.check_permission", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = False

            # Mock the DB fetch to return an event
            with patch("app.api.events.AsyncSession.get") as mock_get:
                mock_get.return_value = AsyncMock(id=event_id, created_by=uuid.uuid4())

                response = await async_client.patch(
                    f"/events/{event_id}", json={"title": "Updated Title"}
                )

                assert response.status_code == status.HTTP_403_FORBIDDEN
                mock_check.assert_called_once()
                # Verify RFC 7807 on 403
                assert response.headers["Content-Type"] == "application/problem+json"
    finally:
        app.dependency_overrides = {}
