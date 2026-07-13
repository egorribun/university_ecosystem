import asyncio
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import cache, partial
from typing import Any
from uuid import UUID, uuid4

# TD-21-04 (Wave 21): bcrypt import removed — legacy hashes no longer verified.
# The bcrypt package remains in pyproject.toml [dependency-groups.dev] for test
# compatibility but is no longer imported in production code.
import httpx
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from jwt import PyJWTError as JWTError
from zxcvbn import zxcvbn

from app.core.config import settings
from app.core.localization import translate
from app.core.logging import get_logger

# PERF-02 (audit 2026-03-04): Reduced from 65536 KiB (64 MiB) to 32768 KiB (32 MiB).
# 4 workers × 32 MiB = 128 MB peak at login burst (was 256 MB).
# OWASP ASVS §2.4.4 requires ≥ 19 MiB — 32 MiB is a comfortable safe margin.
ARGON2_MEMORY_COST_KIB = 32768
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

_logger = get_logger(__name__)


# Executor for CPU-bound auth operations (Argon2 hashing).
# Argon2 at ARGON2_MEMORY_COST_KIB=32768 uses 32 MB per concurrent hash call;
# peak memory at login burst: _AUTH_EXECUTOR_WORKERS × 32 MB.
# (TD-W8-03: corrected from 65536/64 MB — reduced in PERF-02, audit 2026-03-04.)
# Bounding pool size to cpu_count prevents memory exhaustion under login bursts.
# Python's default (cpu_count + 4) is designed for I/O-bound work — not suitable here.
# PERF-2: os.cpu_count() returns HOST core count inside containers; use
# sched_getaffinity (cgroups v2) or cfs_quota (cgroups v1) for correctness.
# A 2-CPU container on a 32-core host would otherwise spin up 32 Argon2
# threads × 64 MB = 2 GB RAM instead of the expected 128 MB.
def _container_cpu_count() -> int:
    """Return cgroup-aware CPU count for container environments."""
    try:
        sched = getattr(os, "sched_getaffinity", None)
        if sched:
            return len(sched(0))  # Linux cgroups v2 — most accurate
    except AttributeError, NotImplementedError:  # RZ-28-01
        pass
    try:  # Fallback for cgroups v1 (Docker legacy)
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as _f:
            quota = int(_f.read().strip())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as _f:
            period = int(_f.read().strip())
        if quota > 0 and period > 0:
            # LOW-W19: cap at 32 to prevent runaway thread/memory usage on
            # hosts where cgroups v1 quota is set to an unreasonably high value.
            return min(max(1, quota // period), 32)
    except FileNotFoundError, ValueError, OSError:  # RZ-28-01
        pass
    return os.cpu_count() or 2


_AUTH_EXECUTOR_WORKERS: int = max(2, _container_cpu_count())
_auth_executor = ThreadPoolExecutor(
    max_workers=_AUTH_EXECUTOR_WORKERS,
    thread_name_prefix="auth_worker",
)

# Semaphore that caps concurrent async Argon2 operations to (worker_count - 1).
# Without this, a login burst fans out 100+ simultaneous 32MB/~300ms hash calls,
# saturating the thread pool and spiking latency for every other request.
# The semaphore provides backpressure: excess callers await a free slot instead
# of all racing to the executor at once. Always >=1 to avoid deadlock.
_ARGON2_CONCURRENCY_LIMIT: int = max(1, _AUTH_EXECUTOR_WORKERS - 1)


# RZ-NEW-002 (audit 2026-03-19): Replace threading.Lock double-checked locking with
# a per-event-loop lru_cache pattern that is safe for Python 3.13 free-threading.
# threading.Lock was relying on CPython GIL-atomicity of None assignment — an implicit
# assumption that BREAKS with free-threaded Python (PEP 703, --disable-gil builds).
# lru_cache keyed on loop identity is threadsafe since CPython 3.2 and GIL-free safe.
@cache
def _get_argon2_semaphore_for_loop(loop_id: int) -> asyncio.Semaphore:
    """Return a Semaphore scoped to a specific event loop instance.

    Called lazily at request-time, AFTER the worker's event loop is running.
    Fork-safe: each forked Gunicorn worker gets its own loop with a unique id.
    Free-threading safe: lru_cache dict operations are GIL-free safe (dict is
    protected by its own per-object lock in Python 3.13 free-threading).
    """
    return asyncio.Semaphore(_ARGON2_CONCURRENCY_LIMIT)


def _get_argon2_semaphore() -> asyncio.Semaphore:
    """Return the per-event-loop Semaphore for Argon2 concurrency control.

    Uses the running event loop's identity as the cache key. This is
    correct because asyncio.Semaphore is bound to its creation loop and
    each OS process has exactly one running loop at a time.
    """
    loop = asyncio.get_running_loop()
    return _get_argon2_semaphore_for_loop(id(loop))


class SecurityError(Exception):
    """Base class for security-related errors."""

    pass


# Native argon2-cffi hasher — the only password hashing scheme.
# TD-21-04 (Wave 21): bcrypt verification removed — _verify_legacy_bcrypt
# always returns False. Users with legacy bcrypt hashes must reset passwords.
argon2_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST_KIB,
    parallelism=ARGON2_PARALLELISM,
    type=Type.ID,
)


def _verify_legacy_bcrypt(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Reject legacy bcrypt hashes with a warning — migration period ended.

    TD-21-04 (audit 2026-03-25 Wave 21): bcrypt verification removed.
    Previously deprecated with hard removal deadline 2026-09-01.  Removed
    early as part of Wave 21 audit — all remaining bcrypt users must reset
    their passwords.  The function signature is retained to avoid changing
    callers; it always returns False and logs a warning.

    TD-33-03: Prometheus counter removed in Wave 33 (bcrypt metrics dead code).
    """
    _logger.warning(
        "bcrypt_hash_rejected: Legacy bcrypt hashes are no longer accepted. "
        "The user must reset their password to migrate to argon2id.",
    )
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
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    return (
        hashlib.sha1(
            input_data.encode("utf-8"), usedforsecurity=False
        )  # codeql[py/weak-sensitive-data-hashing]
        .hexdigest()
        .upper()
    )


# RZ-002 (audit 2026-03-10): asyncio.Lock is NOT fork-safe.
# Same issue as _argon2_semaphore above: the Lock must be created AFTER the
# worker process forks and its event loop is running. Lazy init on first use
# is the correct pattern — each worker creates its own Lock independently.
# LOW-W19: _hibp_client_lock (dead module-level variable) removed; the lock
# is now created lazily via _get_hibp_client_lock() / _get_hibp_lock_for_loop().
_hibp_client: httpx.AsyncClient | None = None


def _get_hibp_client_lock() -> asyncio.Lock:
    """Return (or lazily create) a per-worker asyncio.Lock for HIBP client init.

    RZ-NEW-002 (audit 2026-03-19): Uses lru_cache keyed on event loop id
    to avoid threading.Lock dependency (free-threading Python 3.13 safe).
    Fork-safe: each forked Gunicorn worker gets its own loop with a unique id.
    """
    loop = asyncio.get_running_loop()
    return _get_hibp_lock_for_loop(id(loop))


@cache
def _get_hibp_lock_for_loop(loop_id: int) -> asyncio.Lock:
    """Return an asyncio.Lock scoped to a specific event loop instance."""
    return asyncio.Lock()


async def _get_hibp_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared HIBP AsyncClient — race-free.

    Uses double-checked locking: the fast path (client already exists) avoids
    lock acquisition entirely; the slow path (first call) serialises through
    the lock so only one coroutine creates the client.
    """
    global _hibp_client
    if _hibp_client is not None:
        return _hibp_client  # fast path — no lock contention

    async with _get_hibp_client_lock():
        # Re-check inside the lock: another coroutine may have initialised it
        # while we were waiting to acquire.
        if _hibp_client is None:
            _hibp_client = httpx.AsyncClient(
                timeout=settings.password_hibp_timeout_seconds,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=30.0,
                ),
                headers={
                    "User-Agent": "UniversityEcosystem/1.0",
                    "Add-Padding": "true",
                },
            )
    return _hibp_client  # guaranteed non-None


async def close_hibp_client() -> None:
    """Close the shared HIBP client — call from app lifespan shutdown."""
    global _hibp_client
    if _hibp_client is not None:
        await _hibp_client.aclose()
        _hibp_client = None


async def validate_password_hibp(password: str, *, locale: str | None = None) -> None:
    # SHA-1 is required by the "Have I Been Pwned" API for their k-Anonymity model.
    # We only send the first 5 characters of the hash prefix to the API.
    # The full hash is never transmitted or stored.
    # ref: https://haveibeenpwned.com/API/v3#PwnedPasswords
    sha1 = _calculate_lookup_hash(password)
    prefix = sha1[:5]
    suffix = sha1[5:]
    url = f"{settings.password_hibp_api_url.rstrip('/')}/{prefix}"

    # RZ-2: fail_open mode allows password operations to succeed when HIBP is
    # unreachable. Default is fail-closed (False) for maximum security; set
    # PASSWORD_HIBP_FAIL_OPEN=true in environments with strict availability SLAs.
    fail_open: bool = getattr(settings, "password_hibp_fail_open", False)

    try:
        client = await _get_hibp_client()
        response = await client.get(url)
    except httpx.RequestError as exc:
        _logger.warning(
            "External breach lookup failed (fail-%s): %s",
            "open" if fail_open else "closed",
            exc,
        )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        if fail_open:
            return
        raise ValueError(
            translate("errors.auth.password_policy_hibp_unavailable", locale=locale)
        ) from exc

    if response.status_code != httpx.codes.OK:
        _logger.warning(
            "External breach lookup returned status %s", response.status_code
        )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        if fail_open:
            return
        raise ValueError(
            translate("errors.auth.password_policy_hibp_unavailable", locale=locale)
        )

    for line in response.text.splitlines():
        hashed_suffix, _, count = line.partition(":")
        if hashed_suffix.upper() == suffix:
            # LOW-W19: guard against malformed HIBP response lines where count
            # is not a valid integer (e.g. empty string after stripping padding).
            try:
                hit_count = int(count.strip() or 0)
            except ValueError:
                hit_count = 0
            if hit_count > 0:
                raise ValueError(
                    translate("errors.auth.password_policy_compromised", locale=locale)
                )
            break


def _validate_password_policy(password: str, *, locale: str | None = None) -> None:
    """Synchronous password policy checker (CPU-bound).

    PERF-W5-02 (audit 2026-03-14): This function uses zxcvbn (O(n²) complexity).
    It MUST remain synchronous. In async contexts, call it via get_password_hash()
    which offloads execution to a thread pool executor. Calling it directly
    from the main event loop will block processing.
    """
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
        # PERF-W8-02: Truncate to 72 chars before calling zxcvbn (library limit).
        # Do NOT shortcut to score=4 for long passwords — "a"*73 would be scored as
        # maximum strength despite being trivially weak. Truncating is safe: zxcvbn
        # is pattern-sensitive on the prefix, so a 73-char repeated string still
        # scores as weak after truncation.
        score = zxcvbn(password[:72]).get("score", 0)

        if score < min_score:
            raise ValueError(
                translate("errors.auth.password_policy_strength", locale=locale)
            )

    # HIBP (Have I Been Pwned) check is intentionally excluded here.
    # It requires an async HTTP call and is handled separately by async
    # service-layer callers (auth_service, user_service) via
    # validate_password_hibp().  This keeps get_password_hash() synchronous
    # so it remains usable from CLI commands and MFA code generation.


def verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    """Synchronous verification (CPU blocking)."""
    if hashed_password.startswith("$argon2"):
        try:
            argon2_hasher.verify(hashed_password, plain_password)
            return True
        except VerifyMismatchError:
            return False
        except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — unknown argon2 error returns False (reviewed TD-27-04)
            # TD-W8-01: Hash format is invalid or argon2 raised an unexpected error.
            # Do NOT fall back to bcrypt — a malformed $argon2 hash is not a bcrypt
            # hash, and bcrypt silently ignores unrecognised prefixes, meaning a
            # crafted argon2-prefixed string could pass bcrypt verification.
            # Return False: caller gets an authentication failure (safe default).
            _logger.warning(
                "argon2 verify raised unexpected error for $argon2-prefix hash — "
                "returning False (no bcrypt fallback): %s",
                type(exc).__name__,
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            return False
    # Only reach here for genuine legacy bcrypt hashes (no "$argon2" prefix).
    return _verify_legacy_bcrypt(plain_password, hashed_password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Asynchronous verification offloaded to thread pool with backpressure."""
    async with _get_argon2_semaphore():
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
        except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — falls through to legacy check that always rejects (reviewed TD-27-04)
            # Unexpected error from argon2 (e.g. malformed hash format).
            # TD-21-04 (Wave 21): Falls through to _verify_legacy_bcrypt which
            # now always returns False — forcing the user to reset their password.
            _logger.warning(
                "argon2 native verify_and_update raised unexpected error, "
                "falling through to legacy check (always rejects): %s",
                type(exc).__name__,
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure

    try:
        verified = _verify_legacy_bcrypt(plain_password, hashed_password)
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — bcrypt verification error returns False (reviewed TD-27-04)
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
    async with _get_argon2_semaphore():
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
    async with _get_argon2_semaphore():
        loop = asyncio.get_running_loop()
        func = partial(
            get_password_hash_sync,
            password,
            locale=locale,
            validate_policy=validate_policy,
        )
        return await loop.run_in_executor(_auth_executor, func)


def _mint_pure_jwt(
    subject: str | UUID,
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
        "aud": settings.jwt_audience,
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


_public_key_cache: dict[str, str] = {}
_public_key_cache_lock = threading.Lock()  # RZ-22-05 (Wave 22): reviewed — safe under CPython 3.13+ free-threading; CoW pattern (lines 547-580) ensures readers never see partial state


def _get_cached_public_key_pem(kid: str, private_key_pem: str) -> str:
    """Derive and cache the RSA public key PEM from a private key PEM.

    MOD-004: Adopts Copy-on-Write (CoW) to ensure GIL-free thread safety
    for fast-path reads in Python 3.13. Dictionary instances are never mutated
    in-place; instead, the global reference is swapped.
    """
    global _public_key_cache
    cache_key = kid or hashlib.sha256(private_key_pem.encode()).hexdigest()

    # Fast path — atomic reference read. The local dict copy is immutable.
    local_cache = _public_key_cache
    if cache_key in local_cache:
        return local_cache[cache_key]

    with _public_key_cache_lock:
        if cache_key in _public_key_cache:
            return _public_key_cache[cache_key]

        new_cache = _public_key_cache.copy()
        if len(new_cache) >= 32:
            oldest_key = next(iter(new_cache))
            del new_cache[oldest_key]

        key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        new_cache[cache_key] = (
            key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        _public_key_cache = new_cache
        # LOW-W19: return from new_cache (still in scope) instead of
        # _public_key_cache to avoid a TOCTOU race where another thread
        # could swap _public_key_cache between the assignment above and
        # the return statement outside the lock.
        return new_cache[cache_key]


def decode_token(token: str) -> dict[str, Any] | None:
    """Validate JWT signature and return the payload, or None if invalid.

    Does NOT check revocation — callers in async context must additionally
    call ``check_jti_revoked(jti)`` from deps to honour session invalidation.
    """
    registry = settings.jwt_signing_key_registry
    if not registry:
        return None

    # AUTH-2 (audit 2026-03): If the token carries a `kid` header, verify
    # ONLY with the key bound to that `kid`.  Previously the code fell back to
    # all registry entries, meaning a token signed with a revoked key could
    # still be accepted if any current key happened to verify it.
    #
    # Key-rotation strategy:
    #   • Tokens signed with the active kid → verified by its secret (fast path).
    #   • Tokens signed with an old kid still in the registry → verified by that
    #     old secret only (allows graceful rotation without immediate revocation).
    #   • Tokens with NO kid → fall back to the full registry (legacy tokens
    #     issued before kid-header support was added).
    #   • Tokens with a kid NOT present in the registry → rejected immediately.
    candidates: list[str] = []
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        header = {}

    kid = header.get("kid") if isinstance(header, dict) else None
    if isinstance(kid, str):
        kid_secret = registry.get(kid)
        if not kid_secret:
            # kid present but unknown — reject immediately; do not fall back.
            _logger.warning(
                "JWT rejected", reason="unknown kid", kid=kid
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            return None
        candidates = [kid_secret]
    else:
        # RZ-10 (audit 2026-03-04) fix:
        # Tokens without `kid` are immediately rejected.
        # This closes the O(N) timing side-channel attack vector.
        _logger.warning(
            "JWT rejected", reason="missing kid header"
        )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        return None

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
                        # RZ-5: Cache RSA public key extraction with lru_cache.
                        # load_pem_private_key + public_bytes is a full RSA operation:
                        # O(key_size). Without caching this runs on EVERY JWT request,
                        # Creating a significant CPU spike at scale. lru_cache keyed on
                        # the kid/PEM string auto-invalidates on key rotation.
                        # PERF-NEW-003: Now cached via tied kid+secret.
                        verification_key = _get_cached_public_key_pem(kid, secret)
                    except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — PEM parse error skips key candidate (reviewed TD-27-04)
                        _logger.error(
                            "Failed to extract public key from PEM for RS256 verification: %s",
                            exc,
                        )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                        continue
                else:
                    verification_key = secret

            payload = jwt.decode(
                token,
                verification_key,
                algorithms=[settings.algorithm],
                options={
                    # RZ-NEW-003 (audit 2026-03-19): Added "aud" to required claims.
                    # Previously only exp/iat/sub/jti were required; a token without
                    # an aud claim would be accepted even when audience validation is
                    # configured. Now any token missing aud is explicitly rejected.
                    "require": ["exp", "iat", "sub", "jti", "aud"],
                },
                # Direct access to settings field — never use getattr fallback.
                # (RZ-NEW-003: getattr fallback hides misconfiguration at startup.)
                audience=settings.jwt_audience,
            )
            return payload if isinstance(payload, dict) else dict(payload)
        except JWTError:
            continue
    return None
