"""Unit tests specifically covering WebSocket ticket authentication and validation edge cases.

Focuses on validating the format checks, Redis GETDEL extraction, colon-joined payload
splitting, and DB exception gates in app/api/ws/auth.py.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.ws.auth import (
    _JWT_DECODE_ERRORS,
    extract_bearer_token,
    extract_token_from_subprotocol,
    get_user_from_cookie,
    get_user_from_ticket,
    get_user_from_token,
    select_subprotocol,
    update_last_seen,
)


@pytest.mark.asyncio
async def test_jwt_import_error_coverage() -> None:
    # Mutate the decode errors tuple directly to simulate ImportError fallback
    with patch("app.api.ws.auth._JWT_DECODE_ERRORS", (ValueError,)):
        with patch(
            "app.auth.security.decode_token",
            side_effect=ValueError("Simulated ValueError"),
        ):
            assert await get_user_from_token("token") == (None, None)


@pytest.mark.asyncio
async def test_get_user_from_ticket_invalid_format() -> None:
    # 1. Length is not 64
    user, jti = await get_user_from_ticket("too-short")
    assert user is None
    assert jti is None

    # 2. Length is 64 but contains non-hex characters
    invalid_hex = "g" * 64
    user, jti = await get_user_from_ticket(invalid_hex)
    assert user is None
    assert jti is None

    # 3. Contains uppercase hex characters
    uppercase_hex = "0123456789ABCDEF" + "0" * 48
    user, jti = await get_user_from_ticket(uppercase_hex)
    assert user is None
    assert jti is None


@pytest.mark.asyncio
async def test_get_user_from_ticket_redis_missing() -> None:
    ticket = secrets.token_hex(32)
    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = None

    with patch("app.deps.cache.get_cache_client", return_value=mock_redis):
        user, jti = await get_user_from_ticket(ticket)
        assert user is None
        assert jti is None
        mock_redis.getdel.assert_called_once_with(f"ott:ws:{ticket}")


@pytest.mark.asyncio
async def test_get_user_from_ticket_malformed_payload() -> None:
    ticket = secrets.token_hex(32)
    mock_redis = AsyncMock()

    # Case 1: No colon at all in the Redis payload
    mock_redis.getdel.return_value = "no-colon-payload"
    with patch("app.deps.cache.get_cache_client", return_value=mock_redis):
        user, jti = await get_user_from_ticket(ticket)
        assert user is None
        assert jti is None

    # Case 2: Colon at index 0 (empty user_id)
    mock_redis.getdel.return_value = ":some-jti-here"
    with patch("app.deps.cache.get_cache_client", return_value=mock_redis):
        user, jti = await get_user_from_ticket(ticket)
        assert user is None
        assert jti is None

    # Case 3: Colon at the very end (empty JTI)
    mock_redis.getdel.return_value = "some-user-id:"
    with patch("app.deps.cache.get_cache_client", return_value=mock_redis):
        user, jti = await get_user_from_ticket(ticket)
        assert user is None
        assert jti is None


@pytest.mark.asyncio
async def test_get_user_from_ticket_infrastructure_failure() -> None:
    ticket = secrets.token_hex(32)
    mock_redis = AsyncMock()
    mock_redis.getdel.side_effect = ConnectionError("Redis down")

    with patch("app.deps.cache.get_cache_client", return_value=mock_redis):
        user, jti = await get_user_from_ticket(ticket)
        assert user is None
        assert jti is None


@pytest.mark.asyncio
async def test_get_user_from_ticket_invalid_uuid() -> None:
    ticket = secrets.token_hex(32)
    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = "not-a-uuid:valid-jti-string"

    with patch("app.deps.cache.get_cache_client", return_value=mock_redis):
        user, jti = await get_user_from_ticket(ticket)
        assert user is None
        assert jti is None


@pytest.mark.asyncio
async def test_get_user_from_ticket_valid_lookup_flow() -> None:
    ticket = secrets.token_hex(32)
    user_id = str(uuid.uuid4())
    jti = "mocked-jti-session"
    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = f"{user_id}:{jti}"

    mock_db_user = MagicMock()
    mock_db_user.is_active = True
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)

    mock_session = MagicMock()
    mock_session.user_id = mock_db_user.id
    mock_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    mock_session.revoked_at = None
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_jti = AsyncMock(return_value=mock_session)

    mock_redis.exists = AsyncMock(return_value=False)

    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx

        user, returned_jti = await get_user_from_ticket(ticket)
        assert user == mock_db_user
        assert returned_jti == jti


@pytest.mark.asyncio
async def test_get_user_from_ticket_jti_revoked_redis() -> None:
    ticket = secrets.token_hex(32)
    user_id = str(uuid.uuid4())
    jti = "revoked-jti"
    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = f"{user_id}:{jti}"

    mock_db_user = MagicMock()
    mock_db_user.is_active = True
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)

    mock_redis.exists = AsyncMock(return_value=True)

    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx

        user, returned_jti = await get_user_from_ticket(ticket)
        assert user is None
        assert returned_jti is None


@pytest.mark.asyncio
async def test_get_user_from_ticket_redis_exceptions() -> None:
    # Coverage for lines 235-236 (Redis exists throws exception, fallback to DB)
    ticket = secrets.token_hex(32)
    user_id = str(uuid.uuid4())
    jti = "mocked-jti-session"
    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = f"{user_id}:{jti}"

    mock_db_user = MagicMock()
    mock_db_user.is_active = True
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)

    mock_session = MagicMock()
    mock_session.user_id = mock_db_user.id
    mock_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    mock_session.revoked_at = None
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_jti = AsyncMock(return_value=mock_session)

    # Redis raises error during exists check
    mock_redis.exists = AsyncMock(side_effect=OSError("Redis error"))

    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx

        user, returned_jti = await get_user_from_ticket(ticket)
        assert user == mock_db_user
        assert returned_jti == jti


@pytest.mark.asyncio
async def test_get_user_from_ticket_resolve_user_edge_cases() -> None:
    ticket = secrets.token_hex(32)
    user_id = str(uuid.uuid4())
    jti = "some-jti"

    mock_redis = AsyncMock()
    mock_redis.getdel.return_value = f"{user_id}:{jti}"
    mock_redis.exists = AsyncMock(return_value=False)

    # 1. User not found
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=None)
    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_ticket(ticket) == (None, None)

    # 2. User is inactive (Line 225)
    inactive_user = MagicMock()
    inactive_user.is_active = False
    mock_user_repo.get = AsyncMock(return_value=inactive_user)
    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_ticket(ticket) == (None, None)

    # 3. ActiveSession not found or belongs to another user (Line 240)
    active_user = MagicMock()
    active_user.id = uuid.UUID(user_id)
    active_user.is_active = True
    mock_user_repo.get = AsyncMock(return_value=active_user)

    mock_session_repo = MagicMock()
    mock_session_repo.get_by_jti = AsyncMock(return_value=None)
    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_ticket(ticket) == (None, None)

    # 4. Naive datetime support for expires_at (Line 244)
    naive_session = MagicMock()
    naive_session.user_id = active_user.id
    naive_session.expires_at = datetime.now() + timedelta(hours=1)  # Naive
    naive_session.revoked_at = None
    mock_session_repo.get_by_jti = AsyncMock(return_value=naive_session)
    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        res_user, res_jti = await get_user_from_ticket(ticket)
        assert res_user == active_user
        assert res_jti == jti

    # 5. ActiveSession expired (Line 246)
    expired_session = MagicMock()
    expired_session.user_id = active_user.id
    expired_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
    expired_session.revoked_at = None
    mock_session_repo.get_by_jti = AsyncMock(return_value=expired_session)
    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_ticket(ticket) == (None, None)

    # 6. ActiveSession revoked (Line 248)
    revoked_session = MagicMock()
    revoked_session.user_id = active_user.id
    revoked_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    revoked_session.revoked_at = datetime.now(UTC)
    mock_session_repo.get_by_jti = AsyncMock(return_value=revoked_session)
    with (
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_ticket(ticket) == (None, None)


@pytest.mark.asyncio
async def test_get_user_from_token_success() -> None:
    token = "some-jwt-token"
    user_id = str(uuid.uuid4())
    jti = "session-jti"

    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=False)

    mock_db_user = MagicMock()
    mock_db_user.is_active = True
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)

    mock_session = MagicMock()
    mock_session.user_id = mock_db_user.id
    mock_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    mock_session.revoked_at = None
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_jti = AsyncMock(return_value=mock_session)

    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx

        user, returned_jti = await get_user_from_token(token)
        assert user == mock_db_user
        assert returned_jti == jti


@pytest.mark.asyncio
async def test_get_user_from_token_redis_revoked() -> None:
    # Coverage for lines 55-58 (Redis revoked fast-path)
    token = "some-jwt-token"
    user_id = str(uuid.uuid4())
    jti = "session-jti"

    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=True)

    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
    ):
        assert await get_user_from_token(token) == (None, None)


@pytest.mark.asyncio
async def test_get_user_from_token_redis_error() -> None:
    # Coverage for lines 59-64 (Redis connection error fall-through)
    token = "some-jwt-token"
    user_id = str(uuid.uuid4())
    jti = "session-jti"

    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))

    mock_db_user = MagicMock()
    mock_db_user.is_active = True
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)

    mock_session = MagicMock()
    mock_session.user_id = mock_db_user.id
    mock_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    mock_session.revoked_at = None
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_jti = AsyncMock(return_value=mock_session)

    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx

        user, returned_jti = await get_user_from_token(token)
        assert user == mock_db_user
        assert returned_jti == jti


@pytest.mark.asyncio
async def test_get_user_from_token_edge_cases() -> None:
    # 1. decode_token returns None
    with patch("app.auth.security.decode_token", return_value=None):
        assert await get_user_from_token("token") == (None, None)

    # 2. decode_token missing user_id (sub)
    with patch("app.auth.security.decode_token", return_value={"jti": "some-jti"}):
        assert await get_user_from_token("token") == (None, None)

    # 3. decode_token raises DecodeError
    with patch("app.auth.security.decode_token", side_effect=_JWT_DECODE_ERRORS[0]):
        assert await get_user_from_token("token") == (None, None)

    # 4. decode_token raises unexpected Exception
    with patch(
        "app.auth.security.decode_token", side_effect=RuntimeError("Unexpected")
    ):
        assert await get_user_from_token("token") == (None, None)


@pytest.mark.asyncio
async def test_get_user_from_token_db_failures() -> None:
    token = "some-jwt-token"
    user_id = str(uuid.uuid4())
    jti = "session-jti"

    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=False)

    # Case A: User not found in DB
    mock_user_repo = MagicMock()
    mock_user_repo.get = AsyncMock(return_value=None)
    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_token(token) == (None, None)

    # Case B: User is not active
    mock_db_user = MagicMock()
    mock_db_user.is_active = False
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)
    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_token(token) == (None, None)

    # Case C: session_jti is missing
    mock_db_user.is_active = True
    mock_user_repo.get = AsyncMock(return_value=mock_db_user)
    with (
        patch("app.auth.security.decode_token", return_value={"sub": user_id}),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_token(token) == (None, None)

    # Case D: ActiveSession not found or revoked
    mock_session_repo = MagicMock()
    mock_session_repo.get_by_jti = AsyncMock(return_value=None)
    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_token(token) == (None, None)

    # Case E: ActiveSession expired
    mock_session = MagicMock()
    mock_session.user_id = mock_db_user.id
    mock_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
    mock_session.revoked_at = None
    mock_session_repo.get_by_jti = AsyncMock(return_value=mock_session)
    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_token(token) == (None, None)

    # Case F: Naive datetime support (Line 86)
    naive_session = MagicMock()
    naive_session.user_id = mock_db_user.id
    naive_session.expires_at = datetime.now() + timedelta(hours=1)  # Naive
    naive_session.revoked_at = None
    mock_session_repo.get_by_jti = AsyncMock(return_value=naive_session)
    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        res_user, res_jti = await get_user_from_token(token)
        assert res_user == mock_db_user
        assert res_jti == jti

    # Case G: ActiveSession revoked (Line 90)
    revoked_session = MagicMock()
    revoked_session.user_id = mock_db_user.id
    revoked_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    revoked_session.revoked_at = datetime.now(UTC)
    mock_session_repo.get_by_jti = AsyncMock(return_value=revoked_session)
    with (
        patch(
            "app.auth.security.decode_token", return_value={"sub": user_id, "jti": jti}
        ),
        patch("app.deps.cache.get_cache_client", return_value=mock_redis),
        patch("app.api.ws.auth.UserRepository", return_value=mock_user_repo),
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx
        assert await get_user_from_token(token) == (None, None)


@pytest.mark.asyncio
async def test_get_user_from_cookie() -> None:
    with patch(
        "app.api.ws.auth.get_user_from_token", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = ("user", "jti")
        assert await get_user_from_cookie("cookie") == ("user", "jti")
        mock_get.assert_called_once_with("cookie")


def test_extract_bearer_token() -> None:
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("") is None
    assert extract_bearer_token("Bearer token-value") == "token-value"
    assert extract_bearer_token("bearer token-value") == "token-value"
    assert extract_bearer_token("token-value") == "token-value"
    assert extract_bearer_token("Bearer  ") == "Bearer"
    assert extract_bearer_token("Bearer token extra") is None


def test_extract_token_from_subprotocol() -> None:
    assert extract_token_from_subprotocol(None) is None
    assert extract_token_from_subprotocol("") is None
    assert extract_token_from_subprotocol("access_token, jwt-token") == "jwt-token"
    assert extract_token_from_subprotocol("bearer, jwt-token") == "jwt-token"
    assert extract_token_from_subprotocol("authorization, jwt-token") == "jwt-token"
    assert extract_token_from_subprotocol("access_token") is None
    assert extract_token_from_subprotocol("other, protocol") is None


def test_select_subprotocol() -> None:
    assert select_subprotocol(None) is None
    assert select_subprotocol("") is None
    assert select_subprotocol("access_token, extra") == "access_token"
    assert select_subprotocol("bearer") == "bearer"
    assert select_subprotocol("other") is None


@pytest.mark.asyncio
async def test_update_last_seen() -> None:
    # Case 1: session_jti is None (Line 120 / update_last_seen logic)
    res = await update_last_seen(None)
    assert isinstance(res, datetime)

    # Case 2: session_jti is provided
    mock_session_repo = MagicMock()
    mock_session_repo.touch_by_jti = AsyncMock()

    with (
        patch("app.api.ws.auth.SessionRepository", return_value=mock_session_repo),
        patch("app.api.ws.auth.async_session") as mock_async_session,
    ):
        mock_session = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock()
        mock_async_session.return_value = mock_ctx

        res2 = await update_last_seen("some-jti")
        assert isinstance(res2, datetime)
        mock_session_repo.touch_by_jti.assert_called_once_with("some-jti")
        mock_session.commit.assert_called_once()
