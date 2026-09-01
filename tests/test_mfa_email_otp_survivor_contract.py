"""Focused contracts for mutation-sensitive email MFA boundaries.

These tests intentionally assert security-relevant values, not implementation
incidental details: the opaque identity bindings, outbox routing metadata,
challenge state transitions, and SMTP message envelope are public contracts of
the email-MFA boundary.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

import app.auth.mfa.email_otp as email_otp_module
from app.auth.constants import MFA_METHOD_EMAIL_OTP
from app.auth.mfa.email_otp import (
    EmailOtpService,
    MfaDeliveryError,
    MfaOtpRejected,
    MfaSecurityUnavailable,
    RuntimeMfaRateLimiter,
    build_configured_email_delivery_service,
    build_configured_email_otp_service,
)
from app.core.config import settings
from app.models import ChallengeState, StoredEvent

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
FINGERPRINT = "f" * 64
SESSION = "login-session-nonce"
IP = "203.0.113.8"


class _Limiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        del action, identifier


@pytest.fixture
def service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"active": b"h" * 32, "old": b"o" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32, "old": b"z" * 32},
        active_kek_id="active",
        rate_limiter=_Limiter(),
    )


def _challenge(
    *, user_id: uuid.UUID | None = None, flow: str = "step_up"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.UUID("11111111-1111-7111-8111-111111111111"),
        user_id=user_id or uuid.UUID("22222222-2222-7222-8222-222222222222"),
        flow=flow,
        method=MFA_METHOD_EMAIL_OTP,
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        revision=3,
        token_key_id="active",
        otp_key_id="active",
        token_digest="token-digest",
        otp_digest="otp-digest",
        recipient_digest="recipient-digest",
        state=ChallengeState.PENDING,
        expires_at=NOW + timedelta(minutes=5),
        resend_available_at=NOW,
        attempt_count=0,
        locked_at=None,
        consumed_at=None,
    )


def test_email_delivery_generates_fixed_size_aead_nonces(
    service: EmailOtpService,
) -> None:
    """Both AES-GCM nonces are 96-bit values, never caller-sized defaults."""

    challenge = SimpleNamespace(id=uuid.uuid4())

    with patch.object(
        email_otp_module.secrets,
        "token_bytes",
        side_effect=lambda size: b"n" * size,
    ) as token_bytes:
        delivery_row = service._build_delivery(
            challenge=challenge,  # type: ignore[arg-type]
            revision=1,
            email="student@example.edu",
            otp="123456",
            locale="en",
            display_name="Student",
            now=NOW,
        )

    assert [call.args for call in token_bytes.call_args_list] == [(12,), (12,)]
    assert len(delivery_row.envelope_nonce) == 12
    assert len(delivery_row.wrap_nonce) == 12
    assert delivery_row.created_at == NOW


@pytest.mark.parametrize("kek_length", [16, 24, 32])
def test_email_otp_constructor_accepts_only_aes_gcm_key_lengths(
    kek_length: int,
) -> None:
    """Delivery KEKs use exactly the AES-GCM key sizes supported by the cipher."""

    EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * kek_length},
        active_kek_id="active",
        rate_limiter=_Limiter(),
    )


def test_email_otp_constructor_rejects_non_aes_gcm_key_length() -> None:
    with pytest.raises(MfaSecurityUnavailable, match=r"^MFA service unavailable$"):
        EmailOtpService(
            hmac_keys={"active": b"h" * 32},
            active_hmac_key_id="active",
            delivery_keks={"active": b"k" * 25},
            active_kek_id="active",
            rate_limiter=_Limiter(),
        )


def test_mask_email_is_stable_for_tld_local_and_nested_domains() -> None:
    assert email_otp_module.mask_email("user@example.edu") == "u***@e***.edu"
    assert email_otp_module.mask_email("u@localhost") == "u***@l***"
    assert email_otp_module.mask_email("u@sub.example.edu") == "u***@s***.edu"
    assert email_otp_module.mask_email("not-an-address") == "***"


def test_key_ring_rejects_ambiguous_entries_with_multiple_delimiters() -> None:
    encoded = base64.urlsafe_b64encode(b"h" * 32).decode("ascii").rstrip("=")
    with pytest.raises(MfaSecurityUnavailable, match="MFA service unavailable"):
        # ``urlsafe_b64decode`` silently ignores the colon and can otherwise
        # accept this ambiguous entry, so the key/value delimiter must be
        # validated before decoding.
        email_otp_module._parse_key_ring(f"active:{encoded}:extra")


def test_key_ring_rejects_zero_length_decoded_keys_with_generic_error() -> None:
    """An empty decoded key is unavailable and never exposes parser details."""

    with (
        patch.object(email_otp_module, "_b64decode", return_value=b""),
        pytest.raises(MfaSecurityUnavailable, match=r"^MFA service unavailable$"),
    ):
        email_otp_module._parse_key_ring("active:AA==")


def test_key_ring_rejects_duplicate_identifiers_with_generic_error() -> None:
    """Parser details never cross the generic MFA security boundary."""

    with pytest.raises(
        MfaSecurityUnavailable, match=r"^MFA service unavailable$"
    ) as exc_info:
        email_otp_module._parse_key_ring("active:YWJj,active:ZGVm")

    assert isinstance(exc_info.value.__context__, ValueError)
    assert exc_info.value.__context__.args == ()


def test_issue_validation_has_explicit_inclusive_session_boundary_and_messages() -> (
    None
):
    EmailOtpService._validate_issue_values(
        flow="login", session_identifier="s" * 128, client_fingerprint=FINGERPRINT
    )
    with pytest.raises(ValueError, match=r"^invalid session identifier$"):
        EmailOtpService._validate_issue_values(
            flow="login", session_identifier="s" * 129, client_fingerprint=FINGERPRINT
        )
    with pytest.raises(ValueError, match=r"^unsupported MFA flow$"):
        EmailOtpService._validate_issue_values(
            flow="other", session_identifier=SESSION, client_fingerprint=FINGERPRINT
        )
    with pytest.raises(ValueError, match=r"^invalid client fingerprint$"):
        EmailOtpService._validate_issue_values(
            flow="login", session_identifier=SESSION, client_fingerprint="x"
        )


def test_digest_binds_user_and_challenge_identity() -> None:
    challenge = _challenge()
    service = EmailOtpService(
        hmac_keys={"active": b"h" * 32},
        active_hmac_key_id="active",
        delivery_keks={"active": b"k" * 32},
        active_kek_id="active",
        rate_limiter=_Limiter(),
    )
    digest = service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=challenge,  # type: ignore[arg-type]
        secret_value="123456",
    )
    expected = email_otp_module.hmac.new(
        b"h" * 32,
        email_otp_module._digest_message(
            purpose="email-otp",
            user_id=challenge.user_id,
            challenge_id=challenge.id,
            flow=challenge.flow,
            session_identifier=challenge.session_identifier,
            client_fingerprint=challenge.client_fingerprint,
            method=challenge.method,
            revision=challenge.revision,
            secret_value="123456",
        ),
        email_otp_module.hashlib.sha256,
    ).hexdigest()
    assert digest == expected
    assert digest != service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=SimpleNamespace(**{**vars(challenge), "user_id": uuid.uuid4()}),  # type: ignore[arg-type]
        secret_value="123456",
    )


def test_outbox_contains_canonical_challenge_identity_and_routing_contract() -> None:
    challenge_id = uuid.UUID("33333333-3333-7333-8333-333333333333")
    delivery_id = uuid.UUID("44444444-4444-7444-8444-444444444444")
    delivery = SimpleNamespace(
        id=delivery_id,
        challenge_id=challenge_id,
        template="mfa_email_otp",
        locale="ru",
        revision=2,
    )
    event = EmailOtpService._build_outbox(delivery)  # type: ignore[arg-type]
    assert isinstance(event, StoredEvent)
    assert event.event_type == "auth.mfa_email.requested"
    assert event.aggregate_type == "MfaChallenge"
    assert event.aggregate_id == str(challenge_id)
    assert event.aggregate_id_uuid == challenge_id
    assert event.subject == "auth.mfa.email.requested"
    assert event.payload == {
        "delivery_id": str(delivery_id),
        "template": "mfa_email_otp",
        "locale": "ru",
        "revision": 2,
    }


def test_render_email_without_display_name_has_exact_localized_greeting() -> None:
    subject, plain, html_body = EmailOtpService._render_email(
        otp="123456", display_name="", locale="ru"
    )
    assert subject == "Код подтверждения"
    assert plain == "Здравствуйте!\nКод подтверждения: 123456\nКод действует 10 минут."
    assert html_body == (
        "<p>Здравствуйте!<br>Код подтверждения: 123456<br>Код действует 10 минут.</p>"
    )


def test_runtime_rate_limiter_uses_action_and_identifier_namespace() -> None:
    limiter = RuntimeMfaRateLimiter()
    with (
        patch(
            "app.core.ratelimit.enforce_rate_limit", new_callable=AsyncMock
        ) as enforce,
        patch("app.core.ratelimit.get_default_strategy", return_value="mfa"),
    ):
        import asyncio

        asyncio.run(limiter.enforce(action="verify", identifier="user:abc"))
    enforce.assert_awaited_once_with(
        identifier="mfa-email:verify:user:abc",
        limit=5,
        window_seconds=600,
        strategy="mfa",
    )


def test_configured_builder_preserves_injected_limiter_and_worker_is_inert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded_hmac = base64.urlsafe_b64encode(b"h" * 32).decode("ascii").rstrip("=")
    encoded_kek = base64.urlsafe_b64encode(b"k" * 32).decode("ascii").rstrip("=")
    monkeypatch.setattr(settings, "mfa_email_otp_hmac_keys", f"active:{encoded_hmac}")
    monkeypatch.setattr(settings, "mfa_email_otp_active_hmac_key_id", "active")
    monkeypatch.setattr(settings, "mfa_email_delivery_keks", f"active:{encoded_kek}")
    monkeypatch.setattr(settings, "mfa_email_delivery_active_kek_id", "active")
    limiter = _Limiter()
    configured = build_configured_email_otp_service(rate_limiter=limiter)
    assert configured._rate_limiter is limiter
    worker = build_configured_email_delivery_service()
    assert worker._active_hmac_key_id == ""
    assert worker._hmac_keys == {}


@pytest.mark.asyncio
async def test_issue_binds_recipient_lookup_to_user_and_persists_outbox(
    service: EmailOtpService,
) -> None:
    """Issuance must keep the user identity in the row-lock lookup contract."""

    user_id = uuid.UUID("55555555-5555-7555-8555-555555555555")
    user = SimpleNamespace(id=user_id, email="student@example.edu")
    db = MagicMock()
    db.flush = AsyncMock()
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(user, user.email)
    )

    issued = await service.issue(
        db,
        user_id=user_id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="en",
        now=NOW,
    )

    assert issued.challenge_id is not None
    service._resolve_recipient.assert_awaited_once_with(  # type: ignore[attr-defined]
        db, user_id=user_id, flow="login", for_update=True
    )
    db.add_all.assert_called_once()
    added = db.add_all.call_args.args[0]
    assert len(added) == 3
    assert added[0].user_id == user_id
    assert added[0].session_id is None
    assert added[0].attempt_count == 0
    assert added[0].state is ChallengeState.PENDING
    assert added[0].trust_device_requested is False
    assert added[1].challenge_id == issued.challenge_id
    assert isinstance(added[2], StoredEvent)


@pytest.mark.asyncio
async def test_issue_without_explicit_clock_uses_utc_for_expiry_contract(
    service: EmailOtpService,
) -> None:
    """Implicit issue timestamps must remain timezone-aware UTC values."""

    user_id = uuid.UUID("55555555-5555-7555-8555-555555555555")
    user = SimpleNamespace(id=user_id, email="student@example.edu")
    db = MagicMock()
    db.flush = AsyncMock()
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        return_value=(user, user.email)
    )
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = NOW

    with patch.object(email_otp_module, "datetime", clock):
        issued = await service.issue(
            db,
            user_id=user_id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            locale="en",
        )

    clock.now.assert_called_once_with(UTC)
    assert issued.expires_at == NOW + timedelta(seconds=600)
    assert issued.resend_available_at == NOW + timedelta(seconds=60)
    added = db.add_all.call_args.args[0]
    assert added[0].created_at == NOW


@pytest.mark.asyncio
async def test_opaque_loader_selects_active_session_for_each_non_login_flow(
    service: EmailOtpService,
) -> None:
    token = email_otp_module._generate_challenge_token(_challenge().id)
    for flow, login_session, active_session in (
        ("login", SESSION, None),
        ("step_up", None, SESSION),
        ("email_verification", None, SESSION),
        ("email_mfa_enablement", None, SESSION),
    ):
        challenge = _challenge(flow=flow)
        token = email_otp_module._generate_challenge_token(challenge.id)
        service._digest = MagicMock(return_value="token-digest")  # type: ignore[method-assign]
        result = MagicMock()
        result.scalar_one_or_none.return_value = challenge
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        assert (
            await service._load_opaque_challenge(
                db,
                challenge_token=token,
                client_fingerprint=FINGERPRINT,
                login_session_identifier=login_session,
                active_session_identifier=active_session,
            )
            is challenge
        )


@pytest.mark.asyncio
async def test_verify_forwards_client_ip_to_rate_limiter(
    service: EmailOtpService,
) -> None:
    """Verify uses a UTC clock and binds abuse control to the caller IP."""

    user_id = uuid.UUID("88888888-8888-7888-8888-888888888888")
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(  # type: ignore[method-assign]
        side_effect=MfaOtpRejected()
    )

    clock = MagicMock(wraps=datetime)
    clock.now.return_value = NOW
    with (
        patch.object(email_otp_module, "datetime", clock),
        pytest.raises(MfaOtpRejected),
    ):
        await service.verify(
            MagicMock(),
            challenge_token="opaque-token",
            code="123456",
            user_id=user_id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
        )

    clock.now.assert_called_once_with(UTC)
    service._rate_limit.assert_awaited_once_with(  # type: ignore[attr-defined]
        action="verify", user_id=user_id, client_ip=IP
    )


@pytest.mark.asyncio
async def test_resend_opaque_preserves_the_bound_session_identifier(
    service: EmailOtpService,
) -> None:
    challenge = _challenge(flow="step_up")
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    expected = MagicMock()
    service.resend = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    result = await service.resend_opaque(
        MagicMock(),
        challenge_token="opaque-token",
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        locale="en",
        login_session_identifier=None,
        active_session_identifier=SESSION,
        now=NOW,
    )

    assert result is expected
    assert service.resend.await_args.kwargs["challenge_token"] == "opaque-token"
    assert (
        service.resend.await_args.kwargs["session_identifier"]
        == challenge.session_identifier
    )


@pytest.mark.asyncio
async def test_resend_rate_limits_with_the_resend_action_before_loading_state(
    service: EmailOtpService,
) -> None:
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(side_effect=MfaOtpRejected())  # type: ignore[method-assign]

    with pytest.raises(MfaOtpRejected):
        await service.resend(
            MagicMock(),
            challenge_token="opaque-token",
            user_id=_challenge().user_id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            locale="en",
            now=NOW,
        )

    service._rate_limit.assert_awaited_once_with(  # type: ignore[attr-defined]
        action="resend", user_id=_challenge().user_id, client_ip=IP
    )


@pytest.mark.asyncio
async def test_resend_without_explicit_clock_uses_utc_and_rotates_expiry(
    service: EmailOtpService,
) -> None:
    from sqlalchemy.dialects import postgresql

    challenge = _challenge()
    user = SimpleNamespace(id=challenge.user_id, email="student@example.edu")
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    challenge.resend_available_at = NOW - timedelta(seconds=1)
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    won = SimpleNamespace(one_or_none=Mock(return_value=(challenge.id,)))
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[won, MagicMock()])
    db.flush = AsyncMock()
    clock = MagicMock(wraps=datetime)
    rotated_at = NOW + timedelta(seconds=60)
    clock.now.return_value = rotated_at

    with patch.object(email_otp_module, "datetime", clock):
        issued = await service.resend(
            db,
            challenge_token="opaque-token",
            user_id=user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            locale="en",
        )

    clock.now.assert_called_once_with(UTC)
    assert issued.expires_at == rotated_at + timedelta(seconds=600)
    assert issued.resend_available_at == rotated_at + timedelta(seconds=60)
    rotation_statement = db.execute.await_args_list[0].args[0]
    compiled_rotation = rotation_statement.compile(dialect=postgresql.dialect())
    assert compiled_rotation.params["token_digest"] == challenge.token_digest
    assert compiled_rotation.params["token_key_id"] == "active"
    assert compiled_rotation.params["resend_available_at"] == rotated_at + timedelta(
        seconds=60
    )
    assert "mfa_challenges.id =" in str(rotation_statement.whereclause)
    cancelled_statement = db.execute.await_args_list[1].args[0]
    assert "mfa_email_deliveries.challenge_id =" in str(cancelled_statement.whereclause)


@pytest.mark.asyncio
async def test_verify_rejects_an_exhausted_challenge_before_digest_or_mutation(
    service: EmailOtpService,
) -> None:
    challenge = _challenge()
    user = SimpleNamespace(id=challenge.user_id, email="student@example.edu")
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    challenge.otp_digest = service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=challenge,  # type: ignore[arg-type]
        secret_value="123456",
    )
    challenge.otp_key_id = "active"
    challenge.attempt_count = 5
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = MagicMock()

    with pytest.raises(MfaOtpRejected, match=r"^MFA verification failed$"):
        await service.verify(
            db,
            challenge_token="opaque-token",
            code="123456",
            user_id=user.id,
            flow="login",
            session_identifier=SESSION,
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            now=NOW,
        )

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_verify_consumes_challenge_with_checked_at_persisted(
    service: EmailOtpService,
) -> None:
    """Successful OTP verification persists the exact consumption timestamp."""

    from sqlalchemy.dialects import postgresql

    challenge = _challenge()
    user = SimpleNamespace(id=challenge.user_id, email="student@example.edu")
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    challenge.otp_digest = service._digest(
        key_id="active",
        purpose="email-otp",
        challenge=challenge,  # type: ignore[arg-type]
        secret_value="123456",
    )
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    consumed = MagicMock()
    consumed.one_or_none.return_value = SimpleNamespace(id=challenge.id)
    db = MagicMock(execute=AsyncMock(return_value=consumed), flush=AsyncMock())
    db.refresh = AsyncMock()

    await service.verify(
        db,
        challenge_token="opaque-token",
        code="123456",
        user_id=user.id,
        flow="login",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=NOW,
    )

    statement = db.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "consumed_at" in str(statement)
    assert "mfa_challenges.attempt_count <" in str(statement.whereclause)
    assert "mfa_challenges.attempt_count <=" not in str(statement.whereclause)
    assert NOW in compiled.params.values()


@pytest.mark.asyncio
async def test_verify_opaque_forwards_explicit_now_to_bound_verifier(
    service: EmailOtpService,
) -> None:
    challenge = _challenge()
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service.verify = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    db = MagicMock()
    checked_at = NOW + timedelta(seconds=7)
    result = await service.verify_opaque(
        db,
        challenge_token="opaque-token",
        code="123456",
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        login_session_identifier=None,
        active_session_identifier=SESSION,
        now=checked_at,
    )
    assert result is challenge
    service.verify.assert_awaited_once_with(
        db,
        challenge_token="opaque-token",
        code="123456",
        user_id=challenge.user_id,
        flow=challenge.flow,
        session_identifier=challenge.session_identifier,
        client_fingerprint=FINGERPRINT,
        client_ip=IP,
        now=checked_at,
    )


@pytest.mark.asyncio
async def test_recovery_opaque_forwards_all_binding_arguments_and_locks_at_expiry_boundary(
    service: EmailOtpService,
) -> None:
    user = SimpleNamespace(
        id=uuid.UUID("55555555-5555-7555-8555-555555555555"), email="u@example.edu"
    )
    challenge = _challenge(user_id=user.id)
    challenge.recipient_digest = service._recipient_digest(
        key_id="active", email=user.email
    )
    service._load_opaque_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._resolve_recipient = AsyncMock(return_value=(user, user.email))  # type: ignore[method-assign]
    service._load_bound_challenge = AsyncMock(return_value=challenge)  # type: ignore[method-assign]
    service._rate_limit = AsyncMock()  # type: ignore[method-assign]
    db = MagicMock()
    db.flush = AsyncMock()
    with patch(
        "app.auth.mfa.recovery.verify_recovery_code",
        new_callable=AsyncMock,
        return_value=True,
    ) as verify_recovery:
        consumed = await service.consume_recovery_opaque(
            db,
            challenge_token="opaque-token",
            code="RECOVERY-CODE",
            client_fingerprint=FINGERPRINT,
            client_ip=IP,
            login_session_identifier=None,
            active_session_identifier=SESSION,
            now=NOW,
        )
    assert consumed is challenge
    service._resolve_recipient.assert_awaited_once_with(
        db, user_id=user.id, flow="step_up", for_update=True
    )
    service._load_bound_challenge.assert_awaited_once_with(
        db,
        challenge_token="opaque-token",
        user_id=user.id,
        flow="step_up",
        session_identifier=SESSION,
        client_fingerprint=FINGERPRINT,
    )
    verify_recovery.assert_awaited_once_with(db, user=user, code="RECOVERY-CODE")
    assert challenge.state == ChallengeState.CONSUMED

    # Equality with expiry is already invalid; accepting it would make the
    # strict ``<=`` boundary mutation observable.
    challenge.state = ChallengeState.PENDING
    challenge.consumed_at = None
    service._load_opaque_challenge.reset_mock()
    service._resolve_recipient.reset_mock()
    service._load_bound_challenge.reset_mock()
    with patch(
        "app.auth.mfa.recovery.verify_recovery_code",
        new_callable=AsyncMock,
        return_value=True,
    ) as verify_recovery:
        challenge.expires_at = NOW
        with pytest.raises(MfaOtpRejected, match=r"^MFA verification failed$"):
            await service.consume_recovery_opaque(
                db,
                challenge_token="opaque-token",
                code="RECOVERY-CODE",
                client_fingerprint=FINGERPRINT,
                client_ip=IP,
                login_session_identifier=None,
                active_session_identifier=SESSION,
                now=NOW,
            )
    verify_recovery.assert_not_awaited()


def test_smtp_missing_either_host_or_port_fails_closed_and_preserves_headers() -> None:
    smtp_settings = SimpleNamespace(
        smtp_host="smtp.example.edu",
        smtp_port=587,
        smtp_security="none",
        smtp_starttls=False,
        smtp_user="mailer",
        smtp_password="",
        mail_from="security@example.edu",
    )
    for attr, value in (("smtp_host", ""), ("smtp_port", 0)):
        setattr(smtp_settings, attr, value)
        with (
            patch("app.core.config.settings", smtp_settings),
            pytest.raises(OSError, match=r"^SMTP unavailable$"),
        ):
            email_otp_module.SmtpMfaEmailSender._send_sync(
                to_email="student@example.edu",
                subject="Verification",
                plain="Code: 123456",
                html_body="<p>Code: 123456</p>",
                message_id="<challenge@example.edu>",
            )
        setattr(smtp_settings, attr, 587 if attr == "smtp_port" else "smtp.example.edu")

    client = MagicMock()
    transport = MagicMock()
    transport.return_value.__enter__.return_value = client
    with (
        patch("app.core.config.settings", smtp_settings),
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
    assert message["Subject"] == "Verification"
    raw_headers = dict(message.raw_items())
    assert raw_headers["Subject"] == "Verification"
    assert "SUBJECT" not in raw_headers
    assert message["From"] == "security@example.edu"
    assert message["To"] == "student@example.edu"
    assert message["Message-ID"] == "<challenge@example.edu>"
    assert "from" not in raw_headers
    assert "FROM" not in raw_headers
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    # Keep the MIME subtype canonical.  ``EmailMessage.get_content_type``
    # lowercases it, so inspect the wire header to catch an accidental
    # ``text/HTML`` regression as well.
    assert html_part["Content-Type"].split(";", 1)[0] == "text/html"
    client.login.assert_called_once_with("mailer", "")


def test_smtp_none_security_fallback_is_explicitly_unauthenticated() -> None:
    smtp_settings = SimpleNamespace(
        smtp_host="smtp.example.edu",
        smtp_port=587,
        smtp_security="",
        smtp_starttls=False,
        smtp_user="",
        smtp_password="",
        mail_from="security@example.edu",
    )
    client = MagicMock()
    transport = MagicMock()
    transport.return_value.__enter__.return_value = client
    with (
        patch("app.core.config.settings", smtp_settings),
        patch.object(email_otp_module.smtplib, "SMTP", transport),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )

    client.starttls.assert_not_called()
    transport.assert_called_once_with("smtp.example.edu", 587, timeout=10)


def test_smtp_rejects_an_unknown_transport_mode_before_network_io() -> None:
    """A malformed transport setting must never silently downgrade to plaintext."""

    smtp_settings = SimpleNamespace(
        smtp_host="smtp.example.edu",
        smtp_port=587,
        smtp_security="unsupported",
        smtp_starttls=False,
        smtp_user="",
        smtp_password="",
        mail_from="security@example.edu",
    )
    with (
        patch("app.core.config.settings", smtp_settings),
        patch.object(email_otp_module.smtplib, "SMTP") as smtp,
        pytest.raises(OSError, match=r"^SMTP unavailable$"),
    ):
        email_otp_module.SmtpMfaEmailSender._send_sync(
            to_email="student@example.edu",
            subject="Verification",
            plain="Code: 123456",
            html_body="<p>Code: 123456</p>",
            message_id="<challenge@example.edu>",
        )
    smtp.assert_not_called()


def test_decrypt_delivery_defaults_missing_display_name_to_empty_string(
    service: EmailOtpService,
) -> None:
    challenge = _challenge()
    delivery = service._build_delivery(
        challenge=challenge,  # type: ignore[arg-type]
        revision=challenge.revision,
        email="student@example.edu",
        otp="123456",
        locale="en",
        display_name="Student",
        now=NOW,
    )
    with patch.object(
        email_otp_module.orjson,
        "loads",
        return_value={"email": "student@example.edu", "otp": "123456"},
    ):
        envelope = service._decrypt_delivery(delivery)

    assert envelope == {
        "email": "student@example.edu",
        "otp": "123456",
        "display_name": "",
    }


@pytest.mark.asyncio
async def test_delivery_completion_requires_exactly_one_row_and_forwards_rendered_subject(
    service: EmailOtpService,
) -> None:
    from sqlalchemy.dialects import postgresql

    delivery_id = uuid.UUID("66666666-6666-7666-8666-666666666666")
    challenge_id = uuid.UUID("77777777-7777-7777-8777-777777777777")
    delivery = SimpleNamespace(
        id=delivery_id,
        challenge_id=challenge_id,
        lease_token="lease-token",
        revision=3,
        locale="en",
        message_id="<mfa@example.edu>",
    )
    challenge = SimpleNamespace(
        id=challenge_id,
        method=MFA_METHOD_EMAIL_OTP,
        state=ChallengeState.PENDING,
        revision=3,
        expires_at=NOW + timedelta(minutes=5),
    )
    claimed = SimpleNamespace(
        one_or_none=Mock(return_value=SimpleNamespace(id=delivery_id))
    )
    challenge_result = SimpleNamespace(scalar_one_or_none=Mock(return_value=challenge))
    completed = SimpleNamespace(rowcount=None)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[claimed, challenge_result, completed])
    db.commit = AsyncMock()
    db.get = AsyncMock(return_value=delivery)
    db.flush = AsyncMock()
    sender = AsyncMock()
    service._decrypt_delivery = MagicMock(  # type: ignore[method-assign]
        return_value={
            "email": "student@example.edu",
            "otp": "123456",
            "display_name": "Student",
        }
    )
    service._render_email = MagicMock(  # type: ignore[method-assign]
        return_value=("Expected subject", "Expected plain", "<p>Expected</p>")
    )
    with (
        patch.object(
            email_otp_module.secrets, "token_urlsafe", return_value="lease-token"
        ) as token_urlsafe,
        pytest.raises(MfaDeliveryError, match=r"^MFA delivery failed$"),
    ):
        await service.deliver(db, delivery_id=delivery_id, sender=sender, now=NOW)
    token_urlsafe.assert_called_once_with(32)
    claim_statement = db.execute.await_args_list[0].args[0]
    compiled_claim = claim_statement.compile(dialect=postgresql.dialect())
    assert "lease_expires_at <=" in str(compiled_claim)
    lease_predicate = next(
        clause
        for clause in claim_statement.whereclause.clauses
        if "lease_expires_at" in str(clause)
    )
    assert "mfa_email_deliveries.status =" in str(lease_predicate)
    assert " AND " in str(lease_predicate)
    assert compiled_claim.params["attempt_count_1"] == 1
    assert db.get.await_args is not None
    assert db.get.await_args.kwargs["populate_existing"] is True
    challenge_query = db.execute.await_args_list[1].args[0]
    assert challenge_query.get_execution_options()["populate_existing"] is True
    challenge_lock = challenge_query._for_update_arg
    assert challenge_lock is not None and challenge_lock.nowait is False
    sender.send.assert_awaited_once_with(
        to_email="student@example.edu",
        subject="Expected subject",
        plain="Expected plain",
        html="<p>Expected</p>",
        message_id="<mfa@example.edu>",
    )
    completion = db.execute.await_args_list[-1].args[0]
    assert "mfa_email_deliveries.status" in str(completion)
    assert "mfa_email_deliveries.lease_token" in str(completion)
    where_clause = str(completion.whereclause)
    assert "mfa_email_deliveries.id =" in where_clause
    assert "mfa_email_deliveries.id !=" not in where_clause
    assert "mfa_email_deliveries.lease_token =" in where_clause


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "sending"])
async def test_delivery_claim_loss_is_idempotent_for_sent_or_active_work(
    service: EmailOtpService,
    status: str,
) -> None:
    delivery_id = uuid.uuid4()
    claim = SimpleNamespace(one_or_none=Mock(return_value=None))
    db = MagicMock(
        execute=AsyncMock(return_value=claim),
        scalar=AsyncMock(return_value=status),
        commit=AsyncMock(),
    )
    sender = AsyncMock()

    await service.deliver(db, delivery_id=delivery_id, sender=sender, now=NOW)

    sender.send.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_failure_emits_the_canonical_retryable_event(
    service: EmailOtpService,
) -> None:
    delivery_id = uuid.UUID("88888888-8888-7888-8888-888888888888")
    challenge_id = uuid.UUID("99999999-9999-7999-8999-999999999999")
    delivery = SimpleNamespace(
        id=delivery_id,
        challenge_id=challenge_id,
        lease_token="lease-token",
        revision=1,
        locale="en",
        message_id="<mfa-failure@example.edu>",
    )
    challenge = SimpleNamespace(
        id=challenge_id,
        method=MFA_METHOD_EMAIL_OTP,
        state=ChallengeState.PENDING,
        revision=1,
        expires_at=NOW + timedelta(minutes=5),
    )
    claimed = SimpleNamespace(one_or_none=Mock(return_value=(delivery_id,)))
    challenge_result = SimpleNamespace(scalar_one_or_none=Mock(return_value=challenge))
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[claimed, challenge_result, MagicMock()])
    db.get = AsyncMock(return_value=delivery)
    db.commit = AsyncMock()
    sender = AsyncMock()
    sender.send.side_effect = OSError("smtp unavailable")
    service._decrypt_delivery = MagicMock(  # type: ignore[method-assign]
        return_value={
            "email": "student@example.edu",
            "otp": "123456",
            "display_name": "Student",
        }
    )

    with (
        patch.object(
            email_otp_module.secrets, "token_urlsafe", return_value="lease-token"
        ),
        patch.object(email_otp_module.logger, "error") as logger_error,
        pytest.raises(MfaDeliveryError),
    ):
        await service.deliver(db, delivery_id=delivery_id, sender=sender, now=NOW)

    logger_error.assert_called_once_with(
        "mfa_email_delivery_failed", extra={"delivery_id": str(delivery_id)}
    )
    retry_statement = db.execute.await_args_list[-1].args[0]
    assert retry_statement.compile().params["status"] == "pending"
    retry_sql = str(retry_statement)
    assert "status=:status" in retry_sql
    assert "lease_token=:lease_token" in retry_sql
    assert "lease_expires_at=:lease_expires_at" in retry_sql
    retry_where = str(retry_statement.whereclause)
    assert "mfa_email_deliveries.id =" in retry_where
    assert "mfa_email_deliveries.id !=" not in retry_where
    assert "mfa_email_deliveries.lease_token =" in retry_where


@pytest.mark.asyncio
async def test_delivery_decrypt_failure_logs_delivery_id_for_retry_diagnostics(
    service: EmailOtpService,
) -> None:
    delivery_id = uuid.UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa")
    challenge_id = uuid.UUID("bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb")
    delivery = SimpleNamespace(
        id=delivery_id,
        challenge_id=challenge_id,
        lease_token="lease-token",
        revision=1,
        locale="en",
        message_id="<mfa-decrypt-failure@example.edu>",
    )
    challenge = SimpleNamespace(
        id=challenge_id,
        method=MFA_METHOD_EMAIL_OTP,
        state=ChallengeState.PENDING,
        revision=1,
        expires_at=NOW + timedelta(minutes=5),
    )
    claimed = SimpleNamespace(one_or_none=Mock(return_value=(delivery_id,)))
    challenge_result = SimpleNamespace(scalar_one_or_none=Mock(return_value=challenge))
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[claimed, challenge_result, MagicMock()])
    db.commit = AsyncMock()
    db.get = AsyncMock(return_value=delivery)
    service._decrypt_delivery = MagicMock(side_effect=MfaDeliveryError())  # type: ignore[method-assign]

    with (
        patch.object(
            email_otp_module.secrets, "token_urlsafe", return_value="lease-token"
        ),
        patch.object(email_otp_module.logger, "error") as logger_error,
        pytest.raises(MfaDeliveryError),
    ):
        await service.deliver(db, delivery_id=delivery_id, sender=AsyncMock(), now=NOW)

    logger_error.assert_called_once_with(
        "mfa_email_delivery_failed", extra={"delivery_id": str(delivery_id)}
    )
    retry_statement = db.execute.await_args_list[-1].args[0]
    retry_values = retry_statement.compile().params
    assert retry_values["status"] == "pending"
    assert retry_values["lease_token"] is None
    assert retry_values["lease_expires_at"] is None


def test_rejected_error_is_enumeration_safe_and_exact() -> None:
    assert str(MfaOtpRejected()) == "MFA verification failed"


@pytest.mark.asyncio
async def test_recovery_code_verification_uses_waiting_row_lock() -> None:
    """Concurrent recovery-code checks must wait instead of failing with NOWAIT."""

    from app.auth.mfa.recovery import verify_recovery_code

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    user = SimpleNamespace(id=uuid.uuid4())

    assert await verify_recovery_code(db, user=user, code="unused") is False  # type: ignore[arg-type]

    statement = db.execute.await_args.args[0]
    lock = statement._for_update_arg
    assert lock is not None
    assert lock.nowait is False
