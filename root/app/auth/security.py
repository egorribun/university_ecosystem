from datetime import datetime, timedelta, timezone
from typing import Any, Union

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 200
LEGACY_BCRYPT_MAX_BYTES = 72
ARGON2_MEMORY_COST_KIB = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

DEFAULT_SCHEME = "argon2"
LEGACY_SCHEME = "bcrypt"

pwd_context = CryptContext(
    schemes=[DEFAULT_SCHEME, LEGACY_SCHEME],
    default=DEFAULT_SCHEME,
    deprecated=[LEGACY_SCHEME],
    argon2__type="ID",
    argon2__memory_cost=ARGON2_MEMORY_COST_KIB,
    argon2__time_cost=ARGON2_TIME_COST,
    argon2__parallelism=ARGON2_PARALLELISM,
)


def _validate_password_policy(password: str) -> None:
    length = len(password)
    if length < PASSWORD_MIN_LENGTH or length > PASSWORD_MAX_LENGTH:
        raise ValueError("Пароль должен содержать от 8 до 200 символов.")


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


def get_password_hash(password: str, *, scheme: str | None = None) -> str:
    _validate_password_policy(password)
    target_scheme = scheme or DEFAULT_SCHEME
    prepared_password = (
        _truncate_for_bcrypt(password) if target_scheme == LEGACY_SCHEME else password
    )
    return pwd_context.hash(prepared_password, scheme=target_scheme)


def create_access_token(
    sub: Union[str, Any], expires_delta: int | None = None, extra: dict | None = None
) -> str:
    minutes = expires_delta or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
