import asyncio
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from uuid import uuid4

import bcrypt
import httpx
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from jwt import PyJWTError as JWTError
from zxcvbn import zxcvbn

from app.core.config import settings
from app.core.localization import translate

LEGACY_BCRYPT_MAX_BYTES = 72
ARGON2_MEMORY_COST_KIB = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

DEFAULT_SCHEME = "argon2"
LEGACY_SCHEME = "bcrypt"

_logger = logging.getLogger(__name__)

# Executor for CPU-bound auth operations (Argon2 hashing).
# Argon2 at ARGON2_MEMORY_COST_KIB=65536 uses 64 MB per concurrent hash call;
# bounding pool size to cpu_count prevents memory exhaustion under login bursts.
# Python's default (cpu_count + 4) is designed for I/O-bound work — not suitable here.
_AUTH_EXECUTOR_WORKERS: int = max(2, os.cpu_count() or 2)
_auth_executor = ThreadPoolExecutor(
    max_workers=_AUTH_EXECUTOR_WORKERS,
    thread_name_prefix="auth_worker",
)

# Semaphore that caps concurrent async Argon2 operations to (worker_count - 1).
# Without this, a login burst fans out 100+ simultaneous 64MB/~300ms hash calls,
# saturating the thread pool and spiking latency for every other request.
# The semaphore provides backpressure: excess callers await a free slot instead
# of all racing to the executor at once.  Always ≥1 to avoid deadlock.
_ARGON2_CONCURRENCY_LIMIT: int = max(1, _AUTH_EXECUTOR_WORKERS - 1)
_argon2_semaphore = asyncio.Semaphore(_ARGON2_CONCURRENCY_LIMIT)


class SecurityError(Exception):
    """Base class for security-related errors."""

    pass


# Native argon2-cffi hasher — the only scheme used for NEW passwords.
# Legacy bcrypt hashes are verified below using the bare `bcrypt` package;
# bcrypt is no longer used to create hashes.
argon2_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST_KIB,
    parallelism=ARGON2_PARALLELISM,
    type=Type.ID,
)


def _verify_legacy_bcrypt(plain_password: str, hashed_password: str) -> bool:
    """Verify a bcrypt hash using the native bcrypt package.

    bcrypt silently truncates inputs at 72 bytes (the historical behaviour).
    This matches the semantics passlib used; callers should rehash matching
    legacy passwords to argon2id on successful login.
    """
    try:
        password_bytes = plain_password.encode("utf-8")[:LEGACY_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except Exception as exc:
        _logger.warning("Legacy bcrypt verification failed: %s", type(exc).__name__)
        return False


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


async def _validate_password_hibp(password: str, *, locale: str | None = None) -> None:
    # SHA-1 is required by the "Have I Been Pwned" API for their k-Anonymity model.
    # We only send the first 5 characters of the hash prefix to the API.
    # The full hash is never transmitted or stored.
    # ref: https://haveibeenpwned.com/API/v3#PwnedPasswords
    sha1 = _calculate_lookup_hash(password)
    prefix = sha1[:5]
    suffix = sha1[5:]
    url = f"{settings.password_hibp_api_url.rstrip('/')}/{prefix}"
    try:
        async with httpx.AsyncClient(
            timeout=settings.password_hibp_timeout_seconds
        ) as client:
            response = await client.get(
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

    # HIBP (Have I Been Pwned) check is intentionally excluded here.
    # It requires an async HTTP call and is handled separately by async
    # service-layer callers (auth_service, user_service) via
    # _validate_password_hibp().  This keeps get_password_hash() synchronous
    # so it remains usable from CLI commands and MFA code generation.


def _truncate_for_bcrypt(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) <= LEGACY_BCRYPT_MAX_BYTES:
        return password
    truncated = encoded[:LEGACY_BCRYPT_MAX_BYTES]
    return truncated.decode("utf-8", "ignore")


def verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    """Synchronous verification (CPU blocking)."""
    if hashed_password.startswith("$argon2"):
        try:
            argon2_hasher.verify(hashed_password, plain_password)
            return True
        except VerifyMismatchError:
            return False
        except Exception as exc:
            # Unexpected error from argon2 (e.g. malformed hash format).
            # Log and fall through to passlib for graceful degradation.
            _logger.warning(
                "argon2 native verify raised unexpected error, "
                "falling back to passlib: %s",
                type(exc).__name__,
            )
    # Legacy bcrypt hash: verify with native bcrypt (no passlib)
    return _verify_legacy_bcrypt(plain_password, hashed_password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Asynchronous verification offloaded to thread pool with backpressure."""
    async with _argon2_semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _auth_executor, verify_password_sync, plain_password, hashed_password
        )


def verify_and_update_password_sync(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """Synchronous verify and update (CPU blocking)."""
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
        except Exception as exc:
            # Unexpected error from argon2 (e.g. malformed hash format).
            # Log and fall through to passlib for graceful degradation.
            _logger.warning(
                "argon2 native verify_and_update raised unexpected error, "
                "falling back to passlib: %s",
                type(exc).__name__,
            )

    try:
        verified = _verify_legacy_bcrypt(plain_password, hashed_password)
    except Exception:
        return False, None
    if not verified:
        return False, None
    # Upgrade legacy bcrypt to argon2id on successful login
    new_hash = argon2_hasher.hash(plain_password)
    return True, new_hash


async def verify_and_update_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """Asynchronous verify and update offloaded to thread pool with backpressure."""
    async with _argon2_semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _auth_executor,
            verify_and_update_password_sync,
            plain_password,
            hashed_password,
        )


def get_password_hash_sync(
    password: str, *, locale: str | None = None, validate_policy: bool = True
) -> str:
    """Hash a password using Argon2id (Synchronous/Blocking).

    Runs synchronous policy checks (length, character classes, zxcvbn).
    """
    if validate_policy:
        _validate_password_policy(password, locale=locale)
    return argon2_hasher.hash(password)


async def get_password_hash(
    password: str, *, locale: str | None = None, validate_policy: bool = True
) -> str:
    """Hash a password using Argon2id (Asynchronous/Non-blocking) with backpressure."""
    async with _argon2_semaphore:
        loop = asyncio.get_running_loop()
        func = partial(
            get_password_hash_sync,
            password,
            locale=locale,
            validate_policy=validate_policy,
        )
        return await loop.run_in_executor(_auth_executor, func)


def _mint_pure_jwt(
    subject: str | Any,
    *,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a raw JWT without registering a session in Redis/DB.

    INTERNAL USE ONLY — not for request handlers.
    For authenticated sessions use SessionService.create_access_token,
    which registers the token in ActiveSession and supports revocation.
    Acceptable uses: MFA step-up tokens, internal service-to-service calls,
    test fixtures that need a bare JWT without a full DB session.
    """
    minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": str(uuid4()),
        **(extra_claims or {}),
    }
    kid = settings.jwt_signing_active_kid
    secret = settings.jwt_signing_active_secret
    return jwt.encode(
        payload,
        secret,
        algorithm=settings.algorithm,
        headers={"kid": kid},
    )


def decode_token(token: str) -> dict | None:
    """Validate JWT signature and return the payload, or None if invalid.

    Does NOT check revocation — callers in async context must additionally
    call ``check_jti_revoked(jti)`` from deps to honour session invalidation.
    """
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
            # RZ-3: Strict algorithm check (audit 2026-02-24)
            # If RS256 is used, the secret should be the public key (PEM).
            # If the secret is a private key, jwt.decode usually handles it by extraction.
            # But we can be explicit if we find it's a PEM block.
            verification_key: Any = secret
            if settings.algorithm == "RS256" and secret.startswith("-----BEGIN"):
                if "PRIVATE KEY" in secret:
                    try:
                        # If it's a private key, extract public key for verification.
                        # This is standard practice to separate signing/verifying.
                        key = serialization.load_pem_private_key(
                            secret.encode(), password=None
                        )
                        if hasattr(key, "public_key"):
                            verification_key = (
                                key.public_key()
                                .public_bytes(
                                    encoding=serialization.Encoding.PEM,
                                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                                )
                                .decode()
                            )
                    except Exception as exc:
                        _logger.error(
                            "Failed to extract public key from PEM for RS256 verification: %s",
                            exc,
                        )
                        continue
                else:
                    verification_key = secret

            payload = jwt.decode(
                token, verification_key, algorithms=[settings.algorithm]
            )
            return payload if isinstance(payload, dict) else dict(payload)
        except JWTError:
            continue
    return None
