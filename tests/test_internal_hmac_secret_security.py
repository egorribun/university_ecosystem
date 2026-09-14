"""Security contracts for the gateway-to-backend HMAC trust boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.security import SecuritySettings


def _production_settings(**overrides: str) -> SecuritySettings:
    """Build only the security settings needed by the production validators."""

    values = {
        "algorithm": "RS256",
        "secret_key": "application-signing-material-0123456789abcdef",  # pragma: allowlist secret
        "audit_log_secret": "audit-log-material-0123456789abcdef",  # pragma: allowlist secret
        "token_hmac_secret": "token-recovery-material-0123456789abcdef",  # pragma: allowlist secret
        "internal_hmac_secret": "internal-gateway-material-0123456789abcdef",  # pragma: allowlist secret
    }
    values.update(overrides)
    return SecuritySettings(**values)


@pytest.mark.parametrize(
    "weak_secret",
    [
        "a" * 32,
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


def test_development_internal_hmac_secret_keeps_compatibility_with_short_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")

    settings = SecuritySettings(internal_hmac_secret="dev-secret")

    assert settings.internal_hmac_secret == "dev-secret"  # pragma: allowlist secret
