"""Branch closure test for logout when token session is already absent."""

from datetime import UTC, datetime
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


@pytest.mark.asyncio
async def test_logout_revokes_database_session_from_bearer_token_and_audits():
    request = MagicMock()
    request.cookies = {}
    request.headers = {"Authorization": "Bearer bearer-token"}
    db = AsyncMock()
    result = MagicMock()
    session = MagicMock(user_id="user-1", revoked_at=None, signing_key="old-key")
    result.scalars.return_value.first.return_value = session
    db.execute.return_value = result
    redis = MagicMock()
    redis.revoke_session = AsyncMock()
    audit = MagicMock()

    with (
        patch(
            "app.auth.handlers.logout.decode_token", return_value={"jti": "bearer-jti"}
        ),
        patch(
            "app.services.auth.redis_session.RedisSessionService", return_value=redis
        ),
        patch("app.core.container.get_audit_service", return_value=audit),
        patch("app.auth.handlers.logout.secrets.token_urlsafe", return_value="new-key"),
    ):
        response = Response()
        payload = await logout(response, request, db)

    assert payload["message"] == "Logged out successfully"
    assert session.revoked_at is not None
    assert session.signing_key == "new-key"
    db.commit.assert_awaited_once()
    redis.revoke_session.assert_awaited_once_with("bearer-jti")
    audit.log.assert_called_once_with(
        "auth.logout.revoked",
        request,
        user_id="user-1",
        reason="user_initiated",
    )
    assert response.headers["Clear-Site-Data"] == '"cache", "cookies", "storage"'


@pytest.mark.asyncio
async def test_logout_keeps_existing_revocation_and_ignores_non_bearer_or_empty_tokens():
    request = MagicMock()
    request.cookies = {"access_token_v2": "cookie-token"}
    request.headers = {"Authorization": "Basic not-a-bearer"}
    db = AsyncMock()
    result = MagicMock()
    revoked_at = datetime(2026, 1, 1, tzinfo=UTC)
    session = MagicMock(user_id="user-2", revoked_at=revoked_at, signing_key="old-key")
    result.scalars.return_value.first.return_value = session
    db.execute.return_value = result
    redis = MagicMock()
    redis.revoke_session = AsyncMock()
    audit = MagicMock()

    with (
        patch(
            "app.auth.handlers.logout.decode_token", return_value={"jti": "cookie-jti"}
        ),
        patch(
            "app.services.auth.redis_session.RedisSessionService", return_value=redis
        ),
        patch("app.core.container.get_audit_service", return_value=audit),
        patch("app.auth.handlers.logout.secrets.token_urlsafe", return_value="rotated"),
    ):
        payload = await logout(Response(), request, db)

    assert payload["message"] == "Logged out successfully"
    assert session.revoked_at == revoked_at
    assert session.signing_key == "rotated"
    db.commit.assert_awaited_once()
    audit.log.assert_called_once()

    empty_request = MagicMock()
    empty_request.cookies = {}
    empty_request.headers = {}
    with patch("app.auth.handlers.logout.decode_token") as decode:
        empty_payload = await logout(Response(), empty_request, AsyncMock())

    assert empty_payload["message"] == "Logged out successfully"
    decode.assert_not_called()
