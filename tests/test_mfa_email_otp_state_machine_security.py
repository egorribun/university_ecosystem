"""Adversarial invariants for email OTP state transitions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.auth.constants import MFA_METHOD_EMAIL_OTP
from app.auth.mfa.email_otp import (
    OTP_MAX_FAILED_ATTEMPTS,
    OTP_TTL_SECONDS,
    EmailOtpService,
    IssuedEmailOtp,
    MfaDeliveryError,
    MfaOtpCooldown,
    MfaOtpRejected,
    RuntimeMfaRateLimiter,
    SmtpMfaEmailSender,
)
from app.models import ChallengeState

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
FINGERPRINT = "f" * 64
SESSION = "bound-login-session"
CLIENT_IP = "203.0.113.10"


class _RecordingLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def enforce(self, *, action: str, identifier: str) -> None:
        self.calls.append((action, identifier))


def test_issued_otp_repr_does_not_expose_bearer_secrets() -> None:
    issued = IssuedEmailOtp(
        challenge_id=uuid.uuid4(),
        challenge_token="challenge-token-secret-sentinel",
        otp="734106",
        revision=3,
        expires_at=NOW + timedelta(minutes=10),
        resend_available_at=NOW + timedelta(seconds=60),
        delivery_hint="s***@e***.test",
    )

    representation = repr(issued)

    assert "challenge-token-secret-sentinel" not in representation
    assert "734106" not in representation


@pytest.mark.asyncio
async def test_email_otp_rate_limit_uses_independent_user_and_ip_buckets() -> None:
    user_id = uuid.uuid4()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=RuntimeMfaRateLimiter(),
    )
    enforce_rate_limit = AsyncMock()
    strategy = object()

    with (
        patch("app.core.ratelimit.enforce_rate_limit", enforce_rate_limit),
        patch("app.core.ratelimit.get_default_strategy", return_value=strategy),
    ):
        await service._rate_limit(action="verify", user_id=user_id, client_ip=CLIENT_IP)

    expected_limits = {
        "limit": OTP_MAX_FAILED_ATTEMPTS,
        "window_seconds": OTP_TTL_SECONDS,
        "strategy": strategy,
    }
    assert enforce_rate_limit.await_args_list == [
        call(identifier=f"mfa-email:verify:user:{user_id}", **expected_limits),
        call(identifier=f"mfa-email:verify:ip:{CLIENT_IP}", **expected_limits),
    ]


@pytest.mark.asyncio
async def test_resend_cooldown_uses_supplied_clock_without_mutating_challenge() -> None:
    limiter = _RecordingLimiter()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=limiter,
    )
    user = SimpleNamespace(id=uuid.uuid4(), email="otp-state@example.test")
    challenge = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        method="email_otp",
        revision=1,
        token_key_id="active",
        token_digest="current-token-digest",
        recipient_digest=service._recipient_digest(key_id="active", email=user.email),
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=10),
        resend_available_at=NOW + timedelta(seconds=1),
        attempt_count=0,
    )
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(user, user.email)
    )
    service._load_bound_challenge = AsyncMock(  # type: ignore[method-assign]
        return_value=challenge
    )
    db = MagicMock()
    db.execute = AsyncMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    with pytest.raises(MfaOtpCooldown):
        await service.resend(
            db,
            challenge_token="opaque-token",
            user_id=user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=CLIENT_IP,
            locale="en",
            now=NOW,
        )

    assert limiter.calls == [
        ("resend", f"user:{user.id}"),
        ("resend", f"ip:{CLIENT_IP}"),
    ]
    service._resolve_recipient.assert_awaited_once()
    service._load_bound_challenge.assert_awaited_once()
    db.execute.assert_not_awaited()
    db.add_all.assert_not_called()


def _delivery_fakes(
    *,
    challenge: SimpleNamespace | None,
    update_result: SimpleNamespace,
    lease_expires_at: datetime,
) -> tuple[EmailOtpService, MagicMock, SimpleNamespace]:
    service = EmailOtpService(
        hmac_keys={"test-key": b"h" * 32},
        active_hmac_key_id="test-key",
        delivery_keks={"test-kek": b"k" * 32},
        active_kek_id="test-kek",
        rate_limiter=MagicMock(),
    )
    delivery = SimpleNamespace(
        id=uuid.uuid4(),
        challenge_id=uuid.uuid4(),
        lease_token="synthetic-lease-token",
        lease_expires_at=lease_expires_at,
        locale="en",
        message_id="synthetic-message-id",
        revision=1,
    )
    claim_result = SimpleNamespace(
        one_or_none=MagicMock(return_value=SimpleNamespace(id=delivery.id))
    )
    challenge_result = SimpleNamespace(
        scalar_one_or_none=MagicMock(return_value=challenge)
    )
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[claim_result, challenge_result, update_result])
    db.get = AsyncMock(side_effect=[delivery, delivery])
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return service, db, delivery


@pytest.mark.asyncio
async def test_delivery_rejects_cancel_update_without_rowcount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, db, delivery = _delivery_fakes(
        challenge=None,
        update_result=SimpleNamespace(),
        lease_expires_at=NOW + timedelta(minutes=2),
    )
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(smtp_mfa_total_timeout_seconds=60),
    )

    with patch(
        "app.auth.mfa.email_otp.secrets.token_urlsafe",
        return_value="synthetic-lease-token",
    ):
        with pytest.raises(MfaDeliveryError):
            await service.deliver(
                db,
                delivery_id=delivery.id,
                sender=SimpleNamespace(),
                now=NOW,
            )

    assert db.execute.await_count == 3
    db.commit.assert_awaited_once()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_rejects_completion_update_without_rowcount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, db, delivery = _delivery_fakes(
        challenge=SimpleNamespace(
            method=MFA_METHOD_EMAIL_OTP,
            state=ChallengeState.PENDING,
            revision=1,
            expires_at=NOW + timedelta(minutes=5),
        ),
        update_result=SimpleNamespace(),
        lease_expires_at=NOW + timedelta(minutes=2),
    )
    sender = SimpleNamespace(send=AsyncMock())
    monkeypatch.setattr(
        service,
        "_decrypt_delivery",
        MagicMock(
            return_value={
                "email": "demo@example.test",
                "display_name": "Demo",
                "otp": "synthetic-code",
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_render_email",
        MagicMock(return_value=("subject", "plain", "html")),
    )
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(smtp_mfa_total_timeout_seconds=60),
    )

    with patch(
        "app.auth.mfa.email_otp.secrets.token_urlsafe",
        return_value="synthetic-lease-token",
    ):
        with pytest.raises(MfaDeliveryError):
            await service.deliver(
                db,
                delivery_id=delivery.id,
                sender=sender,
                now=NOW,
            )

    sender.send.assert_awaited_once()
    assert db.execute.await_count == 3
    db.commit.assert_awaited_once()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_uses_sender_timeout_before_global_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, db, delivery = _delivery_fakes(
        challenge=None,
        update_result=SimpleNamespace(rowcount=1),
        lease_expires_at=NOW + timedelta(seconds=15),
    )
    sender = SmtpMfaEmailSender(total_timeout_seconds=5)
    send = AsyncMock()
    monkeypatch.setattr(sender, "send", send)
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(smtp_mfa_total_timeout_seconds=60),
    )

    with patch(
        "app.auth.mfa.email_otp.secrets.token_urlsafe",
        return_value="synthetic-lease-token",
    ):
        await service.deliver(
            db,
            delivery_id=delivery.id,
            sender=sender,
            now=NOW,
        )

    send.assert_not_awaited()
    assert db.execute.await_count == 3
    assert db.commit.await_count == 2
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_rejects_pending_challenge_with_exhausted_attempt_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale/inconsistent pending row must not bypass the shared attempt cap."""
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=MagicMock(),
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="otp-state@example.test",
    )
    challenge = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=1),
        attempt_count=OTP_MAX_FAILED_ATTEMPTS,
        locked_at=None,
        consumed_at=None,
        token_key_id="active",
    )
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    monkeypatch.setattr(
        service, "_load_opaque_challenge", AsyncMock(return_value=challenge)
    )
    monkeypatch.setattr(
        service, "_resolve_recipient", AsyncMock(return_value=(user, user.email))
    )
    monkeypatch.setattr(
        service, "_load_bound_challenge", AsyncMock(return_value=challenge)
    )
    monkeypatch.setattr(service, "_rate_limit", AsyncMock())
    db = MagicMock()
    db.flush = AsyncMock()

    with (
        patch(
            "app.auth.mfa.recovery.verify_recovery_code",
            new_callable=AsyncMock,
            return_value=True,
        ) as verify_recovery_code,
        pytest.raises(MfaOtpRejected),
    ):
        await service.consume_recovery_opaque(
            db,
            challenge_token="opaque-token",
            code="valid-recovery-code",
            client_fingerprint=FINGERPRINT,
            client_ip=CLIENT_IP,
            login_session_identifier=SESSION,
            active_session_identifier=None,
            now=NOW,
        )

    verify_recovery_code.assert_not_awaited()
    db.flush.assert_not_awaited()
    assert challenge.state is ChallengeState.PENDING


@pytest.mark.asyncio
async def test_resend_rejects_pending_challenge_with_exhausted_attempt_budget() -> None:
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=MagicMock(),
    )
    user = SimpleNamespace(id=uuid.uuid4(), email="otp-state@example.test")
    challenge = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        method="email_otp",
        revision=1,
        token_key_id="active",
        token_digest="old-token-digest",
        recipient_digest=service._recipient_digest(key_id="active", email=user.email),
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=1),
        resend_available_at=NOW - timedelta(seconds=1),
        attempt_count=OTP_MAX_FAILED_ATTEMPTS,
    )
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(one_or_none=MagicMock(return_value=(challenge.id,))),
            MagicMock(),
        ]
    )
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    with pytest.raises(MfaOtpRejected):
        await service.resend(
            db,
            challenge_token="opaque-token",
            user_id=user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=CLIENT_IP,
            locale="en",
            now=NOW,
        )

    db.execute.assert_not_awaited()
    db.add_all.assert_not_called()
