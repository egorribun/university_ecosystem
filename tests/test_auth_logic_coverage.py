from datetime import UTC, datetime, timedelta
from unittest.mock import PropertyMock, patch
from uuid import uuid4

import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.models as models
from app.auth import mfa
from app.auth.constants import (
    CHALLENGE_TYPE_TOTP_VERIFY,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.totp import _ct_verify_totp

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(autouse=True)
def _bind_direct_challenge_issuance(monkeypatch: pytest.MonkeyPatch):
    original_issue = mfa.issue_challenge
    original_verify = mfa.verify_totp_for_user
    original_consume = mfa.consume_challenge

    async def issue_bound(*args, **kwargs):
        kwargs.setdefault("flow", "login")
        kwargs.setdefault("session_identifier", "test-bound-session")
        kwargs.setdefault("client_fingerprint", "f" * 64)
        return await original_issue(*args, **kwargs)

    async def verify_bound(*args, **kwargs):
        kwargs.setdefault("client_fingerprint", "f" * 64)
        kwargs.setdefault("login_session_identifier", "test-bound-session")
        return await original_verify(*args, **kwargs)

    async def consume_bound(*args, **kwargs):
        kwargs.setdefault("client_fingerprint", "f" * 64)
        kwargs.setdefault("login_session_identifier", "test-bound-session")
        return await original_consume(*args, **kwargs)

    monkeypatch.setattr(mfa, "issue_challenge", issue_bound)
    monkeypatch.setattr(mfa, "verify_totp_for_user", verify_bound)
    monkeypatch.setattr(mfa, "consume_challenge", consume_bound)


async def test_mfa_check_helpers(db_session, user_factory):
    from sqlalchemy.orm import selectinload

    user = await user_factory()

    # Load MFA relationships for the sync helper
    result = await db_session.execute(
        select(models.User)
        .where(models.User.id == user.id)
        .options(selectinload(models.User.totp_enrollments))
    )
    user = result.scalars().first()

    # Initially no MFA
    assert await mfa.has_totp_enabled(db_session, user) is False
    assert await mfa.user_has_active_factor(db_session, user) is False
    assert mfa.user_has_confirmed_interactive_factor(user) is False

    # Add unconfirmed TOTP
    secret = pyotp.random_base32()
    enrollment = models.MfaTotpEnrollment(user=user, secret=secret, is_active=False)
    db_session.add(enrollment)
    await db_session.commit()

    # Re-load user with totp_enrollments eagerly loaded
    result = await db_session.execute(
        select(models.User)
        .where(models.User.id == user.id)
        .options(selectinload(models.User.totp_enrollments))
    )
    user = result.scalars().first()

    assert (
        await mfa.user_has_active_factor(db_session, user) is False
    )  # is_active=False

    # Activate enrollment
    enrollment_result = await db_session.execute(
        select(models.MfaTotpEnrollment).where(
            models.MfaTotpEnrollment.user_id == user.id
        )
    )
    enrollment = enrollment_result.scalars().first()
    enrollment.is_active = True
    await db_session.commit()

    # Re-load user with relationships
    result = await db_session.execute(
        select(models.User)
        .where(models.User.id == user.id)
        .options(selectinload(models.User.totp_enrollments))
    )
    user = result.scalars().first()
    assert await mfa.user_has_active_factor(db_session, user) is True
    assert mfa.user_has_confirmed_interactive_factor(user) is False  # not confirmed_at

    # Confirm TOTP
    enrollment_result = await db_session.execute(
        select(models.MfaTotpEnrollment).where(
            models.MfaTotpEnrollment.user_id == user.id
        )
    )
    enrollment = enrollment_result.scalars().first()
    enrollment.confirmed_at = datetime.now(UTC)
    await db_session.commit()

    # Re-load user with relationships
    result = await db_session.execute(
        select(models.User)
        .where(models.User.id == user.id)
        .options(selectinload(models.User.totp_enrollments))
    )
    user = result.scalars().first()
    assert await mfa.has_totp_enabled(db_session, user) is True
    assert mfa.user_has_confirmed_interactive_factor(user) is True


async def test_issue_and_get_challenge(db_session, test_user):
    challenge = await mfa.issue_challenge(
        db_session,
        user_id=test_user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        ttl_seconds=300,
    )
    assert challenge.challenge_token
    assert challenge.challenge.challenge_type == CHALLENGE_TYPE_TOTP_VERIFY

    retrieved = await mfa.get_challenge(
        db_session,
        token=challenge.challenge_token,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        user_id=test_user.id,
    )
    assert retrieved.id == challenge.id

    # Test expired challenge
    challenge.challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await mfa.get_challenge(
            db_session,
            token=challenge.challenge_token,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        )
    assert exc.value.status_code == 400


async def test_totp_enrollment_flow(db_session, user_factory):
    user = await user_factory()

    # Start enrollment
    enrollment, secret, uri = await mfa.start_totp_enrollment(db_session, user=user)
    assert secret is not None
    assert "otpauth://" in uri
    assert enrollment.confirmed_at is None

    # Try to start another (should fail)
    with pytest.raises(HTTPException) as exc:
        await mfa.start_totp_enrollment(db_session, user=user)
    assert exc.value.status_code == 400

    # Reuse existing
    enrollment2, _secret2, _uri2 = await mfa.start_totp_enrollment(
        db_session, user=user, reuse_existing=True
    )
    assert enrollment2.id == enrollment.id

    # Complete with wrong code
    with pytest.raises(HTTPException) as exc:
        await mfa.complete_totp_enrollment(
            db_session, enrollment=enrollment, code="000000"
        )
    assert exc.value.status_code == 400

    # Complete with right code
    import pyotp

    totp = pyotp.TOTP(secret)
    code = totp.now()
    await mfa.complete_totp_enrollment(db_session, enrollment=enrollment, code=code)
    assert enrollment.confirmed_at is not None
    assert enrollment.is_active is True


async def test_recovery_codes_flow(db_session, test_user):
    # Generate codes
    codes = await mfa.generate_recovery_codes(
        db_session,
        user=test_user,
        fresh_mfa_verified_at=datetime.now(UTC),
    )
    assert len(codes) == 10
    assert await mfa.count_remaining_recovery_codes(db_session, user=test_user) == 10

    # Verify valid code
    first_code = codes[0]
    is_valid = await mfa.verify_recovery_code(
        db_session, user=test_user, code=first_code
    )
    assert is_valid is True
    assert await mfa.count_remaining_recovery_codes(db_session, user=test_user) == 9

    # Verify same code again (should fail)
    is_valid_again = await mfa.verify_recovery_code(
        db_session, user=test_user, code=first_code
    )
    assert is_valid_again is False

    # Verify invalid code
    assert (
        await mfa.verify_recovery_code(db_session, user=test_user, code="INVALID-CODE")
        is False
    )


async def test_consume_challenge_totp(db_session, user_factory):
    user = await user_factory()
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    import pyotp

    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    await db_session.commit()

    challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()

    # Consume with right code
    consumed, _ = await mfa.consume_challenge(
        db_session,
        challenge_token=challenge.challenge_token,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        provided_code=totp.now(),
        provided_method=MFA_METHOD_TOTP,
    )
    assert consumed.consumed_at is not None


async def test_trusted_device_flow(db_session, test_user):
    token, _expires_at = await mfa.create_trusted_device_token(
        db_session,
        user=test_user,
        ip_address="192.0.2.20",
        user_agent="pytest",
    )
    assert token is not None

    is_valid = await mfa.verify_trusted_device_token(
        db_session,
        user=test_user,
        token=token,
        request_ip="192.0.2.20",
        request_ua="pytest",
    )
    assert is_valid is True

    # Invalid token
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=test_user,
            token="invalid",
            request_ip="192.0.2.20",
            request_ua="pytest",
        )
        is False
    )

    # Expired token (manual update)
    res = await db_session.execute(
        select(models.TrustedDevice).where(models.TrustedDevice.user_id == test_user.id)
    )
    device = res.scalars().first()
    device.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=test_user,
            token=token,
            request_ip="192.0.2.20",
            request_ua="pytest",
        )
        is False
    )


async def test_purge_challenges(db_session, test_user):
    c1 = await mfa.issue_challenge(
        db_session, user_id=test_user.id, challenge_type="test"
    )
    c2 = await mfa.issue_challenge(
        db_session, user_id=test_user.id, challenge_type="test"
    )

    c1.challenge.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()

    purged = await mfa.purge_expired_challenges(db_session, grace_period_seconds=0)
    assert purged >= 1

    # c1 should be gone
    res = await db_session.execute(
        select(models.MfaChallenge).where(models.MfaChallenge.id == c1.id)
    )
    assert res.scalars().first() is None
    # c2 should still be there
    res = await db_session.execute(
        select(models.MfaChallenge).where(models.MfaChallenge.id == c2.id)
    )
    assert res.scalars().first() is not None


async def test_reset_and_refresh_mfa(db_session, user_factory):
    user = await user_factory()

    # 1. Enable TOTP
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    import pyotp

    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    await db_session.commit()

    # Refresh should set default method
    pref = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert pref == MFA_METHOD_TOTP
    assert user.mfa_default_method == MFA_METHOD_TOTP
    assert user.mfa_required is True

    # 2. Reset MFA
    stats = await mfa.reset_user_mfa(db_session, user=user)
    assert stats.totp_deleted == 1
    assert user.mfa_required is False
    assert user.mfa_default_method is None


async def test_mfa_reset_with_last_verified(db_session, user_factory):
    user = await user_factory()
    user.mfa_last_verified_at = datetime.now(UTC)
    user.mfa_required = True
    await db_session.commit()

    stats = await mfa.reset_user_mfa(db_session, user=user)
    assert stats.fields_cleared is True
    assert user.mfa_last_verified_at is None


async def test_record_mfa_success_with_session(db_session, user_factory):
    user = await user_factory()
    session = models.ActiveSession(
        user_id=user.id,
        jti="test-jti",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_required=True,
    )
    db_session.add(session)
    await db_session.commit()

    await mfa.record_mfa_success(db_session, user=user, session=session, method="totp")
    assert user.mfa_last_verified_at is not None
    assert session.mfa_completed_at is not None
    assert session.mfa_required is False
    assert session.mfa_method == "totp"


async def test_trusted_device_edge_cases(db_session, test_user):
    # Empty token
    assert (
        await mfa.verify_trusted_device_token(db_session, user=test_user, token="")
        is False
    )

    # Token hashing exception (unlikely but covered)
    with patch(
        "app.auth.mfa.trusted_device._base64url_encode", side_effect=Exception("fail")
    ):
        assert (
            await mfa.verify_trusted_device_token(
                db_session, user=test_user, token="any"
            )
            is False
        )

    # IP and UA mismatch
    token, _ = await mfa.create_trusted_device_token(
        db_session,
        user=test_user,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )
    # Verify with wrong IP
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=test_user,
            token=token,
            request_ip="192.168.1.2",
            request_ua="Mozilla/5.0",
        )
        is False
    )
    # A mismatch invalidates the token. Issue a fresh token for each probe.
    token, _ = await mfa.create_trusted_device_token(
        db_session,
        user=test_user,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )
    # Verify with wrong UA
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=test_user,
            token=token,
            request_ip="192.168.1.1",
            request_ua="Firefox/5.0",
        )
        is False
    )
    token, _ = await mfa.create_trusted_device_token(
        db_session,
        user=test_user,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )
    # Verify with correct IP and correct UA
    assert (
        await mfa.verify_trusted_device_token(
            db_session,
            user=test_user,
            token=token,
            request_ip="192.168.1.1",
            request_ua="Mozilla/5.0",
        )
        is True
    )


async def test_refresh_preferences_edge_cases(db_session, user_factory):
    user = await user_factory()

    # No factors -> None
    pref = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert pref is None
    assert user.mfa_required is False


async def test_disable_totp(db_session, user_factory):
    user = await user_factory()
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    import pyotp

    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    await db_session.commit()

    # Disable specific enrollment
    count, pending = await mfa.disable_totp(
        db_session, user=user, enrollment_id=enrollment.id
    )
    assert count == 1
    assert pending == []
    assert enrollment.is_active is False
    assert enrollment.revoked_at is not None

    # Disable all (none active now)
    count2, pending2 = await mfa.disable_totp(db_session, user=user)
    assert count2 == 0
    assert pending2 == []


async def test_start_totp_verification(db_session, test_user):
    challenge = await mfa.start_totp_verification(
        db_session,
        user=test_user,
        flow="login",
        session_identifier="start-totp-session",
        client_fingerprint="f" * 64,
    )
    assert challenge.challenge.challenge_type == CHALLENGE_TYPE_TOTP_VERIFY


async def test_verify_totp_for_user_edge_cases(db_session, user_factory):
    user = await user_factory()
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    import pyotp

    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    await db_session.commit()

    # Success — RZ-W8-05: always provide a challenge to exercise replay protection
    challenge_for_success = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    res_enr, res_chal = await mfa.verify_totp_for_user(
        db_session,
        user=user,
        code=totp.now(),
        challenge_token=challenge_for_success.challenge_token,
    )
    assert res_enr.id == enrollment.id

    # No challenge provided — should raise ValueError (RZ-W8-05 enforcement)
    with pytest.raises(ValueError, match="challenge_token is required"):
        await mfa.verify_totp_for_user(db_session, user=user, code=totp.now())

    # Invalid code — must also provide a challenge
    challenge_for_invalid = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    with pytest.raises(HTTPException):  # raise_validation_error raises HTTPException
        await mfa.verify_totp_for_user(
            db_session,
            user=user,
            code="000000",
            challenge_token=challenge_for_invalid.challenge_token,
        )

    # With challenge token — clear last_used_code_hash to avoid replay
    # rejection, then use totp.now() (always valid in current window).
    enrollment.last_used_code_hash = None
    enrollment.last_used_timecode = None
    await db_session.commit()

    challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    res_enr, res_chal = await mfa.verify_totp_for_user(
        db_session,
        user=user,
        code=totp.now(),
        challenge_token=challenge.challenge_token,
    )
    assert res_chal.id == challenge.id
    assert res_chal.consumed_at is not None

    # Invalid challenge type
    bad_challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type="wrong"
    )
    await db_session.commit()
    with pytest.raises(HTTPException):
        await mfa.verify_totp_for_user(
            db_session,
            user=user,
            code=totp.now(),
            challenge_token=bad_challenge.challenge_token,
        )

    # Session ID mismatch
    sid1 = uuid4()
    sid2 = uuid4()

    # Create session for FK constraint
    session_obj = models.ActiveSession(
        id=sid1,
        user_id=user.id,
        jti="jti-sid1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session_obj)
    await db_session.commit()

    chal_with_sid = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        session_id=sid1,
    )
    await db_session.commit()
    with pytest.raises(HTTPException):
        await mfa.verify_totp_for_user(
            db_session,
            user=user,
            code=totp.now(),
            challenge_token=chal_with_sid.challenge_token,
            session_id=sid2,
        )


async def test_mfa_db_fallbacks(db_session, user_factory):
    from unittest.mock import MagicMock

    user = MagicMock(spec=models.User)
    user.id = uuid4()
    # Mock getattr to return None for relationships to trigger DB fallbacks
    user.totp_enrollments = None

    assert await mfa.has_totp_enabled(db_session, user) is False
    assert await mfa.user_has_active_factor(db_session, user) is False


async def test_base64_and_totp_edge_cases(db_session):
    # Padding in decode
    data = "YW55IGNhcm5hbCBwbGVhc3VyZS4"  # base64url without padding
    decoded = mfa._base64url_decode(data)
    assert decoded == b"any carnal pleasure."

    # TOTP length mismatch
    assert mfa.verify_totp("JBSWY3DPEHPK3PXP", "123") is False


async def test_enrollment_secret_none(db_session, user_factory):
    user = await user_factory()
    # secret cannot be None in DB (nullable=False), so we use a dummy one
    # and mock the property to return None.
    enrollment = models.MfaTotpEnrollment(
        user_id=user.id, secret="DUMMY", is_active=True, confirmed_at=datetime.now(UTC)
    )
    db_session.add(enrollment)
    await db_session.commit()

    with patch("app.auth.mfa.verify_totp", return_value=True):
        # We need to simulate enrollment.secret being None during runtime
        with patch.object(
            models.MfaTotpEnrollment, "secret", new_callable=PropertyMock
        ) as mock_secret:
            mock_secret.return_value = None

            # complete_totp_enrollment failure
            with pytest.raises(HTTPException):
                await mfa.complete_totp_enrollment(
                    db_session, enrollment=enrollment, code="123456"
                )

            # verify_totp_for_user skipping — also enforce challenge requirement (RZ-W8-05)
            with pytest.raises(ValueError, match="challenge_token is required"):
                await mfa.verify_totp_for_user(db_session, user=user, code="123456")


async def test_legacy_enrollment_check(db_session, user_factory):
    user = await user_factory()
    user.mfa_default_method = "totp"
    # Active and confirmed enrollment (MED-W19 removed legacy unconfirmed fallback)
    enrollment = models.MfaTotpEnrollment(
        user_id=user.id,
        secret="JBSWY3DPEHPK3PXP",  # pragma: allowlist secret
        is_active=True,
        confirmed_at=datetime.now(UTC),
    )
    db_session.add(enrollment)
    await db_session.commit()
    await db_session.refresh(user)

    import pyotp

    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    # RZ-W8-05: always provide a challenge token
    legacy_challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    res_enr, _ = await mfa.verify_totp_for_user(
        db_session,
        user=user,
        code=totp.now(),
        challenge_token=legacy_challenge.challenge_token,
    )
    assert res_enr.id == enrollment.id


async def test_refresh_preferences_disable_required(db_session, user_factory):
    user = await user_factory()
    user.mfa_required = True
    await db_session.commit()

    # No factors, mfa_required=True -> should set mfa_required=False
    pref = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert pref is None
    assert user.mfa_required is False


# ── TOTP.PY ADDITIONAL COVERAGE TESTS ────────────────────────────────────────


async def test_totp_invalid_digits_length():
    # 12345 (5 digits) is invalid length
    assert _ct_verify_totp("JBSWY3DPEHPK3PXP", "12345") is False
    # 1234567 (7 digits) is invalid length
    assert _ct_verify_totp("JBSWY3DPEHPK3PXP", "1234567") is False


async def test_start_totp_enrollment_limit_reached(db_session, user_factory):
    user = await user_factory()
    # Populate the max active enrollments limit (3 active)
    for i in range(3):
        enrollment = models.MfaTotpEnrollment(
            user_id=user.id,
            secret=f"SECRETKEY{i}DPEHPK",
            is_active=True,
            confirmed_at=datetime.now(UTC),
        )
        db_session.add(enrollment)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await mfa.start_totp_enrollment(db_session, user=user)
    assert exc_info.value.status_code == 400


async def test_start_totp_enrollment_label_update(db_session, user_factory):
    user = await user_factory()
    # Create a pending enrollment
    enrollment, _secret, _ = await mfa.start_totp_enrollment(
        db_session, user=user, label="Initial Label"
    )

    # Reuse pending enrollment and update label
    enrollment2, _secret2, _ = await mfa.start_totp_enrollment(
        db_session, user=user, label="Updated Label", reuse_existing=True
    )
    assert enrollment2.id == enrollment.id
    assert enrollment2.label == "Updated Label"


async def test_verify_totp_no_enrollments(db_session, user_factory):
    user = await user_factory()
    challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await mfa.verify_totp_for_user(
            db_session,
            user=user,
            code="123456",
            challenge_token=challenge.challenge_token,
            challenge=challenge.challenge,
        )
    assert exc_info.value.status_code == 400


async def test_verify_totp_challenge_validation_mismatches(db_session, user_factory):
    user1 = await user_factory()
    user2 = await user_factory()

    # Create confirmed TOTP enrollment for user1
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user1)
    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    await db_session.commit()

    # 1. Challenge type mismatch
    wrong_type_challenge = await mfa.issue_challenge(
        db_session,
        user_id=user1.id,
        challenge_type="recovery-code",
        flow="login",
        session_identifier="test-session",
        client_fingerprint="f" * 64,
    )
    await db_session.commit()
    with pytest.raises(HTTPException):
        await mfa.verify_totp_for_user(
            db_session,
            user=user1,
            code=totp.now(),
            challenge_token=wrong_type_challenge.challenge_token,
            challenge=wrong_type_challenge.challenge,
        )

    # 2. User ID mismatch
    wrong_user_challenge = await mfa.issue_challenge(
        db_session, user_id=user2.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    with pytest.raises(HTTPException):
        await mfa.verify_totp_for_user(
            db_session,
            user=user1,
            code=totp.now(),
            challenge_token=wrong_user_challenge.challenge_token,
            challenge=wrong_user_challenge.challenge,
        )

    # 3. Session ID mismatch
    import uuid
    from datetime import timedelta

    sess_a = models.ActiveSession(
        user_id=user1.id,
        jti="session-a-jti",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_required=True,
    )
    db_session.add(sess_a)
    await db_session.commit()
    session_challenge = await mfa.issue_challenge(
        db_session,
        user_id=user1.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        session_id=sess_a.id,
    )
    await db_session.commit()
    with pytest.raises(HTTPException):
        await mfa.verify_totp_for_user(
            db_session,
            user=user1,
            code=totp.now(),
            challenge_token=session_challenge.challenge_token,
            challenge=session_challenge.challenge,
            session_id=uuid.uuid4(),
        )


async def test_verify_totp_disappeared_enrollment_and_decryption_failure(
    db_session, user_factory
):
    user = await user_factory()
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()

    # 1. Decryption failure simulation
    with patch(
        "app.models.MfaTotpEnrollment.secret",
        new_callable=PropertyMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await mfa.verify_totp_for_user(
                db_session,
                user=user,
                code=totp.now(),
                challenge_token=challenge.challenge_token,
                challenge=challenge.challenge,
            )
        assert exc_info.value.status_code == 400

    # 2. Disappeared enrollment between initial load and SELECT FOR UPDATE
    from unittest.mock import MagicMock

    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_execute:
        # Mock initial query to return the enrollment, but SELECT FOR UPDATE to return empty result
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.first.return_value = enrollment
        mock_result1.scalars.return_value.__iter__.return_value = [enrollment]

        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.first.return_value = None

        mock_execute.side_effect = [mock_result1, mock_result2]

        with pytest.raises(HTTPException) as exc_info:
            await mfa.verify_totp_for_user(
                db_session,
                user=user,
                code=totp.now(),
                challenge_token=challenge.challenge_token,
                challenge=challenge.challenge,
            )
        assert exc_info.value.status_code == 400


async def test_verify_totp_replay_prevention(db_session, user_factory):
    user = await user_factory()
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    totp = pyotp.TOTP(secret)
    code = totp.now()
    await mfa.complete_totp_enrollment(db_session, enrollment=enrollment, code=code)

    challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()

    # First verification succeeds
    res_enr, _ = await mfa.verify_totp_for_user(
        db_session,
        user=user,
        code=code,
        challenge_token=challenge.challenge_token,
        challenge=challenge.challenge,
    )
    assert res_enr.id == enrollment.id

    # Second verification fails with code_already_used
    challenge2 = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    with pytest.raises(HTTPException) as exc_info:
        await mfa.verify_totp_for_user(
            db_session,
            user=user,
            code=code,
            challenge_token=challenge2.challenge_token,
            challenge=challenge2.challenge,
        )
    assert exc_info.value.status_code == 400


# ── LIFECYCLE.PY ADDITIONAL COVERAGE TESTS ──────────────────────────────────

from app.auth.mfa.lifecycle import (
    MfaResetStats,
    has_totp_enabled,
    reset_user_mfa,
    user_has_active_factor,
    user_has_confirmed_interactive_factor,
)


async def test_mfa_reset_stats_changed_no_changes():
    stats = MfaResetStats()
    assert stats.changed is False


async def test_user_has_confirmed_interactive_factor_relationship_not_loaded(
    db_session, user_factory
):
    user = await user_factory()
    await db_session.commit()

    # Expire totp_enrollments collection specifically to put it in NEVER_SET state
    db_session.expire(user, ["totp_enrollments"])

    with pytest.raises(RuntimeError):
        user_has_confirmed_interactive_factor(user)


async def test_user_has_confirmed_interactive_factor_non_orm():
    # Inspection error fallback
    class DummyUser:
        totp_enrollments = None
        mfa_default_method = None
        email_mfa_enabled_at = None

    dummy = DummyUser()
    assert user_has_confirmed_interactive_factor(dummy) is False


async def test_fallback_to_db_in_mfa_enabled_checks(db_session, user_factory):
    user = await user_factory()

    # 1. Create a confirmed TOTP enrollment in DB
    totp_enrollment = models.MfaTotpEnrollment(
        user_id=user.id,
        secret="JBSWY3DPEHPK3PXP",
        is_active=True,
        confirmed_at=datetime.now(UTC),
    )
    db_session.add(totp_enrollment)

    await db_session.commit()

    # Query user but disconnect relationships to force DB query fallback
    from sqlalchemy import select

    stmt = select(models.User).where(models.User.id == user.id)
    result = await db_session.execute(stmt)
    db_user = result.scalars().first()

    # Delete collections from __dict__ so getattr returns None or lazy load fallback triggers
    db_user.__dict__.pop("totp_enrollments", None)

    # Call methods which should fallback to DB queries and return True
    assert await has_totp_enabled(db_session, db_user) is True
    assert await user_has_active_factor(db_session, db_user) is True


async def test_reset_user_mfa_value_error(db_session):
    with pytest.raises(ValueError):
        await reset_user_mfa(db_session, user=None, user_id=None)


async def test_record_mfa_success_dto(db_session):
    # Dummy DTO class
    from pydantic import BaseModel

    class MockUserDTO(BaseModel):
        mfa_last_verified_at: datetime | None = None

    dto = MockUserDTO()
    res_dto = await mfa.record_mfa_success(
        db_session, user=dto, session=None, method="totp"
    )
    assert res_dto.mfa_last_verified_at is not None
