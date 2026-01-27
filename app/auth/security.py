import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
from jwt import PyJWTError as JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from zxcvbn import zxcvbn

from app.auth.redis_session import get_session_backend
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


def _format_password_class_labels(class_names: list[str], *, locale: str | None) -> str:
    translated = [
        translate(f"password.class.{class_name}", locale=locale)
        for class_name in class_names
    ]
    return ", ".join(translated)


def _validate_password_hibp(password: str, *, locale: str | None = None) -> None:
    # SHA-1 is required by the "Have I Been Pwned" API for their k-Anonymity model.
    # We only send the first 5 characters of the hash prefix to the API.
    # The full hash is never transmitted or stored.
    # ref: https://haveibeenpwned.com/API/v3#PwnedPasswords
    sha1 = (
        hashlib.sha1(password.encode("utf-8"), usedforsecurity=False)
        .hexdigest()
        .upper()
    )
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
    return pwd_context.verify(plain_password, hashed_password)


def verify_and_update_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
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
    return pwd_context.hash(password)


async def create_access_token(
    sub: str | Any,
    expires_delta: int | None = None,
    extra: dict | None = None,
    db: AsyncSession | None = None,
    session_metadata: dict | None = None,
) -> str | tuple[str, ActiveSession]:
    minutes = expires_delta or settings.access_token_expire_minutes
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
    if extra:
        payload.update(extra)
    kid = settings.jwt_signing_active_kid
    secret = settings.jwt_signing_active_secret
    token = jwt.encode(
        payload,
        secret,
        algorithm=settings.algorithm,
        headers={"kid": kid},
    )
    if db is not None:
        try:
            user_id = int(sub)
        except (TypeError, ValueError):  # pragma: no cover - defensive guard
            raise ValueError(
                "sub must be an integer when persisting sessions"
            ) from None
        session = ActiveSession(user_id=user_id, jti=jti, expires_at=expires_at)
        session.signing_key = secrets.token_urlsafe(32)
        if session_metadata:
            ip_address = session_metadata.get("ip_address")
            user_agent = session_metadata.get("user_agent")
            accept_language = session_metadata.get("accept_language")
            fingerprint_hash = session_metadata.get("fingerprint_hash")
            last_seen_at = session_metadata.get("last_seen_at")
            mfa_required = session_metadata.get("mfa_required")
            mfa_method = session_metadata.get("mfa_method")
            mfa_completed_at = session_metadata.get("mfa_completed_at")
            mfa_verified_at = session_metadata.get("mfa_verified_at")
            if ip_address:
                session.ip_address = str(ip_address)[:64]
            if user_agent:
                session.user_agent = str(user_agent)[:512]
            if accept_language:
                session.accept_language = str(accept_language)[:256]
            if fingerprint_hash:
                session.fingerprint_hash = str(fingerprint_hash)[:64]
            if last_seen_at is not None:
                session.last_seen_at = last_seen_at
            if mfa_required is not None:
                session.mfa_required = bool(mfa_required)
            if mfa_method is not None:
                method_text = str(mfa_method).strip()
                session.mfa_method = method_text[:64] if method_text else None
            if mfa_completed_at is not None:
                session.mfa_completed_at = mfa_completed_at
            if mfa_verified_at is not None:
                session.mfa_verified_at = mfa_verified_at
        db.add(session)

        # Enforce concurrent session limit (revoke oldest sessions if limit exceeded)
        max_sessions = settings.max_sessions_per_user
        if max_sessions > 0:
            from sqlalchemy import func, select
            from sqlalchemy.orm import load_only

            # Count current active sessions for this user (excluding just-created one)
            count_stmt = (
                select(func.count(ActiveSession.id))
                .where(ActiveSession.user_id == user_id)
                .where(ActiveSession.revoked_at.is_(None))
                .where(ActiveSession.expires_at > now)
            )
            result = await db.execute(count_stmt)
            active_count = result.scalar_one_or_none() or 0

            # If limit exceeded, revoke oldest sessions
            if active_count > max_sessions:
                excess_count = active_count - max_sessions
                oldest_stmt = (
                    select(ActiveSession)
                    .options(load_only(ActiveSession.id, ActiveSession.jti))
                    .where(ActiveSession.user_id == user_id)
                    .where(ActiveSession.revoked_at.is_(None))
                    .where(ActiveSession.expires_at > now)
                    .where(ActiveSession.jti != jti)  # Exclude current session
                    .order_by(ActiveSession.created_at.asc())
                    .limit(excess_count)
                )
                oldest_sessions = (await db.execute(oldest_stmt)).scalars().all()

                session_backend = await get_session_backend()
                for old_session in oldest_sessions:
                    old_session.revoked_at = now
                    await session_backend.revoke_session(old_session.jti)

        await db.commit()
        await db.refresh(session)

        # Register in Redis session backend if enabled
        session_backend = await get_session_backend()
        await session_backend.register_session(
            user_id=user_id,
            jti=jti,
            expires_at=expires_at,
            metadata={
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
            },
        )
        return token, session
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
