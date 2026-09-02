from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status

from app.api.deps import (
    _enforce_fresh_mfa,
    get_current_admin_user,
    get_current_user,
    get_current_user_optional,
    get_locale,
)
from app.models import ActiveSession, User


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.headers = {}
    request.cookies = {}
    request.state = MagicMock()
    return request


@pytest.mark.asyncio
async def test_get_current_user_no_token(mock_request, db_session):
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(mock_request, None, db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(mock_request, db_session):
    with patch("app.services.auth.token_service.decode_token", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "invalid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_user_not_found(mock_request, db_session):
    payload = {"sub": "999", "jti": "some-jti"}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_inactive_user(mock_request, db_session, user_factory):
    user = await user_factory(is_active=False)
    payload = {"sub": str(user.id), "jti": "some-jti"}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_missing_jti(mock_request, db_session, user_factory):
    user = await user_factory(is_active=True)
    payload = {"sub": str(user.id)}  # No jti
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_revoked_session(mock_request, db_session, user_factory):
    user = await user_factory(is_active=True)
    jti = "revoked-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
        revoked_at=now - timedelta(minutes=5),
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_expired_session(mock_request, db_session, user_factory):
    user = await user_factory(is_active=True)
    jti = "expired-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id, jti=jti, expires_at=now - timedelta(minutes=1)
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_optional(mock_request, db_session):
    # Coverage for get_current_user_optional returning None on 401
    user = await get_current_user_optional(mock_request, None, db_session)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_admin_user_forbidden(mock_request):
    user = MagicMock(spec=User)
    user.id = "test-user-id"
    user.role = "student"
    # Mock PermissionChecker that returns False for admin check
    mock_checker = MagicMock()
    mock_checker.check_admin = AsyncMock(return_value=False)
    with patch("app.api.deps.localization.resolve_locale", return_value="en"):
        with patch("app.api.deps.auth.raise_forbidden") as mock_raise:
            await get_current_admin_user(mock_request, user, mock_checker)
            mock_raise.assert_called_once()


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_no_session(mock_request):
    mock_request.state.active_session = None
    with (
        patch("app.api.deps.localization.resolve_locale", return_value="en"),
        patch(
            "app.api.deps.auth.raise_forbidden",
            side_effect=HTTPException(status_code=403),
        ) as mock_raise,
    ):
        with pytest.raises(HTTPException) as excinfo:
            _enforce_fresh_mfa(mock_request)
        assert excinfo.value.status_code == 403
        mock_raise.assert_called_once()


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_not_verified(mock_request):
    session = MagicMock(spec=ActiveSession)
    session.mfa_verified_at = None
    mock_request.state.active_session = session
    with patch("app.api.deps.auth.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        with patch("app.api.deps.localization.resolve_locale", return_value="en"):
            with pytest.raises(HTTPException) as excinfo:
                _enforce_fresh_mfa(mock_request)
            assert excinfo.value.status_code == status.HTTP_428_PRECONDITION_REQUIRED


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_expired(mock_request):
    now = datetime.now(UTC)
    session = MagicMock(spec=ActiveSession)
    session.mfa_verified_at = now - timedelta(seconds=600)
    mock_request.state.active_session = session
    with patch("app.api.deps.auth.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        with patch("app.api.deps.localization.resolve_locale", return_value="en"):
            with pytest.raises(HTTPException) as excinfo:
                _enforce_fresh_mfa(mock_request)
            assert excinfo.value.status_code == status.HTTP_428_PRECONDITION_REQUIRED


@pytest.mark.asyncio
async def test_get_locale_preferred(mock_request):
    user = MagicMock(spec=User)
    user.preferred_locale = "ru"
    with patch("app.api.deps.localization.resolve_locale", return_value="en"):
        locale = get_locale(mock_request, user)
        assert locale == "ru"


@pytest.mark.asyncio
async def test_get_current_user_fingerprint_mismatch(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "fp-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
        fingerprint_hash="stored-hash",
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}

    mock_fp = MagicMock()
    mock_fp.fingerprint_hash = "different-hash"

    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with patch(
            "app.services.auth.fingerprint_service.extract_fingerprint",
            return_value=mock_fp,
        ):
            with patch(
                "app.services.auth.fingerprint_service.get_suspicious_activity_detector"
            ) as mock_detector:
                mock_det_inst = MagicMock()
                mock_detector.return_value = mock_det_inst
                mock_det_inst.check_fingerprint_mismatch.return_value = MagicMock(
                    to_log_record=lambda: {}
                )

                returned_user = await get_current_user(
                    mock_request, "token", db_session
                )
                assert returned_user.id == user.id
                mock_det_inst.check_fingerprint_mismatch.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_user_invalid_sub_type(mock_request, db_session):
    payload = {"sub": "abc", "jti": "some-jti"}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_session_user_mismatch(
    mock_request, db_session, user_factory
):
    user1 = await user_factory()
    user2 = await user_factory()
    jti = "mismatch-jti"
    session = ActiveSession(
        user_id=user2.id,  # Belongs to user2
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user1.id), "jti": jti}  # Token for user1
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_mfa_ttl_expired(mock_request, db_session, user_factory):
    user = await user_factory(is_active=True)
    jti = "mfa-ttl-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
        mfa_verified_at=now - timedelta(seconds=600),
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with patch(
            "app.api.deps.auth.settings", MagicMock(mfa_step_up_ttl_seconds=300)
        ):
            returned_user = await get_current_user(mock_request, "token", db_session)
            assert returned_user.id == user.id
            await db_session.refresh(session)
            assert session.mfa_verified_at is None


@pytest.mark.asyncio
async def test_get_current_user_last_seen_throttled(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "throttle-jti"
    now = datetime.now(UTC)
    last_seen = now - timedelta(seconds=100)  # Less than 300s
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
        last_seen_at=last_seen,
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        await get_current_user(mock_request, "token", db_session)
        await db_session.refresh(session)
        # Compare actual values by stripping tzinfo if present,
        # ensuring we compare UTC to UTC.
        actual = session.last_seen_at
        if actual.tzinfo is not None:
            actual = actual.astimezone(UTC).replace(tzinfo=None)
        expected = last_seen.replace(tzinfo=None)
        assert actual == expected


@pytest.mark.asyncio
async def test_get_locale_header_fallback(mock_request):
    user = MagicMock(spec=User)
    user.preferred_locale = None
    with patch("app.api.deps.localization.resolve_locale", return_value="fr"):
        locale = get_locale(mock_request, user)
        assert locale == "fr"


@pytest.mark.asyncio
async def test_require_fresh_mfa_confirmed(mock_request, db_session):
    user = MagicMock(spec=User)
    with patch("app.auth.mfa.user_has_confirmed_interactive_factor", return_value=True):
        with patch("app.models.user_loaders.ensure_mfa_relationships_loaded"):
            with patch("app.api.deps.auth._enforce_fresh_mfa") as mock_enforce:
                from app.api.deps import require_fresh_mfa

                await require_fresh_mfa(mock_request, user, db_session)
                mock_enforce.assert_called_once()


@pytest.mark.asyncio
async def test_require_fresh_mfa_not_confirmed(mock_request, db_session):
    user = MagicMock(spec=User)
    user.email_mfa_enabled_at = None
    with (
        patch(
            "app.auth.mfa.has_totp_enabled",
            new=AsyncMock(return_value=False),
        ),
        patch("app.models.user_loaders.ensure_mfa_relationships_loaded"),
    ):
        with patch("app.api.deps.auth._enforce_fresh_mfa") as mock_enforce:
            from app.api.deps import require_fresh_mfa

            await require_fresh_mfa(mock_request, user, db_session)
            mock_enforce.assert_not_called()


@pytest.mark.asyncio
async def test_get_chat_service(db_session):
    """TD-W9-05: ChatService wrapper removed — get_chat_service returns ChatMessageDispatcher."""
    from app.api import deps
    from app.services.chat.command_service import ChatMessageDispatcher

    service = deps.get_chat_message_dispatcher(db_session)
    assert isinstance(service, ChatMessageDispatcher)
    # The service delegates session management to the repository (architectural boundary).
    assert service.repository.db == db_session


@pytest.mark.asyncio
async def test_get_current_user_no_expiration_mock(
    mock_request, db_session, user_factory
):
    """
    Test that ensures we fallback to DB and fail if session has no expiration
    (which shouldn't happen for valid sessions), even if we mock the DB return.
    """
    user = await user_factory(is_active=True)
    jti = "no-exp-jti"

    # Mock Redis failure/miss to force DB path
    # Mock Redis failure/miss to force DB path
    with patch(
        "app.services.auth.redis_session.RedisSessionService", autospec=True
    ) as MockRedisService:
        mock_service = MockRedisService.return_value
        mock_service.get_session.return_value = None

        # Create a mock session object
        mock_session = MagicMock(spec=ActiveSession)
        mock_session.user_id = user.id
        mock_session.jti = jti
        mock_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
        mock_session.revoked_at = None
        mock_session.fingerprint_hash = None

        payload = {"sub": str(user.id), "jti": jti}

        with patch(
            "app.services.auth.token_service.decode_token", return_value=payload
        ):
            # Mock the DB execution result
            mock_res_user = MagicMock()
            mock_res_user.first.return_value = (user, mock_session)

            with patch.object(db_session, "execute", return_value=mock_res_user):
                from app.api.deps import get_current_user

                with pytest.raises(HTTPException) as excinfo:
                    await get_current_user(mock_request, "token", db_session)
                assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_admin_user_success(mock_request):
    user = MagicMock(spec=User)
    user.id = "test-admin-id"
    user.role = "admin"
    from app.api.deps import get_current_admin_user

    # Mock PermissionChecker that returns True for admin check
    # (SpiceDB unavailable fallback)
    mock_checker = MagicMock()
    mock_checker.check_admin = AsyncMock(return_value=True)
    returned_user = await get_current_admin_user(mock_request, user, mock_checker)
    assert returned_user == user


@pytest.mark.asyncio
async def test_get_current_user_mfa_ttl_not_expired(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "mfa-fresh-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
        mfa_verified_at=now - timedelta(seconds=10),  # Only 10s old
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with patch(
            "app.api.deps.auth.settings", MagicMock(mfa_step_up_ttl_seconds=300)
        ):
            returned_user = await get_current_user(mock_request, "token", db_session)
            assert returned_user.id == user.id
            await db_session.refresh(session)
            assert session.mfa_verified_at is not None  # Should NOT be cleared


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_success(mock_request):
    session = MagicMock(spec=ActiveSession)
    session.mfa_verified_at = datetime.now(UTC) - timedelta(seconds=10)
    mock_request.state.active_session = session
    with patch("app.api.deps.auth.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        from app.api.deps import _enforce_fresh_mfa

        # Should not raise
        _enforce_fresh_mfa(mock_request)


import hashlib
import hmac


@pytest.mark.asyncio
async def test_get_current_user_gateway_signature_success(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "gateway-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()

    user_id_str = str(user.id)
    mock_request.headers = {
        "X-User-ID": user_id_str,
        "X-Session-ID": jti,
    }

    # Set internal_hmac_secret
    with patch(
        "app.api.deps.auth.settings",
        MagicMock(
            internal_hmac_secret="secret-key",  # pragma: allowlist secret
            environment="testing",
        ),
    ):
        # Calculate signature
        sig = hmac.new(
            b"secret-key",  # pragma: allowlist secret
            f"{user_id_str}:{jti}".encode(),
            hashlib.sha256,
        ).hexdigest()
        mock_request.headers["X-Internal-Signature"] = sig

        returned_user = await get_current_user(mock_request, None, db_session)
        assert returned_user.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_gateway_signature_failure(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "gateway-jti"

    mock_request.headers = {
        "X-User-ID": str(user.id),
        "X-Session-ID": jti,
        "X-Internal-Signature": "wrong-signature",
    }

    with patch(
        "app.api.deps.auth.settings",
        MagicMock(
            internal_hmac_secret="secret-key",  # pragma: allowlist secret
            environment="testing",
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, None, db_session)
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_gateway_secret_missing_production(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "gateway-jti"

    mock_request.headers = {
        "X-User-ID": str(user.id),
        "X-Session-ID": jti,
    }

    with patch(
        "app.api.deps.auth.settings",
        MagicMock(internal_hmac_secret="", environment="production"),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, None, db_session)
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_gateway_invalid_uuid(mock_request, db_session):
    mock_request.headers = {
        "X-User-ID": "invalid-uuid-format",
        "X-Session-ID": "some-session",
    }

    with patch(
        "app.api.deps.auth.settings",
        MagicMock(internal_hmac_secret="", environment="testing"),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, None, db_session)
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_jti_revoked_in_redis(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "revoked-redis-jti"

    payload = {"sub": str(user.id), "jti": jti}

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = True

    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with patch(
            "app.api.deps.auth.get_revocation_redis_client", return_value=mock_redis
        ):
            with pytest.raises(HTTPException) as exc:
                await get_current_user(mock_request, "token", db_session)
            assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
            mock_redis.exists.assert_called_once_with(f"revoked:jti:{jti}")


@pytest.mark.asyncio
async def test_get_current_user_jti_redis_connection_error(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "redis-error-jti"
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}

    mock_redis = AsyncMock()
    mock_redis.exists.side_effect = ConnectionError("Redis down")

    with patch("app.services.auth.token_service.decode_token", return_value=payload):
        with patch(
            "app.api.deps.auth.get_revocation_redis_client", return_value=mock_redis
        ):
            # Should fall through and succeed from DB
            returned_user = await get_current_user(mock_request, "token", db_session)
            assert returned_user.id == user.id


@pytest.mark.asyncio
async def test_get_current_admin_user_spicedb_unavailable(mock_request):
    from app.auth.rbac import SpiceDBUnavailableError

    user = MagicMock(spec=User)
    user.id = "test-user-id"
    user.role = "admin"

    mock_checker = MagicMock()
    mock_checker.check_admin = AsyncMock(
        side_effect=SpiceDBUnavailableError("SpiceDB down")
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_admin_user(mock_request, user, mock_checker)
    assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
