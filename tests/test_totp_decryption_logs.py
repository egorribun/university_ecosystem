from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from unittest.mock import patch

import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import String, literal, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa import totp
from app.core.localization import translate
from app.models import MfaTotpEnrollment, User


async def test_unreadable_totp_enrollment_is_rejected_without_logging_account_id(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await user_factory()
    enrollment = MfaTotpEnrollment(
        user_id=user.id,
        secret=pyotp.random_base32(),
        is_active=True,
        confirmed_at=datetime.now(UTC),
    )
    db_session.add(enrollment)
    await db_session.flush()

    fingerprint = "b" * 64
    flow = "totp-unreadable-enrollment"
    challenge = await totp.start_totp_verification(
        db_session,
        user=user,
        flow="login",
        session_identifier=flow,
        client_fingerprint=fingerprint,
    )
    # An empty legacy ciphertext can exist in the non-null text column.
    await db_session.execute(
        update(MfaTotpEnrollment)
        .where(MfaTotpEnrollment.id == enrollment.id)
        .values(secret=literal("", type_=String()))
        .execution_options(synchronize_session=False)
    )
    await db_session.refresh(enrollment)
    with (
        patch.object(totp.logger, "warning") as warning,
        pytest.raises(HTTPException) as rejected,
    ):
        await totp.verify_totp_for_user(
            db_session,
            user=user,
            code="000000",
            challenge_token=challenge.challenge_token,
            client_fingerprint=fingerprint,
            login_session_identifier=flow,
            locale="en",
        )

    assert rejected.value.status_code == 400
    assert rejected.value.detail == translate("errors.mfa.invalid_code", locale="en")
    warning.assert_called_once_with(
        "Skipping TOTP enrollment: decryption failed",
        extra={"event": "mfa.totp.enrollment_skipped", "reason": "decryption_failed"},
    )
