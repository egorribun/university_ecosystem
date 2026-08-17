"""Behavioral closure for authentication dependencies without app bootstrap."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.api.deps import auth as module
from app.auth.rbac import SpiceDBUnavailableError


def _request(headers: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    request.state = SimpleNamespace()
    return request


def _session(*, user_id=None, jti="jti") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or uuid4(),
        jti=jti,
        revoked_at=None,
        expires_at=now + timedelta(hours=1),
        user_agent="pytest",
        ip_address="127.0.0.1",
        accept_language="en",
        fingerprint_hash=None,
        mfa_verified_at=None,
        last_seen_at=None,
    )


async def _run_db_success(
    request: MagicMock,
    user_id,
    jti: str,
    redis_service: AsyncMock | None,
    *,
    cache_client: AsyncMock | None = None,
    settings_value: SimpleNamespace | None = None,
    use_factory: bool = False,
):
    user = SimpleNamespace(id=user_id, is_active=True)
    session = _session(user_id=user_id, jti=jti)
    repo = MagicMock()
    repo.get_active_session_with_user = AsyncMock(return_value=(user, session))
    service = redis_service or AsyncMock()
    service.get_session.return_value = None
    client = cache_client or AsyncMock()
    client.exists.return_value = False
    security = MagicMock()
    security.validate_session_expiry = MagicMock()
    security.handle_mfa_ttl = AsyncMock()
    security.sync_last_seen = AsyncMock()
    fingerprint = MagicMock()
    fingerprint.validate_fingerprint = AsyncMock()

    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(
            module,
            "get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=client,
        ),
        patch.object(
            module.AuthTokenService,
            "extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": jti},
        ),
        patch.object(
            module.AuthTokenService, "validate_payload", return_value=(user_id, jti)
        ),
        patch.object(module, "ActiveSessionRepository", return_value=repo),
        patch.object(module, "AuthSecurityService", return_value=security),
        patch.object(module, "AuthFingerprintService", return_value=fingerprint),
        patch.object(module, "get_redis_session_service", return_value=service),
        patch.object(
            module,
            "settings",
            settings_value
            or SimpleNamespace(internal_hmac_secret="", environment="testing"),
        ),
    ):
        if use_factory:
            result = await module.get_current_user(request, "token", AsyncMock())
        else:
            result = await module.get_current_user(
                request, "token", AsyncMock(), service
            )
    return result, user, session, client, repo


def test_redis_service_factory_constructs_service():
    service = module.get_redis_session_service()
    assert isinstance(service, module.RedisSessionService)


@pytest.mark.asyncio
@pytest.mark.parametrize("use_tenant_signature", [True, False])
async def test_gateway_hmac_accepts_three_and_two_part_signatures(use_tenant_signature):
    user_id = uuid4()
    jti = "gateway-jti"
    tenant = str(uuid4()) if use_tenant_signature else ""
    headers = {
        "X-User-ID": str(user_id),
        "X-Session-ID": jti,
        "X-Tenant-ID": tenant,
    }
    signed_value = (
        f"{user_id}:{jti}:{tenant}" if use_tenant_signature else f"{user_id}:{jti}"
    )
    headers["X-Internal-Signature"] = hmac.new(
        b"secret", signed_value.encode(), hashlib.sha256
    ).hexdigest()
    redis_service = AsyncMock()
    redis_service.get_session.return_value = None

    result, user, _session_obj, _client, repo = await _run_db_success(
        _request(headers),
        user_id,
        jti,
        redis_service,
        settings_value=SimpleNamespace(
            internal_hmac_secret="secret",  # pragma: allowlist secret
            environment="testing",
        ),
    )

    assert result is user
    repo.get_active_session_with_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_gateway_hmac_rejects_two_part_signature_when_tenant_is_present():
    user_id = uuid4()
    jti = "gateway-jti"
    headers = {
        "X-User-ID": str(user_id),
        "X-Session-ID": jti,
        "X-Tenant-ID": str(uuid4()),
        "X-Internal-Signature": hmac.new(
            b"secret", f"{user_id}:{jti}".encode(), hashlib.sha256
        ).hexdigest(),
    }

    with pytest.raises(HTTPException) as exc_info:
        await _run_db_success(
            _request(headers),
            user_id,
            jti,
            AsyncMock(),
            settings_value=SimpleNamespace(
                internal_hmac_secret="secret",  # pragma: allowlist secret
                environment="testing",
            ),
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_current_user_uses_redis_dependency_factory_when_omitted():
    result, user, _session_obj, _client, _repo = await _run_db_success(
        _request(), uuid4(), "factory-jti", None, use_factory=True
    )
    assert result is user


@pytest.mark.asyncio
async def test_gateway_missing_secret_development_and_invalid_signature_paths():
    user_id = uuid4()
    redis_service = AsyncMock()
    redis_service.get_session.return_value = None
    with pytest.raises(HTTPException) as invalid:
        await module.get_current_user(
            _request({"X-User-ID": "not-a-uuid", "X-Session-ID": "jti"}),
            None,
            AsyncMock(),
            redis_service,
        )
    assert invalid.value.status_code == 401

    with pytest.raises(HTTPException) as production:
        with patch.object(
            module,
            "settings",
            SimpleNamespace(internal_hmac_secret="", environment="production"),
        ):
            await module.get_current_user(
                _request({"X-User-ID": str(user_id), "X-Session-ID": "jti"}),
                None,
                AsyncMock(),
                redis_service,
            )
    assert production.value.status_code == 401


@pytest.mark.asyncio
async def test_gateway_invalid_signature_is_rejected():
    with patch.object(
        module,
        "settings",
        SimpleNamespace(
            internal_hmac_secret="secret",  # pragma: allowlist secret
            environment="testing",
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await module.get_current_user(
                _request(
                    {
                        "X-User-ID": str(uuid4()),
                        "X-Session-ID": "jti",
                        "X-Internal-Signature": "wrong",
                    }
                ),
                None,
                AsyncMock(),
                AsyncMock(),
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_revoked_jti_and_redis_error_paths():
    user_id = uuid4()
    redis_service = AsyncMock()
    revoked_client = AsyncMock()
    revoked_client.exists.return_value = True
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(
            module,
            "get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=revoked_client,
        ),
        patch.object(
            module.AuthTokenService,
            "extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": "revoked"},
        ),
        patch.object(
            module.AuthTokenService,
            "validate_payload",
            return_value=(user_id, "revoked"),
        ),
    ):
        with pytest.raises(HTTPException):
            await module.get_current_user(
                _request(), "token", AsyncMock(), redis_service
            )

    error_client = AsyncMock()
    error_client.exists.side_effect = ConnectionError("redis unavailable")
    redis_service.get_session.return_value = None
    result, user, _session_obj, _client, _repo = await _run_db_success(
        _request(), user_id, "redis-error", redis_service, cache_client=error_client
    )
    assert result is user


@pytest.mark.asyncio
async def test_db_cache_miss_without_active_session_is_rejected():
    user_id = uuid4()
    redis_service = AsyncMock()
    redis_service.get_session.return_value = None
    repo = MagicMock()
    repo.get_active_session_with_user = AsyncMock(return_value=None)
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(
            module,
            "get_revocation_redis_client",
            new_callable=AsyncMock,
            return_value=AsyncMock(exists=AsyncMock(return_value=False)),
        ),
        patch.object(
            module.AuthTokenService,
            "extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": "missing"},
        ),
        patch.object(
            module.AuthTokenService,
            "validate_payload",
            return_value=(user_id, "missing"),
        ),
        patch.object(module, "ActiveSessionRepository", return_value=repo),
        patch.object(
            module,
            "settings",
            SimpleNamespace(internal_hmac_secret="", environment="testing"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await module.get_current_user(
                _request(), "token", AsyncMock(), redis_service
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_optional_user_converts_auth_error_to_none():
    with patch.object(
        module,
        "get_current_user",
        new=AsyncMock(side_effect=HTTPException(status_code=401)),
    ):
        assert (
            await module.get_current_user_optional(_request(), None, AsyncMock())
            is None
        )


@pytest.mark.asyncio
async def test_admin_dependency_success_forbidden_and_spicedb_unavailable():
    user = SimpleNamespace(id=uuid4())
    request = _request()
    good_checker = MagicMock(check_admin=AsyncMock(return_value=True))
    assert await module.get_current_admin_user(request, user, good_checker) is user

    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(
            module, "raise_forbidden", side_effect=HTTPException(status_code=403)
        ),
    ):
        with pytest.raises(HTTPException) as forbidden:
            await module.get_current_admin_user(
                request, user, MagicMock(check_admin=AsyncMock(return_value=False))
            )
    assert forbidden.value.status_code == 403

    unavailable = MagicMock(
        check_admin=AsyncMock(side_effect=SpiceDBUnavailableError("down"))
    )
    with pytest.raises(HTTPException) as unavailable_error:
        await module.get_current_admin_user(request, user, unavailable)
    assert unavailable_error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_fresh_mfa_all_lifecycle_branches():
    request = _request()
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(
            module, "raise_forbidden", side_effect=HTTPException(status_code=403)
        ),
    ):
        request.state.active_session = None
        with pytest.raises(HTTPException):
            module._enforce_fresh_mfa(request)

    request.state.active_session = SimpleNamespace(id=uuid4(), mfa_verified_at=None)
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(module, "settings", SimpleNamespace(mfa_step_up_ttl_seconds=60)),
    ):
        with pytest.raises(HTTPException) as missing:
            module._enforce_fresh_mfa(request)
    assert missing.value.status_code == 428

    request.state.active_session.mfa_verified_at = datetime.now(UTC) - timedelta(
        seconds=120
    )
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(module, "settings", SimpleNamespace(mfa_step_up_ttl_seconds=60)),
    ):
        with pytest.raises(HTTPException) as expired:
            module._enforce_fresh_mfa(request)
    assert expired.value.status_code == 428

    request.state.active_session.mfa_verified_at = datetime.now(UTC)
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(module, "settings", SimpleNamespace(mfa_step_up_ttl_seconds=60)),
    ):
        module._enforce_fresh_mfa(request)

    request.state.active_session.mfa_verified_at = datetime.now().replace(tzinfo=None)
    with (
        patch.object(module, "resolve_locale", return_value="en"),
        patch.object(module, "settings", SimpleNamespace(mfa_step_up_ttl_seconds=60)),
    ):
        module._enforce_fresh_mfa(request)


@pytest.mark.asyncio
async def test_require_fresh_mfa_delegates_only_for_confirmed_factor():
    user = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    request = _request()
    with (
        patch.object(module, "ensure_mfa_relationships_loaded", new=AsyncMock()),
        patch.object(
            module.mfa, "user_has_confirmed_interactive_factor", return_value=False
        ),
        patch.object(module, "_enforce_fresh_mfa") as enforce,
    ):
        await module.require_fresh_mfa(request, user, db)
    enforce.assert_not_called()

    with (
        patch.object(module, "ensure_mfa_relationships_loaded", new=AsyncMock()),
        patch.object(
            module.mfa, "user_has_confirmed_interactive_factor", return_value=True
        ),
        patch.object(module, "_enforce_fresh_mfa") as enforce,
    ):
        await module.require_fresh_mfa(request, user, db)
    enforce.assert_called_once_with(request)
