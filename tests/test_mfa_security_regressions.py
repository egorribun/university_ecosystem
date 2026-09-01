from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.auth.mfa.challenge as challenge_module
import app.auth.mfa.email_otp as email_otp_module
import app.auth.mfa.lifecycle as lifecycle_module
import app.auth.mfa.recovery as recovery_module
import app.auth.mfa.trusted_device as trusted_device_module
import app.services.auth.mfa_coordinator as mfa_coordinator_module
from app.api.auth import login as login_api
from app.api.auth import mfa as mfa_api
from app.auth.constants import CHALLENGE_TYPE_TOTP_AUTH, MFA_METHOD_EMAIL_OTP
from app.auth.mfa.challenge import IssuedChallenge, get_challenge, issue_challenge
from app.auth.mfa.email_otp import (
    EmailOtpService,
    MfaDeliveryError,
    MfaNotEmailChallenge,
    MfaOtpRejected,
    MfaSecurityUnavailable,
)
from app.auth.mfa.lifecycle import (
    MfaSessionRevocation,
    disable_email_mfa,
    publish_mfa_session_revocations,
    record_mfa_success,
    refresh_user_mfa_preferences,
    reset_user_mfa,
)
from app.auth.mfa.recovery import generate_recovery_codes
from app.auth.mfa.totp import complete_totp_enrollment
from app.auth.schemas import (
    EmailOtpResendIn,
    LoginIn,
    MfaVerifyIn,
    TotpEnrollmentConfirmIn,
)
from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
from app.models import ActiveSession, ChallengeState, User
from app.services.auth.login_service import LoginService
from app.services.auth.mfa_coordinator import MfaCoordinator


class _NoopLimiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        del action, identifier


def _service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=_NoopLimiter(),
    )


def _email_challenge(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "flow": "login",
        "method": MFA_METHOD_EMAIL_OTP,
        "session_identifier": "login-session",
        "client_fingerprint": "f" * 64,
        "revision": 1,
        "token_key_id": "active",
        "token_digest": "expected-token-digest",
        "recipient_digest": "recipient-digest",
        "state": ChallengeState.PENDING,
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "attempt_count": 0,
        "locked_at": None,
        "consumed_at": None,
        "trust_device_requested": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_delivery_only_limiter_fails_closed() -> None:
    limiter = email_otp_module._DeliveryOnlyRateLimiter()

    with pytest.raises(MfaSecurityUnavailable, match="MFA service unavailable"):
        await limiter.enforce(action="verify", identifier="user:opaque")


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"delivery_keks": {}}, MfaSecurityUnavailable),
        ({"active_kek_id": "missing"}, MfaSecurityUnavailable),
        ({"active_hmac_key_id": "missing"}, MfaSecurityUnavailable),
        ({"hmac_keys": {"active": b"short"}}, MfaSecurityUnavailable),
        ({"delivery_keks": {"active": b"short"}}, MfaSecurityUnavailable),
    ],
)
def test_email_otp_service_rejects_incomplete_or_weak_keyrings(
    overrides: dict[str, object], error: type[Exception]
) -> None:
    kwargs: dict[str, object] = {
        "hmac_keys": {"active": b"h" * 32},
        "active_hmac_key_id": "active",
        "delivery_keks": {"active": b"k" * 32},
        "active_kek_id": "active",
        "rate_limiter": _NoopLimiter(),
    }
    kwargs.update(overrides)

    with pytest.raises(error):
        EmailOtpService(**kwargs)  # type: ignore[arg-type]


def test_email_otp_helpers_reject_ambiguous_or_unbound_inputs() -> None:
    service = _service()
    challenge = _email_challenge()

    assert email_otp_module.mask_email("not-an-address") == "***"
    with pytest.raises(MfaOtpRejected):
        email_otp_module._parse_challenge_id("invalid.short")
    with pytest.raises(MfaSecurityUnavailable):
        service._digest(
            key_id="retired",
            purpose="otp",
            challenge=challenge,  # type: ignore[arg-type]
            secret_value="123456",
        )
    with pytest.raises(MfaSecurityUnavailable):
        service._recipient_digest(key_id="retired", email="student@example.edu")
    with pytest.raises(MfaOtpRejected):
        service._validate_binding(
            challenge,  # type: ignore[arg-type]
            user_id=challenge.user_id,
            flow="step_up",
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
        )
    for values in (
        {
            "flow": "unknown",
            "session_identifier": "session",
            "client_fingerprint": "f" * 64,
        },
        {"flow": "login", "session_identifier": "", "client_fingerprint": "f" * 64},
        {
            "flow": "login",
            "session_identifier": "session",
            "client_fingerprint": "short",
        },
    ):
        with pytest.raises(ValueError):
            service._validate_issue_values(**values)


@pytest.mark.parametrize(
    ("flow", "user", "expected_email"),
    [
        (
            "email_verification",
            SimpleNamespace(
                is_active=True,
                email="pending@example.edu",
                email_verified_at=None,
                email_mfa_enabled_at=None,
            ),
            "pending@example.edu",
        ),
        (
            "email_mfa_enablement",
            SimpleNamespace(
                is_active=True,
                email="verified@example.edu",
                email_verified_at=datetime.now(UTC),
                email_mfa_enabled_at=None,
            ),
            "verified@example.edu",
        ),
        (
            "login",
            SimpleNamespace(
                is_active=True,
                email="mfa@example.edu",
                email_verified_at=datetime.now(UTC),
                email_mfa_enabled_at=datetime.now(UTC),
            ),
            "mfa@example.edu",
        ),
    ],
)
@pytest.mark.asyncio
async def test_resolve_recipient_enforces_flow_specific_email_state(
    flow: str, user: SimpleNamespace, expected_email: str
) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = result

    resolved_user, email = await EmailOtpService._resolve_recipient(
        db, user_id=uuid.uuid4(), flow=flow, for_update=True
    )

    assert resolved_user is user
    assert email == expected_email
    statement = db.execute.await_args.args[0]
    lock = statement._for_update_arg
    assert lock is not None and lock.nowait is False


@pytest.mark.parametrize(
    ("flow", "user"),
    [
        ("login", None),
        (
            "login",
            SimpleNamespace(
                is_active=False,
                email="inactive@example.edu",
                email_verified_at=None,
                email_mfa_enabled_at=None,
            ),
        ),
        (
            "email_mfa_enablement",
            SimpleNamespace(
                is_active=True,
                email="unverified@example.edu",
                email_verified_at=None,
                email_mfa_enabled_at=None,
            ),
        ),
        (
            "login",
            SimpleNamespace(
                is_active=True,
                email="disabled@example.edu",
                email_verified_at=datetime.now(UTC),
                email_mfa_enabled_at=None,
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_resolve_recipient_rejects_missing_or_ineligible_accounts(
    flow: str, user: SimpleNamespace | None
) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = result

    with pytest.raises(MfaOtpRejected):
        await EmailOtpService._resolve_recipient(db, user_id=uuid.uuid4(), flow=flow)


@pytest.mark.asyncio
async def test_bound_and_opaque_loaders_fail_closed_for_missing_or_mismatched_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    token = email_otp_module._generate_challenge_token(uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result
    db.scalar.return_value = None

    with pytest.raises(MfaOtpRejected):
        await service._load_bound_challenge(
            db,
            challenge_token=token,
            user_id=uuid.uuid4(),
            flow="login",
            session_identifier="login-session",
            client_fingerprint="f" * 64,
        )
    with pytest.raises(MfaOtpRejected):
        await service._user_id_from_token(db, token)
    with pytest.raises(MfaNotEmailChallenge):
        await service._load_opaque_challenge(
            db,
            challenge_token=token,
            client_fingerprint="f" * 64,
            login_session_identifier="login-session",
            active_session_identifier=None,
        )

    challenge = _email_challenge()
    result.scalar_one_or_none.return_value = challenge
    monkeypatch.setattr(service, "_digest", lambda **_: "wrong-digest")
    with pytest.raises(MfaOtpRejected):
        await service._load_opaque_challenge(
            db,
            challenge_token=token,
            client_fingerprint=challenge.client_fingerprint,
            login_session_identifier=challenge.session_identifier,
            active_session_identifier=None,
        )


@pytest.mark.asyncio
async def test_opaque_loader_rejects_fingerprint_and_session_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    challenge = _email_challenge()
    token = email_otp_module._generate_challenge_token(challenge.id)
    result = MagicMock()
    result.scalar_one_or_none.return_value = challenge
    db = AsyncMock()
    db.execute.return_value = result
    monkeypatch.setattr(service, "_digest", lambda **_: challenge.token_digest)

    with pytest.raises(MfaOtpRejected):
        await service._load_opaque_challenge(
            db,
            challenge_token=token,
            client_fingerprint="x" * 64,
            login_session_identifier=challenge.session_identifier,
            active_session_identifier=None,
        )
    with pytest.raises(MfaOtpRejected):
        await service._load_opaque_challenge(
            db,
            challenge_token=token,
            client_fingerprint=challenge.client_fingerprint,
            login_session_identifier=None,
            active_session_identifier=None,
        )


@pytest.mark.asyncio
async def test_recovery_opaque_locks_after_fifth_wrong_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    challenge = _email_challenge(attempt_count=4)
    user = SimpleNamespace(id=challenge.user_id)
    monkeypatch.setattr(
        service, "_load_opaque_challenge", AsyncMock(return_value=challenge)
    )
    monkeypatch.setattr(service, "_rate_limit", AsyncMock())
    monkeypatch.setattr(
        service,
        "_resolve_recipient",
        AsyncMock(return_value=(user, "student@example.edu")),
    )
    monkeypatch.setattr(
        service, "_load_bound_challenge", AsyncMock(return_value=challenge)
    )
    monkeypatch.setattr(
        service,
        "_recipient_digest",
        lambda **_: challenge.recipient_digest,
    )
    monkeypatch.setattr(
        recovery_module, "verify_recovery_code", AsyncMock(return_value=False)
    )
    db = AsyncMock()

    with pytest.raises(MfaOtpRejected):
        await service.consume_recovery_opaque(
            db,
            challenge_token="opaque-token",
            code="WRONG-CODE",
            client_fingerprint=challenge.client_fingerprint,
            client_ip="203.0.113.1",
            login_session_identifier=challenge.session_identifier,
            active_session_identifier=None,
            now=datetime.now(UTC),
        )

    assert challenge.attempt_count == 5
    assert challenge.state == ChallengeState.LOCKED
    assert challenge.locked_at is not None
    db.flush.assert_awaited_once()


def test_delivery_decryption_and_keyring_parsing_fail_closed() -> None:
    service = _service()
    delivery = SimpleNamespace(
        kek_id="missing",
        wrap_nonce=None,
        wrapped_dek=None,
        envelope_nonce=None,
        envelope_ciphertext=None,
    )

    with pytest.raises(MfaDeliveryError, match="MFA delivery failed"):
        service._decrypt_delivery(delivery)  # type: ignore[arg-type]
    with pytest.raises(MfaSecurityUnavailable):
        email_otp_module._parse_key_ring("invalid-key-entry")
    encoded = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    assert email_otp_module._parse_key_ring(f",active:{encoded},") == {
        "active": b"k" * 32
    }


def test_trusted_device_keyring_uses_stable_error_for_malformed_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trusted_device_module.settings, "environment", "staging")
    monkeypatch.setattr(
        trusted_device_module.settings, "mfa_trusted_device_hmac_keys", "malformed"
    )
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_active_hmac_key_id",
        "primary",
    )

    with pytest.raises(
        RuntimeError, match=r"^trusted-device key configuration invalid$"
    ):
        trusted_device_module._configured_keyring()


def test_delivery_decryption_rejects_partial_envelope_before_crypto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing envelope component must never reach the decryption primitive."""

    service = _service()
    delivery = SimpleNamespace(
        kek_id="active",
        wrap_nonce=b"n" * 12,
        wrapped_dek=b"wrapped",
        envelope_nonce=None,
        envelope_ciphertext=b"ciphertext",
    )
    monkeypatch.setattr(
        email_otp_module,
        "AESGCM",
        MagicMock(side_effect=AssertionError("partial envelope reached crypto")),
    )

    with pytest.raises(MfaDeliveryError, match="MFA delivery failed"):
        service._decrypt_delivery(delivery)  # type: ignore[arg-type]


def test_russian_email_rendering_escapes_display_name() -> None:
    subject, plain, body = EmailOtpService._render_email(
        otp="123456", display_name="<Студент>", locale="ru"
    )

    assert subject == "Код подтверждения"
    assert "<Студент>" in plain
    assert "&lt;Студент&gt;" in body
    assert "123456" in body


@pytest.mark.asyncio
async def test_naive_fresh_mfa_timestamp_is_normalized_before_recovery_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(recovery_module, "_utcnow", lambda: now)
    monkeypatch.setattr(
        recovery_module,
        "get_password_hash",
        AsyncMock(side_effect=lambda value, **_: f"hash:{value}"),
    )
    db = AsyncMock()
    db.add = MagicMock()
    user = SimpleNamespace(id=uuid.uuid4())

    codes = await generate_recovery_codes(
        db,
        user=user,  # type: ignore[arg-type]
        fresh_mfa_verified_at=(now - timedelta(minutes=1)).replace(tzinfo=None),
    )

    assert len(codes) == 10
    assert db.add.call_count == 10
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_totp_completion_rejects_missing_locked_enrollment() -> None:
    user_result = MagicMock()
    user_result.scalar_one.return_value = SimpleNamespace(mfa_epoch=0)
    enrollment_result = MagicMock()
    enrollment_result.scalars.return_value.first.return_value = None
    db = AsyncMock()
    db.execute.side_effect = [user_result, enrollment_result]
    enrollment = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await complete_totp_enrollment(
            db,
            enrollment=enrollment,  # type: ignore[arg-type]
            code="123456",
        )

    assert exc_info.value.status_code == 400


def test_challenge_properties_and_login_service_email_otp_delegation() -> None:
    challenge = _email_challenge(payload={"trust_device": True}, attempt_count=2)
    issued = IssuedChallenge(challenge=challenge, challenge_token="opaque")  # type: ignore[arg-type]
    coordinator = MagicMock()
    expected_service = _service()
    coordinator.get_email_otp_service.return_value = expected_service
    login_service = object.__new__(LoginService)
    login_service.mfa_coord = coordinator

    assert issued.attempt_count == 2
    assert issued.payload == {"trust_device": True}
    assert login_service.get_email_otp_service() is expected_service


@pytest.mark.asyncio
async def test_issue_challenge_rejects_incomplete_binding_before_database_write() -> (
    None
):
    db = AsyncMock()

    with pytest.raises(ValueError, match="complete MFA challenge binding"):
        await issue_challenge(
            db,
            user_id=uuid.uuid4(),
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            flow="login",
            session_identifier="",
            client_fingerprint="f" * 64,
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_challenge_rejects_missing_row_and_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = challenge_module._generate_challenge_token(uuid.uuid4())
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    with pytest.raises(HTTPException):
        await get_challenge(db, token=token, challenge_type=CHALLENGE_TYPE_TOTP_AUTH)

    challenge = _email_challenge(challenge_type=CHALLENGE_TYPE_TOTP_AUTH)
    result.scalars.return_value.first.return_value = challenge
    monkeypatch.setattr(challenge_module.hmac, "compare_digest", lambda *_: False)
    with pytest.raises(HTTPException):
        await get_challenge(db, token=token, challenge_type=CHALLENGE_TYPE_TOTP_AUTH)


@pytest.mark.asyncio
async def test_publish_revocations_keeps_database_authoritative_on_backend_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.auth.redis_session as redis_session_module

    monkeypatch.setattr(
        redis_session_module,
        "get_session_backend",
        AsyncMock(side_effect=RuntimeError("redis unavailable")),
    )
    revocation = MfaSessionRevocation(
        jti="session-jti",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    await publish_mfa_session_revocations([revocation])


@pytest.mark.parametrize(("ip", "user_agent"), [(None, "agent"), ("203.0.113.2", None)])
@pytest.mark.asyncio
async def test_trusted_device_creation_requires_complete_binding(
    ip: str | None, user_agent: str | None
) -> None:
    with pytest.raises(ValueError) as exc_info:
        await trusted_device_module.create_trusted_device_token(
            AsyncMock(),
            user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
            ip_address=ip,
            user_agent=user_agent,
        )
    assert str(exc_info.value) == "trusted-device binding is required"


def test_trusted_device_binding_digest_caps_user_agent_at_512_characters() -> None:
    key = b"trusted-device-binding-key-material!"
    prefix = "u" * 512

    # The first character after the contract boundary must not influence the
    # binding.  This protects against accidental truncation changes that would
    # make equivalent browser identities produce different bindings.
    assert trusted_device_module._binding_digest(key, "203.0.113.2", prefix + "A") == (
        trusted_device_module._binding_digest(key, "203.0.113.2", prefix + "B")
    )


def test_trusted_device_keyring_rejects_malformed_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_hmac_keys",
        "malformed",
    )

    with pytest.raises(RuntimeError, match="configuration invalid"):
        trusted_device_module._configured_keyring()


def test_trusted_device_keyring_unavailable_message_is_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_hmac_keys",
        f"primary:{encoded}",
    )
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_active_hmac_key_id",
        "missing",
    )

    with pytest.raises(RuntimeError) as exc_info:
        trusted_device_module._configured_keyring()
    assert str(exc_info.value) == "trusted-device key configuration unavailable"


def test_trusted_device_keyring_rejects_key_ids_with_ambiguous_delimiters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_hmac_keys",
        f"id:part:{encoded}",
    )
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_active_hmac_key_id",
        "id:part",
    )

    with pytest.raises(RuntimeError, match="configuration"):
        trusted_device_module._configured_keyring()


@pytest.mark.asyncio
async def test_trusted_device_consume_rejects_deleted_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trusted_device_module,
        "_configured_keyring",
        lambda: ({"active": b"k" * 32}, "active"),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    rotated = await trusted_device_module._consume_trusted_device_token(
        db,
        user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
        token="opaque-trusted-device-token",
        request_ip="203.0.113.2",
        request_ua="browser",
        rotate=True,
    )

    assert rotated is None
    statement = db.execute.await_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True
    lock = statement._for_update_arg
    assert lock is not None and lock.nowait is False


@pytest.mark.asyncio
async def test_trusted_device_consume_locks_device_with_waiting_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The device row lock must wait, preventing concurrent token use races."""

    key = b"trusted-device-test-key-material-32!"
    monkeypatch.setattr(
        trusted_device_module,
        "_configured_keyring",
        lambda: ({"active": key}, "active"),
    )
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=0)
    locked_user = MagicMock(id=user.id, mfa_epoch=0)
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = locked_user
    device_result = MagicMock()
    device_result.scalars.return_value.first.return_value = None
    db = MagicMock(execute=AsyncMock(side_effect=[user_result, device_result]))

    assert (
        await trusted_device_module._consume_trusted_device_token(
            db,
            user=user,  # type: ignore[arg-type]
            token="presented-token",
            request_ip="203.0.113.2",
            request_ua="browser",
            rotate=False,
        )
        is None
    )

    device_statement = db.execute.await_args_list[1].args[0]
    lock = device_statement._for_update_arg
    assert lock is not None and lock.nowait is False


@pytest.mark.asyncio
async def test_trusted_device_creation_persists_usage_time_and_binding_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = b"trusted-device-test-key-material-32!"
    monkeypatch.setattr(
        trusted_device_module,
        "_configured_keyring",
        lambda: ({"active": key}, "active"),
    )
    fixed_now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(trusted_device_module, "_utcnow", lambda: fixed_now)
    db = MagicMock(flush=AsyncMock())
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=4)
    ip_address = "203.0.113.22"
    user_agent = "UniversityBrowser/1.0"

    token, expires_at = await trusted_device_module.create_trusted_device_token(
        db,
        user=user,  # type: ignore[arg-type]
        ip_address=ip_address,
        user_agent=user_agent,
    )

    device = db.add.call_args.args[0]
    assert token
    assert expires_at > fixed_now
    assert device.last_used_at == fixed_now
    assert device.ip_hash == trusted_device_module._sha256_hex(ip_address)
    assert device.ua_hash == trusted_device_module._sha256_hex(user_agent)


def _api_request(*, active_session: object | None = None) -> MagicMock:
    request = MagicMock()
    request.state.active_session = active_session
    request.headers = {"user-agent": "coverage-browser"}
    request.cookies = {MfaCoordinator.PREAUTH_COOKIE_NAME: "login-session"}
    request.client.host = "203.0.113.5"
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "error", "expected_status"),
    [
        ("form", RateLimitExceeded(RateLimitInfo(False, 0, 11)), 429),
        ("form", MfaSecurityUnavailable(), 503),
        ("json", RateLimitExceeded(RateLimitInfo(False, 0, 13)), 429),
    ],
)
async def test_login_boundaries_rollback_security_failures(
    endpoint: str, error: Exception, expected_status: int
) -> None:
    service = AsyncMock()
    service.perform_login.side_effect = error
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        if endpoint == "form":
            await login_api.login.__dishka_orig_func__(
                MagicMock(),
                _api_request(),
                MagicMock(),
                service,
                db,
                False,
                SimpleNamespace(
                    username="student@example.edu",
                    password="valid-password",  # pragma: allowlist secret
                ),
            )
        else:
            await login_api.login_json.__dishka_orig_func__(
                LoginIn(
                    email="student@example.edu",
                    password="valid-password",  # pragma: allowlist secret
                ),
                MagicMock(),
                _api_request(),
                MagicMock(),
                service,
                db,
            )

    assert exc_info.value.status_code == expected_status
    if expected_status == 400:
        assert exc_info.value.detail == "MFA request rejected"
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["email_otp", "recovery_code"])
async def test_mfa_verify_requires_code_for_code_based_methods(method: str) -> None:
    payload = MfaVerifyIn(
        method=method,  # type: ignore[arg-type]
        challenge_token="a" * 32,
        code=None,
    )
    db = AsyncMock()
    request = _api_request()

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            payload,
            MagicMock(),
            request,
            MagicMock(),
            MagicMock(),
            db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "MFA verification failed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_email_mfa_verify_maps_security_outage_to_503() -> None:
    email_service = MagicMock()
    email_service.verify_opaque = AsyncMock(side_effect=MfaSecurityUnavailable())
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method="email_otp",
                challenge_token="a" * 32,
                code="123456",
            ),
            MagicMock(),
            _api_request(),
            MagicMock(),
            login_service,
            db,
        )

    assert exc_info.value.status_code == 503
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_mfa_challenge_rejects_deleted_user() -> None:
    challenge = _email_challenge()
    email_service = MagicMock()
    email_service.verify_opaque = AsyncMock(return_value=challenge)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()
    db.get.return_value = None

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method="email_otp",
                challenge_token="a" * 32,
                code="123456",
            ),
            MagicMock(),
            _api_request(),
            MagicMock(),
            login_service,
            db,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_trusted_device_issuance_failure_rolls_back_verified_challenge() -> None:
    challenge = _email_challenge(trust_device_requested=True)
    email_service = MagicMock()
    email_service.verify_opaque = AsyncMock(return_value=challenge)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=challenge.user_id)

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        patch.object(
            login_api.mfa,
            "create_trusted_device_token",
            AsyncMock(side_effect=RuntimeError("keyring unavailable")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method="email_otp",
                challenge_token="a" * 32,
                code="123456",
            ),
            MagicMock(),
            _api_request(),
            MagicMock(),
            login_service,
            db,
        )

    assert exc_info.value.status_code == 503
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_step_up_challenge_requires_active_session_at_completion() -> None:
    challenge = _email_challenge(flow="step_up")
    email_service = MagicMock()
    email_service.verify_opaque = AsyncMock(return_value=challenge)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=challenge.user_id)

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method="email_otp",
                challenge_token="a" * 32,
                code="123456",
            ),
            MagicMock(),
            _api_request(),
            MagicMock(),
            login_service,
            db,
        )

    assert exc_info.value.status_code == 400
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (email_otp_module.MfaOtpCooldown(), 429),
        (MfaSecurityUnavailable(), 503),
        (MfaOtpRejected(), 400),
    ],
)
async def test_resend_maps_domain_errors_without_leaking_account_state(
    error: Exception, expected_status: int
) -> None:
    email_service = MagicMock()
    email_service.resend_opaque = AsyncMock(side_effect=error)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()

    with (
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        patch.object(login_api, "resolve_locale", return_value="en"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.resend_email_mfa_challenge.__dishka_orig_func__(
            EmailOtpResendIn(challenge_token="a" * 32),
            _api_request(),
            login_service,
            db,
        )

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == (
        "MFA service unavailable" if expected_status == 503 else "MFA request rejected"
    )
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_email_factor_start_requires_an_active_session() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await mfa_api._issue_email_challenge_for_session(
            flow="email_verification",
            request=_api_request(),
            db=AsyncMock(),
            login_service=MagicMock(),
            user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "MFA request rejected"


@pytest.mark.asyncio
async def test_email_factor_start_handles_missing_active_session_attribute() -> None:
    """A request state without the optional session field is unauthenticated.

    ``getattr(..., None)`` is intentional at this boundary: middleware may
    provide a state object without installing ``active_session`` at all.  The
    endpoint must return the same safe 400 contract instead of leaking an
    ``AttributeError``.
    """

    request = _api_request()
    request.state = SimpleNamespace()
    with pytest.raises(HTTPException) as exc_info:
        await mfa_api._issue_email_challenge_for_session(
            flow="email_verification",
            request=request,
            db=AsyncMock(),
            login_service=MagicMock(),
            user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "MFA request rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [(MfaSecurityUnavailable(), 503), (MfaOtpRejected(), 400)],
)
async def test_email_factor_start_maps_security_domain_errors(
    error: Exception, expected_status: int
) -> None:
    email_service = MagicMock()
    email_service.issue = AsyncMock(side_effect=error)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()
    request = _api_request(active_session=SimpleNamespace(id=uuid.uuid4()))

    with (
        patch.object(mfa_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        patch("app.core.localization.resolve_locale", return_value="en"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mfa_api._issue_email_challenge_for_session(
            flow="email_mfa_enablement",
            request=request,
            db=db,
            login_service=login_service,
            user=SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == (
        "MFA service unavailable" if expected_status == 503 else "MFA request rejected"
    )
    db.rollback.assert_awaited_once()


def test_coordinator_builds_email_service_lazily_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _service()
    builder = MagicMock(return_value=expected)
    monkeypatch.setattr(email_otp_module, "build_configured_email_otp_service", builder)
    coordinator = MfaCoordinator(MagicMock(), MagicMock())

    assert coordinator.get_email_otp_service() is expected
    assert coordinator.get_email_otp_service() is expected
    builder.assert_called_once()
    limiter = builder.call_args.kwargs["rate_limiter"]
    assert isinstance(limiter, email_otp_module.RuntimeMfaRateLimiter)


@pytest.mark.asyncio
async def test_coordinator_collects_bound_email_challenge() -> None:
    issued = SimpleNamespace(
        challenge_token="a" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        delivery_hint="s***@e***.edu",
        resend_available_at=datetime.now(UTC) + timedelta(seconds=60),
        revision=2,
    )
    email_service = MagicMock()
    email_service.issue = AsyncMock(return_value=issued)
    repo = SimpleNamespace(db=AsyncMock())
    coordinator = MfaCoordinator(MagicMock(), repo, email_service)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid.uuid4())

    methods = await coordinator._collect_mfa_challenges(
        user,  # type: ignore[arg-type]
        "en",
        {MFA_METHOD_EMAIL_OTP: True},
        flow="step_up",
        session_identifier="bound-session",
    )

    assert len(methods) == 1
    assert methods[0].method == MFA_METHOD_EMAIL_OTP
    assert methods[0].revision == 2
    assert (
        email_service.issue.await_args.kwargs["session_identifier"] == "bound-session"
    )


@pytest.mark.asyncio
async def test_refresh_preferences_selects_verified_email_without_totp() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email_mfa_enabled_at=datetime.now(UTC),
        mfa_default_method=None,
        mfa_required=False,
    )
    totp_result = MagicMock()
    totp_result.scalars.return_value.first.return_value = None
    db = AsyncMock()
    db.execute.side_effect = [totp_result, MagicMock()]

    selected = await refresh_user_mfa_preferences(db, user=user)  # type: ignore[arg-type]

    assert selected == MFA_METHOD_EMAIL_OTP
    assert user.mfa_default_method == MFA_METHOD_EMAIL_OTP
    assert user.mfa_required is True
    assert db.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starting_epoch", "expected_epoch"),
    [(7, 8), (None, 1)],
)
async def test_disable_email_factor_advances_epoch_and_clears_preferences(
    starting_epoch: int | None,
    expected_epoch: int,
) -> None:
    from sqlalchemy.dialects import postgresql

    user_id = uuid.uuid4()
    locked_user = SimpleNamespace(
        id=user_id,
        email_mfa_enabled_at=datetime.now(UTC),
        mfa_default_method=MFA_METHOD_EMAIL_OTP,
        mfa_required=True,
        mfa_epoch=starting_epoch,
    )
    request_user = SimpleNamespace(**vars(locked_user))
    locked_result = MagicMock()
    locked_result.scalar_one.return_value = locked_user
    totp_result = MagicMock()
    totp_result.scalars.return_value.first.return_value = None
    db = AsyncMock()
    db.execute.side_effect = [
        locked_result,
        totp_result,
        MagicMock(),
        MagicMock(),
    ]

    with patch.object(
        lifecycle_module,
        "collect_mfa_session_revocations",
        AsyncMock(return_value=[]),
    ) as collect:
        pending = await disable_email_mfa(db, user=request_user)  # type: ignore[arg-type]

    assert pending == []
    assert locked_user.email_mfa_enabled_at is None
    assert locked_user.mfa_default_method is None
    assert locked_user.mfa_required is False
    assert locked_user.mfa_epoch == expected_epoch
    assert request_user.email_mfa_enabled_at is None
    assert request_user.mfa_required is False
    assert request_user.mfa_epoch == expected_epoch
    lock_statement = db.execute.await_args_list[0].args[0]
    assert "users.id" in str(lock_statement.whereclause)
    assert "users.id =" in str(lock_statement.whereclause)
    assert "users.id !=" not in str(lock_statement.whereclause)
    assert "SELECT users." in str(lock_statement.compile(dialect=postgresql.dialect()))
    assert user_id in lock_statement.compile().params.values()
    assert lock_statement._for_update_arg is not None
    assert lock_statement._for_update_arg.nowait is False
    collect.assert_awaited_once_with(db, user_id=user_id)
    db.flush.assert_awaited_once()
    delete_statements = [
        call.args[0]
        for call in db.execute.await_args_list
        if "trusted_devices" in str(call.args[0])
    ]
    assert len(delete_statements) == 1
    assert "trusted_devices.user_id" in str(delete_statements[0])


@pytest.mark.asyncio
async def test_reset_missing_account_by_id_is_idempotent() -> None:
    user_id = uuid.uuid4()
    missing = MagicMock()
    missing.scalar_one_or_none.return_value = None
    zero_rows = [SimpleNamespace(rowcount=0) for _ in range(5)]
    db = AsyncMock()
    db.execute.side_effect = [missing, *zero_rows]

    with patch.object(
        lifecycle_module,
        "collect_mfa_session_revocations",
        AsyncMock(return_value=[]),
    ) as collect:
        stats = await reset_user_mfa(db, user_id=user_id)

    assert stats.changed is False
    assert stats.fields_cleared is False
    assert stats.session_revocations == []
    collect.assert_awaited_once_with(db, user_id=user_id)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_existing_account_clears_request_security_state() -> None:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="mfa-reset@example.edu",
        hashed_password="hash",  # pragma: allowlist secret
        mfa_required=True,
        mfa_default_method=MFA_METHOD_EMAIL_OTP,
        mfa_last_verified_at=datetime.now(UTC),
        email_mfa_enabled_at=datetime.now(UTC),
        mfa_epoch=4,
    )
    assert user.trusted_devices == []
    locked = MagicMock()
    locked.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.side_effect = [
        locked,
        SimpleNamespace(rowcount=1),
        SimpleNamespace(rowcount=2),
        SimpleNamespace(rowcount=3),
        SimpleNamespace(rowcount=4),
        SimpleNamespace(rowcount=1),
    ]
    revocations = [
        MfaSessionRevocation(
            jti="session-jti", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
    ]

    with patch.object(
        lifecycle_module,
        "collect_mfa_session_revocations",
        AsyncMock(return_value=revocations),
    ):
        stats = await reset_user_mfa(db, user=user)

    assert stats.totp_deleted == 1
    assert stats.trusted_devices_revoked == 2
    assert stats.challenges_revoked == 3
    assert stats.recovery_codes_deleted == 4
    assert stats.fields_cleared is True
    assert stats.session_revocations == revocations
    assert user.mfa_required is False
    assert user.mfa_default_method is None
    assert user.email_mfa_enabled_at is None
    assert user.mfa_epoch == 5
    assert user.trusted_devices == []


@pytest.mark.asyncio
async def test_record_mfa_success_rejects_deleted_account() -> None:
    user = User(
        id=uuid.uuid4(),
        email="deleted@example.edu",
        hashed_password="hash",  # pragma: allowlist secret
    )
    missing_epoch = MagicMock()
    missing_epoch.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = missing_epoch

    with pytest.raises(RuntimeError, match="missing user"):
        await record_mfa_success(db, user=user, session=None, method="totp")

    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_mfa_success_without_session_updates_user_only() -> None:
    user = User(
        id=uuid.uuid4(),
        email="verified@example.edu",
        hashed_password="hash",  # pragma: allowlist secret
        mfa_epoch=1,
    )
    epoch = MagicMock()
    epoch.scalar_one_or_none.return_value = 3
    db = AsyncMock()
    db.execute.side_effect = [epoch, MagicMock()]

    updated = await record_mfa_success(db, user=user, session=None, method="totp")

    assert updated is user
    assert user.mfa_epoch == 3
    assert user.mfa_last_verified_at is not None
    assert db.execute.await_count == 2
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_mfa_success_updates_bound_session_and_dto() -> None:
    user_id = uuid.uuid4()
    updated_dto = SimpleNamespace(
        id=user_id, mfa_epoch=9, mfa_last_verified_at=datetime.now(UTC)
    )
    dto = SimpleNamespace(id=user_id, model_copy=MagicMock(return_value=updated_dto))
    session = ActiveSession(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=str(uuid.uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        signing_key="s" * 32,
        mfa_required=True,
        mfa_epoch=8,
    )
    epoch = MagicMock()
    epoch.scalar_one_or_none.return_value = 9
    db = AsyncMock()
    db.execute.side_effect = [epoch, MagicMock(), SimpleNamespace(rowcount=1)]
    method = "email_otp" + ("x" * 100)

    result = await record_mfa_success(
        db,
        user=dto,  # type: ignore[arg-type]
        session=session,
        method=method,
    )

    assert result is updated_dto
    dto.model_copy.assert_called_once()
    assert session.mfa_required is False
    assert session.mfa_method == method[:64]
    assert session.mfa_epoch == 9
    assert session.mfa_completed_at is not None
    assert session.mfa_verified_at == session.mfa_completed_at
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_mfa_success_rejects_inactive_bound_session() -> None:
    user = User(
        id=uuid.uuid4(),
        email="inactive-session@example.edu",
        hashed_password="hash",  # pragma: allowlist secret
    )
    session = ActiveSession(
        id=uuid.uuid4(),
        user_id=user.id,
        jti=str(uuid.uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        signing_key="s" * 32,
    )
    epoch = MagicMock()
    epoch.scalar_one_or_none.return_value = 2
    db = AsyncMock()
    db.execute.side_effect = [epoch, MagicMock(), SimpleNamespace(rowcount=0)]

    with pytest.raises(RuntimeError, match="inactive session"):
        await record_mfa_success(db, user=user, session=session, method="totp")

    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_factor_start_commits_and_returns_delivery_contract() -> None:
    issued = SimpleNamespace(
        challenge_token="a" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        delivery_hint="s***@e***.edu",
        resend_available_at=datetime.now(UTC) + timedelta(seconds=60),
        revision=4,
    )
    email_service = MagicMock()
    email_service.issue = AsyncMock(return_value=issued)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()
    session = SimpleNamespace(id=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4())
    request = _api_request(active_session=session)

    with (
        patch.object(
            mfa_api, "extract_request_fingerprint", return_value="f" * 64
        ) as extract_fingerprint,
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        patch(
            "app.core.localization.resolve_locale", return_value="en"
        ) as resolve_locale,
    ):
        result = await mfa_api._issue_email_challenge_for_session(
            flow="email_verification",
            request=request,
            db=db,
            login_service=login_service,
            user=user,  # type: ignore[arg-type]
        )

    resolve_locale.assert_called_once_with(request=request, user=user)
    extract_fingerprint.assert_called_once_with(request)
    assert email_service.issue.await_args.kwargs["session_identifier"] == str(
        session.id
    )

    assert result.method == MFA_METHOD_EMAIL_OTP
    assert result.challenge_token == issued.challenge_token
    assert result.delivery_hint == issued.delivery_hint
    assert result.resend_available_at == issued.resend_available_at
    assert result.attempt_count == 0
    assert result.attempt_limit == 5
    assert result.remaining_attempts == 5
    assert result.revision == 4
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "expected_flow"),
    [
        (mfa_api.start_email_verification, "email_verification"),
        (mfa_api.start_email_mfa_enablement, "email_mfa_enablement"),
    ],
)
async def test_email_factor_routes_preserve_their_security_flow(
    endpoint: object, expected_flow: str
) -> None:
    expected = MagicMock()
    helper = AsyncMock(return_value=expected)
    request = _api_request(active_session=SimpleNamespace(id=uuid.uuid4()))
    db = AsyncMock()
    login_service = MagicMock()
    user = SimpleNamespace(id=uuid.uuid4())

    with patch.object(mfa_api, "_issue_email_challenge_for_session", helper):
        result = await endpoint.__dishka_orig_func__(  # type: ignore[attr-defined]
            request,
            db,
            login_service,
            user,
        )

    assert result is expected
    assert helper.await_args.kwargs["flow"] == expected_flow
    assert helper.await_args.kwargs["request"] is request
    assert helper.await_args.kwargs["user"] is user


@pytest.mark.asyncio
async def test_disable_email_endpoint_publishes_revocations_and_audits() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), mfa_default_method=None, mfa_required=False)
    pending = [
        MfaSessionRevocation(
            jti="disabled-session",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    ]
    db = AsyncMock()
    audit = MagicMock()
    commit_and_publish = AsyncMock()

    with (
        patch.object(mfa_api.mfa, "disable_email_mfa", AsyncMock(return_value=pending)),
        patch.object(
            mfa_api,
            "_commit_and_publish_mfa_revocations",
            commit_and_publish,
        ),
    ):
        result = await mfa_api.disable_email_mfa_endpoint.__dishka_orig_func__(
            _api_request(), db, audit, user
        )

    assert result.disabled is True
    assert result.mfa_default_method is None
    assert result.mfa_required is False
    commit_and_publish.assert_awaited_once_with(db, pending)
    audit.log.assert_called_once()


@pytest.mark.asyncio
async def test_totp_confirmation_without_active_session_rolls_back() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    enrollment = SimpleNamespace(id=uuid.uuid4(), user_id=user.id)
    db = AsyncMock()
    db.get.return_value = enrollment
    audit = MagicMock()

    with (
        patch.object(
            mfa_api.mfa,
            "complete_totp_enrollment",
            AsyncMock(return_value=enrollment),
        ),
        patch.object(
            mfa_api.mfa,
            "refresh_user_mfa_preferences",
            AsyncMock(return_value="totp"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mfa_api.confirm_totp_enrollment.__dishka_orig_func__(
            TotpEnrollmentConfirmIn(enrollment_id=enrollment.id, code="123456"),
            _api_request(),
            db,
            audit,
            user,
        )

    assert exc_info.value.status_code == 400
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_step_up_rate_limit_rolls_back_without_partial_challenge() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), mfa_default_method=MFA_METHOD_EMAIL_OTP)
    login_service = MagicMock()
    login_service._resolve_mfa_capabilities = AsyncMock(
        return_value={MFA_METHOD_EMAIL_OTP: True, "totp": False}
    )
    login_service._collect_mfa_challenges = AsyncMock(
        side_effect=RateLimitExceeded(RateLimitInfo(False, 0, 17))
    )
    db = AsyncMock()

    with (
        patch("app.core.localization.resolve_locale", return_value="en"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mfa_api.request_step_up.__dishka_orig_func__(
            _api_request(active_session=SimpleNamespace(id=uuid.uuid4())),
            db,
            MagicMock(),
            login_service,
            user,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "17"}
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_mfa_verify_rejects_unknown_method_before_challenge_lookup() -> None:
    payload = MfaVerifyIn.model_construct(
        method="unknown", challenge_token="a" * 32, code="123456"
    )
    db = AsyncMock()

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await login_api.verify_mfa_challenge.__dishka_orig_func__(
            payload,
            MagicMock(),
            _api_request(),
            MagicMock(),
            MagicMock(),
            db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid MFA method"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_login_sets_trusted_cookie_and_finalizes_session() -> None:
    challenge = _email_challenge(flow="login", trust_device_requested=True)
    user = SimpleNamespace(id=challenge.user_id)
    email_service = MagicMock()
    email_service.verify_opaque = AsyncMock(return_value=challenge)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    expected = MagicMock()
    login_service.finalize_login = AsyncMock(return_value=expected)
    db = AsyncMock()
    db.get.return_value = user
    response = MagicMock()
    expires_at = datetime.now(UTC) + timedelta(days=30)

    with (
        patch.object(login_api, "get_current_user_optional", AsyncMock()),
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        patch.object(
            login_api.mfa,
            "create_trusted_device_token",
            AsyncMock(return_value=("trusted-token", expires_at)),
        ),
    ):
        result = await login_api.verify_mfa_challenge.__dishka_orig_func__(
            MfaVerifyIn(
                method=MFA_METHOD_EMAIL_OTP,
                challenge_token="a" * 32,
                code="123456",
            ),
            response,
            _api_request(),
            MagicMock(),
            login_service,
            db,
        )

    assert result is expected
    response.set_cookie.assert_called_once()
    assert response.set_cookie.call_args.args[1] == "trusted-token"
    assert response.set_cookie.call_args.kwargs["httponly"] is True
    assert response.set_cookie.call_args.kwargs["expires"] == expires_at
    login_service.finalize_login.assert_awaited_once()
    response.delete_cookie.assert_called_once()


@pytest.mark.asyncio
async def test_resend_email_challenge_commits_rotated_contract() -> None:
    issued = SimpleNamespace(
        challenge_token="b" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        resend_available_at=datetime.now(UTC) + timedelta(seconds=60),
        delivery_hint="s***@e***.edu",
        revision=5,
    )
    email_service = MagicMock()
    email_service.resend_opaque = AsyncMock(return_value=issued)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    db = AsyncMock()
    request = _api_request()
    request.headers["authorization"] = "Bearer step-up-token"
    request.cookies = {}
    active_session = SimpleNamespace(id=uuid.uuid4())

    async def bind_active_session(request_arg, token_arg, db_arg):
        assert request_arg is request
        assert token_arg == "step-up-token"
        assert db_arg is db
        request.state.active_session = active_session
        return None

    with (
        patch.object(
            login_api,
            "get_current_user_optional",
            AsyncMock(side_effect=bind_active_session),
        ) as load_optional_session,
        patch.object(login_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
        patch.object(login_api, "resolve_locale", return_value="en"),
    ):
        result = await login_api.resend_email_mfa_challenge.__dishka_orig_func__(
            EmailOtpResendIn(challenge_token="a" * 32),
            request,
            login_service,
            db,
        )

    assert result.challenge_token == "b" * 32
    assert result.revision == 5
    assert result.method == MFA_METHOD_EMAIL_OTP
    load_optional_session.assert_awaited_once()
    assert email_service.resend_opaque.await_args.kwargs[
        "active_session_identifier"
    ] == str(active_session.id)
    assert (
        email_service.resend_opaque.await_args.kwargs["login_session_identifier"]
        is None
    )
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_challenge_consumer_rejects_unknown_factor_fail_closed() -> None:
    challenge = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        challenge_type="unexpected-factor",
        session_id=None,
        flow="login",
        consumed_at=None,
        state=ChallengeState.PENDING,
    )
    locked = MagicMock()
    locked.scalars.return_value.first.return_value = SimpleNamespace(
        id=challenge.user_id
    )
    db = AsyncMock()
    db.execute.return_value = locked

    with (
        patch.object(
            challenge_module,
            "get_challenge",
            AsyncMock(side_effect=[challenge, challenge]),
        ),
        patch.object(
            challenge_module,
            "validate_challenge_binding",
            MagicMock(),
        ),
        patch.object(
            challenge_module,
            "_ensure_challenge_not_locked",
            AsyncMock(),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await challenge_module.consume_challenge(
            db,
            challenge_token="a" * 32,
            challenge_type="unexpected-factor",
            client_fingerprint="f" * 64,
        )

    assert exc_info.value.status_code == 400
    assert challenge.consumed_at is None
    assert challenge.state == ChallengeState.PENDING
    db.flush.assert_not_awaited()


def _smtp_settings(*, security: str) -> SimpleNamespace:
    return SimpleNamespace(
        smtp_host="smtp.example.edu",
        smtp_port=587,
        smtp_security=security,
        smtp_starttls=False,
        smtp_user="mailer",
        smtp_password="smtp-password",  # pragma: allowlist secret
        mail_from="security@example.edu",
    )


def test_smtp_sender_fails_closed_when_transport_is_unconfigured() -> None:
    settings = _smtp_settings(security="none")
    settings.smtp_host = ""
    settings.smtp_port = 0

    with (
        patch("app.core.config.settings", settings),
        pytest.raises(OSError, match="SMTP unavailable"),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_smtp_sender_applies_transport_security_and_authentication(
    security: str,
) -> None:
    settings = _smtp_settings(security=security)
    client = MagicMock()
    transport = MagicMock()
    transport.return_value.__enter__.return_value = client
    transport_name = "SMTP_SSL" if security == "ssl" else "SMTP"

    with (
        patch("app.core.config.settings", settings),
        patch.object(email_otp_module.smtplib, transport_name, transport),
        patch.object(
            email_otp_module.ssl, "create_default_context", return_value="tls"
        ),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    client.login.assert_called_once_with("mailer", "smtp-password")
    client.send_message.assert_called_once()
    message = client.send_message.call_args.args[0]
    assert message["To"] == "student@example.edu"
    assert next(name for name, _ in message.items() if name.lower() == "to") == "To"
    assert message["From"] == "security@example.edu"
    assert message["Message-ID"] == "<challenge@example.edu>"
    raw_headers = dict(message.raw_items())
    assert raw_headers["Message-ID"] == "<challenge@example.edu>"
    assert "message-id" not in raw_headers
    assert message.get_payload()[1].get_content_subtype() == "html"
    transport.assert_called_once_with(
        settings.smtp_host,
        settings.smtp_port,
        **({"context": "tls"} if security == "ssl" else {}),
        timeout=10,
    )
    if security == "starttls":
        assert client.ehlo.call_count == 2
        client.starttls.assert_called_once_with(context="tls")
    else:
        client.starttls.assert_not_called()


def test_smtp_sender_uses_safe_default_sender_address() -> None:
    settings = _smtp_settings(security="none")
    settings.mail_from = ""
    client = MagicMock()
    transport = MagicMock()
    transport.return_value.__enter__.return_value = client

    with (
        patch("app.core.config.settings", settings),
        patch.object(email_otp_module.smtplib, "SMTP", transport),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    message = client.send_message.call_args.args[0]
    assert message["From"] == "no-reply@example.com"


def test_smtp_sender_legacy_starttls_flag_selects_canonical_security_mode() -> None:
    settings = _smtp_settings(security="")
    settings.smtp_starttls = True
    client = MagicMock()
    transport = MagicMock()
    transport.return_value.__enter__.return_value = client

    with (
        patch("app.core.config.settings", settings),
        patch.object(email_otp_module.smtplib, "SMTP", transport),
        patch.object(
            email_otp_module.ssl, "create_default_context", return_value="tls"
        ),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    client.starttls.assert_called_once_with(context="tls")


def test_smtp_sender_redacts_transport_failure() -> None:
    settings = _smtp_settings(security="none")
    transport = MagicMock()
    client = transport.return_value.__enter__.return_value
    client.send_message.side_effect = email_otp_module.smtplib.SMTPException(
        "provider details"
    )

    with (
        patch("app.core.config.settings", settings),
        patch.object(email_otp_module.smtplib, "SMTP", transport),
        pytest.raises(OSError) as exc_info,
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="sensitive.student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    assert str(exc_info.value) == "SMTP unavailable"
    assert "sensitive.student" not in str(exc_info.value)
    assert "provider details" not in str(exc_info.value)


def test_smtp_sender_sends_without_authentication_when_credentials_are_absent() -> None:
    settings = _smtp_settings(security="none")
    settings.smtp_user = ""
    settings.smtp_password = ""
    client = MagicMock()
    transport = MagicMock()
    transport.return_value.__enter__.return_value = client

    with (
        patch("app.core.config.settings", settings),
        patch.object(email_otp_module.smtplib, "SMTP", transport),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    client.login.assert_not_called()
    client.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_async_smtp_sender_offloads_blocking_transport() -> None:
    sender = email_otp_module.SmtpMfaEmailSender()
    to_thread = AsyncMock()

    with patch("asyncio.to_thread", to_thread):
        await sender.send(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    to_thread.assert_awaited_once_with(
        sender._send_sync,
        to_email="student@example.edu",
        subject="Verification",
        plain="Code: 123456",
        html_body="<p>Code: 123456</p>",
        message_id="<challenge@example.edu>",
    )


@pytest.mark.asyncio
async def test_mfa_transport_protocol_declarations_are_awaitable() -> None:
    limiter_result = await email_otp_module.MfaRateLimiter.enforce(
        object(), action="verify", identifier="user:opaque"
    )
    sender_result = await email_otp_module.MfaEmailSender.send(
        object(),
        to_email="student@example.edu",
        subject="Verification",
        plain="Code: 123456",
        html="<p>Code: 123456</p>",
        message_id="<challenge@example.edu>",
    )

    assert limiter_result is None
    assert sender_result is None


@pytest.mark.asyncio
async def test_recovery_opaque_rejects_expired_email_challenge() -> None:
    service = _service()
    now = datetime.now(UTC)
    challenge = _email_challenge(
        flow="login",
        expires_at=now - timedelta(seconds=1),
    )
    recipient = "student@example.edu"
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(id=challenge.user_id), recipient)
    )
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = AsyncMock()

    with pytest.raises(MfaOtpRejected):
        await service.consume_recovery_opaque(
            db,
            challenge_token="a" * 32,
            code="recovery-code",
            client_fingerprint="f" * 64,
            client_ip="203.0.113.5",
            login_session_identifier="login-session",
            active_session_identifier=None,
            now=now,
        )

    assert challenge.state == ChallengeState.PENDING
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_opaque_consumes_challenge_once_after_valid_proof() -> None:
    service = _service()
    now = datetime.now(UTC)
    challenge = _email_challenge(flow="login")
    recipient = "student@example.edu"
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    user = SimpleNamespace(id=challenge.user_id)
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, recipient))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = AsyncMock()

    with patch.object(
        recovery_module, "verify_recovery_code", AsyncMock(return_value=True)
    ) as verify:
        result = await service.consume_recovery_opaque(
            db,
            challenge_token="a" * 32,
            code="recovery-code",
            client_fingerprint="f" * 64,
            client_ip="203.0.113.5",
            login_session_identifier="login-session",
            active_session_identifier=None,
            now=now,
        )

    assert result is challenge
    assert challenge.state == ChallengeState.CONSUMED
    assert challenge.consumed_at == now
    verify.assert_awaited_once_with(db, user=user, code="recovery-code")
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_rotates_trusted_cookie_with_secure_attributes() -> None:
    repo = SimpleNamespace(db=AsyncMock(), has_active_mfa=AsyncMock(return_value=True))
    coordinator = MfaCoordinator(MagicMock(), repo)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid.uuid4(), mfa_required=True)
    request = _api_request()
    request.cookies[trusted_device_module.settings.trusted_device_cookie_name] = (
        "old-trusted-token"
    )
    response = MagicMock()

    with (
        patch.object(
            mfa_coordinator_module.mfa,
            "verify_and_rotate_trusted_device_token",
            AsyncMock(return_value="rotated-trusted-token"),
        ) as rotate,
        patch("app.core.ratelimit.resolve_client_ip", return_value="203.0.113.5"),
    ):
        result = await coordinator.check_and_issue_challenges(
            user,  # type: ignore[arg-type]
            request,
            response,
            locale="en",
        )

    assert result is None
    rotate.assert_awaited_once()
    response.set_cookie.assert_called_once()
    assert response.set_cookie.call_args.args[1] == "rotated-trusted-token"
    assert response.set_cookie.call_args.kwargs["httponly"] is True
    assert response.set_cookie.call_args.kwargs["path"] == "/"


def test_trusted_device_keyring_decodes_configured_active_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = b"trusted-device-hmac-key-material!"
    encoded = base64.urlsafe_b64encode(key).decode().rstrip("=")
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_hmac_keys",
        f"primary:{encoded}",
    )
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_active_hmac_key_id",
        "primary",
    )

    keys, active = trusted_device_module._configured_keyring()

    assert active == "primary"
    assert keys == {"primary": key}


def test_trusted_device_keyring_preserves_multiple_comma_delimited_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Key rotation keeps every configured generation addressable."""

    primary = b"trusted-device-primary-key-material!"
    previous = b"trusted-device-previous-key-material"
    primary_encoded = base64.urlsafe_b64encode(primary).decode().rstrip("=")
    previous_encoded = base64.urlsafe_b64encode(previous).decode().rstrip("=")
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_hmac_keys",
        f"primary:{primary_encoded},previous:{previous_encoded}",
    )
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_active_hmac_key_id",
        "primary",
    )

    keys, active = trusted_device_module._configured_keyring()

    assert active == "primary"
    assert keys == {"primary": primary, "previous": previous}


def test_trusted_device_testing_keyring_uses_stable_fallback_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "x" * 32
    monkeypatch.setattr(trusted_device_module.settings, "environment", "testing")
    monkeypatch.setattr(trusted_device_module.settings, "secret_key", secret)
    monkeypatch.setattr(
        trusted_device_module.settings, "mfa_trusted_device_hmac_keys", ""
    )
    monkeypatch.setattr(
        trusted_device_module.settings,
        "mfa_trusted_device_active_hmac_key_id",
        "",
    )

    keys, active = trusted_device_module._configured_keyring()

    assert active == "test-primary"
    assert keys == {"test-primary": hashlib.sha256(secret.encode()).digest()}


@pytest.mark.asyncio
async def test_opaque_token_routes_to_its_embedded_user() -> None:
    service = _service()
    challenge_id = uuid.uuid4()
    expected_user_id = uuid.uuid4()
    db = AsyncMock()
    db.scalar.return_value = expected_user_id

    user_id = await service._user_id_from_token(
        db, email_otp_module._generate_challenge_token(challenge_id)
    )

    assert user_id == expected_user_id
    db.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_otp_rejects_without_flush_when_attempt_update_loses_race() -> None:
    service = _service()
    now = datetime.now(UTC)
    recipient = "student@example.edu"
    challenge = _email_challenge(otp_key_id="active", otp_digest=None, attempt_count=4)
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    challenge.otp_digest = service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=challenge,
        secret_value="123456",
    )
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(id=challenge.user_id), recipient)
    )
    service._load_bound_challenge = AsyncMock(  # type: ignore[method-assign]
        return_value=challenge
    )
    stale_update = MagicMock()
    stale_update.one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = stale_update

    with pytest.raises(MfaOtpRejected):
        await service.verify(
            db,
            challenge_token="a" * 32,
            code="000000",
            user_id=challenge.user_id,
            flow="login",
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
            client_ip="203.0.113.5",
            now=now,
        )

    attempt_update = db.execute.await_args.args[0]
    update_params = attempt_update.compile().params
    assert update_params["state"] is ChallengeState.LOCKED
    assert update_params["locked_at"] == now
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_correct_otp_rejects_when_atomic_consume_loses_race() -> None:
    service = _service()
    now = datetime.now(UTC)
    recipient = "student@example.edu"
    code = "123456"
    challenge = _email_challenge(otp_key_id="active", otp_digest=None)
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    challenge.otp_digest = service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=challenge,
        secret_value=code,
    )
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(id=challenge.user_id), recipient)
    )
    service._load_bound_challenge = AsyncMock(  # type: ignore[method-assign]
        return_value=challenge
    )
    stale_consume = MagicMock()
    stale_consume.one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = stale_consume

    with pytest.raises(MfaOtpRejected):
        await service.verify(
            db,
            challenge_token="a" * 32,
            code=code,
            user_id=challenge.user_id,
            flow="login",
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
            client_ip="203.0.113.5",
            now=now,
        )

    db.flush.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_opaque_wrong_code_records_nonterminal_attempt() -> None:
    service = _service()
    now = datetime.now(UTC)
    challenge = _email_challenge(flow="login", attempt_count=0)
    recipient = "student@example.edu"
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(id=challenge.user_id), recipient)
    )
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = AsyncMock()

    with (
        patch.object(
            recovery_module, "verify_recovery_code", AsyncMock(return_value=False)
        ),
        pytest.raises(MfaOtpRejected),
    ):
        await service.consume_recovery_opaque(
            db,
            challenge_token="a" * 32,
            code="wrong-recovery-code",
            client_fingerprint="f" * 64,
            client_ip="203.0.113.5",
            login_session_identifier="login-session",
            active_session_identifier=None,
            now=now,
        )

    assert challenge.attempt_count == 1
    assert challenge.state == ChallengeState.PENDING
    assert challenge.locked_at is None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flow", "initial_default"),
    [
        ("email_verification", None),
        ("email_mfa_enablement", None),
        ("email_mfa_enablement", "totp"),
    ],
)
async def test_verified_email_otp_applies_only_its_factor_side_effects(
    flow: str, initial_default: str | None
) -> None:
    service = _service()
    now = datetime.now(UTC)
    recipient = "student@example.edu"
    code = "123456"
    challenge = _email_challenge(
        flow=flow,
        otp_key_id="active",
        otp_digest=None,
    )
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    challenge.otp_digest = service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=challenge,
        secret_value=code,
    )
    user = SimpleNamespace(
        id=challenge.user_id,
        email_verified_at=None,
        email_mfa_enabled_at=None,
        mfa_required=False,
        mfa_epoch=2,
        mfa_default_method=initial_default,
    )
    service._resolve_recipient = AsyncMock(return_value=(user, recipient))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    consumed = MagicMock()
    consumed.one_or_none.return_value = (challenge.id,)
    db = AsyncMock()
    db.execute.side_effect = [consumed, MagicMock()]

    result = await service.verify(
        db,
        challenge_token="a" * 32,
        code=code,
        user_id=challenge.user_id,
        flow=flow,
        session_identifier=challenge.session_identifier,
        client_fingerprint=challenge.client_fingerprint,
        client_ip="203.0.113.5",
        now=now,
    )

    assert result is challenge
    if flow == "email_verification":
        assert user.email_verified_at == now
        assert user.email_mfa_enabled_at is None
        assert db.execute.await_count == 1
    else:
        assert user.email_verified_at is None
        assert user.email_mfa_enabled_at == now
        assert user.mfa_required is True
        assert user.mfa_epoch == 3
        assert user.mfa_default_method == (
            MFA_METHOD_EMAIL_OTP if initial_default is None else initial_default
        )
        assert db.execute.await_count == 2
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once_with(challenge)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["recipient", "state"])
async def test_resend_rejects_stale_or_recipient_mismatched_challenge(
    failure: str,
) -> None:
    service = _service()
    recipient = "student@example.edu"
    challenge = _email_challenge()
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=recipient
    )
    if failure == "recipient":
        challenge.recipient_digest = "wrong-recipient-digest"
    else:
        challenge.state = ChallengeState.CONSUMED
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(id=challenge.user_id), recipient)
    )
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = AsyncMock()

    with pytest.raises(MfaOtpRejected):
        await service.resend(
            db,
            challenge_token="a" * 32,
            user_id=challenge.user_id,
            flow=challenge.flow,
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
            client_ip="203.0.113.5",
            locale="en",
        )

    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "malformed_envelope",
    [
        ["student@example.edu", "123456"],
        {"email": 7, "otp": "123456"},
        {"email": "student@example.edu", "otp": 7, "display_name": "Student"},
    ],
)
def test_delivery_envelope_rejects_invalid_json_shape(
    malformed_envelope: object,
) -> None:
    service = _service()
    challenge = _email_challenge()
    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=datetime.now(UTC),
    )

    with (
        patch.object(email_otp_module.orjson, "loads", return_value=malformed_envelope),
        pytest.raises(MfaDeliveryError),
    ):
        service._decrypt_delivery(delivery)


def test_delivery_decryption_rejects_a_missing_wrap_nonce_before_crypto() -> None:
    service = _service()
    challenge = _email_challenge()
    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=datetime.now(UTC),
    )
    delivery.wrap_nonce = None

    with (
        patch.object(email_otp_module, "AESGCM") as aesgcm,
        pytest.raises(MfaDeliveryError),
    ):
        service._decrypt_delivery(delivery)

    aesgcm.assert_not_called()


@pytest.mark.asyncio
async def test_delivery_claim_failure_distinguishes_terminal_from_invalid_state() -> (
    None
):
    service = _service()
    delivery_id = uuid.uuid4()
    sender = AsyncMock()
    claim = MagicMock()
    claim.one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = claim
    db.scalar.return_value = "failed"

    with pytest.raises(MfaDeliveryError):
        await service.deliver(db, delivery_id=delivery_id, sender=sender)

    sender.send.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_rejects_lost_worker_lease_before_decryption() -> None:
    service = _service()
    delivery_id = uuid.uuid4()
    sender = AsyncMock()
    claim = MagicMock()
    claim.one_or_none.return_value = (delivery_id,)
    db = AsyncMock()
    db.execute.return_value = claim
    db.get.return_value = None

    with pytest.raises(MfaDeliveryError):
        await service.deliver(db, delivery_id=delivery_id, sender=sender)

    db.commit.assert_awaited_once()
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_cancellation_fails_closed_after_cas_loss() -> None:
    service = _service()
    now = datetime.now(UTC)
    challenge = _email_challenge(expires_at=now - timedelta(seconds=1))
    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=now,
    )
    delivery.lease_token = "worker-lease"
    claim = MagicMock()
    claim.one_or_none.return_value = (delivery.id,)
    challenge_result = MagicMock()
    challenge_result.scalar_one_or_none.return_value = challenge
    db = AsyncMock()
    db.execute.side_effect = [claim, challenge_result, SimpleNamespace(rowcount=0)]
    db.get.return_value = delivery
    sender = AsyncMock()

    with (
        patch.object(
            email_otp_module.secrets, "token_urlsafe", return_value="worker-lease"
        ),
        pytest.raises(MfaDeliveryError),
    ):
        await service.deliver(db, delivery_id=delivery.id, sender=sender, now=now)

    sender.send.assert_not_awaited()
    cancellation_statement = db.execute.await_args_list[2].args[0]
    compiled = cancellation_statement.compile()
    assert compiled.params["status"] == "cancelled"
    assert compiled.params["lease_token"] is None
    assert compiled.params["lease_expires_at"] is None


@pytest.mark.asyncio
async def test_delivery_cancels_when_challenge_expires_at_validation_boundary() -> None:
    """An OTP expiring at the validation instant is already unusable."""

    service = _service()
    challenge = _email_challenge()
    challenge.expires_at = datetime.now(UTC)
    now = challenge.expires_at
    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=now,
    )
    delivery.lease_token = "worker-lease"
    claim = SimpleNamespace(one_or_none=MagicMock(return_value=(delivery.id,)))
    challenge_result = SimpleNamespace(
        scalar_one_or_none=MagicMock(return_value=challenge)
    )
    cancellation = SimpleNamespace(rowcount=1)
    db = AsyncMock()
    db.execute.side_effect = [claim, challenge_result, cancellation]
    db.get.return_value = delivery
    sender = AsyncMock()

    with patch.object(
        email_otp_module.secrets, "token_urlsafe", return_value="worker-lease"
    ):
        await service.deliver(db, delivery_id=delivery.id, sender=sender, now=now)

    sender.send.assert_not_awaited()
    assert db.commit.await_count == 2
    cancellation_statement = db.execute.await_args_list[2].args[0]
    assert cancellation_statement.compile().params["status"] == "cancelled"


@pytest.mark.asyncio
async def test_delivery_completion_fails_closed_after_cas_loss() -> None:
    service = _service()
    now = datetime.now(UTC)
    challenge = _email_challenge(expires_at=now + timedelta(minutes=5))
    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=now,
    )
    delivery.lease_token = "worker-lease"
    claim = MagicMock()
    claim.one_or_none.return_value = (delivery.id,)
    challenge_result = MagicMock()
    challenge_result.scalar_one_or_none.return_value = challenge
    db = AsyncMock()
    db.execute.side_effect = [claim, challenge_result, SimpleNamespace(rowcount=0)]
    db.get.return_value = delivery
    sender = AsyncMock()

    with (
        patch.object(
            email_otp_module.secrets, "token_urlsafe", return_value="worker-lease"
        ),
        pytest.raises(MfaDeliveryError),
    ):
        await service.deliver(db, delivery_id=delivery.id, sender=sender, now=now)

    sender.send.assert_awaited_once()
    db.flush.assert_not_awaited()
    completion_statement = db.execute.await_args_list[2].args[0]
    # Completion is a lease CAS: a concurrent worker must not be able to mark
    # a row sent after its status has changed away from ``sending``.
    assert "mfa_email_deliveries.status" in str(completion_statement)
    assert "mfa_email_deliveries.lease_token" in str(completion_statement)


def test_configured_email_otp_service_round_trips_encrypted_delivery() -> None:
    hmac_key = base64.urlsafe_b64encode(b"h" * 32).decode().rstrip("=")
    delivery_key = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    settings = SimpleNamespace(
        mfa_email_otp_hmac_keys=f"primary:{hmac_key}",
        mfa_email_otp_active_hmac_key_id="primary",
        mfa_email_delivery_keks=f"delivery:{delivery_key}",
        mfa_email_delivery_active_kek_id="delivery",
    )
    challenge = _email_challenge()

    with patch("app.core.config.settings", settings):
        service = email_otp_module.build_configured_email_otp_service(
            rate_limiter=_NoopLimiter()
        )

    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=datetime.now(UTC),
    )
    assert service._decrypt_delivery(delivery) == {
        "email": "student@example.edu",
        "otp": "123456",
        "display_name": "Student",
    }


def test_delivery_service_rejects_empty_decryption_keyring() -> None:
    settings = SimpleNamespace(mfa_email_delivery_keks="")

    with (
        patch("app.core.config.settings", settings),
        pytest.raises(MfaSecurityUnavailable),
    ):
        email_otp_module.build_configured_email_delivery_service()
