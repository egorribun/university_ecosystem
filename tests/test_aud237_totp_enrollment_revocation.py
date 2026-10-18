from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi import HTTPException

from app.auth.mfa.totp import complete_totp_enrollment
from app.core import database
from app.models import MfaTotpEnrollment


@pytest.mark.asyncio
async def test_revoked_totp_enrollment_cannot_be_reactivated(
    db_session, user_factory
) -> None:
    user = await user_factory(email="aud237-revoked@example.com")
    secret = pyotp.random_base32()
    revoked_at = datetime.now(UTC)
    enrollment = MfaTotpEnrollment(
        user_id=user.id,
        secret=secret,
        label="old-authenticator",
        is_active=False,
        confirmed_at=revoked_at - timedelta(days=1),
        revoked_at=revoked_at,
    )
    db_session.add(enrollment)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await complete_totp_enrollment(
            db_session,
            enrollment=enrollment,
            code=pyotp.TOTP(secret).now(),
        )

    assert exc_info.value.status_code == 400
    await db_session.rollback()
    await db_session.refresh(enrollment)
    assert enrollment.is_active is False
    assert enrollment.revoked_at is not None


@pytest.mark.asyncio
async def test_active_totp_confirmation_remains_retryable_with_a_valid_code(
    db_session, user_factory
) -> None:
    user = await user_factory(email="aud237-confirm-retry@example.com")
    secret = pyotp.random_base32()
    enrollment = MfaTotpEnrollment(
        user_id=user.id,
        secret=secret,
        label="authenticator",
        is_active=False,
    )
    db_session.add(enrollment)
    await db_session.commit()

    first_result = await complete_totp_enrollment(
        db_session,
        enrollment=enrollment,
        code=pyotp.TOTP(secret).now(),
    )
    await db_session.commit()
    retry_result = await complete_totp_enrollment(
        db_session,
        enrollment=first_result,
        code=pyotp.TOTP(secret).now(),
    )

    assert retry_result.id == enrollment.id
    assert retry_result.is_active is True
    assert retry_result.revoked_at is None


@pytest.mark.asyncio
async def test_pending_totp_confirmation_rechecks_the_one_factor_limit(
    db_session, user_factory
) -> None:
    user = await user_factory(email="aud237-factor-limit@example.com")
    first_secret = pyotp.random_base32()
    second_secret = pyotp.random_base32()
    first = MfaTotpEnrollment(
        user_id=user.id,
        secret=first_secret,
        label="first",
        is_active=False,
    )
    second = MfaTotpEnrollment(
        user_id=user.id,
        secret=second_secret,
        label="second",
        is_active=False,
    )
    db_session.add_all([first, second])
    await db_session.commit()

    await complete_totp_enrollment(
        db_session,
        enrollment=first,
        code=pyotp.TOTP(first_secret).now(),
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await complete_totp_enrollment(
            db_session,
            enrollment=second,
            code=pyotp.TOTP(second_secret).now(),
        )

    assert exc_info.value.status_code == 400
    await db_session.rollback()
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.is_active is True
    assert first.confirmed_at is not None
    assert second.is_active is False
    assert second.confirmed_at is None
    assert second.revoked_at is None


@pytest.mark.asyncio
@pytest.mark.skipif(
    database.engine.dialect.name != "postgresql",
    reason="User-row serialization is a PostgreSQL locking contract",
)
async def test_concurrent_pending_totp_confirmations_share_one_factor_slot(
    db_session, user_factory
) -> None:
    user = await user_factory(email="aud237-confirm-race@example.com")
    enrollments = [
        (pyotp.random_base32(), "first"),
        (pyotp.random_base32(), "second"),
    ]
    rows = [
        MfaTotpEnrollment(
            user_id=user.id,
            secret=secret,
            label=label,
            is_active=False,
        )
        for secret, label in enrollments
    ]
    db_session.add_all(rows)
    await db_session.commit()
    start_together = asyncio.Barrier(2)

    async def confirm_one(row: MfaTotpEnrollment, secret: str) -> bool:
        async with database.async_session() as session:
            await asyncio.wait_for(start_together.wait(), timeout=2)
            try:
                await complete_totp_enrollment(
                    session,
                    enrollment=row,
                    code=pyotp.TOTP(secret).now(),
                )
                await session.commit()
                return True
            except HTTPException as exc:
                assert exc.status_code == 400
                await session.rollback()
                return False

    results = await asyncio.gather(
        confirm_one(rows[0], enrollments[0][0]),
        confirm_one(rows[1], enrollments[1][0]),
    )

    assert sorted(results) == [False, True]
    await db_session.refresh(rows[0])
    await db_session.refresh(rows[1])
    assert sum(row.is_active is True for row in rows) == 1
    assert sum(row.confirmed_at is not None for row in rows) == 1
