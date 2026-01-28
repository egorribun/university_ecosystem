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
from app.models.models import ActiveSession, User


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
    with patch("app.api.deps.decode_token", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "invalid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_user_not_found(mock_request, db_session):
    payload = {"sub": "999", "jti": "some-jti"}
    with patch("app.api.deps.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_inactive_user(mock_request, db_session, user_factory):
    user = await user_factory(is_active=False)
    payload = {"sub": str(user.id), "jti": "some-jti"}
    with patch("app.api.deps.decode_token", return_value=payload):
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user(mock_request, "valid-token", db_session)
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_missing_jti(mock_request, db_session, user_factory):
    user = await user_factory(is_active=True)
    payload = {"sub": str(user.id)}  # No jti
    with patch("app.api.deps.decode_token", return_value=payload):
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
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
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
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
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
    user.role = "student"
    with patch("app.api.deps.resolve_locale", return_value="en"):
        with patch("app.api.deps.raise_forbidden") as mock_raise:
            await get_current_admin_user(mock_request, user)
            mock_raise.assert_called_once()


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_no_session(mock_request):
    mock_request.state.active_session = None
    with patch("app.api.deps.resolve_locale", return_value="en"):
        with patch(
            "app.api.deps.raise_forbidden", side_effect=HTTPException(status_code=403)
        ) as mock_raise:
            with pytest.raises(HTTPException) as excinfo:
                _enforce_fresh_mfa(mock_request)
            assert excinfo.value.status_code == 403
            mock_raise.assert_called_once()


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_not_verified(mock_request):
    session = MagicMock(spec=ActiveSession)
    session.mfa_verified_at = None
    mock_request.state.active_session = session
    with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        with patch("app.api.deps.resolve_locale", return_value="en"):
            with pytest.raises(HTTPException) as excinfo:
                _enforce_fresh_mfa(mock_request)
            assert excinfo.value.status_code == status.HTTP_428_PRECONDITION_REQUIRED


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_expired(mock_request):
    now = datetime.now(UTC)
    session = MagicMock(spec=ActiveSession)
    session.mfa_verified_at = now - timedelta(seconds=600)
    mock_request.state.active_session = session
    with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        with patch("app.api.deps.resolve_locale", return_value="en"):
            with pytest.raises(HTTPException) as excinfo:
                _enforce_fresh_mfa(mock_request)
            assert excinfo.value.status_code == status.HTTP_428_PRECONDITION_REQUIRED


@pytest.mark.asyncio
async def test_get_locale_preferred(mock_request):
    user = MagicMock(spec=User)
    user.preferred_locale = "ru"
    with patch("app.api.deps.resolve_locale", return_value="en"):
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

    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch(
                "app.auth.fingerprint.extract_fingerprint", return_value=mock_fp
            ):
                with patch(
                    "app.auth.fingerprint.get_suspicious_activity_detector"
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
    with patch("app.api.deps.decode_token", return_value=payload):
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
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
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
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
                returned_user = await get_current_user(
                    mock_request, "token", db_session
                )
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
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
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
    with patch("app.api.deps.resolve_locale", return_value="fr"):
        locale = get_locale(mock_request, user)
        assert locale == "fr"


@pytest.mark.asyncio
async def test_require_fresh_mfa_confirmed(mock_request):
    user = MagicMock(spec=User)
    with patch("app.auth.mfa.user_has_confirmed_interactive_factor", return_value=True):
        with patch("app.api.deps._enforce_fresh_mfa") as mock_enforce:
            from app.api.deps import require_fresh_mfa

            require_fresh_mfa(mock_request, user)
            mock_enforce.assert_called_once()


@pytest.mark.asyncio
async def test_require_fresh_mfa_not_confirmed(mock_request):
    user = MagicMock(spec=User)
    with patch(
        "app.auth.mfa.user_has_confirmed_interactive_factor", return_value=False
    ):
        with patch("app.api.deps._enforce_fresh_mfa") as mock_enforce:
            from app.api.deps import require_fresh_mfa

            require_fresh_mfa(mock_request, user)
            mock_enforce.assert_not_called()


@pytest.mark.asyncio
async def test_get_chat_service(db_session):
    from app.api import deps

    service = deps.get_chat_service(db_session)
    from app.services.chat_service import ChatService

    assert isinstance(service, ChatService)
    assert service.session == db_session


@pytest.mark.asyncio
async def test_get_current_user_redis_backend_fail(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    payload = {"sub": str(user.id), "jti": "redis-jti"}
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=False)),
        ):
            with patch(
                "app.api.deps.settings", MagicMock(session_storage_backend="redis")
            ):
                with pytest.raises(HTTPException) as excinfo:
                    await get_current_user(mock_request, "token", db_session)
                assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_naive_datetimes(mock_request, db_session, user_factory):
    user = await user_factory(is_active=True)
    jti = "naive-jti"
    # Create naive datetimes that correspond to UTC
    now_utc_naive = datetime.now(UTC).replace(tzinfo=None)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=now_utc_naive + timedelta(hours=1),
        mfa_verified_at=now_utc_naive - timedelta(seconds=600),
        last_seen_at=now_utc_naive - timedelta(seconds=400),
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
                returned_user = await get_current_user(
                    mock_request, "token", db_session
                )
                assert returned_user.id == user.id
                await db_session.refresh(session)
                assert session.mfa_verified_at is None


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_naive(mock_request):
    session = MagicMock(spec=ActiveSession)
    # Use naive UTC time so that comparison with code's now(UTC) works
    session.mfa_verified_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        seconds=600
    )
    mock_request.state.active_session = session
    with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        with patch("app.api.deps.resolve_locale", return_value="en"):
            with pytest.raises(HTTPException) as excinfo:
                _enforce_fresh_mfa(mock_request)
            assert excinfo.value.status_code == status.HTTP_428_PRECONDITION_REQUIRED


@pytest.mark.asyncio
async def test_require_fresh_mfa_for_enrollment_confirmed(mock_request):
    user = MagicMock(spec=User)
    with patch("app.auth.mfa.user_has_confirmed_interactive_factor", return_value=True):
        with patch("app.api.deps._enforce_fresh_mfa") as mock_enforce:
            from app.api.deps import require_fresh_mfa_for_enrollment

            require_fresh_mfa_for_enrollment(mock_request, user)
            mock_enforce.assert_called_once()


@pytest.mark.asyncio
async def test_require_fresh_mfa_for_enrollment_not_confirmed(mock_request):
    user = MagicMock(spec=User)
    with patch(
        "app.auth.mfa.user_has_confirmed_interactive_factor", return_value=False
    ):
        with patch("app.api.deps._enforce_fresh_mfa") as mock_enforce:
            from app.api.deps import require_fresh_mfa_for_enrollment

            require_fresh_mfa_for_enrollment(mock_request, user)
            mock_enforce.assert_not_called()


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_disabled(mock_request):
    session = MagicMock(spec=ActiveSession)
    mock_request.state.active_session = session
    with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=0)):
        _enforce_fresh_mfa(mock_request)  # Should not raise


@pytest.mark.asyncio
async def test_get_current_user_no_expiration_mock(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "no-exp-jti"
    # Create a mock session object instead of using DB
    mock_session = MagicMock(spec=ActiveSession)
    mock_session.user_id = user.id
    mock_session.jti = jti
    mock_session.expires_at = None
    mock_session.revoked_at = None
    mock_session.fingerprint_hash = None

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            # Mock db.execute to return our mock_session
            mock_res = MagicMock()
            mock_res.scalars.return_value.first.return_value = mock_session
            with patch.object(db_session, "execute", return_value=mock_res):
                from app.api.deps import get_current_user

                with pytest.raises(HTTPException) as excinfo:
                    await get_current_user(mock_request, "token", db_session)
                assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_admin_user_forbidden_literal(mock_request):
    user = MagicMock(spec=User)
    user.role = "user"
    from app.api.deps import get_current_admin_user

    with patch("app.api.deps.resolve_locale", return_value="en"):
        with patch("app.api.deps.raise_forbidden") as mock_forbidden:
            mock_forbidden.side_effect = HTTPException(status_code=403)
            with pytest.raises(HTTPException):
                await get_current_admin_user(mock_request, user)
            mock_forbidden.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_user_fingerprint_mismatch_no_event(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "fp-no-event-jti"
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        fingerprint_hash="old-hash",
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    mock_fp = MagicMock()
    mock_fp.fingerprint_hash = "new-hash"

    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch(
                "app.auth.fingerprint.extract_fingerprint", return_value=mock_fp
            ):
                with patch(
                    "app.auth.fingerprint.get_suspicious_activity_detector"
                ) as mock_detector:
                    mock_det_inst = MagicMock()
                    mock_detector.return_value = mock_det_inst
                    mock_det_inst.check_fingerprint_mismatch.return_value = (
                        None  # No event returned
                    )

                    # Should NOT raise, just log
                    # (and we mocked detector to return None event)
                    returned_user = await get_current_user(
                        mock_request, "token", db_session
                    )
                    assert returned_user.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_fingerprint_mismatch_with_event_log(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "fp-event-log-jti"
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        fingerprint_hash="old-hash",
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    mock_fp = MagicMock()
    mock_fp.fingerprint_hash = "new-hash"

    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch(
                "app.auth.fingerprint.extract_fingerprint", return_value=mock_fp
            ):
                with patch(
                    "app.auth.fingerprint.get_suspicious_activity_detector"
                ) as mock_detector:
                    mock_det_inst = MagicMock()
                    mock_detector.return_value = mock_det_inst
                    mock_event = MagicMock()
                    mock_event.to_log_record.return_value = {"log": "data"}
                    mock_det_inst.check_fingerprint_mismatch.return_value = mock_event

                    with patch("logging.getLogger") as mock_get_logger:
                        mock_logger = MagicMock()
                        mock_get_logger.return_value = mock_logger
                        await get_current_user(mock_request, "token", db_session)
                        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_user_fingerprint_match(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "fp-match-jti"
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        fingerprint_hash="same-hash",
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    mock_fp = MagicMock()
    mock_fp.fingerprint_hash = "same-hash"

    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch(
                "app.auth.fingerprint.extract_fingerprint", return_value=mock_fp
            ):
                # Should hit the match path (skip inner if mismatch)
                returned_user = await get_current_user(
                    mock_request, "token", db_session
                )
                assert returned_user.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_no_session_fingerprint(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    jti = "no-fp-jti"
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        fingerprint_hash=None,
    )
    db_session.add(session)
    await db_session.commit()

    payload = {"sub": str(user.id), "jti": jti}
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            # Should skip fingerprint check block
            await get_current_user(mock_request, "token", db_session)


@pytest.mark.asyncio
async def test_get_current_user_settings_session_backend_not_redis(
    mock_request, db_session, user_factory
):
    user = await user_factory(is_active=True)
    payload = {"sub": str(user.id), "jti": "not-redis-jti"}
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=False)),
        ):
            # is_valid_redis is False,
            # but settings.session_storage_backend is NOT "redis"
            with patch(
                "app.api.deps.settings",
                MagicMock(session_storage_backend="db", mfa_step_up_ttl_seconds=300),
            ):
                # Should proceed to check DB
                jti = "not-redis-jti"
                session = ActiveSession(
                    user_id=user.id,
                    jti=jti,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
                db_session.add(session)
                await db_session.commit()

                returned_user = await get_current_user(
                    mock_request, "token", db_session
                )
                assert returned_user.id == user.id


@pytest.mark.asyncio
async def test_get_current_admin_user_success(mock_request):
    user = MagicMock(spec=User)
    user.role = "admin"
    from app.api.deps import get_current_admin_user

    returned_user = await get_current_admin_user(mock_request, user)
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
    with patch("app.api.deps.decode_token", return_value=payload):
        with patch(
            "app.api.deps.get_session_backend",
            return_value=AsyncMock(is_session_valid=AsyncMock(return_value=True)),
        ):
            with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
                returned_user = await get_current_user(
                    mock_request, "token", db_session
                )
                assert returned_user.id == user.id
                await db_session.refresh(session)
                assert session.mfa_verified_at is not None  # Should NOT be cleared


@pytest.mark.asyncio
async def test_enforce_fresh_mfa_success(mock_request):
    session = MagicMock(spec=ActiveSession)
    session.mfa_verified_at = datetime.now(UTC) - timedelta(seconds=10)
    mock_request.state.active_session = session
    with patch("app.api.deps.settings", MagicMock(mfa_step_up_ttl_seconds=300)):
        from app.api.deps import _enforce_fresh_mfa

        # Should not raise
        _enforce_fresh_mfa(mock_request)
