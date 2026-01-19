from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_env_file(base_dir: Path) -> Path | None:
    """Locate a concrete environment file if one has been provided."""

    example_path = base_dir / ".env.example"
    try:
        example_bytes = example_path.read_bytes()
    except OSError:
        example_bytes = None

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
                    logging.getLogger(__name__).warning(
                        "%s is identical to %s; update it with real secrets "
                        "before deploying.",
                        candidate,
                        example_path,
                    )
        return candidate
    return None


_ENV_FILE = _resolve_env_file(_PROJECT_ROOT)


def _coerce_str_list(values: Iterable[str] | str | None) -> list[str]:
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


_logger = logging.getLogger(__name__)

_DEVELOPMENT_ENVIRONMENTS = {
    "dev",
    "development",
    "local",
    "test",
    "testing",
}

_DEVELOPMENT_FALLBACKS: dict[str, str] = {
    "database_url": "sqlite+aiosqlite:///./dev.db",
}


def _generate_development_secret_key() -> str:
    """Generate a secure random key for local development only.

    This key is regenerated on every application restart, ensuring that
    sessions are invalidated. For production, always provide a stable
    SECRET_KEY via environment variables.
    """
    import secrets

    return secrets.token_urlsafe(32)


class BaseAppSettings(BaseSettings):
    def __init__(self, **values) -> None:
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
                error.missing_required = tuple(missing_required)
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
    )


def _should_allow_development_defaults(missing: Iterable[str] | None = None) -> bool:
    """Determine if development fallback values are permitted.

    Fallbacks are only allowed if ENVIRONMENT is set to a development-like
    value (dev, test, etc.) and if no concrete .env file has been loaded
    (which would imply a more production-ready configuration attempt).
    """
    # Prefer explicit ENVIRONMENT setting if available
    env_name = (os.environ.get("ENVIRONMENT") or "").lower()
    if env_name:
        if env_name not in _DEVELOPMENT_ENVIRONMENTS:
            return False
    elif _ENV_FILE is not None:
        # If no ENVIRONMENT set but .env exists, assume production-like intent
        return False

    if missing is None:
        # Generic check: only allow if we don't have main secrets in env
        return not any(os.environ.get(name) for name in ("DATABASE_URL", "SECRET_KEY"))

    # Check if all missing fields have valid fallbacks
    allowed = {name.upper() for name in _DEVELOPMENT_FALLBACKS}
    allowed.add("SECRET_KEY")

    return all(name in allowed for name in missing)
