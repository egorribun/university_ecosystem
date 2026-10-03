"""Regression checks for authentication lifecycle security boundaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pyotp
import pytest
from fastapi import HTTPException, Request, Response

from app.api.auth import login as login_api
from app.api.deps.auth import _enforce_fresh_mfa
from app.auth.schemas import MfaVerifyIn


@pytest.mark.asyncio
@pytest.mark.parametrize("verified_at", [None, datetime(2020, 1, 1, tzinfo=UTC)])
async def test_email_ownership_verification_never_grants_mfa_freshness(verified_at):
    user = SimpleNamespace(id=uuid4(), email_mfa_enabled_at=None)
    session = SimpleNamespace(id=uuid4(), mfa_verified_at=verified_at)
    request = Request(
        {
            "type": "http",
            "headers": [],
            "method": "POST",
            "path": "/",
            "query_string": b"",
        }
    )
    request.state.active_session = session
    challenge = SimpleNamespace(
        user_id=user.id, flow="email_verification", trust_device_requested=False
    )
    service = MagicMock()
    service.get_email_otp_service.return_value.verify_opaque = AsyncMock(
        return_value=challenge
    )
    service.complete_step_up = AsyncMock()
    service.publish_completed_step_up = AsyncMock()
    service.finalize_login = AsyncMock()
    service.build_session_response = AsyncMock(return_value=object())
    db = AsyncMock()
    db.get.return_value = user

    with patch.object(
        login_api, "_load_optional_active_session", AsyncMock(return_value=session)
    ):
        result = await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(method="email_otp", challenge_token="a" * 32, code="123456"),
            Response(),
            request,
            MagicMock(),
            service,
            db,
        )

    service.complete_step_up.assert_not_awaited()
    service.publish_completed_step_up.assert_not_awaited()
    service.finalize_login.assert_not_awaited()
    service.build_session_response.assert_awaited_once_with(user=user, session=session)
    assert result is service.build_session_response.return_value
    assert session.mfa_verified_at is verified_at
    db.commit.assert_awaited_once()
    with pytest.raises(HTTPException) as denied:
        _enforce_fresh_mfa(request)
    assert denied.value.status_code == 428


@pytest.mark.asyncio
@pytest.mark.parametrize("preserve_current", [True, False])
async def test_password_session_revocation_reaches_redis_consumers(
    db_session, test_user, mock_global_redis, preserve_current
):
    from app.models import ActiveSession
    from app.repositories.active_session_repository import ActiveSessionRepository

    current = ActiveSession(
        user_id=test_user.id,
        jti="password-current",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    sibling = ActiveSession(
        user_id=test_user.id,
        jti="password-sibling",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add_all([current, sibling])
    await db_session.flush()
    repository = ActiveSessionRepository(db_session)
    if preserve_current:
        count = await repository.revoke_all_except(test_user.id, current.id)
    else:
        count = await repository.revoke_all_for_user(test_user.id)

    assert count == (1 if preserve_current else 2)
    assert await mock_global_redis.exists("revoked:jti:password-sibling") == 1
    assert await mock_global_redis.exists("revoked:jti:password-current") == (
        0 if preserve_current else 1
    )
    assert sibling.revoked_at is not None
    assert (current.revoked_at is None) is preserve_current


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["redis", "commit", None])
async def test_factor_change_requires_tombstones_before_commit(failure):
    from app.api.auth import mfa as mfa_api
    from app.auth.mfa.lifecycle import MfaSessionRevocation

    events = []
    db = AsyncMock()
    pending = [
        MfaSessionRevocation(
            jti="sibling", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
    ]

    async def publish(_):
        events.append("tombstone")
        if failure == "redis":
            raise OSError("Redis unavailable")

    async def commit():
        events.append("commit")
        if failure == "commit":
            raise RuntimeError("Commit failed")

    db.commit.side_effect = commit
    with patch.object(
        mfa_api.mfa, "publish_mfa_session_revocations", AsyncMock(side_effect=publish)
    ):
        if failure:
            with pytest.raises((OSError, RuntimeError)):
                await mfa_api._commit_and_publish_mfa_revocations(db, pending)
            db.rollback.assert_awaited_once()
        else:
            await mfa_api._commit_and_publish_mfa_revocations(db, pending)
    assert events == (["tombstone"] if failure == "redis" else ["tombstone", "commit"])


@pytest.mark.asyncio
async def test_revocation_publication_failure_is_never_swallowed():
    from app.auth.mfa.lifecycle import (
        MfaSessionRevocation,
        publish_mfa_session_revocations,
    )

    pending = [
        MfaSessionRevocation(
            jti="sibling", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
    ]
    with patch(
        "app.services.auth.redis_session.RedisSessionService",
        MagicMock(side_effect=RuntimeError("Redis unavailable")),
    ):
        with pytest.raises(RuntimeError, match="Redis unavailable"):
            await publish_mfa_session_revocations(pending)


@pytest.mark.asyncio
async def test_password_change_rolls_back_on_redis_failure_and_retry_revokes(
    db_session, test_user, mock_global_redis
):
    from app.models import ActiveSession
    from app.repositories.active_session_repository import ActiveSessionRepository
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import uow_from_session
    from app.repositories.user_repository import UserRepository
    from app.schemas.schemas import UserPasswordChangeIn
    from app.services.auth_service import AuthService

    user_id = test_user.id
    old_password = test_user.hashed_password
    sibling = ActiveSession(
        user_id=user_id,
        jti="retry-sibling",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sibling)
    await db_session.commit()
    service = AuthService(
        audit=MagicMock(),
        auth_repo=AuthRepository(db_session),
        user_repo=UserRepository(db_session),
        session_repo=ActiveSessionRepository(db_session),
        uow=uow_from_session(db_session),
    )
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = None
    expected_hash = uuid4().hex
    payload = UserPasswordChangeIn(
        current_password=f"Old-{uuid4().hex}!1",
        new_password=f"New-{uuid4().hex}!2",
    )
    with (
        patch(
            "app.services.auth_service.verify_password",
            AsyncMock(side_effect=[True, False, True, False]),
        ),
        patch("app.services.auth_service.validate_password_hibp", AsyncMock()),
        patch(
            "app.services.auth_service.get_password_hash",
            AsyncMock(return_value=expected_hash),
        ),
    ):
        with patch(
            "app.services.auth.redis_session.RedisSessionService.revoke_session",
            AsyncMock(side_effect=OSError("Redis unavailable")),
        ):
            with pytest.raises(OSError, match="Redis unavailable"):
                await service.change_password(test_user, payload, request)
        await db_session.refresh(test_user)
        await db_session.refresh(sibling)
        assert test_user.hashed_password == old_password
        assert sibling.revoked_at is None
        assert await mock_global_redis.exists("revoked:jti:retry-sibling") == 0
        assert await service.change_password(test_user, payload, request) == (True, 1)

    assert await mock_global_redis.exists("revoked:jti:retry-sibling") == 1
    assert test_user.hashed_password == expected_hash
    assert sibling.revoked_at is not None


@pytest.mark.asyncio
async def test_security_tombstones_are_required_even_without_session_cache(
    mock_global_redis,
):
    from app.auth.mfa.lifecycle import (
        MfaSessionRevocation,
        publish_mfa_session_revocations,
    )

    with patch(
        "app.services.auth.redis_session.settings",
        SimpleNamespace(cache_redis_url="", access_token_expire_minutes=60),
    ):
        await publish_mfa_session_revocations(
            [
                MfaSessionRevocation(
                    jti="no-cache-session",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            ]
        )
    assert await mock_global_redis.exists("revoked:jti:no-cache-session") == 1


@pytest.mark.asyncio
async def test_real_email_verification_leaves_totp_only_account_step_up_required(
    db_session, test_user
):
    from app.api.deps.auth import require_fresh_mfa
    from app.auth.mfa.email_otp import EmailOtpService
    from app.models import ActiveSession, MfaTotpEnrollment
    from app.services.auth.login_service import LoginService
    from app.services.auth.login_session_manager import LoginSessionManager

    now = datetime.now(UTC)
    stale = now - timedelta(days=1)
    test_user.email_verified_at = None
    test_user.email_mfa_enabled_at = None
    test_user.mfa_required = True
    test_user.mfa_default_method = "totp"
    enrollment = MfaTotpEnrollment(
        user_id=test_user.id,
        secret=pyotp.random_base32(),
        is_active=True,
        confirmed_at=stale,
    )
    session = ActiveSession(
        user_id=test_user.id,
        jti="mailbox-only",
        expires_at=now + timedelta(hours=1),
        mfa_verified_at=stale,
        mfa_method="totp",
    )
    db_session.add_all([enrollment, session])
    await db_session.flush()
    otp_service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=SimpleNamespace(enforce=AsyncMock()),
    )
    issued = await otp_service.issue(
        db_session,
        user_id=test_user.id,
        expected_mfa_epoch=int(test_user.mfa_epoch or 0),
        flow="email_verification",
        session_identifier=str(session.id),
        client_fingerprint="f" * 64,
        client_ip="203.0.113.8",
        locale="en",
    )
    await db_session.commit()
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = session
    coordinator = MagicMock()
    coordinator.get_email_otp_service.return_value = otp_service
    manager = LoginSessionManager(MagicMock(), AsyncMock(), MagicMock(), MagicMock())
    service = LoginService(MagicMock(), coordinator, manager, db_session)

    with (
        patch.object(
            login_api, "_load_optional_active_session", AsyncMock(return_value=session)
        ),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.8"),
    ):
        result = await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method="email_otp",
                challenge_token=issued.challenge_token,
                code=issued.otp,
            ),
            Response(),
            request,
            MagicMock(),
            service,
            db_session,
        )
    assert result.access_token is None
    assert test_user.email_verified_at is not None
    assert test_user.email_mfa_enabled_at is None
    assert session.mfa_verified_at == stale
    with pytest.raises(HTTPException) as error:
        await require_fresh_mfa.__dishka_orig_func__(request, test_user, db_session)
    assert error.value.status_code == 428


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["redis", "commit"])
async def test_email_factor_enablement_rolls_back_and_can_retry_after_publish_failure(
    db_session, test_user, mock_global_redis, failure
):
    from app.auth.mfa.email_otp import EmailOtpService
    from app.models import ActiveSession, MfaChallenge
    from app.models.auth import ChallengeState
    from app.services.auth.login_service import LoginService
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.auth.redis_session import RedisSessionService

    now = datetime.now(UTC)
    original_epoch = test_user.mfa_epoch
    test_user.email_verified_at = now
    test_user.email_mfa_enabled_at = None
    current = ActiveSession(
        user_id=test_user.id,
        jti="factor-current",
        expires_at=now + timedelta(hours=1),
        mfa_epoch=original_epoch,
    )
    sibling = ActiveSession(
        user_id=test_user.id,
        jti="factor-sibling",
        expires_at=now + timedelta(hours=1),
        mfa_epoch=original_epoch,
    )
    db_session.add_all([current, sibling])
    await db_session.flush()
    otp_service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=SimpleNamespace(enforce=AsyncMock()),
    )
    issued = await otp_service.issue(
        db_session,
        user_id=test_user.id,
        expected_mfa_epoch=original_epoch,
        flow="email_mfa_enablement",
        session_identifier=str(current.id),
        client_fingerprint="f" * 64,
        client_ip="203.0.113.8",
        locale="en",
    )
    await db_session.commit()
    redis_session = RedisSessionService(redis_url="redis://localhost:6379/0")
    await redis_session.create_session(
        current.jti,
        test_user.id,
        fingerprint=None,
        mfa_verified_at=None,
        session_id=current.id,
        mfa_epoch=original_epoch,
    )
    cached_before = await redis_session.get_session(current.jti)
    assert cached_before is not None
    coordinator = MagicMock()
    coordinator.get_email_otp_service.return_value = otp_service
    manager = LoginSessionManager(MagicMock(), redis_session, MagicMock(), MagicMock())
    service = LoginService(MagicMock(), coordinator, manager, db_session)
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = current
    payload = MfaVerifyIn(
        method="email_otp", challenge_token=issued.challenge_token, code=issued.otp
    )
    fail_publication = (
        patch(
            "app.services.auth.redis_session.get_revocation_redis_client",
            AsyncMock(side_effect=OSError("revocation store unavailable")),
        )
        if failure == "redis"
        else patch.object(
            db_session, "commit", AsyncMock(side_effect=OSError("commit unavailable"))
        )
    )

    with (
        patch.object(
            login_api, "_load_optional_active_session", AsyncMock(return_value=current)
        ),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.8"),
    ):
        with fail_publication, pytest.raises(OSError, match="unavailable"):
            await login_api.verify_mfa_challenge.__dishka_orig_func__(
                payload, Response(), request, MagicMock(), service, db_session
            )

        await db_session.refresh(test_user)
        await db_session.refresh(current)
        await db_session.refresh(sibling)
        challenge = await db_session.get(MfaChallenge, issued.challenge_id)
        assert challenge.state == ChallengeState.PENDING
        assert challenge.consumed_at is None
        assert test_user.email_mfa_enabled_at is None
        assert test_user.mfa_epoch == original_epoch
        assert current.mfa_verified_at is None
        assert current.mfa_epoch == original_epoch
        assert sibling.revoked_at is None
        assert await redis_session.get_session(current.jti) == cached_before
        assert not getattr(request.state, "rotate_csrf", False)
        # A committed tombstone must survive a later database rollback.
        assert await mock_global_redis.exists("revoked:jti:factor-sibling") == (
            1 if failure == "commit" else 0
        )

        result = await login_api.verify_mfa_challenge.__dishka_orig_func__(
            payload, Response(), request, MagicMock(), service, db_session
        )

    await db_session.refresh(challenge)
    assert result.access_token is None
    assert challenge.state == ChallengeState.CONSUMED
    assert test_user.email_mfa_enabled_at is not None
    assert test_user.mfa_epoch == original_epoch + 1
    assert current.mfa_verified_at is not None
    assert current.mfa_epoch == original_epoch + 1
    assert sibling.revoked_at is not None
    assert await mock_global_redis.exists("revoked:jti:factor-sibling") == 1
    cached_after = await redis_session.get_session(current.jti)
    assert cached_after["mfa_verified_at"] is not None
    assert cached_after["mfa_epoch"] == original_epoch + 1
    assert request.state.rotate_csrf is True
