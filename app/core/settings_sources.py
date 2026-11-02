"""Shared configuration sources without application settings initialization."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

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

_MAX_SECRET_FILE_SIZE_BYTES = 1 << 20
_SECRET_FILE_READ_CHUNK_BYTES = 64 * 1024

# These integration secrets are optional; an explicit empty source file disables
# the integration. Spotify's token-encryption secret is intentionally absent.
_OPTIONAL_EMPTY_SECRET_FILE_ENV_VARS: frozenset[str] = frozenset(
    {
        "SPOTIFY_CLIENT_SECRET_FILE",
        "SPOTIFY_OAUTH_STATE_SECRET_FILE",
        "VAPID_PRIVATE_KEY_FILE",
    }
)


class _SecretFileValidationError(ValueError):
    """A safe configuration error for invalid mounted secret files."""


def resolve_env_file(base_dir: Path, *, logger: Any) -> Path | None:
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
                        logger.warning(
                            "%s is identical to %s; update it with real secrets "
                            "before deploying.",
                            str(candidate),
                            str(example_path),
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
                    logger.warning(
                        "%s is identical to %s; update it with real secrets "
                        "before deploying.",
                        str(candidate),
                        str(example_path),
                    )
        return candidate
    return None


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
    UTF-8, and empty files fail closed instead of falling back to a default or a
    plain environment value. Only VAPID_PRIVATE_KEY_FILE,
    SPOTIFY_CLIENT_SECRET_FILE, and SPOTIFY_OAUTH_STATE_SECRET_FILE accept an
    empty regular file as an explicit disabled-integration input. The Spotify
    token-encryption key remains mandatory in production.
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
            with suppress(OSError):
                os.close(descriptor)
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
        if env_file_var in _OPTIONAL_EMPTY_SECRET_FILE_ENV_VARS:
            return ""
        raise ValueError(f"configured secret file for {env_file_var} must not be empty")
    return secret


def should_allow_development_defaults(
    missing: Iterable[str] | None = None, *, env_file: Path | None
) -> bool:
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

    if env_file is not None and not is_ci:
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
