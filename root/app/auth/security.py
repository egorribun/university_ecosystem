import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.redis_session import get_session_backend
from app.core.config import settings
from app.localization import translate
from app.models.models import ActiveSession

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 200
LEGACY_BCRYPT_MAX_BYTES = 72
ARGON2_MEMORY_COST_KIB = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

DEFAULT_SCHEME = "argon2"
LEGACY_SCHEME = "bcrypt"


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
            secret, ident = _orig(cls, secret, ident, new=new)
            if (
                isinstance(secret, bytes | bytearray)
                and len(secret) > LEGACY_BCRYPT_MAX_BYTES
            ):
                secret = secret[:LEGACY_BCRYPT_MAX_BYTES]
            return secret, ident

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


def _validate_password_policy(password: str, *, locale: str | None = None) -> None:
    length = len(password)
    if length < PASSWORD_MIN_LENGTH or length > PASSWORD_MAX_LENGTH:
        raise ValueError(translate("errors.auth.password_policy", locale=locale))


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


def get_password_hash(password: str, *, locale: str | None = None) -> str:
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
            last_seen_at = session_metadata.get("last_seen_at")
            mfa_required = session_metadata.get("mfa_required")
            mfa_method = session_metadata.get("mfa_method")
            mfa_completed_at = session_metadata.get("mfa_completed_at")
            mfa_verified_at = session_metadata.get("mfa_verified_at")
            if ip_address:
                session.ip_address = str(ip_address)[:64]
            if user_agent:
                session.user_agent = str(user_agent)[:512]
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
            }
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
