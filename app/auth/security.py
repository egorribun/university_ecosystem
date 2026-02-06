import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from fastapi import BackgroundTasks
from jwt import PyJWTError as JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from zxcvbn import zxcvbn

from app.core.config import settings
from app.core.localization import translate
from app.models.models import ActiveSession

LEGACY_BCRYPT_MAX_BYTES = 72
ARGON2_MEMORY_COST_KIB = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

DEFAULT_SCHEME = "argon2"
LEGACY_SCHEME = "bcrypt"

_logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Base class for security-related errors."""

    pass


# NOTE: the upstream ``bcrypt`` package started raising ``ValueError`` for
# inputs longer than 72 bytes during backend feature detection when running
# under Python 3.12+.  Passlib expects backends to gracefully truncate these
# probes, so the detection step aborts before we can create or verify legacy
# hashes.  To keep migrations deterministic across interpreter versions we
# proactively reinstate the historical truncation semantics so feature
# detection and legacy verifications succeed across interpreter versions.
try:  # pragma: no cover - optional backend
    from passlib.handlers import bcrypt as passlib_bcrypt_handlers
except ImportError:  # pragma: no cover - optional dependency
    pass
else:  # pragma: no cover - executed during import
    _backend_common = getattr(passlib_bcrypt_handlers, "_BcryptCommon", None)
    if _backend_common is not None:
        _original_norm_digest = _backend_common._norm_digest_args.__func__

        def _norm_digest_args_with_legacy_truncation(
            cls, secret, ident, new=False, _orig=_original_norm_digest
        ):
            if secret and isinstance(secret, str):
                secret = secret.encode("utf-8")

            if (
                isinstance(secret, bytes | bytearray)
                and len(secret) > LEGACY_BCRYPT_MAX_BYTES
            ):
                secret = secret[:LEGACY_BCRYPT_MAX_BYTES]

            return _orig(cls, secret, ident, new=new)

        _backend_common._norm_digest_args = classmethod(
            _norm_digest_args_with_legacy_truncation
        )

pwd_context = CryptContext(
    schemes=[DEFAULT_SCHEME, LEGACY_SCHEME],
    default=DEFAULT_SCHEME,
    deprecated="auto",
    argon2__type="ID",
    argon2__memory_cost=ARGON2_MEMORY_COST_KIB,
    argon2__time_cost=ARGON2_TIME_COST,
    argon2__parallelism=ARGON2_PARALLELISM,
)

# Native argon2-cffi hasher for primary operations (2026 performance)
argon2_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST_KIB,
    parallelism=ARGON2_PARALLELISM,
    type=Type.ID,
)


def _format_password_class_labels(class_names: list[str], *, locale: str | None) -> str:
    translated = [
        translate(f"password.class.{class_name}", locale=locale)
        for class_name in class_names
    ]
    return ", ".join(translated)


def _calculate_lookup_hash(input_data: str) -> str:
    """
    Calculate a SHA-1 hash for API lookups (e.g. HIBP).
    This is NOT used for password storage or verification.
    """
    # nosec: B303 - SHA-1 is required by the external API
    return (
        hashlib.sha1(
            input_data.encode("utf-8"), usedforsecurity=False
        )  # codeql[py/weak-sensitive-data-hashing]
        .hexdigest()
        .upper()
    )


def _validate_password_hibp(password: str, *, locale: str | None = None) -> None:
    # SHA-1 is required by the "Have I Been Pwned" API for their k-Anonymity model.
    # We only send the first 5 characters of the hash prefix to the API.
    # The full hash is never transmitted or stored.
    # ref: https://haveibeenpwned.com/API/v3#PwnedPasswords
    sha1 = _calculate_lookup_hash(password)
    prefix = sha1[:5]
    suffix = sha1[5:]
    url = f"{settings.password_hibp_api_url.rstrip('/')}/{prefix}"
    try:
        with httpx.Client(timeout=settings.password_hibp_timeout_seconds) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "UniversityEcosystem/1.0",
                    "Add-Padding": "true",
                },
            )
    except httpx.RequestError as exc:
        _logger.warning("HIBP password check failed: %s", exc)
        raise ValueError(
            translate("errors.auth.password_policy_hibp_unavailable", locale=locale)
        ) from exc

    if response.status_code != httpx.codes.OK:
        _logger.warning("HIBP password check returned status %s", response.status_code)
        raise ValueError(
            translate("errors.auth.password_policy_hibp_unavailable", locale=locale)
        )

    for line in response.text.splitlines():
        hashed_suffix, _, count = line.partition(":")
        if hashed_suffix.upper() == suffix:
            if int(count.strip() or 0) > 0:
                raise ValueError(
                    translate("errors.auth.password_policy_compromised", locale=locale)
                )
            break


def _validate_password_policy(password: str, *, locale: str | None = None) -> None:
    print(f"DEBUG: Validating policy for length {len(password)}")
    length = len(password)
    min_length = settings.password_min_length
    max_length = settings.password_max_length
    if length < min_length or length > max_length:
        raise ValueError(
            translate(
                "errors.auth.password_policy_length",
                locale=locale,
                min_length=min_length,
                max_length=max_length,
            )
        )

    class_checks = {
        "uppercase": any(char.isupper() for char in password),
        "lowercase": any(char.islower() for char in password),
        "digit": any(char.isdigit() for char in password),
        "symbol": any(not char.isalnum() for char in password),
    }
    required_classes = {
        "uppercase": settings.password_require_uppercase,
        "lowercase": settings.password_require_lowercase,
        "digit": settings.password_require_digit,
        "symbol": settings.password_require_special,
    }
    missing_required = [
        class_name
        for class_name, required in required_classes.items()
        if required and not class_checks[class_name]
    ]
    if missing_required:
        raise ValueError(
            translate(
                "errors.auth.password_policy_required_classes",
                locale=locale,
                classes=_format_password_class_labels(missing_required, locale=locale),
            )
        )

    min_classes = settings.password_min_character_classes
    if min_classes > 0:
        present_classes = sum(1 for present in class_checks.values() if present)
        if present_classes < min_classes:
            raise ValueError(
                translate(
                    "errors.auth.password_policy_min_classes",
                    locale=locale,
                    min_classes=min_classes,
                    classes=_format_password_class_labels(
                        list(class_checks.keys()), locale=locale
                    ),
                )
            )

    min_score = settings.password_zxcvbn_min_score
    if min_score > 0:
        # zxcvbn enforces a 72 character limit
        if len(password) > 72:
            score = 4  # Assume maximum strength for very long passwords
        else:
            score = zxcvbn(password).get("score", 0)

        if score < min_score:
            raise ValueError(
                translate("errors.auth.password_policy_strength", locale=locale)
            )

    if settings.password_hibp_check_enabled:
        _validate_password_hibp(password, locale=locale)


def _truncate_for_bcrypt(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) <= LEGACY_BCRYPT_MAX_BYTES:
        return password
    truncated = encoded[:LEGACY_BCRYPT_MAX_BYTES]
    return truncated.decode("utf-8", "ignore")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$argon2"):
        try:
            argon2_hasher.verify(hashed_password, plain_password)
            return True
        except VerifyMismatchError:
            return False
        except Exception:
            # Fallback to passlib for complex cases/malformed hashes
            pass
    return pwd_context.verify(plain_password, hashed_password)


def verify_and_update_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    # Check if we should upgrade/verify with native argon2 first
    if hashed_password.startswith("$argon2"):
        try:
            argon2_hasher.verify(hashed_password, plain_password)
            # Check if rehash is needed
            if argon2_hasher.check_needs_rehash(hashed_password):
                return True, argon2_hasher.hash(plain_password)
            return True, None
        except VerifyMismatchError:
            return False, None
        except Exception:
            pass

    try:
        verified, new_hash = pwd_context.verify_and_update(
            plain_password, hashed_password
        )
    except ValueError:
        return False, None
    return verified, new_hash


def get_password_hash(
    password: str, *, locale: str | None = None, validate_policy: bool = True
) -> str:
    if validate_policy:
        _validate_password_policy(password, locale=locale)
    return argon2_hasher.hash(password)


@dataclass(slots=True)
class AccessTokenConfig:
    """Configuration for access token creation."""

    expires_delta: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    session_metadata: dict[str, Any] = field(default_factory=dict)


async def create_access_token(
    sub: str | Any,
    db: AsyncSession | None = None,
    config: AccessTokenConfig | None = None,
    bg_tasks: BackgroundTasks | None = None,
) -> str | tuple[str, ActiveSession]:
    """
    Create an access token.

    DEPRECATED: Use SessionService.create_access_token for full session management.
    This function remains for backward compatibility and delegates to SessionService
    if a database session is provided.
    """
    if db is not None:
        from app.repositories.active_session_repository import ActiveSessionRepository
        from app.services.session_service import SessionService

        repo = ActiveSessionRepository(db)
        service = SessionService(db, repo)

        metadata = config.session_metadata if config else {}
        extra = config.extra if config else {}

        return await service.create_access_token(
            sub=sub,
            expires_delta_minutes=config.expires_delta if config else None,
            metadata=metadata,
            bg_tasks=bg_tasks,
            extra_claims=extra,
        )

    # Pure JWT minting (no DB/Redis registration)
    config = config or AccessTokenConfig()
    minutes = config.expires_delta or settings.access_token_expire_minutes
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=minutes)
    jti = str(uuid4())
    payload = {
        "sub": str(sub),
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "jti": jti,
    }
    if config.extra:
        payload.update(config.extra)

    kid = settings.jwt_signing_active_kid
    secret = settings.jwt_signing_active_secret
    token = jwt.encode(
        payload,
        secret,
        algorithm=settings.algorithm,
        headers={"kid": kid},
    )
    return token


def decode_token(token: str) -> dict | None:
    registry = settings.jwt_signing_key_registry
    if not registry:
        return None

    candidates: list[str] = []
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        header = {}

    kid = header.get("kid") if isinstance(header, dict) else None
    if isinstance(kid, str):
        kid_secret = registry.get(kid)
        if kid_secret:
            candidates.append(kid_secret)

    seen: set[str] = set(candidates)
    for secret in registry.values():
        if secret not in seen:
            candidates.append(secret)
            seen.add(secret)

    for secret in candidates:
        try:
            return jwt.decode(token, secret, algorithms=[settings.algorithm])
        except JWTError:
            continue
    return None
