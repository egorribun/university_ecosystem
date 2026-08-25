from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa, security


@pytest.mark.asyncio
async def test_count_remaining_recovery_codes_coverage(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    # Initial count should be 0
    count = await mfa.count_remaining_recovery_codes(db_session, user=user)
    assert count == 0

    # Generate codes
    await mfa.generate_recovery_codes(
        db_session, user=user, fresh_mfa_verified_at=datetime.now(UTC)
    )
    count = await mfa.count_remaining_recovery_codes(db_session, user=user)
    assert count == 10


@pytest.mark.asyncio
async def test_disable_totp_logic_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    # No TOTP yet
    count, pending = await mfa.disable_totp(db_session, user=user)
    assert count == 0
    assert pending == []

    # Start enrollment
    enrollment, _, _ = await mfa.start_totp_enrollment(db_session, user=user)
    enrollment.confirmed_at = mfa._utcnow()
    enrollment.is_active = True
    await db_session.commit()

    count, pending = await mfa.disable_totp(db_session, user=user)
    assert count == 1
    assert pending == []

    # Verify enrollment is deactivated
    await db_session.refresh(enrollment)
    assert enrollment.is_active is False


def test_format_password_class_labels_coverage():
    # Test with empty list
    res_empty = security._format_password_class_labels([], locale="en")
    assert res_empty == ""

    # Test with multiple labels to check joining
    res_multi = security._format_password_class_labels(
        ["uppercase", "digit"], locale="en"
    )
    assert "uppercase letters" in res_multi
    assert "digits" in res_multi


@pytest.mark.asyncio
async def test_purge_expired_challenges_coverage(db_session: AsyncSession):
    # Exercises the SQL construction and execution
    count = await mfa.purge_expired_challenges(db_session, grace_period_seconds=3600)
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_get_password_hash_bypass_policy_coverage():
    # "short" would normally fail (min_length=8)
    pw = "short"
    h = await security.get_password_hash(pw, validate_policy=False)
    assert await security.verify_password(pw, h)


@pytest.mark.asyncio
async def test_mfa_reset_stats_changed_coverage():
    from app.auth.mfa import MfaResetStats

    stats = MfaResetStats()
    assert stats.changed is False
    stats.totp_deleted = 1
    assert stats.changed is True


@pytest.mark.asyncio
async def test_reset_user_mfa_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    user.mfa_required = True
    user.mfa_default_method = "totp"
    await db_session.commit()

    stats = await mfa.reset_user_mfa(db_session, user=user)
    assert stats.fields_cleared is True
    assert user.mfa_required is False
    assert user.mfa_default_method is None


@pytest.mark.asyncio
async def test_refresh_user_mfa_preferences_coverage(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    # Case: No MFA
    res = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert res is None

    # Case: Add TOTP (mocked active enrollment)
    enrollment = mfa.MfaTotpEnrollment(
        user_id=user.id, secret="secret", is_active=True, confirmed_at=mfa._utcnow()
    )
    db_session.add(enrollment)
    await db_session.commit()

    res = await mfa.refresh_user_mfa_preferences(db_session, user=user)
    assert res == mfa.MFA_METHOD_TOTP
    assert user.mfa_required is True


def test_password_policy_min_classes_coverage(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "password_min_character_classes", 4)
    monkeypatch.setattr(settings, "password_require_uppercase", False)
    monkeypatch.setattr(settings, "password_require_lowercase", False)
    monkeypatch.setattr(settings, "password_require_digit", False)
    monkeypatch.setattr(settings, "password_require_special", False)

    # Fails because it only has 3 classes (Upper, Lower, Digit)
    with pytest.raises(ValueError) as excinfo:
        security._validate_password_policy("Ab1Ab1Ab1")
    assert "include at least 4" in str(excinfo.value)


def test_password_policy_strength_coverage(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "password_zxcvbn_min_score", 4)
    # Disable class checks to ensure we reach the strength check
    monkeypatch.setattr(settings, "password_require_uppercase", False)
    monkeypatch.setattr(settings, "password_require_lowercase", False)
    monkeypatch.setattr(settings, "password_require_digit", False)
    monkeypatch.setattr(settings, "password_require_special", False)
    monkeypatch.setattr(settings, "password_min_character_classes", 0)

    # "password" is very weak
    with pytest.raises(ValueError) as excinfo:
        security._validate_password_policy("password")
    assert "too weak" in str(excinfo.value)


@pytest.mark.asyncio
async def test_verify_recovery_code_invalid_coverage(
    db_session: AsyncSession, user_factory
):
    user = await user_factory()
    await mfa.generate_recovery_codes(
        db_session, user=user, fresh_mfa_verified_at=datetime.now(UTC)
    )
    res = await mfa.verify_recovery_code(db_session, user=user, code="NOT-VALID-CODE")
    assert res is False


@pytest.mark.asyncio
async def test_trusted_device_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    token, _expires_at = await mfa.create_trusted_device_token(
        db_session,
        user=user,
        ip_address="192.0.2.10",
        user_agent="pytest",
    )
    assert token is not None

    # Verify success
    is_valid = await mfa.verify_trusted_device_token(
        db_session,
        user=user,
        token=token,
        request_ip="192.0.2.10",
        request_ua="pytest",
    )
    assert is_valid is True

    is_valid_invalid = await mfa.verify_trusted_device_token(
        db_session,
        user=user,
        token="invalid-token",
        request_ip="192.0.2.10",
        request_ua="pytest",
    )
    assert is_valid_invalid is False


@pytest.mark.asyncio
async def test_trusted_device_expired_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    token, _ = await mfa.create_trusted_device_token(
        db_session,
        user=user,
        ip_address="192.0.2.11",
        user_agent="pytest-expired",
    )
    from sqlalchemy import select

    from app.models import TrustedDevice

    device = (
        await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.user_id == user.id)
        )
    ).scalar_one()
    device.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    # Verification should fail and delete the device
    is_valid = await mfa.verify_trusted_device_token(
        db_session,
        user=user,
        token=token,
        request_ip="192.0.2.11",
        request_ua="pytest-expired",
    )
    assert is_valid is False


@pytest.mark.asyncio
async def test_get_challenge_error_coverage(db_session: AsyncSession):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await mfa.get_challenge(
            db_session, token="nonexistent", challenge_type="totp-verify"
        )


@pytest.mark.asyncio
async def test_get_challenge_expired_coverage(db_session: AsyncSession, user_factory):
    user = await user_factory()
    issued = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier="expired-session",
        client_fingerprint="f" * 64,
    )
    issued.challenge.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await mfa.get_challenge(
            db_session,
            token=issued.challenge_token,
            challenge_type="totp-verify",
        )


@pytest.mark.asyncio
async def test_consume_challenge_coverage(db_session: AsyncSession, user_factory):
    """Test that challenges are properly marked as consumed.

    Note: The consume_challenge function now performs full MFA verification.
    This test verifies the basic challenge marking functionality by testing
    the get_challenge function with consume=True parameter instead.
    """
    user = await user_factory()
    issued = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier="consume-session",
        client_fingerprint="f" * 64,
    )
    await db_session.commit()

    # Use get_challenge with consume=True to mark it consumed
    retrieved = await mfa.get_challenge(
        db_session,
        token=issued.challenge_token,
        challenge_type="totp-verify",
        consume=True,
    )
    assert retrieved.consumed_at is not None
