"""Security contracts for the gateway-to-backend HMAC trust boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.security import (
    SecuritySettings,
    _validate_internal_hmac_secret_strength,
)


def _production_settings(**overrides: str) -> SecuritySettings:
    """Build only the security settings needed by the production validators."""

    values = {
        "algorithm": "RS256",
        "secret_key": "application-signing-material-0123456789abcdef",  # pragma: allowlist secret
        "audit_log_secret": "audit-log-material-0123456789abcdef",  # pragma: allowlist secret
        "token_hmac_secret": "token-recovery-material-0123456789abcdef",  # pragma: allowlist secret
        "internal_hmac_secret": "internal-gateway-material-0123456789abcdef",  # pragma: allowlist secret
        "internal_auth_token": "internal-route-token-0123456789abcdef",  # pragma: allowlist secret
    }
    values.update(overrides)
    return SecuritySettings(**values)


@pytest.mark.parametrize(
    "weak_secret",
    [
        "a" * 32,
        # Exactly 32 bytes but only two distinct bytes must still fail the
        # diversity guard; this kills the mutmut ``or`` -> ``and`` survivor.
        "A" * 31 + "B",
        "internal-hmac-secret-012345678901",
        "change-me-internal-hmac-secret-012345",
    ],
)
def test_production_internal_hmac_secret_rejects_weak_non_empty_values(
    monkeypatch: pytest.MonkeyPatch, weak_secret: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValidationError, match="INTERNAL_HMAC_SECRET"):
        _production_settings(internal_hmac_secret=weak_secret)


def test_production_internal_hmac_secret_rejects_missing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="INTERNAL_HMAC_SECRET MUST be set"):
        _production_settings(internal_hmac_secret="")


def test_production_internal_hmac_secret_accepts_random_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    configured = "6d4b4a4a-fd2f-4a74-a63a-746cc0f244f1/qX8!"  # pragma: allowlist secret
    settings = _production_settings(internal_hmac_secret=configured)

    assert settings.internal_hmac_secret == configured


def test_production_internal_hmac_secret_accepts_exactly_four_distinct_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Four distinct bytes are the lower boundary of the diversity guard."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    configured = "A" * 29 + "BCD"  # pragma: allowlist secret
    settings = _production_settings(internal_hmac_secret=configured)

    assert settings.internal_hmac_secret == configured


def test_development_internal_hmac_secret_keeps_compatibility_with_short_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")

    settings = SecuritySettings(internal_hmac_secret="dev-secret")

    assert settings.internal_hmac_secret == "dev-secret"  # pragma: allowlist secret


def test_internal_hmac_strength_rejects_short_material_before_entropy_checks() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes of entropy"):
        _validate_internal_hmac_secret_strength("short", label="INTERNAL_HMAC_SECRET")


def test_internal_hmac_strength_rejects_repeated_multi_byte_patterns() -> None:
    # Four distinct bytes bypass the diversity guard, so the repeated-pattern
    # regex must still reject a deterministic key made from a repeated block.
    with pytest.raises(ValueError, match="placeholder or repeated values"):
        _validate_internal_hmac_secret_strength(
            "abcd" * 8, label="INTERNAL_HMAC_SECRET"
        )


def test_internal_hmac_strength_uses_stable_repeated_value_error() -> None:
    """Keep the security validator's operator-facing error contract exact."""
    with pytest.raises(ValueError) as exc_info:
        _validate_internal_hmac_secret_strength(
            "abcd" * 8, label="INTERNAL_HMAC_SECRET"
        )

    assert str(exc_info.value) == (
        "INTERNAL_HMAC_SECRET must contain at least 32 bytes of entropy; "
        "placeholder or repeated values are not allowed"
    )
