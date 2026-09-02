import secrets
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa
from app.auth.security import get_password_hash
from app.models import User


@pytest.fixture
async def unit_user_mfa(db_session: AsyncSession) -> User:
    """User with MFA setup."""
    email = f"user_{secrets.token_hex(4)}@example.com"
    user = User(
        email=email,
        hashed_password=await get_password_hash("Ab1!Ab1!Ab1!"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Enroll TOTP
    enrollment, _, _ = await mfa.start_totp_enrollment(db_session, user=user)
    enrollment.confirmed_at = mfa._utcnow()
    enrollment.is_active = True
    user.mfa_required = True
    user.mfa_default_method = mfa.MFA_METHOD_TOTP
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_generate_recovery_codes_unit(
    db_session: AsyncSession, unit_user_mfa: User
):
    """Unit test for generating recovery codes."""
    codes = await mfa.generate_recovery_codes(
        db_session,
        user=unit_user_mfa,
        fresh_mfa_verified_at=datetime.now(UTC),
    )

    assert len(codes) == 10

    # Verify DB
    user_codes = (
        (
            await db_session.execute(
                select(mfa.RecoveryCode).where(
                    mfa.RecoveryCode.user_id == unit_user_mfa.id
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(user_codes) == 10
    assert not any(c.is_used for c in user_codes)

    # Verify hash — RZ-33-01: codes are hashed from dash-free canonical form

    from app.auth.security import verify_password

    # Check that at least one code matches using the normalized (dash-free) form
    canonical = codes[0].replace("-", "")
    match = None
    for c in user_codes:
        if await verify_password(canonical, c.code_hash):
            match = c
            break
    assert match is not None


async def test_verify_recovery_code_unit(db_session: AsyncSession, unit_user_mfa: User):
    """Unit test for verifying codes."""
    codes = await mfa.generate_recovery_codes(
        db_session,
        user=unit_user_mfa,
        fresh_mfa_verified_at=datetime.now(UTC),
    )
    valid_code = codes[0]

    # Verify success
    verified = await mfa.verify_recovery_code(
        db_session, user=unit_user_mfa, code=valid_code
    )
    assert verified is True

    # Verify DB marked used
    user_codes = (
        (
            await db_session.execute(
                select(mfa.RecoveryCode).where(
                    mfa.RecoveryCode.user_id == unit_user_mfa.id
                )
            )
        )
        .scalars()
        .all()
    )
    # Find the used one
    used = [c for c in user_codes if c.is_used]
    assert len(used) == 1

    # Verify reuse fails
    verified_reuse = await mfa.verify_recovery_code(
        db_session, user=unit_user_mfa, code=valid_code
    )
    assert verified_reuse is False

    # Verify invalid fails
    verified_invalid = await mfa.verify_recovery_code(
        db_session, user=unit_user_mfa, code="invalid"
    )
    assert verified_invalid is False


async def test_invalidation_unit(db_session: AsyncSession, unit_user_mfa: User):
    """Unit test: generating new codes invalidates old ones."""
    fresh = datetime.now(UTC)
    codes1 = await mfa.generate_recovery_codes(
        db_session, user=unit_user_mfa, fresh_mfa_verified_at=fresh
    )
    codes2 = await mfa.generate_recovery_codes(
        db_session, user=unit_user_mfa, fresh_mfa_verified_at=fresh
    )

    # Try verifying code from batch 1
    verified = await mfa.verify_recovery_code(
        db_session, user=unit_user_mfa, code=codes1[0]
    )
    assert verified is False

    # Try verifying code from batch 2
    verified2 = await mfa.verify_recovery_code(
        db_session, user=unit_user_mfa, code=codes2[0]
    )
    assert verified2 is True
