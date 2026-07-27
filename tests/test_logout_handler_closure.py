"""Branch closure test for logout when token session is already absent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.responses import Response

from app.auth.handlers.logout import logout


@pytest.mark.asyncio
async def test_logout_revokes_redis_when_database_session_is_missing():
    request = MagicMock()
    request.cookies = {"access_token_v2": "token"}
    request.headers = {}
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db.execute.return_value = result
    redis = MagicMock()
    redis.revoke_session = AsyncMock()

    with (
        patch(
            "app.auth.handlers.logout.decode_token", return_value={"jti": "missing-jti"}
        ),
        patch(
            "app.services.auth.redis_session.RedisSessionService", return_value=redis
        ),
    ):
        payload = await logout(Response(), request, db)

    assert payload["message"] == "Logged out successfully"
    redis.revoke_session.assert_awaited_once_with("missing-jti")
    db.commit.assert_not_awaited()
