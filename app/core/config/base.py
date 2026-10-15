from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_logger = get_logger(__name__)


def _resolve_env_file(base_dir: Path) -> Path | None:
    """Locate a concrete environment file if one has been provided."""
    example_override = os.environ.get("ENV_EXAMPLE_PATH")
    if example_override:
        example_path = Path(example_override)
    else:
        example_path = base_dir / ".env.example"

    try:
        example_bytes = example_path.read_bytes()
    except OSError:
        example_bytes = None

    env_override = os.environ.get("ENV_FILE_PATH")
    if env_override is not None:
        if not env_override:
            return None
        candidate = Path(env_override)
        if candidate.is_file():
            if example_bytes is not None:
                try:
                    candidate_bytes = candidate.read_bytes()
                except OSError:
                    candidate_bytes = None
                else:
                    if candidate_bytes == example_bytes:
                        _logger.warning(
                            "%s is identical to %s; update it with real secrets "
                            "before deploying.",
                            candidate,
                            example_path,
                        )
            return candidate
        return None

    for name in (".env", ".env.local"):
        candidate = base_dir / name
        if not candidate.is_file():
            continue
        if name == ".env" and example_bytes is not None:
            try:
                candidate_bytes = candidate.read_bytes()
            except OSError:
                candidate_bytes = None
            else:
                if candidate_bytes == example_bytes:
                    _logger.warning(
                        "%s is identical to %s; update it with real secrets "
                        "before deploying.",
                        candidate,
                        example_path,
                    )
        return candidate
    return None


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

_DEVELOPMENT_ENVIRONMENTS: frozenset[str] = frozenset(
    {
        "dev",
        "development",
        "local",
        "test",
        "testing",
    }
)

_DEVELOPMENT_FALLBACKS: dict[str, str] = {
    "database_url": "sqlite+aiosqlite:///./dev.db",
}

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
        "nats_auth_token",
        "nats_url",
        "revocation_redis_url",
        "secret_key",
        "smtp_password",
        "spicedb_preshared_key",
        "spotify_client_secret",
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

_MAX_SECRET_FILE_SIZE_BYTES = 1 << 20
_SECRET_FILE_READ_CHUNK_BYTES = 64 * 1024


class _SecretFileValidationError(ValueError):
    """A safe configuration error for invalid mounted secret files."""


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


def _load_file_secret(env_file_var: str, value: str | None) -> str | None:
    """Return the file contents when configured; never hide a broken file input.

    Implements the Docker/K8s *_FILE convention (used by the official postgres,
    redis, and nginx images).  The file is expected to be a /run/secrets/ tmpfs
    mount — never visible in ``docker inspect`` or image layers.

    RZ-05 (audit Wave 12): native secret field validators use this loader;
    BaseAppSettings also resolves the explicitly allowlisted secret fields that
    do not have a native field validator.

    Args:
        env_file_var: Name of the ``*_FILE`` environment variable (e.g. ``"SECRET_KEY_FILE"``).
        value: The raw field value received from the environment (may be None
               when the plain env var is absent).

    Returns:
        Stripped file contents when configured, otherwise *value* unchanged.

    A configured path is an explicit operator choice. Blank, unreadable, invalid
    UTF-8, and empty files therefore fail closed instead of falling back to a
    default or a plain environment value.
    """
    file_path = os.environ.get(env_file_var)
    if file_path is None:
        return value
    if not file_path.strip():
        raise ValueError(f"{env_file_var} must name a non-empty file path")

    secret_path = Path(file_path)
    try:
        if not stat.S_ISREG(secret_path.stat().st_mode):
            raise _SecretFileValidationError(
                f"configured secret file for {env_file_var} must be a regular file"
            )

        open_flags = os.O_RDONLY
        open_flags |= getattr(os, "O_CLOEXEC", 0)
        open_flags |= getattr(os, "O_NONBLOCK", 0)
        open_flags |= getattr(os, "O_BINARY", 0)
        descriptor = os.open(secret_path, open_flags)
        try:
            file_info = os.fstat(descriptor)
            if not stat.S_ISREG(file_info.st_mode):
                raise _SecretFileValidationError(
                    f"configured secret file for {env_file_var} must be a regular file"
                )
            if file_info.st_size > _MAX_SECRET_FILE_SIZE_BYTES:
                raise _SecretFileValidationError(
                    f"configured secret file for {env_file_var} exceeds the size limit"
                )

            chunks: list[bytes] = []
            bytes_remaining = _MAX_SECRET_FILE_SIZE_BYTES + 1
            while bytes_remaining:
                chunk = os.read(
                    descriptor, min(_SECRET_FILE_READ_CHUNK_BYTES, bytes_remaining)
                )
                if not chunk:
                    break
                chunks.append(chunk)
                bytes_remaining -= len(chunk)
            contents = b"".join(chunks)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
    except _SecretFileValidationError:
        raise
    except (OSError, ValueError):
        raise ValueError(
            f"unable to read configured secret file for {env_file_var}"
        ) from None
    if len(contents) > _MAX_SECRET_FILE_SIZE_BYTES:
        raise _SecretFileValidationError(
            f"configured secret file for {env_file_var} exceeds the size limit"
        )
    try:
        secret = contents.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        raise ValueError(
            f"configured secret file for {env_file_var} must contain valid UTF-8"
        ) from None
    if not secret:
        raise ValueError(f"configured secret file for {env_file_var} must not be empty")
    return secret


def _should_allow_development_defaults(missing: Iterable[str] | None = None) -> bool:
    """Determine if development fallback values are permitted.

    Fallbacks are only allowed if ENVIRONMENT is set to a development-like
    value (dev, test, etc.) and if no concrete .env file has been loaded
    (which would imply a more production-ready configuration attempt).
    """
    # Prefer explicit ENVIRONMENT setting if available
    env_name = (os.environ.get("ENVIRONMENT") or "").lower()

    # CI/CD environments (e.g., GitHub Actions) frequently run tools like Alembic or tests
    # where strict secret enforcement is unnecessary overhead for non-sensitive steps.
    is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

    # MED-W19: production must never fall back to development defaults regardless
    # of the CI flag — a misconfigured prod deploy with CI=true would otherwise
    # silently use insecure generated secrets.
    if env_name == "production":
        return False

    # STRICT SECURITY: Only allow defaults if we are explicitly in a development environment.
    # If ENVIRONMENT is unset, empty, or "production", we fail securely unless in a CI environment.
    if env_name not in _DEVELOPMENT_ENVIRONMENTS and not is_ci:
        return False

    if _ENV_FILE is not None and not is_ci:
        # If no ENVIRONMENT set but .env exists, assume production-like intent
        # (Wait, if CI is true and .env exists, we might still want fallbacks if .env is incomplete)
        return False

    if missing is None:
        # Generic check: only allow if we don't have main secrets in env
        return not any(os.environ.get(name) for name in ("DATABASE_URL", "SECRET_KEY"))

    # Check if all missing fields have valid fallbacks
    allowed = {name.upper() for name in _DEVELOPMENT_FALLBACKS}
    allowed.add("SECRET_KEY")

    return all(name in allowed for name in missing)
