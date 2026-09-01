"""Focused contracts for backend mutants found in the previous CI run.

The tests in this module exercise the observable security and reliability
contracts that were not represented in the normal domain suites.  They are
intentionally small so incremental mutation shards can classify these paths
without booting the full application stack.
"""

from __future__ import annotations

import builtins
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import status

from app.api.auth import login as login_api
from app.api.auth import mfa as mfa_api
from app.auth.constants import MFA_METHOD_EMAIL_OTP
from app.auth.mfa import email_otp as email_otp_module
from app.auth.mfa import totp
from app.auth.mfa.email_otp import EmailOtpService, MfaDeliveryError
from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
from app.models import ChallengeState
from app.services import cwv, cwv_retention, notification_queue

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
FINGERPRINT = "f" * 64
SESSION = "login-session-nonce"
IP = "203.0.113.8"


class _Limiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        del action, identifier


def _email_service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=_Limiter(),
    )


def _delivery_fixture(*, revision: int = 3) -> tuple[SimpleNamespace, SimpleNamespace]:
    delivery_id = uuid.UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa")
    challenge_id = uuid.UUID("bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb")
    delivery = SimpleNamespace(
        id=delivery_id,
        challenge_id=challenge_id,
        lease_token="lease-token",
        revision=revision,
        locale="en",
        message_id="<mfa-contract@example.edu>",
    )
    challenge = SimpleNamespace(
        id=challenge_id,
        method=MFA_METHOD_EMAIL_OTP,
        state=ChallengeState.PENDING,
        revision=revision,
        expires_at=NOW + timedelta(minutes=5),
    )
    return delivery, challenge


def test_login_mfa_rate_limit_error_preserves_zero_retry_after() -> None:
    error = RateLimitExceeded(RateLimitInfo(False, 0, 0))

    response = login_api._mfa_rate_limit_error(error, detail="MFA request rejected")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.detail == "MFA request rejected"
    assert response.headers == {"Retry-After": "0"}


def test_mfa_rate_limit_error_preserves_zero_retry_after() -> None:
    error = RateLimitExceeded(RateLimitInfo(False, 0, 0))

    response = mfa_api._mfa_rate_limit_error(error)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.detail == "MFA request rejected"
    assert response.headers == {"Retry-After": "0"}


@pytest.mark.asyncio
async def test_resolve_recipient_default_does_not_take_a_row_lock() -> None:
    user_id = uuid.UUID("11111111-1111-7111-8111-111111111111")
    user = SimpleNamespace(
        id=user_id,
        email="student@example.edu",
        is_active=True,
        email_verified_at=NOW,
        email_mfa_enabled_at=NOW,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    resolved_user, recipient = await EmailOtpService._resolve_recipient(
        db, user_id=user_id, flow="login"
    )

    assert resolved_user is user
    assert recipient == user.email
    statement = db.execute.await_args.args[0]
    assert statement._for_update_arg is None


@pytest.mark.asyncio
async def test_delivery_cancellation_requires_an_explicit_single_row_update() -> None:
    service = _email_service()
    delivery, _challenge = _delivery_fixture()
    claimed = SimpleNamespace(one_or_none=Mock(return_value=delivery.id))
    challenge_result = SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
    cancelled = SimpleNamespace()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[claimed, challenge_result, cancelled])
    db.get = AsyncMock(return_value=delivery)
    db.commit = AsyncMock()

    with patch.object(
        email_otp_module.secrets, "token_urlsafe", return_value="lease-token"
    ):
        with pytest.raises(MfaDeliveryError, match=r"^MFA delivery failed$"):
            await service.deliver(
                db, delivery_id=delivery.id, sender=AsyncMock(), now=NOW
            )

    # The missing ``rowcount`` must fail closed before the cancellation commit.
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_delivery_completion_requires_an_explicit_single_row_update() -> None:
    service = _email_service()
    delivery, challenge = _delivery_fixture()
    claimed = SimpleNamespace(one_or_none=Mock(return_value=delivery.id))
    challenge_result = SimpleNamespace(scalar_one_or_none=Mock(return_value=challenge))
    completed = SimpleNamespace()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[claimed, challenge_result, completed])
    db.get = AsyncMock(return_value=delivery)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    service._decrypt_delivery = MagicMock(  # type: ignore[method-assign]
        return_value={
            "email": "student@example.edu",
            "otp": "123456",
            "display_name": "Student",
        }
    )
    sender = AsyncMock()

    with patch.object(
        email_otp_module.secrets, "token_urlsafe", return_value="lease-token"
    ):
        with pytest.raises(MfaDeliveryError, match=r"^MFA delivery failed$"):
            await service.deliver(db, delivery_id=delivery.id, sender=sender, now=NOW)

    sender.send.assert_awaited_once()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_mfa_enablement_increments_zero_epoch_once() -> None:
    service = _email_service()
    user_id = uuid.UUID("11111111-1111-7111-8111-111111111111")
    challenge = SimpleNamespace(
        id=uuid.UUID("22222222-2222-7222-8222-222222222222"),
        user_id=user_id,
        flow="email_mfa_enablement",
        token_key_id="active",
        otp_key_id="active",
        recipient_digest="recipient",
        otp_digest="otp",
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=5),
        attempt_count=0,
        revision=1,
    )
    user = SimpleNamespace(
        id=user_id,
        email="student@example.edu",
        email_mfa_enabled_at=None,
        mfa_required=False,
        mfa_epoch=0,
        mfa_default_method=None,
    )
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(user, user.email)
    )
    service._load_bound_challenge = AsyncMock(  # type: ignore[method-assign]
        return_value=challenge
    )
    service._recipient_digest = MagicMock(return_value="recipient")  # type: ignore[method-assign]
    service._digest = MagicMock(return_value="otp")  # type: ignore[method-assign]
    consumed = SimpleNamespace(one_or_none=Mock(return_value=(challenge.id,)))
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[consumed, MagicMock()])
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await service.verify(
        db,
        challenge_token="opaque-token",
        code="123456",
        user_id=user_id,
        flow="email_mfa_enablement",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=NOW,
    )

    assert result is challenge
    assert user.mfa_epoch == 1
    assert user.mfa_required is True
    assert user.mfa_default_method == MFA_METHOD_EMAIL_OTP


def test_ct_verify_totp_forwards_the_explicit_valid_window() -> None:
    with patch.object(totp, "_ct_match_totp_timecode", return_value=123) as match:
        assert totp._ct_verify_totp("secret", "123456", valid_window=2) is True

    match.assert_called_once_with("secret", "123456", valid_window=2)


def _cwv_binding() -> cwv.CwvRumBinding:
    return cwv.CwvRumBinding(
        enabled=True,
        # Deterministic fixture only; never used outside this test process.
        signing_secret="cwv-contract-signing-secret-0123456789",  # pragma: allowlist secret
        release_sha="a" * 40,
        frontend_image_digest="sha256:" + "b" * 64,
        deployment_run_id=123,
        deployment_run_attempt=2,
        deployment_url="https://staging.example.edu",
        allowed_origins=("https://staging.example.edu",),
        envelope_ttl_seconds=300,
    )


def test_cwv_issue_envelope_uses_utc_for_default_clock_and_normalization() -> None:
    clock_calls: list[object] = []
    normalization_calls: list[object] = []

    class TrackingValue(datetime):
        def astimezone(self, tz: object = None) -> datetime:
            normalization_calls.append(tz)
            return self

    class TrackingClock:
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            clock_calls.append(tz)
            return TrackingValue(2026, 8, 25, 12, 0, tzinfo=UTC)

    with patch.object(cwv, "datetime", TrackingClock):
        _token, expires_at = cwv.issue_envelope(
            _cwv_binding(),
            origin="https://staging.example.edu",
            pathname="/dashboard",
            device_class="desktop",
            collector_principal_id="collector-one",
            gateway_session_id="session-one",
            nonce_factory=lambda: "nonce_abcdefghijklmnop",
        )

    assert clock_calls == [UTC]
    assert normalization_calls == [UTC]
    assert expires_at.tzinfo is UTC


@pytest.mark.asyncio
async def test_cwv_retention_missing_rowcount_defaults_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    db.execute.return_value = object()
    seen_defaults: list[object] = []
    builtin_getattr = builtins.getattr

    def tracking_getattr(obj: object, name: str, default: object = None) -> object:
        if name == "rowcount":
            seen_defaults.append(default)
        return builtin_getattr(obj, name, default)

    monkeypatch.setattr(cwv_retention, "getattr", tracking_getattr, raising=False)

    assert (
        await cwv_retention.cleanup_stale_cwv_observations(
            db=db, now=NOW, retention_days=7
        )
        == 0
    )
    assert seen_defaults == [0]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cwv_retention_owned_session_forwards_explicit_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An owned session must recurse with the same wall-clock instant."""
    outer_cleanup = cwv_retention.cleanup_stale_cwv_observations
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    nested_cleanup = AsyncMock(return_value=23)
    monkeypatch.setattr(cwv_retention, "async_session", lambda: context)
    monkeypatch.setattr(cwv_retention, "cleanup_stale_cwv_observations", nested_cleanup)

    result = await outer_cleanup(db=None, now=NOW, retention_days=7)

    assert result == 23
    nested_cleanup.assert_awaited_once_with(db=session, now=NOW, retention_days=7)


@pytest.mark.asyncio
async def test_retry_dead_letter_audit_records_canonical_batch_count() -> None:
    job_ids = [
        uuid.UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
        uuid.UUID("bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb"),
    ]
    jobs = [SimpleNamespace(id=job_id) for job_id in job_ids]
    lock = AsyncMock(return_value=jobs)
    audit = MagicMock()
    audit.record_domain_event = AsyncMock()
    db = AsyncMock()

    with patch.object(notification_queue, "_lock_dead_lettered_jobs", lock):
        result = await notification_queue.retry_dead_lettered_jobs(
            db,
            job_ids,
            audit=audit,
            actor_id=uuid.UUID("cccccccc-cccc-7ccc-8ccc-cccccccccccc"),
            now=NOW,
        )

    assert result == 2
    audit.record_domain_event.assert_awaited_once()
    assert audit.record_domain_event.await_args.kwargs["payload"] == {"batch_count": 2}
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
