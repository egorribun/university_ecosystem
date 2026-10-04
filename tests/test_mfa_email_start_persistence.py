"""Email challenge issuance persists the current user's bound request."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import select

from app.api.auth import mfa as mfa_api
from app.auth.mfa.email_otp import EmailOtpService
from app.core import database
from app.models import (
    ActiveSession,
    ChallengeState,
    MfaChallenge,
    MfaEmailDelivery,
    StoredEvent,
)


class RecordingLimiter:
    def __init__(self):
        self.calls = []

    async def enforce(self, *, action, identifier):
        self.calls.append((action, identifier))


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_email_verification_start_commits_bound_challenge_delivery_and_outbox(
    db_session, user_factory, locale
):
    user = await user_factory(mfa_epoch=3)
    user_id = user.id
    session = ActiveSession(
        user_id=user_id,
        jti=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.flush()
    session_id = str(session.id)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mfa/email/verification/start",
            "query_string": b"",
            "headers": [
                (b"user-agent", b"mfa-persistence-test"),
                (b"accept-language", locale.encode()),
            ],
            "client": ("203.0.113.10", 12345),
        }
    )
    request.state.active_session = session
    limiter = RecordingLimiter()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=limiter,
    )
    login_service = SimpleNamespace(get_email_otp_service=lambda: service)

    response = await mfa_api.start_email_verification.__dishka_orig_func__(
        request=request, db=db_session, login_service=login_service, user=user
    )

    # A second session reads committed rows, not the issuing session's identity map.
    async with database.async_session() as reader:
        challenge = (
            await reader.execute(
                select(MfaChallenge).where(MfaChallenge.user_id == user_id)
            )
        ).scalar_one()
        delivery = (
            await reader.execute(
                select(MfaEmailDelivery).where(
                    MfaEmailDelivery.challenge_id == challenge.id
                )
            )
        ).scalar_one()
        event = (
            await reader.execute(
                select(StoredEvent).where(
                    StoredEvent.event_type == "auth.mfa_email.requested",
                    StoredEvent.aggregate_id_uuid == challenge.id,
                )
            )
        ).scalar_one()
        assert challenge.flow == "email_verification"
        assert challenge.session_identifier == session_id
        assert challenge.client_fingerprint == mfa_api.extract_request_fingerprint(
            request
        )
        assert challenge.payload == {"mfa_epoch": 3}
        assert challenge.state == ChallengeState.PENDING
        assert challenge.attempt_count == 0
        assert delivery.status == "pending"
        assert delivery.locale == event.payload["locale"] == locale
        assert delivery.revision == challenge.revision == response.revision == 1
        assert event.payload["delivery_id"] == str(delivery.id)
        assert event.payload["revision"] == 1
        assert response.method == "email_otp"
        assert response.challenge_token
        assert response.attempt_count == 0
        assert response.remaining_attempts == response.attempt_limit == 5
    assert limiter.calls == [
        ("issue", f"user:{user_id}"),
        ("issue", "ip:203.0.113.10"),
    ]
