"""Focused configuration regressions for the dedicated TOTP key ring."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import BaseModel, ValidationError

from app.core.config.mixins.mfa_settings import MfaSettingsMixin


class _MfaSettingsProbe(MfaSettingsMixin, BaseModel):
    environment: str = "production"
    app_process_role: str = "api"
    secret_key: str = ""
    spotify_token_secret: str = ""


def _fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.mark.parametrize(
    "malformation",
    (
        "missing-separator",
        "invalid-key-id",
        "empty-key",
        "key-whitespace",
        "duplicate-key-id",
    ),
)
def test_totp_keyring_rejects_malformed_key_id_pairs(malformation: str) -> None:
    generated_key = _fernet_key()
    malformed_entries = {
        "missing-separator": "entry-without-separator",
        "invalid-key-id": f"invalid/id:{generated_key}",
        "empty-key": "active:",
        "key-whitespace": f"active: {generated_key}",
        "duplicate-key-id": f"active:{generated_key},active:{_fernet_key()}",
    }

    with pytest.raises(ValidationError) as error:
        _MfaSettingsProbe(
            mfa_totp_encryption_keys=malformed_entries[malformation],
            mfa_totp_active_encryption_key_id="active",
        )

    assert "MFA_TOTP_ENCRYPTION_KEYS entries must use unique" in str(error.value)


def test_totp_active_key_id_rejects_invalid_identifier() -> None:
    with pytest.raises(ValidationError) as error:
        _MfaSettingsProbe(
            mfa_totp_encryption_keys=f"active:{_fernet_key()}",
            mfa_totp_active_encryption_key_id="invalid identifier",
        )

    assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID must be a valid key identifier" in str(
        error.value
    )


def test_totp_active_key_id_cannot_be_configured_without_a_keyring() -> None:
    with pytest.raises(ValidationError) as error:
        _MfaSettingsProbe(mfa_totp_active_encryption_key_id="active")

    assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID requires" in str(error.value)
    assert "MFA_TOTP_ENCRYPTION_KEYS" in str(error.value)


@pytest.mark.parametrize("active_key_id", ("", "unknown"))
def test_totp_keyring_requires_an_existing_active_key_id(active_key_id: str) -> None:
    with pytest.raises(ValidationError) as error:
        _MfaSettingsProbe(
            mfa_totp_encryption_keys=f"active:{_fernet_key()}",
            mfa_totp_active_encryption_key_id=active_key_id,
        )

    assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID must identify a configured" in str(
        error.value
    )
