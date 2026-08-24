from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException


def _request() -> MagicMock:
    request = MagicMock()
    request.headers = {}
    request.state = SimpleNamespace()
    return request


def _session() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_agent=None,
        ip_address=None,
        accept_language=None,
        fingerprint_hash=None,
        mfa_verified_at=None,
        last_seen_at=None,
    )


def _auth_patches(user_id, jti, redis_session):
    user = SimpleNamespace(id=user_id, is_active=True)
    session = _session()
    client = AsyncMock()
    client.exists.return_value = False
    security = MagicMock()
    security.handle_mfa_ttl = AsyncMock()
    security.sync_last_seen = AsyncMock()
    fingerprint = MagicMock()
    fingerprint.validate_fingerprint = AsyncMock()
    return user, session, client, security, fingerprint


@pytest.mark.asyncio
async def test_get_current_user_cached_session_rejects_different_user():
    from app.api.deps.auth import get_current_user

    user_id = uuid4()
    redis_session = AsyncMock()
    redis_session.get_session.return_value = {"user_id": str(uuid4())}
    request = _request()
    with (
        patch("app.api.deps.auth.resolve_locale", return_value="en"),
        patch("app.api.deps.auth.AuthTokenService.extract_and_decode_token"),
        patch(
            "app.api.deps.auth.AuthTokenService.validate_payload",
            return_value=(user_id, "jti"),
        ),
        patch(
            "app.api.deps.auth.get_revocation_redis_client", new_callable=AsyncMock
        ) as get_cache,
    ):
        get_cache.return_value.exists.return_value = False
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, "token", AsyncMock(), redis_session)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_cached_invalid_session_id_falls_back_to_db():
    from app.api.deps.auth import get_current_user
    from app.models import User

    user_id = uuid4()
    jti = "cached-fallback"
    user, session, client, security, fingerprint = _auth_patches(
        user_id, jti, AsyncMock()
    )
    redis_session = AsyncMock()
    redis_session.get_session.return_value = {
        "user_id": str(user_id),
        "session_id": "not-a-uuid",
    }
    db = AsyncMock()

    async def db_get(model, *_args, **_kwargs):
        return user if model is User else None

    db.get.side_effect = db_get
    result = MagicMock()
    result.scalars.return_value.first.return_value = session
    db.execute.return_value = result
    request = _request()

    with (
        patch("app.api.deps.auth.resolve_locale", return_value="en"),
        patch(
            "app.api.deps.auth.get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": jti},
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.validate_payload",
            return_value=(user_id, jti),
        ),
        patch("app.api.deps.auth.AuthSecurityService", return_value=security),
        patch("app.api.deps.auth.AuthFingerprintService", return_value=fingerprint),
    ):
        assert await get_current_user(request, "token", db, redis_session) is user

    redis_session.update_last_seen.assert_awaited_once_with(jti)
    assert request.state.active_session is session


@pytest.mark.asyncio
async def test_get_current_user_cached_stale_db_session_is_rejected():
    from app.api.deps.auth import get_current_user
    from app.models import User

    user_id = uuid4()
    redis_session = AsyncMock()
    redis_session.get_session.return_value = {
        "user_id": str(user_id),
        "session_id": str(uuid4()),
    }
    user = SimpleNamespace(id=user_id, is_active=True)
    db = AsyncMock()
    db.get.side_effect = lambda model, *_args, **_kwargs: (
        user if model is User else None
    )
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db.execute.return_value = result
    client = AsyncMock()
    client.exists.return_value = False
    request = _request()

    with (
        patch("app.api.deps.auth.resolve_locale", return_value="en"),
        patch(
            "app.api.deps.auth.get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": "jti"},
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.validate_payload",
            return_value=(user_id, "jti"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, "token", db, redis_session)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_cached_inactive_user_is_rejected():
    from app.api.deps.auth import get_current_user

    user_id = uuid4()
    redis_session = AsyncMock()
    redis_session.get_session.return_value = {"user_id": str(user_id)}
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=user_id, is_active=False)
    client = AsyncMock()
    client.exists.return_value = False
    request = _request()

    with (
        patch("app.api.deps.auth.resolve_locale", return_value="en"),
        patch(
            "app.api.deps.auth.get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": "inactive-jti"},
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.validate_payload",
            return_value=(user_id, "inactive-jti"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, "token", db, redis_session)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", [None, "valid-session-id"])
async def test_get_current_user_cached_session_id_branches(session_id: str | None):
    from app.api.deps.auth import get_current_user
    from app.models import User

    user_id = uuid4()
    jti = "session-id-branch"
    user = SimpleNamespace(id=user_id, is_active=True)
    session = _session()
    redis_session = AsyncMock()
    cached = {"user_id": str(user_id)}
    if session_id is not None:
        cached["session_id"] = str(session.id)
    redis_session.get_session.return_value = cached
    db = AsyncMock()

    async def db_get(model, *_args, **_kwargs):
        return user if model is User else session

    db.get.side_effect = db_get
    result = MagicMock()
    result.scalars.return_value.first.return_value = session
    db.execute.return_value = result
    client = AsyncMock()
    client.exists.return_value = False
    security = MagicMock()
    security.handle_mfa_ttl = AsyncMock()
    security.sync_last_seen = AsyncMock()
    fingerprint = MagicMock()
    fingerprint.validate_fingerprint = AsyncMock()
    request = _request()

    with (
        patch("app.api.deps.auth.resolve_locale", return_value="en"),
        patch(
            "app.api.deps.auth.get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": jti},
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.validate_payload",
            return_value=(user_id, jti),
        ),
        patch("app.api.deps.auth.AuthSecurityService", return_value=security),
        patch("app.api.deps.auth.AuthFingerprintService", return_value=fingerprint),
    ):
        assert await get_current_user(request, "token", db, redis_session) is user

    assert request.state.active_session is session
    if session_id is None:
        db.execute.assert_awaited()
    else:
        assert db.execute.await_count == 0


@pytest.mark.asyncio
async def test_get_current_user_rejects_none_session_after_cache_lookup():
    from app.api.deps.auth import get_current_user

    user_id = uuid4()
    jti = "none-session"
    user = SimpleNamespace(id=user_id, is_active=True)
    redis_session = AsyncMock()
    redis_session.get_session.return_value = {"user_id": str(user_id)}
    db = AsyncMock()
    db.get.return_value = user
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db.execute.return_value = result
    client = AsyncMock()
    client.exists.return_value = False
    request = _request()

    with (
        patch("app.api.deps.auth.resolve_locale", return_value="en"),
        patch(
            "app.api.deps.auth.get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": jti},
        ),
        patch(
            "app.api.deps.auth.AuthTokenService.validate_payload",
            return_value=(user_id, jti),
        ),
        patch("app.api.deps.auth.raise_unauthorized") as unauthorized,
    ):
        with pytest.raises(AssertionError):
            await get_current_user(request, "token", db, redis_session)

    assert unauthorized.call_count >= 2


@pytest.mark.asyncio
async def test_get_current_user_dto_helpers_and_full_loader():
    from app.api.deps import auth as module

    user = MagicMock()
    db = AsyncMock()
    dto = MagicMock()
    auth_dto = MagicMock()
    with (
        patch.object(module.UserDTO, "model_validate", return_value=dto) as make_dto,
        patch.object(
            module.UserAuthDTO, "model_validate", return_value=auth_dto
        ) as make_auth_dto,
        patch.object(
            module, "ensure_mfa_relationships_loaded", new=AsyncMock()
        ) as ensure_loaded,
    ):
        assert await module.get_current_user_dto(user) is dto
        assert await module.get_current_user_auth_dto(user) is auth_dto
        assert await module.get_current_user_full(user, db) is user

    make_dto.assert_called_once_with(user)
    make_auth_dto.assert_called_once_with(user)
    ensure_loaded.assert_awaited_once_with(db, user)


@pytest.mark.asyncio
async def test_get_permission_checker_returns_dishka_checker():
    from app.api.deps.auth import get_permission_checker

    checker = object()
    implementation = get_permission_checker.__dishka_orig_func__
    assert await implementation(checker=checker) is checker


def test_enforce_fresh_mfa_handles_zero_ttl_and_naive_timestamp():
    from app.api.deps.auth import _enforce_fresh_mfa

    request = _request()
    request.state.active_session = SimpleNamespace(id=uuid4(), mfa_verified_at=None)
    with patch(
        "app.api.deps.auth.settings", SimpleNamespace(mfa_step_up_ttl_seconds=0)
    ):
        _enforce_fresh_mfa(request)

    request.state.active_session.mfa_verified_at = datetime.now(UTC).replace(
        tzinfo=None
    )
    with patch(
        "app.api.deps.auth.settings", SimpleNamespace(mfa_step_up_ttl_seconds=300)
    ):
        _enforce_fresh_mfa(request)
