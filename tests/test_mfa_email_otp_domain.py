from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.auth.mfa.email_otp as email_otp_module
from app.auth.constants import (
    MFA_METHOD_EMAIL_OTP,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.email_otp import (
    EmailOtpService,
    MfaDeliveryError,
    MfaOtpCooldown,
    MfaOtpRejected,
    MfaSecurityUnavailable,
    RuntimeMfaRateLimiter,
    build_configured_email_delivery_service,
)
from app.core.config import settings
from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
from app.models import ChallengeState, MfaChallenge, MfaEmailDelivery, StoredEvent, User

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
FINGERPRINT = "f" * 64
SESSION = "login-session-nonce"
IP = "203.0.113.8"


class RecordingRateLimiter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def enforce(self, *, action: str, identifier: str) -> None:
        self.calls.append((action, identifier))
        if self.fail:
            raise ConnectionError("rate limit backend unavailable")


class RecordingSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict[str, str]] = []

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        plain: str,
        html: str,
        message_id: str,
    ) -> None:
        if self.fail:
            raise OSError("smtp unavailable")
        self.messages.append(
            {
                "to_email": to_email,
                "subject": subject,
                "plain": plain,
                "html": html,
                "message_id": message_id,
            }
        )


@pytest.fixture
def limiter() -> RecordingRateLimiter:
    return RecordingRateLimiter()


@pytest.fixture
def otp_service(limiter: RecordingRateLimiter) -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"hmac-2026-08": b"h" * 32, "hmac-old": b"o" * 32},
        active_hmac_key_id="hmac-2026-08",
        delivery_keks={"kek-2026-08": b"k" * 32, "kek-old": b"z" * 32},
        active_kek_id="kek-2026-08",
        rate_limiter=limiter,
    )


async def _issue(
    service: EmailOtpService,
    db: AsyncSession,
    user: User,
    *,
    now: datetime = NOW,
    display_name: str = "Student",
    locale: str = "en",
) -> Any:
    user.email_verified_at = NOW - timedelta(days=1)
    user.email_mfa_enabled_at = NOW - timedelta(hours=1)
    await db.flush()
    return await service.issue(
        db,
        user_id=user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale=locale,
        display_name=display_name,
        now=now,
    )


def test_public_mfa_method_contract_excludes_security_keys() -> None:
    assert {MFA_METHOD_TOTP, MFA_METHOD_EMAIL_OTP} == {"totp", "email_otp"}
    assert MFA_METHOD_RECOVERY_CODE == "recovery_code"


@pytest.mark.asyncio
async def test_rate_limit_exceeded_is_not_downgraded_to_dependency_outage(
    db_session: AsyncSession, test_user: User
) -> None:
    class Limited:
        async def enforce(self, *, action: str, identifier: str) -> None:
            raise RateLimitExceeded(MagicMock())

    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=Limited(),
    )
    with pytest.raises(RateLimitExceeded):
        await _issue(service, db_session, test_user)


@pytest.mark.asyncio
async def test_issue_uses_exact_otp_contract_and_stores_no_plaintext(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
    limiter: RecordingRateLimiter,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)

    assert issued.otp.isdecimal() and len(issued.otp) == 6
    assert issued.expires_at == NOW + timedelta(seconds=600)
    assert issued.resend_available_at == NOW + timedelta(seconds=60)
    assert issued.revision == 1
    assert limiter.calls == [
        ("issue", f"user:{test_user.id}"),
        ("issue", f"ip:{IP}"),
    ]

    challenge = await db_session.get(MfaChallenge, issued.challenge_id)
    assert challenge is not None
    assert challenge.flow == "login"
    assert challenge.method == "email_otp"
    assert challenge.session_identifier == SESSION
    assert challenge.client_fingerprint == FINGERPRINT
    assert challenge.otp_key_id == "hmac-2026-08"
    assert challenge.token_key_id == "hmac-2026-08"
    assert len(challenge.recipient_digest) == 64
    assert test_user.email not in challenge.recipient_digest
    assert challenge.otp_digest != issued.otp
    assert challenge.token_digest != issued.challenge_token
    assert issued.otp not in repr(challenge.__dict__)

    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == challenge.id
            )
        )
    ).scalar_one()
    assert delivery.kek_id == "kek-2026-08"
    assert issued.otp not in repr(delivery.__dict__)
    assert test_user.email not in repr(delivery.__dict__)

    event = (
        await db_session.execute(
            select(StoredEvent).where(
                StoredEvent.event_type == "auth.mfa_email.requested"
            )
        )
    ).scalar_one()
    serialized = repr(event.payload)
    assert issued.otp not in serialized
    assert test_user.email not in serialized
    assert event.payload == {
        "delivery_id": str(delivery.id),
        "template": "mfa_email_otp",
        "locale": "en",
        "revision": 1,
    }


@pytest.mark.asyncio
async def test_issue_persists_requested_locale_in_delivery_and_outbox(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user, locale="ru")
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    assert delivery.locale == "ru"
    event = (
        await db_session.execute(
            select(StoredEvent).where(
                StoredEvent.event_type == "auth.mfa_email.requested",
                StoredEvent.aggregate_id_uuid == issued.challenge_id,
            )
        )
    ).scalar_one()
    assert event.payload["locale"] == "ru"


def _runtime_limited_service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"hmac-2026-08": b"h" * 32, "hmac-old": b"o" * 32},
        active_hmac_key_id="hmac-2026-08",
        delivery_keks={"kek-2026-08": b"k" * 32, "kek-old": b"z" * 32},
        active_kek_id="kek-2026-08",
        rate_limiter=RuntimeMfaRateLimiter(),
    )


@pytest.mark.asyncio
async def test_email_otp_start_api_translates_real_runtime_limit_to_429(
    db_session: AsyncSession, test_user: User
) -> None:
    from app.api.auth import mfa as mfa_api

    request = MagicMock()
    request.state.active_session = SimpleNamespace(id=SESSION)
    request.headers = {"user-agent": "test"}
    request.client.host = IP
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = _runtime_limited_service()
    limited = RateLimitExceeded(RateLimitInfo(False, 0, 17))
    with (
        patch("app.core.ratelimit.enforce_rate_limit", AsyncMock(side_effect=limited)),
        patch.object(mfa_api, "extract_request_fingerprint", return_value=FINGERPRINT),
        pytest.raises(HTTPException) as caught,
    ):
        await mfa_api._issue_email_challenge_for_session(
            flow="email_verification",
            request=request,
            db=db_session,
            login_service=login_service,
            user=test_user,
        )

    assert caught.value.status_code == 429
    assert caught.value.detail == "MFA request rejected"
    assert caught.value.headers == {"Retry-After": "17"}


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["verify", "resend"])
async def test_email_otp_existing_challenge_api_translates_real_runtime_limit_to_429(
    boundary: str,
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    from app.api.auth import login as login_api
    from app.auth.schemas import EmailOtpResendIn, MfaVerifyIn

    issued = await _issue(otp_service, db_session, test_user)
    await db_session.commit()
    request = MagicMock()
    request.state.active_session = None
    request.cookies = {"mfa_pre_auth_v1": SESSION}
    request.headers = {"user-agent": "test"}
    request.client.host = IP
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = _runtime_limited_service()
    limited = RateLimitExceeded(RateLimitInfo(False, 0, 23))

    with (
        patch("app.core.ratelimit.enforce_rate_limit", AsyncMock(side_effect=limited)),
        patch.object(
            login_api, "extract_request_fingerprint", return_value=FINGERPRINT
        ),
        patch("app.core.ratelimit.resolve_client_ip", return_value=IP),
        pytest.raises(HTTPException) as caught,
    ):
        if boundary == "verify":
            await login_api.verify_mfa_challenge.__dishka_orig_func__(
                MfaVerifyIn(
                    method="email_otp",
                    challenge_token=issued.challenge_token,
                    code=issued.otp,
                ),
                MagicMock(),
                request,
                MagicMock(),
                login_service,
                db_session,
            )
        else:
            await login_api.resend_email_mfa_challenge.__dishka_orig_func__(
                EmailOtpResendIn(challenge_token=issued.challenge_token),
                request,
                login_service,
                db_session,
            )

    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "23"}


@pytest.mark.asyncio
async def test_email_change_invalidates_recipient_bound_otp(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    test_user.email = "new-current-address@example.test"
    await db_session.commit()

    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=issued.challenge_token,
            code=issued.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_opaque_loader_accepts_step_up_bound_to_active_session() -> None:
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=RecordingRateLimiter(),
    )
    challenge = SimpleNamespace(
        id=uuid.uuid4(),
        method=MFA_METHOD_EMAIL_OTP,
        flow="step_up",
        token_key_id="active",
        token_digest="token-digest",
        client_fingerprint=FINGERPRINT,
        session_identifier=SESSION,
    )
    service._digest = MagicMock(return_value="token-digest")  # type: ignore[method-assign]
    result = MagicMock()
    result.scalar_one_or_none.return_value = challenge
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    token = email_otp_module._generate_challenge_token(challenge.id)
    loaded = await service._load_opaque_challenge(
        db,
        challenge_token=token,
        client_fingerprint=FINGERPRINT,
        login_session_identifier=None,
        active_session_identifier=SESSION,
    )

    assert loaded is challenge


@pytest.mark.asyncio
async def test_verify_is_one_time_bound_and_counts_cumulative_failures(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)

    for attempt in range(1, 6):
        with pytest.raises(MfaOtpRejected, match="MFA verification failed"):
            await otp_service.verify(
                db_session,
                challenge_token=issued.challenge_token,
                code="000000" if issued.otp != "000000" else "111111",
                user_id=test_user.id,
                flow="login",
                session_identifier=SESSION,
                client_fingerprint=FINGERPRINT,
                client_ip=IP,
                now=NOW + timedelta(seconds=attempt),
            )

    challenge = await db_session.get(MfaChallenge, issued.challenge_id)
    assert challenge is not None
    assert challenge.attempt_count == 5
    assert challenge.state == ChallengeState.LOCKED
    assert ("verify", f"user:{test_user.id}") in otp_service._rate_limiter.calls

    with pytest.raises(MfaOtpRejected, match="MFA verification failed"):
        await otp_service.verify(
            db_session,
            challenge_token=issued.challenge_token,
            code=issued.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=10),
        )


@pytest.mark.asyncio
async def test_verify_rejects_expiry_replay_and_binding_mismatch(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=issued.challenge_token,
            code=issued.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier="different-session",
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=issued.challenge_token,
            code=issued.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint="a" * 64,
            client_ip=IP,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=issued.challenge_token,
            code=issued.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=601),
        )

    fresh = await _issue(
        otp_service, db_session, test_user, now=NOW + timedelta(seconds=700)
    )
    await otp_service.verify(
        db_session,
        challenge_token=fresh.challenge_token,
        code=fresh.otp,
        user_id=test_user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=NOW + timedelta(seconds=701),
    )
    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=fresh.challenge_token,
            code=fresh.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=702),
        )


@pytest.mark.asyncio
async def test_resend_cooldown_rotates_revision_and_invalidates_old_code(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    first = await _issue(otp_service, db_session, test_user)
    with pytest.raises(MfaOtpCooldown):
        await otp_service.resend(
            db_session,
            challenge_token=first.challenge_token,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            locale="ru",
            now=NOW + timedelta(seconds=59),
        )

    rotated = await otp_service.resend(
        db_session,
        challenge_token=first.challenge_token,
        user_id=test_user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="ru",
        now=NOW + timedelta(seconds=60),
    )
    assert rotated.challenge_id == first.challenge_id
    assert rotated.revision == 2
    assert rotated.challenge_token != first.challenge_token
    assert rotated.otp != first.otp or rotated.revision == 2
    assert rotated.expires_at == NOW + timedelta(seconds=660)

    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=first.challenge_token,
            code=first.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=61),
        )
    await otp_service.verify(
        db_session,
        challenge_token=rotated.challenge_token,
        code=rotated.otp,
        user_id=test_user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=NOW + timedelta(seconds=62),
    )


@pytest.mark.asyncio
async def test_rate_limit_dependency_failure_is_fail_closed(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    service = EmailOtpService(
        hmac_keys={"h": b"h" * 32},
        active_hmac_key_id="h",
        delivery_keks={"k": b"k" * 32},
        active_kek_id="k",
        rate_limiter=RecordingRateLimiter(fail=True),
    )
    with pytest.raises(MfaSecurityUnavailable, match="MFA service unavailable"):
        await _issue(service, db_session, test_user)
    assert (
        not (
            await db_session.execute(
                select(MfaChallenge).where(MfaChallenge.user_id == test_user.id)
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_delivery_decrypts_only_at_send_and_crypto_shreds_terminal_success(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(
        otp_service,
        db_session,
        test_user,
        display_name='<img src=x onerror="alert(1)">',
    )
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    sender = RecordingSender()
    await otp_service.deliver(
        db_session, delivery_id=delivery.id, sender=sender, now=NOW
    )

    assert sender.messages[0]["to_email"] == test_user.email
    assert issued.otp in sender.messages[0]["plain"]
    assert "<img" not in sender.messages[0]["html"]
    assert "&lt;img" in sender.messages[0]["html"]
    assert delivery.status == "sent"
    assert delivery.envelope_ciphertext is None
    assert delivery.wrapped_dek is None
    assert delivery.shredded_at == NOW


@pytest.mark.asyncio
async def test_delivery_lease_covers_the_network_send_window(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    observed: list[datetime | None] = []

    class InspectingSender(RecordingSender):
        async def send(self, **kwargs: str) -> None:
            await db_session.refresh(delivery)
            observed.append(delivery.lease_expires_at)
            await super().send(**kwargs)

    await otp_service.deliver(
        db_session,
        delivery_id=delivery.id,
        sender=InspectingSender(),
        now=NOW,
    )
    assert observed[0] is not None
    assert observed[0].replace(tzinfo=UTC) == NOW + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_worker_delivery_builder_needs_only_kek_ring_and_cannot_issue_otp(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    encoded_kek = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    monkeypatch.setattr(
        settings, "mfa_email_delivery_keks", f"kek-2026-08:{encoded_kek}"
    )
    monkeypatch.setattr(settings, "mfa_email_otp_hmac_keys", "")
    monkeypatch.setattr(settings, "mfa_email_otp_active_hmac_key_id", "")
    monkeypatch.setattr(settings, "mfa_trusted_device_hmac_keys", "")
    monkeypatch.setattr(settings, "mfa_trusted_device_active_hmac_key_id", "")

    worker_service = build_configured_email_delivery_service()
    sender = RecordingSender()
    await worker_service.deliver(
        db_session, delivery_id=delivery.id, sender=sender, now=NOW
    )
    assert len(sender.messages) == 1
    with pytest.raises(MfaSecurityUnavailable):
        await _issue(
            worker_service, db_session, test_user, now=NOW + timedelta(seconds=1)
        )


@pytest.mark.asyncio
async def test_delivery_failure_preserves_retry_envelope_without_pii_logs(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(MfaDeliveryError, match="MFA delivery failed"),
    ):
        await otp_service.deliver(
            db_session,
            delivery_id=delivery.id,
            sender=RecordingSender(fail=True),
            now=NOW,
        )

    assert delivery.envelope_ciphertext is not None
    assert delivery.wrapped_dek is not None
    assert delivery.status == "pending"
    assert issued.otp not in caplog.text
    assert test_user.email not in caplog.text


@pytest.mark.asyncio
async def test_concurrent_verify_has_exactly_one_winner(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    await db_session.commit()

    from app.core.database import async_session

    async def attempt() -> str:
        async with async_session() as isolated:
            try:
                await otp_service.verify(
                    isolated,
                    challenge_token=issued.challenge_token,
                    code=issued.otp,
                    user_id=test_user.id,
                    flow="login",
                    session_identifier=SESSION,
                    client_fingerprint=FINGERPRINT,
                    client_ip=IP,
                    now=NOW + timedelta(seconds=1),
                )
                await isolated.commit()
                return "won"
            except MfaOtpRejected:
                await isolated.rollback()
                return "rejected"

    assert sorted(await asyncio.gather(attempt(), attempt())) == ["rejected", "won"]


@pytest.mark.asyncio
async def test_concurrent_resend_has_one_monotonic_revision_winner(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    await db_session.commit()

    from app.core.database import async_session

    async def resend() -> tuple[str, int | None]:
        async with async_session() as isolated:
            try:
                result = await otp_service.resend(
                    isolated,
                    challenge_token=issued.challenge_token,
                    user_id=test_user.id,
                    flow="login",
                    session_identifier=SESSION,
                    client_fingerprint=FINGERPRINT,
                    client_ip=IP,
                    locale="en",
                    now=NOW + timedelta(seconds=60),
                )
                await isolated.commit()
                return "won", result.revision
            except MfaOtpRejected:
                await isolated.rollback()
                return "rejected", None

    outcomes = await asyncio.gather(resend(), resend())
    assert sorted(status for status, _ in outcomes) == ["rejected", "won"]
    assert [revision for _, revision in outcomes if revision is not None] == [2]

    async with async_session() as check:
        challenge = await check.get(MfaChallenge, issued.challenge_id)
        deliveries = (
            (
                await check.execute(
                    select(MfaEmailDelivery).where(
                        MfaEmailDelivery.challenge_id == issued.challenge_id,
                        MfaEmailDelivery.status == "pending",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert challenge is not None and challenge.revision == 2
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_hmac_and_kek_rotation_verify_old_material(
    db_session: AsyncSession,
    test_user: User,
    limiter: RecordingRateLimiter,
) -> None:
    old = EmailOtpService(
        hmac_keys={"old-hmac": b"o" * 32},
        active_hmac_key_id="old-hmac",
        delivery_keks={"old-kek": b"d" * 32},
        active_kek_id="old-kek",
        rate_limiter=limiter,
    )
    issued = await _issue(old, db_session, test_user)
    rotated = EmailOtpService(
        hmac_keys={"new-hmac": b"n" * 32, "old-hmac": b"o" * 32},
        active_hmac_key_id="new-hmac",
        delivery_keks={"new-kek": b"e" * 32, "old-kek": b"d" * 32},
        active_kek_id="new-kek",
        rate_limiter=limiter,
    )
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    sender = RecordingSender()
    await rotated.deliver(db_session, delivery_id=delivery.id, sender=sender, now=NOW)
    assert issued.otp in sender.messages[0]["plain"]

    await rotated.verify(
        db_session,
        challenge_token=issued.challenge_token,
        code=issued.otp,
        user_id=test_user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=NOW + timedelta(seconds=1),
    )


@pytest.mark.asyncio
async def test_resend_rotates_recipient_digest_with_active_hmac_key(
    db_session: AsyncSession,
    test_user: User,
    limiter: RecordingRateLimiter,
) -> None:
    old = EmailOtpService(
        hmac_keys={"old-hmac": b"o" * 32},
        active_hmac_key_id="old-hmac",
        delivery_keks={"old-kek": b"d" * 32},
        active_kek_id="old-kek",
        rate_limiter=limiter,
    )
    issued = await _issue(old, db_session, test_user)
    rotated_service = EmailOtpService(
        hmac_keys={"new-hmac": b"n" * 32, "old-hmac": b"o" * 32},
        active_hmac_key_id="new-hmac",
        delivery_keks={"new-kek": b"e" * 32, "old-kek": b"d" * 32},
        active_kek_id="new-kek",
        rate_limiter=limiter,
    )
    resent = await rotated_service.resend(
        db_session,
        challenge_token=issued.challenge_token,
        user_id=test_user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="en",
        now=NOW + timedelta(seconds=61),
    )
    await rotated_service.verify(
        db_session,
        challenge_token=resent.challenge_token,
        code=resent.otp,
        user_id=test_user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=NOW + timedelta(seconds=62),
    )


@pytest.mark.asyncio
async def test_domain_binding_prevents_cross_challenge_code_or_token_swap(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    first = await _issue(otp_service, db_session, test_user)
    second = await _issue(
        otp_service, db_session, test_user, now=NOW + timedelta(seconds=1)
    )
    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=first.challenge_token,
            code=second.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=2),
        )
    with pytest.raises(MfaOtpRejected):
        await otp_service.verify(
            db_session,
            challenge_token=second.challenge_token,
            code=first.otp,
            user_id=test_user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_delivery_tamper_is_generic_and_success_retry_is_idempotent(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    tampered_issue = await _issue(otp_service, db_session, test_user)
    tampered = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == tampered_issue.challenge_id
            )
        )
    ).scalar_one()
    assert tampered.envelope_ciphertext is not None
    tampered.envelope_ciphertext = (
        bytes([tampered.envelope_ciphertext[0] ^ 1]) + tampered.envelope_ciphertext[1:]
    )
    with pytest.raises(MfaDeliveryError, match="MFA delivery failed"):
        await otp_service.deliver(
            db_session, delivery_id=tampered.id, sender=RecordingSender(), now=NOW
        )

    clean_issue = await _issue(
        otp_service, db_session, test_user, now=NOW + timedelta(seconds=2)
    )
    clean = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == clean_issue.challenge_id
            )
        )
    ).scalar_one()
    sender = RecordingSender()
    await otp_service.deliver(db_session, delivery_id=clean.id, sender=sender, now=NOW)
    await otp_service.deliver(db_session, delivery_id=clean.id, sender=sender, now=NOW)
    assert len(sender.messages) == 1
    assert sender.messages[0]["message_id"] == clean.message_id


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["email_verification", "email_mfa_enablement"])
async def test_recovery_code_is_rejected_for_email_only_flows(
    flow: str,
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    test_user.email_verified_at = NOW - timedelta(days=1)
    await db_session.flush()
    issued = await otp_service.issue(
        db_session,
        user_id=test_user.id,
        flow=flow,
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="en",
        now=NOW,
    )
    with (
        patch(
            "app.auth.mfa.recovery.verify_recovery_code",
            AsyncMock(return_value=True),
        ) as verify_recovery,
        pytest.raises(MfaOtpRejected),
    ):
        await otp_service.consume_recovery_opaque(
            db_session,
            challenge_token=issued.challenge_token,
            code="RECOVERY-CODE",
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            login_session_identifier=None,
            active_session_identifier=SESSION,
            now=NOW,
        )

    verify_recovery.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_opaque_uses_utc_for_default_consumption_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=RecordingRateLimiter(),
    )
    user = SimpleNamespace(id=uuid.uuid4(), email="student@example.edu")
    challenge = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        flow="step_up",
        method=MFA_METHOD_EMAIL_OTP,
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        token_key_id="active",
        recipient_digest=service._recipient_digest(key_id="active", email=user.email),
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=5),
        attempt_count=0,
        locked_at=None,
        consumed_at=None,
    )
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    db = MagicMock()
    db.flush = AsyncMock()
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = NOW
    monkeypatch.setattr(email_otp_module, "datetime", clock)

    with patch(
        "app.auth.mfa.recovery.verify_recovery_code",
        AsyncMock(return_value=True),
    ):
        consumed = await service.consume_recovery_opaque(
            db,
            challenge_token="opaque-token",
            code="RECOVERY-CODE",
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            login_session_identifier=None,
            active_session_identifier=SESSION,
        )

    assert consumed is challenge
    assert challenge.consumed_at == NOW
    clock.now.assert_called_once_with(UTC)


@pytest.mark.asyncio
async def test_leased_old_revision_is_shredded_without_smtp_send(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    challenge = await db_session.get(MfaChallenge, issued.challenge_id)
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    assert challenge is not None
    challenge.revision = 2
    delivery.status = "sending"
    delivery.lease_token = "expired-lease"
    delivery.lease_expires_at = NOW - timedelta(seconds=1)
    await db_session.commit()

    sender = RecordingSender()
    await otp_service.deliver(
        db_session,
        delivery_id=delivery.id,
        sender=sender,
        now=NOW,
    )
    await db_session.refresh(delivery)

    assert sender.messages == []
    assert delivery.status == "cancelled"
    assert delivery.envelope_ciphertext is None
    assert delivery.wrapped_dek is None
    assert delivery.lease_token is None
    assert delivery.lease_expires_at is None
    assert delivery.shredded_at is not None
    assert delivery.shredded_at.replace(tzinfo=UTC) == NOW


@pytest.mark.asyncio
async def test_delivery_rechecks_expiry_after_waiting_for_challenge_lock(
    db_session: AsyncSession,
    test_user: User,
    otp_service: EmailOtpService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = await _issue(otp_service, db_session, test_user)
    challenge = await db_session.get(MfaChallenge, issued.challenge_id)
    delivery = (
        await db_session.execute(
            select(MfaEmailDelivery).where(
                MfaEmailDelivery.challenge_id == issued.challenge_id
            )
        )
    ).scalar_one()
    assert challenge is not None
    challenge.expires_at = NOW + timedelta(seconds=1)
    await db_session.commit()

    clock = MagicMock(wraps=datetime)
    clock.now.side_effect = [NOW, NOW + timedelta(seconds=2)]
    monkeypatch.setattr(email_otp_module, "datetime", clock)
    sender = RecordingSender()

    await otp_service.deliver(db_session, delivery_id=delivery.id, sender=sender)
    await db_session.refresh(delivery)

    assert clock.now.call_count == 2
    assert sender.messages == []
    assert delivery.status == "cancelled"
    assert delivery.envelope_ciphertext is None


def test_plaintext_otp_is_not_a_public_schema_field() -> None:
    from app.auth import schemas

    for schema_name in schemas.__all__:
        schema = getattr(schemas, schema_name)
        fields = getattr(schema, "model_fields", {})
        assert "otp" not in fields


def test_issue_and_resend_do_not_accept_a_caller_supplied_recipient() -> None:
    issue_parameters = inspect.signature(EmailOtpService.issue).parameters
    resend_parameters = inspect.signature(EmailOtpService.resend).parameters
    assert "email" not in issue_parameters
    assert "email" not in resend_parameters


@pytest.mark.asyncio
async def test_outbox_unknown_event_fails_closed_instead_of_marking_success() -> None:
    from app.models import StoredEvent
    from app.workers.outbox import OutboxWorker

    event = StoredEvent(
        event_type="unknown.security.event",
        aggregate_type="MfaChallenge",
        aggregate_id="unknown",
        payload={},
    )
    with patch("app.workers.outbox.logger.error") as log_error:
        with pytest.raises(RuntimeError, match="Unknown outbox event type"):
            await OutboxWorker()._dispatch_event(event)
    assert str(event.id) in " ".join(str(value) for value in log_error.call_args.args)
    assert event.error_count is None
