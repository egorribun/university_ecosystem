from __future__ import annotations

from datetime import UTC, datetime

import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy.orm.attributes import set_committed_value

from app.auth.mfa import totp as totp_module
from app.models import MfaTotpEnrollment, User


@pytest.mark.asyncio
async def test_distinct_challenges_cannot_replay_one_totp_timecode(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_time = 2_000_000_000
    monkeypatch.setattr(totp_module.time, "time", lambda: fixed_time)
    user: User = await user_factory(email="totp-atomic@example.com")
    secret = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
    enrollment = MfaTotpEnrollment(
        user_id=user.id,
        secret=secret,
        is_active=True,
        confirmed_at=datetime.now(UTC),
    )
    db_session.add(enrollment)
    await db_session.flush()

    fingerprint = "a" * 64
    first = await totp_module.start_totp_verification(
        db_session,
        user=user,
        flow="login",
        session_identifier="totp-race-first",
        client_fingerprint=fingerprint,
    )
    second = await totp_module.start_totp_verification(
        db_session,
        user=user,
        flow="login",
        session_identifier="totp-race-second",
        client_fingerprint=fingerprint,
    )
    code = pyotp.TOTP(secret).at(fixed_time)

    accepted, _ = await totp_module.verify_totp_for_user(
        db_session,
        user=user,
        code=code,
        challenge_token=first.challenge_token,
        client_fingerprint=fingerprint,
        login_session_identifier="totp-race-first",
    )
    assert accepted.last_used_timecode == fixed_time // 30

    # Reproduce the old failure mode: the enrollment is present in the ORM
    # identity map with stale replay fields after another transaction's commit.
    set_committed_value(enrollment, "last_used_timecode", None)
    set_committed_value(enrollment, "last_used_code_hash", None)

    with pytest.raises(HTTPException) as replay:
        await totp_module.verify_totp_for_user(
            db_session,
            user=user,
            code=code,
            challenge_token=second.challenge_token,
            client_fingerprint=fingerprint,
            login_session_identifier="totp-race-second",
        )

    assert replay.value.status_code == 400
    assert "already" in str(replay.value.detail).lower()
