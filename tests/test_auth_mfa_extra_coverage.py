from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import app.auth.mfa as mfa
from app.auth.constants import (
    CHALLENGE_TYPE_RECOVERY_CODE,
    CHALLENGE_TYPE_TOTP_VERIFY,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.challenge import (
    _enforce_challenge_rate_limit,
    _ensure_challenge_not_locked,
    _extract_attempt_limit,
    _lock_challenge,
    describe_challenge_attempts,
    get_challenge,
)
from app.auth.mfa.challenge import (
    consume_challenge as _consume_challenge_runtime,
)
from app.auth.mfa.lifecycle import (
    has_totp_enabled,
    record_mfa_success,
    reset_user_mfa,
    user_has_active_factor,
    user_has_confirmed_interactive_factor,
)
from app.auth.mfa.totp import (
    _ct_verify_totp,
)
from app.auth.mfa.totp import (
    verify_totp_for_user as _verify_totp_for_user_runtime,
)
from app.core.config import settings
from app.core.ratelimit.exceptions import RateLimitExceeded
from app.models import (
    ActiveSession,
    MfaChallenge,
    MfaTotpEnrollment,
    RecoveryCode,
    User,
)


async def _create_challenge(
    db_session: AsyncSession,
    user: User,
    challenge_type: str = CHALLENGE_TYPE_TOTP_VERIFY,
    session_id=None,
) -> MfaChallenge:
    issued = await mfa.issue_challenge(
        db_session,
        challenge_type=challenge_type,
        user_id=user.id,
        session_id=session_id,
        flow="login",
        session_identifier="mfa-extra-bound-session",
        client_fingerprint="f" * 64,
        method=(
            MFA_METHOD_RECOVERY_CODE
            if challenge_type == CHALLENGE_TYPE_RECOVERY_CODE
            else MFA_METHOD_TOTP
        ),
    )
    await db_session.commit()
    issued.challenge.token = issued.challenge_token
    return issued.challenge


async def verify_totp_for_user(*args, **kwargs):
    kwargs.setdefault("client_fingerprint", "f" * 64)
    kwargs.setdefault("login_session_identifier", "mfa-extra-bound-session")
    return await _verify_totp_for_user_runtime(*args, **kwargs)


async def consume_challenge(*args, **kwargs):
    kwargs.setdefault("client_fingerprint", "f" * 64)
    kwargs.setdefault("login_session_identifier", "mfa-extra-bound-session")
    return await _consume_challenge_runtime(*args, **kwargs)


@pytest.mark.asyncio
async def test_recovery_code_loop_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    import app.auth.security as sec

    h = sec.get_password_hash_sync("A1B2C3D4", validate_policy=False)
    rc1 = RecoveryCode(user_id=user.id, code_hash=h, is_used=False)
    rc2 = RecoveryCode(user_id=user.id, code_hash=h, is_used=False)
    db_session.add(rc1)
    db_session.add(rc2)
    await db_session.commit()

    res = await mfa.verify_recovery_code(db_session, user=user, code="A1B2-C3D4")
    assert res is True


@pytest.mark.asyncio
async def test_trusted_device_extra_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    token, _ = await mfa.create_trusted_device_token(
        db_session, user=user, user_agent="Mozilla/5.0", ip_address="192.168.1.1"
    )
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=user,
            token=token,
            request_ip="192.168.1.1",
            request_ua="Mozilla/5.0",
        )
        is True
    )
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=user,
            token=token,
            request_ip="10.0.0.1",
            request_ua="Mozilla/5.0",
        )
        is False
    )
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=user,
            token=token,
            request_ip="192.168.1.1",
            request_ua="Safari",
        )
        is False
    )
    # Use 123 to trigger exception handler (raises AttributeError on token.encode)
    assert (
        await mfa.verify_trusted_device_token(db_session, user=user, token=123)
    ) is False


def test_ct_verify_totp_length():
    assert _ct_verify_totp("some-secret", "12345") is False


@pytest.mark.asyncio
async def test_totp_enrollment_update_label(db_session: AsyncSession, user_factory):
    user = await user_factory()
    e1, _secret, _ = await mfa.start_totp_enrollment(
        db_session, user=user, label="InitialLabel"
    )
    e2, _, _ = await mfa.start_totp_enrollment(
        db_session, user=user, label="UpdatedLabel", reuse_existing=True
    )
    assert e2.id == e1.id
    assert e2.label == "UpdatedLabel"


@pytest.mark.asyncio
async def test_verify_totp_no_challenge_raises_value_error(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    with pytest.raises(ValueError) as exc:
        await verify_totp_for_user(db_session, user=user, code="123456")
    assert "challenge_token is required" in str(exc.value)


@pytest.mark.asyncio
async def test_verify_totp_skip_enrollment_when_secret_none(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    e1, _secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    c = await _create_challenge(db_session, user)

    with patch(
        "app.models.auth.MfaTotpEnrollment.secret", new_callable=PropertyMock
    ) as mock_secret:
        mock_secret.return_value = None

        with pytest.raises(HTTPException) as exc:
            await verify_totp_for_user(
                db_session, user=user, code="123456", challenge_token=c.token
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_totp_locked_enrollment_none(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    c = await _create_challenge(db_session, user)

    original_execute = db_session.execute

    async def mock_execute(stmt, *args, **kwargs):
        if getattr(stmt, "_for_update_arg", None) is not None:
            res = MagicMock()
            res.scalars.return_value.first.return_value = None
            return res
        return await original_execute(stmt, *args, **kwargs)

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    with patch.object(db_session, "execute", mock_execute):
        with pytest.raises(HTTPException) as exc:
            await verify_totp_for_user(
                db_session, user=user, code=valid_code, challenge_token=c.token
            )
        assert exc.value.status_code == 400
        assert "invalid" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_verify_totp_replay_check(db_session: AsyncSession, user_factory):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    c1 = await _create_challenge(db_session, user)
    c2 = await _create_challenge(db_session, user)

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    await verify_totp_for_user(
        db_session, user=user, code=valid_code, challenge_token=c1.token
    )

    with pytest.raises(HTTPException) as exc:
        await verify_totp_for_user(
            db_session, user=user, code=valid_code, challenge_token=c2.token
        )
    assert "used" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_verify_totp_success_without_challenge(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    c = await _create_challenge(db_session, user)

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    new_code = totp_obj.now()

    res_enroll, res_chal = await verify_totp_for_user(
        db_session,
        user=user,
        code=new_code,
        challenge=None,
        challenge_token=c.token,
    )
    assert res_enroll is not None
    assert res_chal is not None


@pytest.mark.asyncio
async def test_challenge_ensure_not_locked_and_lock():
    await _ensure_challenge_not_locked(
        None, None, method="totp", limit=None, locale="en"
    )


@pytest.mark.asyncio
async def test_user_has_confirmed_interactive_factor_never_set(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    from sqlalchemy.orm.base import NEVER_SET

    user.__dict__["totp_enrollments"] = NEVER_SET

    with pytest.raises(RuntimeError):
        user_has_confirmed_interactive_factor(user)


@pytest.mark.asyncio
async def test_lifecycle_extra_branches(db_session: AsyncSession, user_factory):
    user = await user_factory()
    user.totp_enrollments = [MfaTotpEnrollment(confirmed_at=None)]
    assert await has_totp_enabled(db_session, user) is False

    user.totp_enrollments = []
    e = MfaTotpEnrollment(
        user_id=user.id,
        secret="secret",  # pragma: allowlist secret
        confirmed_at=datetime.now(UTC),
        is_active=True,
    )
    db_session.add(e)
    await db_session.commit()
    assert await has_totp_enabled(db_session, user) is True

    user.totp_enrollments = []
    assert await user_has_active_factor(db_session, user) is True


@pytest.mark.asyncio
async def test_reset_user_mfa_value_error(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await reset_user_mfa(db_session, user=None, user_id=None)


@pytest.mark.asyncio
async def test_record_mfa_success_dto(db_session: AsyncSession, user_factory):
    class MockDTO:
        def __init__(self):
            self.mfa_last_verified_at = None

        def model_copy(self, update):
            for k, v in update.items():
                setattr(self, k, v)
            return self

    dto = MockDTO()
    res = await record_mfa_success(db_session, user=dto, session=None, method="totp")
    assert res.mfa_last_verified_at is not None


# --- 100% COVERAGE POLISHING TESTS ---


@pytest.mark.asyncio
async def test_user_has_confirmed_interactive_factor_exception_swallowing():
    # Pass a non-ORM object (dict) which will raise NoInspectionAvailable during ORM inspection.
    # It should not raise an exception, and return False (since it has no active factors).
    assert user_has_confirmed_interactive_factor({}) is False


@pytest.mark.asyncio
async def test_user_has_confirmed_interactive_factor_empty_lists():
    class DummyUser:
        def __init__(self):
            self.mfa_default_method = None
            self.totp_enrollments = []

    user = DummyUser()
    assert user_has_confirmed_interactive_factor(user) is False

    user.totp_enrollments = [None]
    assert user_has_confirmed_interactive_factor(user) is False


@pytest.mark.asyncio
async def test_verify_totp_no_enrollment(db_session: AsyncSession, user_factory):
    user = await user_factory()
    c = await _create_challenge(db_session, user)
    # No TOTP enrollments exist for this user -> raises 400 errors.mfa.no_enrollment (lines 315-317 covered)
    with pytest.raises(HTTPException) as exc:
        await verify_totp_for_user(
            db_session, user=user, code="123456", challenge_token=c.token
        )
    assert exc.value.status_code == 400
    assert (
        "no_enrollment" in str(exc.value.detail)
        or "enrollment" in str(exc.value.detail).lower()
    )


@pytest.mark.asyncio
async def test_verify_totp_challenge_mock_none(db_session: AsyncSession, user_factory):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    # Mock get_challenge to return None -> triggers 328->347 and 423->432 (loaded_challenge is None branches)
    with patch("app.auth.mfa.totp.get_challenge", return_value=None):
        res_enroll, res_chal = await verify_totp_for_user(
            db_session,
            user=user,
            code=valid_code,
            challenge=None,
            challenge_token="some-token",
        )
        assert res_enroll is not None
        assert res_chal is None


@pytest.mark.asyncio
async def test_verify_totp_challenge_type_mismatch(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    # Create challenge with mismatched type CHALLENGE_TYPE_RECOVERY_CODE
    c = await _create_challenge(
        db_session, user, challenge_type=CHALLENGE_TYPE_RECOVERY_CODE
    )

    # Should raise invalid_challenge (lines 330-332 covered)
    with pytest.raises(HTTPException) as exc:
        await verify_totp_for_user(
            db_session, user=user, code=valid_code, challenge=c, challenge_token=None
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_totp_challenge_user_mismatch(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    other_user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    # Create challenge for other_user
    c = await _create_challenge(db_session, other_user)

    # Should raise invalid_challenge (lines 335-338 covered)
    with pytest.raises(HTTPException) as exc:
        await verify_totp_for_user(
            db_session, user=user, code=valid_code, challenge=c, challenge_token=None
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_totp_challenge_session_mismatch(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    # Create challenge with a session ID
    from app.models import ActiveSession

    sess = ActiveSession(
        id=uuid4(),
        user_id=user.id,
        jti=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(sess)
    await db_session.commit()

    c = await _create_challenge(db_session, user, session_id=sess.id)

    # Should raise invalid_challenge when we provide a mismatched session_id (lines 341-344 covered)
    with pytest.raises(HTTPException) as exc:
        await verify_totp_for_user(
            db_session,
            user=user,
            code=valid_code,
            challenge=c,
            challenge_token=None,
            session_id=uuid4(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_challenge_unreachable_value_error(db_session: AsyncSession):
    # Mock raise_http_error to do nothing, letting get_challenge reach the unreachable raise ValueError("Invalid challenge") (line 327 covered)
    with patch("app.auth.mfa.challenge.raise_http_error"):
        with pytest.raises(ValueError) as exc:
            await get_challenge(
                db_session, token="nonexistent-token", challenge_type="totp"
            )
        assert "Invalid challenge" in str(exc.value)


@pytest.mark.asyncio
async def test_consume_challenge_revoked_session(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    # Create active session that is revoked
    sess = ActiveSession(
        id=uuid4(),
        user_id=user.id,
        jti=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(sess)
    await db_session.commit()

    # Create challenge associated with the revoked session
    c = await _create_challenge(db_session, user, session_id=sess.id)

    # Should raise HTTPException for revoked session (lines 386-393 covered)
    with pytest.raises(HTTPException) as exc:
        await consume_challenge(
            db_session,
            challenge_token=c.token,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
            provided_method=MFA_METHOD_TOTP,
            provided_code="123456",
        )
    assert exc.value.status_code == 400
    assert "revoked" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_challenge_rate_limiting_disabled(db_session: AsyncSession):
    # Verify line 59: return early if limit == 0 or window == 0
    with patch.object(settings, "mfa_challenge_max_attempts", 0):
        # Should return None without raising RateLimitExceeded or executing rate limits
        await _enforce_challenge_rate_limit(user_id=uuid4(), challenge_type="totp")


@pytest.mark.asyncio
async def test_challenge_rate_limiting_exceeded():
    # Mock enforce_rate_limit to raise RateLimitExceeded -> raises HTTPException (lines 69-70 covered)
    with patch(
        "app.auth.mfa.challenge.enforce_rate_limit",
        side_effect=RateLimitExceeded(info=MagicMock()),
    ):
        with patch.object(settings, "mfa_challenge_max_attempts", 5):
            with patch.object(settings, "mfa_challenge_ttl_seconds", 300):
                with pytest.raises(HTTPException) as exc:
                    await _enforce_challenge_rate_limit(
                        user_id=uuid4(), challenge_type="totp"
                    )
                assert exc.value.status_code == 429


def test_extract_attempt_limit_none():
    # Verify resolved to None due to invalid type (TypeError or ValueError) (line 90-91 covered)
    c = MagicMock()
    c.payload = {"attempt_limit": "invalid-limit-type"}
    assert _extract_attempt_limit(c) is None

    # Verify resolution to None due to unresolved limit <= 0 (line 92-93 covered)
    c.payload = {"attempt_limit": -5}
    assert _extract_attempt_limit(c) is None


def test_describe_challenge_attempts_no_limit():
    c = MagicMock()
    c.attempt_count = 3
    c.payload = None
    # No limit configured -> returns (attempts, None, None) (line 105->107 false branch covered)
    attempts, limit, remaining = describe_challenge_attempts(c, default_limit=None)
    assert attempts == 3
    assert limit is None
    assert remaining is None


@pytest.mark.asyncio
async def test_lock_challenge_direct(db_session: AsyncSession, user_factory):
    user = await user_factory()
    c = await _create_challenge(db_session, user)
    # Direct lock call (lines 119-135 covered)
    with pytest.raises(HTTPException) as exc:
        await _lock_challenge(
            db_session, challenge=c, method="totp", limit=5, locale="en"
        )
    assert exc.value.status_code == 429
    assert c.consumed_at is not None


@pytest.mark.asyncio
async def test_ensure_challenge_not_locked_trigger(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    c = await _create_challenge(db_session, user)
    c.attempt_count = 5
    await db_session.commit()

    # Trigger lock (line 151 covered)
    with pytest.raises(HTTPException) as exc:
        await _ensure_challenge_not_locked(
            db_session, challenge=c, method="totp", limit=5, locale="en"
        )
    assert exc.value.status_code == 429
    assert c.consumed_at is not None


@pytest.mark.asyncio
async def test_register_failed_attempt_none(db_session: AsyncSession):
    from app.auth.mfa.challenge import _register_failed_attempt

    # Verify line 178: returns None early if challenge is None
    res = await _register_failed_attempt(
        db_session, None, method="totp", limit=5, locale="en"
    )
    assert res is None


@pytest.mark.asyncio
async def test_consume_challenge_valid_active_session(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    e1, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    e1.confirmed_at = datetime.now(UTC)
    e1.is_active = True
    await db_session.commit()

    # Create active session that is valid (not revoked)
    sess = ActiveSession(
        id=uuid4(),
        user_id=user.id,
        jti=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_at=None,
    )
    db_session.add(sess)
    await db_session.commit()

    c = await _create_challenge(db_session, user, session_id=sess.id)

    import pyotp

    totp_obj = pyotp.TOTP(secret)
    valid_code = totp_obj.now()

    # Verify consume challenge succeeds and handles valid session correctly (branches 386->393 covered)
    chal, mfa_sess = await consume_challenge(
        db_session,
        challenge_token=c.token,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        provided_method=MFA_METHOD_TOTP,
        provided_code=valid_code,
    )
    assert chal.consumed_at is not None
    assert mfa_sess is not None
    assert mfa_sess.id == sess.id
