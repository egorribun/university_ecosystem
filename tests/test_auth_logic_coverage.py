from datetime import UTC, datetime, timedelta
from unittest.mock import PropertyMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import mfa
from app.auth.constants import (
    CHALLENGE_TYPE_TOTP_VERIFY,
    MFA_METHOD_TOTP,
)
from app.models import models

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_mfa_check_helpers(db_session, user_factory):
    user = await user_factory()

    # Initially no MFA
    assert await mfa.has_totp_enabled(db_session, user) is False
    assert await mfa.has_webauthn_enabled(db_session, user) is False
    assert await mfa.user_has_active_factor(db_session, user) is False
    assert mfa.user_has_confirmed_interactive_factor(user) is False

    # Add unconfirmed TOTP
    enrollment = models.MfaTotpEnrollment(
        user_id=user.id, secret="JBSWY3DPEHPK3PXP", is_active=False
    )
    db_session.add(enrollment)
    await db_session.commit()
    await db_session.refresh(user, attribute_names=["totp_enrollments"])

    assert (
        await mfa.user_has_active_factor(db_session, user) is False
    )  # is_active=False
    enrollment.is_active = True
    await db_session.commit()
    await db_session.refresh(user, attribute_names=["totp_enrollments"])
    assert await mfa.user_has_active_factor(db_session, user) is True
    assert mfa.user_has_confirmed_interactive_factor(user) is False  # not confirmed_at

    # Confirm TOTP
    enrollment.confirmed_at = datetime.now(UTC)
    await db_session.commit()
    await db_session.refresh(user, attribute_names=["totp_enrollments"])
    assert await mfa.has_totp_enabled(db_session, user) is True
    assert mfa.user_has_confirmed_interactive_factor(user) is True


async def test_issue_and_get_challenge(db_session, test_user):
    challenge = await mfa.issue_challenge(
        db_session,
        user_id=test_user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        ttl_seconds=300,
    )
    assert challenge.token is not None
    assert challenge.challenge_type == CHALLENGE_TYPE_TOTP_VERIFY

    retrieved = await mfa.get_challenge(
        db_session,
        token=challenge.token,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        user_id=test_user.id,
    )
    assert retrieved.id == challenge.id

    # Test expired challenge
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await mfa.get_challenge(
            db_session, token=challenge.token, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
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
    enrollment2, secret2, uri2 = await mfa.start_totp_enrollment(
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
    codes = await mfa.generate_recovery_codes(db_session, user=test_user)
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
        challenge_token=challenge.token,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        provided_code=totp.now(),
        provided_method=MFA_METHOD_TOTP,
    )
    assert consumed.consumed_at is not None


async def test_trusted_device_flow(db_session, test_user):
    token, expires_at = await mfa.create_trusted_device_token(
        db_session, user=test_user
    )
    assert token is not None

    is_valid = await mfa.verify_trusted_device_token(
        db_session, user=test_user, token=token
    )
    assert is_valid is True

    # Invalid token
    assert (
        await mfa.verify_trusted_device_token(
            db_session, user=test_user, token="invalid"
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
        await mfa.verify_trusted_device_token(db_session, user=test_user, token=token)
        is False
    )


async def test_purge_challenges(db_session, test_user):
    c1 = await mfa.issue_challenge(
        db_session, user_id=test_user.id, challenge_type="test"
    )
    c2 = await mfa.issue_challenge(
        db_session, user_id=test_user.id, challenge_type="test"
    )

    c1.expires_at = datetime.now(UTC) - timedelta(hours=1)
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
    with patch("app.auth.mfa._base64url_encode", side_effect=Exception("fail")):
        assert (
            await mfa.verify_trusted_device_token(
                db_session, user=test_user, token="any"
            )
            is False
        )


async def test_refresh_preferences_edge_cases(db_session, user_factory):
    user = await user_factory()

    # No factors -> None
    pref = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert pref is None
    assert user.mfa_required is False

    # Mock WebAuthn available
    from app.models.models import WebAuthnCredential

    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=b"cid",
        public_key=b"pk",
        sign_count=0,
    )
    db_session.add(cred)
    await db_session.commit()
    await db_session.refresh(user)

    pref = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert pref == "webauthn"
    assert user.mfa_required is True


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
    count = await mfa.disable_totp(db_session, user=user, enrollment_id=enrollment.id)
    assert count == 1
    assert enrollment.is_active is False
    assert enrollment.revoked_at is not None

    # Disable all (none active now)
    count2 = await mfa.disable_totp(db_session, user=user)
    assert count2 == 0


async def test_start_totp_verification(db_session, test_user):
    challenge = await mfa.start_totp_verification(db_session, user=test_user)
    assert challenge.challenge_type == CHALLENGE_TYPE_TOTP_VERIFY


async def test_verify_totp_for_user_edge_cases(db_session, user_factory):
    user = await user_factory()
    enrollment, secret, _ = await mfa.start_totp_enrollment(db_session, user=user)
    import pyotp

    totp = pyotp.TOTP(secret)
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=totp.now()
    )
    await db_session.commit()

    # Success
    res_enr, res_chal = await mfa.verify_totp_for_user(
        db_session, user=user, code=totp.now()
    )
    assert res_enr.id == enrollment.id

    # Invalid code
    with pytest.raises(Exception):  # raise_validation_error raises HTTPException
        await mfa.verify_totp_for_user(db_session, user=user, code="000000")

    # With challenge token
    challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type=CHALLENGE_TYPE_TOTP_VERIFY
    )
    await db_session.commit()
    res_enr, res_chal = await mfa.verify_totp_for_user(
        db_session, user=user, code=totp.now(), challenge_token=challenge.token
    )
    assert res_chal.id == challenge.id
    assert res_chal.consumed_at is not None

    # Invalid challenge type
    bad_challenge = await mfa.issue_challenge(
        db_session, user_id=user.id, challenge_type="wrong"
    )
    await db_session.commit()
    with pytest.raises(Exception):
        await mfa.verify_totp_for_user(
            db_session, user=user, code=totp.now(), challenge_token=bad_challenge.token
        )

    # Session ID mismatch
    sid1 = uuid4()
    sid2 = uuid4()
    chal_with_sid = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        session_id=sid1,
    )
    await db_session.commit()
    with pytest.raises(Exception):
        await mfa.verify_totp_for_user(
            db_session,
            user=user,
            code=totp.now(),
            challenge_token=chal_with_sid.token,
            session_id=sid2,
        )


async def test_mfa_db_fallbacks(db_session, user_factory):
    from unittest.mock import MagicMock

    user = MagicMock(spec=models.User)
    user.id = uuid4()
    # Mock getattr to return None for relationships to trigger DB fallbacks
    user.totp_enrollments = None
    user.webauthn_credentials = None

    assert await mfa.has_totp_enabled(db_session, user) is False
    assert await mfa.has_webauthn_enabled(db_session, user) is False
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

            # verify_totp_for_user skipping
            with pytest.raises(HTTPException):  # No enrollment available if skipped
                await mfa.verify_totp_for_user(db_session, user=user, code="123456")


async def test_consume_challenge_webauthn(db_session, user_factory):
    user = await user_factory()
    challenge = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type="webauthn-authentication",
        payload={"options": {"challenge": "dummy-challenge"}},
    )
    await db_session.commit()

    with patch(
        "app.services.webauthn.WebAuthnService.verify_authentication"
    ) as mock_verify:
        mock_verify.return_value = None  # success

        consumed, _ = await mfa.consume_challenge(
            db_session,
            challenge_token=challenge.token,
            challenge_type="webauthn-authentication",
            provided_webauthn_response={"dummy": "data"},
            provided_method="webauthn",
        )
        assert consumed.consumed_at is not None
        mock_verify.assert_called_once()


async def test_legacy_enrollment_check(db_session, user_factory):
    user = await user_factory()
    user.mfa_default_method = "totp"
    # Unconfirmed but active enrollment (legacy case)
    enrollment = models.MfaTotpEnrollment(
        user_id=user.id, secret="JBSWY3DPEHPK3PXP", is_active=True, confirmed_at=None
    )
    db_session.add(enrollment)
    await db_session.commit()
    await db_session.refresh(user)

    import pyotp

    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    res_enr, _ = await mfa.verify_totp_for_user(db_session, user=user, code=totp.now())
    assert res_enr.id == enrollment.id


async def test_refresh_preferences_disable_required(db_session, user_factory):
    user = await user_factory()
    user.mfa_required = True
    await db_session.commit()

    # No factors, mfa_required=True -> should set mfa_required=False
    pref = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert pref is None
    assert user.mfa_required is False
