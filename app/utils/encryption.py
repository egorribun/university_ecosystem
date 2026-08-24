"""Utilities for encrypting sensitive application data."""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import settings
from app.core.logging import get_logger

_logger = get_logger(__name__)


class SpotifyEncryptionError(RuntimeError):
    """Raised when Spotify token encryption fails."""


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


def _derive_default_secret() -> str:
    """Derive a deterministic Fernet key from the primary app secret.

    When ``SPOTIFY_TOKEN_SECRET`` is not explicitly configured we fall back to a key
    derived from :setting:`secret_key`. This keeps development environments working
    out of the box while still requiring a strong base secret.
    """

    primary = settings.secret_key.strip()
    if not primary:
        raise SpotifyEncryptionError("SPOTIFY_TOKEN_SECRET is not configured")
    digest = hashlib.sha256(primary.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def _get_cipher() -> Fernet | MultiFernet:
    raw = settings.spotify_token_secret.strip()
    if not raw:
        raw = _derive_default_secret()
    return _build_cipher(raw)


def reset_cached_cipher() -> None:
    """Clear the cached cipher (useful in tests when the key changes)."""

    _build_cipher.cache_clear()


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


class EncryptedString(TypeDecorator[str]):
    """TypeDecorator that transparently encrypts/decrypts string values."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return encrypt_string(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return decrypt_string(value)
