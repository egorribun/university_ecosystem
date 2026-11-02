from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logging import get_logger
from app.core.settings_sources import (
    _DEVELOPMENT_ENVIRONMENTS as _DEVELOPMENT_ENVIRONMENTS,
)
from app.core.settings_sources import _DEVELOPMENT_FALLBACKS as _DEVELOPMENT_FALLBACKS
from app.core.settings_sources import (
    _MAX_SECRET_FILE_SIZE_BYTES as _MAX_SECRET_FILE_SIZE_BYTES,
)
from app.core.settings_sources import _load_file_secret as _load_file_secret
from app.core.settings_sources import (
    resolve_env_file,
    should_allow_development_defaults,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_logger = get_logger(__name__)


def _resolve_env_file(base_dir: Path) -> Path | None:
    """Locate an environment file using the shared fail-closed source policy."""
    return resolve_env_file(base_dir, logger=_logger)


_ENV_FILE = _resolve_env_file(_PROJECT_ROOT)


def _coerce_str_list(values: Iterable[str | int] | str | None) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        items = [item.strip() for item in values.split(",")]
    else:
        items = [str(item).strip() for item in values]
    return [item for item in items if item]


def _coerce_int_list(values: Iterable[str | int] | str | None) -> list[int]:
    raw_items = _coerce_str_list(values) if not isinstance(values, list) else values
    converted: list[int] = []
    for item in raw_items:
        try:
            converted.append(int(item))
        except (TypeError, ValueError):
            continue
    return converted


def _validate_non_empty(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def _validate_positive_int(value: int, *, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


def _validate_non_negative_int(value: int, *, label: str) -> int:
    if value < 0:
        raise ValueError(f"{label} must be zero or positive")
    return value


def _validate_positive_float(value: float, *, label: str) -> float:
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


_logger = get_logger(__name__)


# Secret fields whose mounted-file form is part of the supported deployment
# contract. Keep this allowlist explicit so ordinary configuration cannot be
# redirected to arbitrary files through a generic ``*_FILE`` convention.
_FILE_SECRET_FIELDS: frozenset[str] = frozenset(
    {
        "audit_log_secret",
        "cache_redis_url",
        "csrf_hmac_secret",
        "cwv_manual_tester_user_ids",
        "cwv_rum_signing_secret",
        "database_url",
        "elasticsearch_password",
        "idempotency_hmac_secret",
        "internal_auth_token",
        "internal_hmac_secret",
        "mfa_email_delivery_active_kek_id",
        "mfa_email_delivery_keks",
        "mfa_email_otp_active_hmac_key_id",
        "mfa_email_otp_hmac_keys",
        "mfa_trusted_device_active_hmac_key_id",
        "mfa_trusted_device_hmac_keys",
        "mfa_totp_encryption_keys",
        "nats_auth_token",
        "nats_url",
        "rate_limit_storage_uri",
        "revocation_redis_url",
        "secret_key",
        "smtp_password",
        "spicedb_preshared_key",
        "spotify_client_secret",
        "spotify_oauth_state_secret",
        "spotify_token_secret",
        "storage_s3_access_key_id",
        "storage_s3_secret_access_key",
        "token_hmac_secret",
        "vapid_private_key",
        "ws_hub_internal_secret",
    }
)

# These fields already have field-level validators that perform file loading
# and domain validation. Supplying an empty input when the environment only
# provides ``*_FILE`` makes those existing validators run before required or
# default handling, without reading the file twice.
_FILE_SECRET_FIELDS_WITH_NATIVE_LOADERS: frozenset[str] = frozenset(
    {
        "database_url",
        "elasticsearch_password",
        "internal_hmac_secret",
        "nats_auth_token",
        "secret_key",
        "smtp_password",
        "spicedb_preshared_key",
        "spotify_client_secret",
        "token_hmac_secret",
        "vapid_private_key",
        "ws_hub_internal_secret",
    }
)


def _generate_development_secret_key() -> str:
    """Generate a secure random key for local development only.

    This key is regenerated on every application restart, ensuring that
    sessions are invalidated. For production, always provide a stable
    SECRET_KEY via environment variables.
    """
    import secrets

    return secrets.token_urlsafe(32)


class BaseAppSettings(BaseSettings):
    def __init__(self, **values: Any) -> None:
        allow_missing = values.pop("_allow_missing", False)
        try:
            super().__init__(**values)
        except ValidationError as exc:

            def _format_missing(loc: tuple[object, ...]) -> str | None:
                if not loc:
                    return None
                first = loc[0]
                if isinstance(first, str):
                    return first.upper()
                return str(first)

            missing_required = sorted(
                {
                    formatted
                    for error in exc.errors(include_url=False)
                    if error.get("type") == "missing"
                    for formatted in [
                        _format_missing(tuple(error.get("loc", ()) or ()))
                    ]
                    if formatted
                }
            )
            if allow_missing and missing_required:
                fallback_values: dict[str, str] = {}
                unresolved: list[str] = []
                for missing in missing_required:
                    field_name = missing.lower()
                    if field_name == "secret_key":
                        # Generate a secure random key for development
                        fallback_values[field_name] = _generate_development_secret_key()
                    elif field_name in _DEVELOPMENT_FALLBACKS:
                        fallback_values[field_name] = _DEVELOPMENT_FALLBACKS[field_name]
                    else:
                        unresolved.append(missing)
                if not unresolved:
                    combined_values = {**values, **fallback_values}
                    super().__init__(**combined_values)
                    object.__setattr__(
                        self,
                        "_development_fallback_fields",
                        tuple(sorted(fallback_values.keys())),
                    )
                    return
            if missing_required:
                details = ", ".join(missing_required)
                error = RuntimeError(
                    "Missing required environment variables: "
                    f"{details}. Provide real secrets via environment variables or an"
                    " application .env file (not .env.example)."
                )
                error.missing_required = tuple(missing_required)  # type: ignore[attr-defined]
                raise error from None
            raise

    @property
    def development_fallback_fields(self) -> tuple[str, ...]:
        stored = getattr(self, "_development_fallback_fields", ())
        if isinstance(stored, tuple):
            return stored
        return tuple(stored)

    @property
    def has_development_fallbacks(self) -> bool:
        return bool(self.development_fallback_fields)

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE is not None else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _prepare_configured_secret_files(cls, values: Any) -> Any:
        """Resolve only approved ``*_FILE`` inputs before defaults/required checks."""
        if not isinstance(values, dict):
            return values

        resolved = dict(values)
        for field_name in sorted(_FILE_SECRET_FIELDS):
            if field_name not in cls.model_fields:
                continue
            env_file_var = f"{field_name.upper()}_FILE"
            if env_file_var not in os.environ:
                continue
            if field_name in _FILE_SECRET_FIELDS_WITH_NATIVE_LOADERS:
                resolved.setdefault(field_name, "")
            else:
                resolved[field_name] = _load_file_secret(
                    env_file_var, resolved.get(field_name)
                )
        return resolved


def _should_allow_development_defaults(missing: Iterable[str] | None = None) -> bool:
    """Retain the runtime fallback policy with this module's env-file snapshot."""
    return should_allow_development_defaults(missing, env_file=_ENV_FILE)
