import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_check_participant_endpoint(async_client):
    user_id = str(uuid.uuid4())
    room_id = str(uuid.uuid4())

    # 1. Test participant true -> returns 200
    with patch(
        "app.api.internal.chat.ChatRepository.check_participant",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = True
        response = await async_client.get(
            "/chat/check-participant",
            params={"user_id": user_id, "room_id": room_id},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"participant": True}
        mock_check.assert_awaited_once_with(uuid.UUID(room_id), uuid.UUID(user_id))

    # 2. Test participant false -> returns 403
    with patch(
        "app.api.internal.chat.ChatRepository.check_participant",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = False
        response = await async_client.get(
            "/chat/check-participant",
            params={"user_id": user_id, "room_id": room_id},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"]["error"] == "not_participant"
