"""The legacy current-user adapter forwards every credential it receives."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps.auth import get_current_user


@pytest.mark.asyncio
async def test_get_current_user_forwards_request_token_session_and_redis() -> None:
    request, db, redis_service, user = MagicMock(), MagicMock(), MagicMock(), object()
    resolve = AsyncMock(return_value=user)
    with patch("app.api.deps.auth._resolve_current_user", resolve):
        assert (
            await get_current_user(request, "bearer-token", db, redis_service) is user
        )

    resolve.assert_awaited_once_with(request, "bearer-token", db, redis_service)
