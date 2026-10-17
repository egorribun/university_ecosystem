"""Configuration contract for the account-wide TOTP attempt budget."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.security import SecuritySettings


def test_totp_attempt_limit_uses_positive_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MFA_TOTP_ATTEMPT_LIMIT", raising=False)

    settings = SecuritySettings(_env_file=None)

    assert settings.mfa_totp_attempt_limit == 5


def test_totp_attempt_limit_accepts_explicit_positive_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MFA_TOTP_ATTEMPT_LIMIT", raising=False)

    settings = SecuritySettings(_env_file=None, mfa_totp_attempt_limit=9)

    assert settings.mfa_totp_attempt_limit == 9


def test_totp_attempt_limit_loads_positive_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MFA_TOTP_ATTEMPT_LIMIT", "7")

    settings = SecuritySettings(_env_file=None)

    assert settings.mfa_totp_attempt_limit == 7


@pytest.mark.parametrize("raw_value", ["0", "-1"])
def test_totp_attempt_limit_rejects_nonpositive_environment_values(
    monkeypatch: pytest.MonkeyPatch, raw_value: str
) -> None:
    monkeypatch.setenv("MFA_TOTP_ATTEMPT_LIMIT", raw_value)

    with pytest.raises(ValidationError) as exc_info:
        SecuritySettings(_env_file=None)

    assert "MFA_TOTP_ATTEMPT_LIMIT must be greater than zero" in str(exc_info.value)
