"""Utilities for encrypting sensitive application data."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import settings
from app.core.logging import get_logger

_logger = get_logger(__name__)


class SpotifyEncryptionError(RuntimeError):
    """Raised when Spotify token encryption fails."""


class TotpEncryptionError(RuntimeError):
    """Raised when a TOTP enrollment secret cannot be safely encrypted or read."""


def _normalize_secret(secret: str) -> str:
    value = secret.strip()
    if not value:
        raise SpotifyEncryptionError("SPOTIFY_TOKEN_SECRET contains an empty entry")
    # ``Fernet`` will validate the key format; propagate errors with more context.
    try:
        Fernet(value.encode("utf-8"))
    except Exception as exc:  # RZ-22-01-JUSTIFIED: convert-to-domain — wraps cryptography errors into SpotifyEncryptionError (reviewed TD-27-04)
        raise SpotifyEncryptionError(
            "Invalid SPOTIFY_TOKEN_SECRET entry; expected a Fernet key"
        ) from exc
    return value


@lru_cache(maxsize=4)
def _build_cipher(raw_secret: str) -> Fernet | MultiFernet:
    secrets = [
        _normalize_secret(item) for item in raw_secret.split(",") if item.strip()
    ]
    if not secrets:
        raise SpotifyEncryptionError("SPOTIFY_TOKEN_SECRET is not configured")
    ciphers = [Fernet(secret.encode("utf-8")) for secret in secrets]
    if len(ciphers) == 1:
        return ciphers[0]
    return MultiFernet(ciphers)


def _derive_spotify_fallback_key(secret_key: str) -> str:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _derive_default_secret() -> str:
    """Derive a deterministic Fernet key from the primary app secret.

    When ``SPOTIFY_TOKEN_SECRET`` is not explicitly configured we fall back to a key
    derived from :setting:`secret_key`. This keeps development environments working
    out of the box while still requiring a strong base secret.
    """

    primary = settings.secret_key.strip()
    if not primary:
        raise SpotifyEncryptionError("SPOTIFY_TOKEN_SECRET is not configured")
    return _derive_spotify_fallback_key(primary)


def _get_cipher() -> Fernet | MultiFernet:
    raw = settings.spotify_token_secret.strip()
    if not raw:
        raw = _derive_default_secret()
    return _build_cipher(raw)


def _derive_totp_default_key() -> str:
    """Derive a stable local-only key distinct from Spotify's fallback key."""
    primary = settings.secret_key.strip()
    if not primary:
        raise TotpEncryptionError("MFA_TOTP_ENCRYPTION_KEYS is not configured")
    digest = hmac.digest(
        primary.encode("utf-8"),
        b"university-ecosystem:mfa-totp-encryption:v1",
        "sha256",
    )
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _validated_totp_fernet_key(value: str) -> tuple[bytes, Fernet]:
    """Return the validated key material and cipher for any accepted encoding."""
    try:
        encoded = value.encode("ascii")
        key_material = base64.urlsafe_b64decode(encoded)
        cipher = Fernet(encoded)
    except (UnicodeEncodeError, ValueError, binascii.Error):
        raise ValueError("Invalid Fernet key") from None
    return key_material, cipher


def _ensure_totp_active_key_independent(raw_keyring: str, active_key_id: str) -> None:
    """Recheck the composed live settings before every TOTP crypto operation."""
    active_key: str | None = None
    for entry in raw_keyring.split(","):
        key_id, separator, encoded_key = entry.strip().partition(":")
        if separator and key_id == active_key_id:
            active_key = encoded_key
            break
    if active_key is None:
        raise TotpEncryptionError("Invalid MFA TOTP encryption configuration")

    spotify_keys = [
        key.strip()
        for key in str(getattr(settings, "spotify_token_secret", "") or "").split(",")
        if key.strip()
    ]
    secret_key = str(getattr(settings, "secret_key", "") or "").strip()
    if secret_key:
        spotify_keys.append(_derive_spotify_fallback_key(secret_key))

    active_key_material, _ = _validated_totp_fernet_key(active_key)
    spotify_key_materials = [_validated_totp_fernet_key(key)[0] for key in spotify_keys]
    if any(
        hmac.compare_digest(active_key_material, key_material)
        for key_material in spotify_key_materials
    ):
        raise TotpEncryptionError(
            "The active MFA_TOTP key must be independent of Spotify encryption keys"
        )


@lru_cache(maxsize=4)
def _build_totp_cipher(
    raw_keyring: str, active_key_id: str
) -> tuple[Fernet, MultiFernet]:
    keyring: dict[str, Fernet] = {}
    key_materials: set[bytes] = set()
    for entry in raw_keyring.split(","):
        key_id, separator, encoded_key = entry.strip().partition(":")
        if not separator or not key_id or not encoded_key or key_id in keyring:
            raise TotpEncryptionError(
                "MFA_TOTP_ENCRYPTION_KEYS must contain unique key-id:Fernet-key pairs"
            )
        try:
            key_material, cipher = _validated_totp_fernet_key(encoded_key)
        except (UnicodeEncodeError, ValueError, binascii.Error):
            raise TotpEncryptionError(
                "MFA_TOTP_ENCRYPTION_KEYS contains an invalid Fernet key"
            ) from None
        if key_material in key_materials:
            raise TotpEncryptionError(
                "MFA_TOTP_ENCRYPTION_KEYS contains duplicate keys"
            )
        key_materials.add(key_material)
        keyring[key_id] = cipher
    active_cipher = keyring.get(active_key_id)
    if active_cipher is None:
        raise TotpEncryptionError(
            "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID does not identify a configured key"
        )
    ordered_ciphers = [active_cipher]
    ordered_ciphers.extend(
        cipher for key_id, cipher in keyring.items() if key_id != active_key_id
    )
    return active_cipher, MultiFernet(ordered_ciphers)


def _get_totp_cipher() -> tuple[Fernet, MultiFernet]:
    raw_keyring = settings.mfa_totp_encryption_keys.strip()
    active_key_id = settings.mfa_totp_active_encryption_key_id.strip()
    if not raw_keyring:
        environment = str(
            getattr(settings, "environment", "development") or "development"
        ).lower()
        if environment not in {"dev", "development", "local", "test", "testing"}:
            raise TotpEncryptionError(
                "MFA_TOTP_ENCRYPTION_KEYS and "
                "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID are required outside development"
            )
        raw_keyring = f"development:{_derive_totp_default_key()}"
        active_key_id = "development"
    try:
        active_cipher, read_cipher = _build_totp_cipher(raw_keyring, active_key_id)
        _ensure_totp_active_key_independent(raw_keyring, active_key_id)
        return active_cipher, read_cipher
    except TotpEncryptionError:
        raise
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed key configuration conversion hides backend exception details
        raise TotpEncryptionError("Invalid MFA TOTP encryption configuration") from None


def _totp_token_bytes(value: str | bytes | None) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value or None
    return value.encode("utf-8") if value else None


def _decode_totp_plaintext(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        raise TotpEncryptionError("TOTP secret is not valid UTF-8 plaintext") from None


def encrypt_totp_string(value: str | bytes | None) -> str | None:
    """Encrypt TOTP secrets with their dedicated active key."""
    if isinstance(value, str):
        plaintext = value.encode("utf-8") if value else b""
    else:
        plaintext = value or b""
    if not plaintext:
        return None
    _decode_totp_plaintext(plaintext)
    active_cipher, _ = _get_totp_cipher()
    return active_cipher.encrypt(plaintext).decode("ascii")


def decrypt_totp_string(value: str | bytes | None) -> str | None:
    """Decrypt configured TOTP ring entries, failing closed on unknown tokens."""
    token = _totp_token_bytes(value)
    if token is None:
        return None
    _, read_cipher = _get_totp_cipher()
    try:
        plaintext = read_cipher.decrypt(token)
    except InvalidToken:
        _logger.warning(
            "Failed to decrypt stored TOTP secret with configured key ring."
        )
        raise TotpEncryptionError(
            "Stored TOTP secret cannot be decrypted with the configured key ring"
        ) from None
    return _decode_totp_plaintext(plaintext)


def rotate_totp_encrypted_string(value: str | bytes | None) -> str | None:
    """Re-encrypt a stored TOTP token with the active TOTP key, idempotently."""
    token = _totp_token_bytes(value)
    if token is None:
        return None
    active_cipher, read_cipher = _get_totp_cipher()
    try:
        plaintext = active_cipher.decrypt(token)
    except InvalidToken:
        try:
            plaintext = read_cipher.decrypt(token)
        except InvalidToken:
            raise TotpEncryptionError(
                "Stored TOTP secret cannot be decrypted with the configured key ring"
            ) from None
        _decode_totp_plaintext(plaintext)
        return active_cipher.encrypt(plaintext).decode("ascii")
    _decode_totp_plaintext(plaintext)
    return token.decode("ascii")


def reset_cached_cipher() -> None:
    """Clear cached ciphers (useful in tests when configured keys change)."""
    _build_cipher.cache_clear()
    _build_totp_cipher.cache_clear()


def encrypt_string(value: str | bytes | None) -> str | None:
    """Encrypt a value using the configured Fernet key.

    Empty strings are normalised to ``None`` to avoid storing meaningless blobs.
    """

    if value is None:
        return None
    if isinstance(value, bytes):
        if not value:
            return None
        data = value
    else:
        if value == "":
            return None
        data = value.encode("utf-8")
    token = _get_cipher().encrypt(data)
    return token.decode("utf-8")


def decrypt_string(value: str | bytes | None) -> str | None:
    """Decrypt a value previously produced by :func:`encrypt_string`.

    If decryption fails (e.g., due to key change), returns None and logs a warning
    instead of raising an exception to prevent application crashes.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        if not value:
            return None
        token = value
    else:
        if value == "":
            return None
        token = value.encode("utf-8")
    try:
        data = _get_cipher().decrypt(token)
    except InvalidToken:
        _logger.warning(
            "Failed to decrypt stored token (key mismatch?). Returning None."
        )
        return None
    return data.decode("utf-8")


def rotate_encrypted_string(value: str | bytes | None) -> str | None:
    """Re-encrypt a token with the primary key when multiple keys are provided."""

    if value is None:
        return None
    cipher = _get_cipher()
    raw = value.encode("utf-8") if isinstance(value, str) else value
    if not raw:
        return None
    if isinstance(cipher, MultiFernet):
        rotated = cipher.rotate(raw)
        return rotated.decode("utf-8")
    return value if isinstance(value, str) else value.decode("utf-8")


class TotpEncryptedString(TypeDecorator[str]):
    """TypeDecorator using the dedicated MFA TOTP encryption key ring."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return encrypt_totp_string(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return decrypt_totp_string(value)


class EncryptedString(TypeDecorator[str]):
    """TypeDecorator that transparently encrypts/decrypts string values."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return encrypt_string(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return decrypt_string(value)
