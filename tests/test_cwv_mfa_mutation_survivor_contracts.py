"""Focused contracts for CWV and MFA survivors from the previous mutmut run.

The tests in this module pin externally meaningful behaviour at boundaries where
the broad domain suites previously allowed a mutation to survive.  They avoid
asserting generated implementation details except where an error message or
SQL predicate is itself part of the security contract.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql

from app.api import cwv as cwv_api
from app.api.auth import mfa as mfa_api
from app.auth.constants import MFA_METHOD_EMAIL_OTP, MFA_METHOD_TOTP
from app.auth.mfa import email_otp as email_otp_module
from app.auth.mfa import lifecycle as lifecycle_module
from app.auth.mfa.email_otp import MfaSecurityUnavailable
from app.auth.mfa.totp import _ct_verify_totp
from app.core import observability
from app.services import cwv
from app.services.cwv import CwvConfigurationError, CwvEnvelopeError, CwvRumBinding

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
SECRET = "cwv-signing-secret-with-at-least-32-bytes"  # pragma: allowlist secret
MFA_IP = "203.0.113.8"


def _binding(**overrides: object) -> CwvRumBinding:
    values: dict[str, object] = {
        "enabled": True,
        "signing_secret": SECRET,
        "release_sha": SHA,
        "frontend_image_digest": DIGEST,
        "deployment_run_id": 123,
        "deployment_run_attempt": 2,
        "deployment_url": "https://staging.example.edu",
        "allowed_origins": ("https://staging.example.edu",),
        "envelope_ttl_seconds": 300,
    }
    values.update(overrides)
    return CwvRumBinding(**values)


def _issued_envelope() -> str:
    token, _ = cwv.issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/dashboard",
        device_class="desktop",
        collector_principal_id="collector-one",
        gateway_session_id="gateway-session-one",
        now=NOW,
        nonce_factory=lambda: "nonce_abcdefghijklmnop",
    )
    return token


def test_cwv_api_binding_propagates_enabled_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API adapter must not turn enabled CWV collection into ``None``."""

    values = {
        "cwv_rum_enabled": True,
        "cwv_rum_signing_secret": SecretStr(SECRET),
        "cwv_release_sha": SHA,
        "cwv_frontend_image_digest": DIGEST,
        "cwv_deployment_run_id": 123,
        "cwv_deployment_run_attempt": 2,
        "cwv_deployment_url": "https://staging.example.edu",
        "cwv_allowed_origins": "https://staging.example.edu",
        "cwv_envelope_ttl_seconds": 300,
    }
    for name, value in values.items():
        monkeypatch.setattr(cwv_api.settings, name, value)

    binding = cwv_api._binding()

    assert binding.enabled is True


def test_cwv_binding_release_sha_error_message_is_stable() -> None:
    with pytest.raises(CwvConfigurationError) as exc_info:
        cwv._validate_binding(_binding(release_sha="not-a-commit"))

    assert str(exc_info.value) == "CWV release SHA is invalid"


def test_cwv_expiry_error_message_is_stable() -> None:
    with pytest.raises(CwvEnvelopeError) as exc_info:
        cwv.verify_envelope(
            _binding(), _issued_envelope(), now=NOW + timedelta(seconds=301)
        )

    assert str(exc_info.value) == "CWV envelope expired or is not yet valid"


def test_cwv_route_fragment_on_root_remains_in_core_group() -> None:
    """A fragment on the root path must be stripped before classification."""

    assert cwv.derive_route_group("/#fragment") == "core"


@pytest.mark.asyncio
async def test_email_challenge_forwards_resolved_client_ip_to_service() -> None:
    issued = SimpleNamespace(
        challenge_token="a" * 32,
        expires_at=NOW + timedelta(minutes=10),
        delivery_hint="s***@e***.edu",
        resend_available_at=NOW + timedelta(seconds=60),
        revision=2,
    )
    email_service = MagicMock()
    email_service.issue = AsyncMock(return_value=issued)
    login_service = MagicMock()
    login_service.get_email_otp_service.return_value = email_service
    request = SimpleNamespace(
        state=SimpleNamespace(active_session=SimpleNamespace(id="session-1"))
    )
    user = SimpleNamespace(id=uuid.UUID("22222222-2222-7222-8222-222222222222"))
    db = AsyncMock()

    with (
        patch.object(mfa_api, "extract_request_fingerprint", return_value="f" * 64),
        patch("app.core.ratelimit.resolve_client_ip", return_value=MFA_IP),
        patch("app.core.localization.resolve_locale", return_value="en"),
    ):
        await mfa_api._issue_email_challenge_for_session(
            flow="email_verification",
            request=request,
            db=db,
            login_service=login_service,
            user=user,
        )

    assert email_service.issue.await_args.kwargs["client_ip"] == MFA_IP


@pytest.mark.asyncio
async def test_disable_email_mfa_deletes_only_the_requesting_users_devices_and_preserves_totp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.UUID("11111111-1111-7111-8111-111111111111")
    locked_user = SimpleNamespace(
        id=user_id,
        email_mfa_enabled_at=NOW,
        mfa_default_method=MFA_METHOD_EMAIL_OTP,
        mfa_required=True,
        mfa_epoch=7,
    )
    request_user = SimpleNamespace(**vars(locked_user))
    locked_result = MagicMock()
    locked_result.scalar_one.return_value = locked_user
    delete_result = MagicMock(rowcount=2)
    db = AsyncMock()
    db.execute.side_effect = [locked_result, delete_result]

    async def refresh_with_totp(_db: object, *, user: object) -> str:
        user.mfa_default_method = MFA_METHOD_TOTP  # type: ignore[attr-defined]
        user.mfa_required = True  # type: ignore[attr-defined]
        return MFA_METHOD_TOTP

    monkeypatch.setattr(
        lifecycle_module, "refresh_user_mfa_preferences", refresh_with_totp
    )
    monkeypatch.setattr(
        lifecycle_module,
        "collect_mfa_session_revocations",
        AsyncMock(return_value=[]),
    )

    pending = await lifecycle_module.disable_email_mfa(db, user=request_user)

    assert pending == []
    assert request_user.mfa_default_method == MFA_METHOD_TOTP
    assert request_user.mfa_required is True
    assert request_user.email_mfa_enabled_at is None
    delete_statement = db.execute.await_args_list[1].args[0]
    compiled = delete_statement.compile(dialect=postgresql.dialect())
    assert "trusted_devices.user_id =" in str(compiled)
    assert "trusted_devices.user_id !=" not in str(compiled)
    assert user_id in compiled.params.values()


def test_email_key_ring_parser_preserves_delimiter_diagnostic_context() -> None:
    with pytest.raises(MfaSecurityUnavailable) as exc_info:
        email_otp_module._parse_key_ring("entry-without-delimiter")

    assert isinstance(exc_info.value.__context__, ValueError)
    assert str(exc_info.value.__context__) == (
        "key-ring entry must contain exactly one delimiter"
    )


def test_email_key_ring_parser_rejects_invalid_characters_before_permissive_decode() -> (
    None
):
    with pytest.raises(MfaSecurityUnavailable, match=r"^MFA service unavailable$"):
        # The two invalid bytes keep the encoded length at modulo 2.  A parser
        # that accidentally combines the character check with the modulo-1
        # check would let Python's permissive decoder accept this value.
        email_otp_module._parse_key_ring("active:$$YWJj")


def test_email_key_ring_parser_accepts_valid_modulo_two_encoding() -> None:
    assert email_otp_module._parse_key_ring("active:YWJjAA") == {"active": b"abc\x00"}


def test_otel_shutdown_uses_the_real_provider_for_legacy_fallback() -> None:
    provider = MagicMock()
    provider.shutdown.side_effect = [TypeError("legacy provider"), None]
    seen_annotations: list[object] = []

    def record_cast(annotation: object, value: object) -> object:
        seen_annotations.append(annotation)
        return value

    with patch.object(observability, "cast", side_effect=record_cast):
        observability._shutdown_otel_provider(provider)

    assert seen_annotations == [observability.Any, observability.Any]
    provider.shutdown.assert_has_calls(
        [call(timeout_millis=1200), call()],
    )


def test_ct_verify_totp_forwards_none_valid_window() -> None:
    with patch("app.auth.mfa.totp._ct_match_totp_timecode", return_value=123) as match:
        assert _ct_verify_totp("secret", "123456") is True

    match.assert_called_once_with("secret", "123456", valid_window=None)
