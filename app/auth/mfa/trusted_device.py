"""Trusted device token issuance and verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models import TrustedDevice, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sha256_hex(value: str) -> str:
    """Return lowercase hex-encoded SHA-256 digest of a string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _configured_keyring() -> tuple[dict[str, bytes], str]:
    keys: dict[str, bytes] = {}
    for entry in settings.mfa_trusted_device_hmac_keys.split(","):
        if not entry.strip():
            continue
        try:
            parts = entry.split(":")
            if len(parts) != 2:
                raise ValueError("trusted-device key entry must contain one delimiter")
            key_id, encoded = parts
            keys[key_id.strip()] = _base64url_decode(encoded.strip())
        except (ValueError, TypeError):
            raise RuntimeError("trusted-device key configuration invalid") from None
    active = settings.mfa_trusted_device_active_hmac_key_id
    if not keys and settings.environment == "testing":
        active = "test-primary"
        keys[active] = hashlib.sha256(settings.secret_key.encode()).digest()
    if not active or active not in keys or any(len(key) < 32 for key in keys.values()):
        raise RuntimeError("trusted-device key configuration unavailable")
    return keys, active


def _token_digest(key: bytes, token: str) -> str:
    return hmac.new(
        key, f"trusted-token\x1f{token}".encode(), hashlib.sha256
    ).hexdigest()


def _binding_digest(key: bytes, ip_address: str, user_agent: str) -> str:
    normalized = f"{ip_address.strip()}\x1f{user_agent.strip()[:512]}"
    return hmac.new(
        key, f"trusted-binding\x1f{normalized}".encode(), hashlib.sha256
    ).hexdigest()


async def create_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, datetime]:
    """Issue a new trusted device token for the user."""
    token = secrets.token_urlsafe(48)
    if not ip_address or not user_agent:
        raise ValueError("trusted-device binding is required")
    keys, active_key_id = _configured_keyring()
    key = keys[active_key_id]
    token_hash = _token_digest(key, token)
    now = _utcnow()
    expires_at = now + timedelta(days=settings.trusted_device_expire_days)

    # P1-W5-07: Store SHA-256 hashes for constant-time binding verification.
    ip_hash = _sha256_hex(ip_address)
    ua_hash = _sha256_hex(user_agent)

    device = TrustedDevice(
        user_id=user.id,
        token_hash=token_hash,
        token_key_id=active_key_id,
        binding_digest=_binding_digest(key, ip_address, user_agent),
        expires_at=expires_at,
        last_used_at=now,
        user_agent=user_agent[:512] if user_agent else None,
        ip_address=ip_address[:64] if ip_address else None,
        ip_hash=ip_hash,
        ua_hash=ua_hash,
        mfa_epoch=int(user.mfa_epoch or 0),
    )
    db.add(device)
    await db.flush()
    return token, expires_at


async def verify_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    token: str,
    request_ip: str | None = None,
    request_ua: str | None = None,
) -> bool:
    """Check if the provided token is valid for the user.

    P1-W5-07: When *request_ip* and *request_ua* are supplied, the stored
    SHA-256 hashes are compared via ``hmac.compare_digest`` (constant-time).
    A mismatch emits a warning and returns ``False`` so the caller can
    re-challenge with full MFA.  When either binding value is absent
    (old device records or callers without request context), the check
    is skipped.
    """
    return (
        await _consume_trusted_device_token(
            db,
            user=user,
            token=token,
            request_ip=request_ip,
            request_ua=request_ua,
            rotate=False,
        )
        is not None
    )


async def verify_and_rotate_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    token: str,
    request_ip: str | None,
    request_ua: str | None,
) -> str | None:
    return await _consume_trusted_device_token(
        db,
        user=user,
        token=token,
        request_ip=request_ip,
        request_ua=request_ua,
        rotate=True,
    )


async def _consume_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    token: str,
    request_ip: str | None,
    request_ua: str | None,
    rotate: bool,
) -> str | None:
    if not token or not isinstance(token, str) or not request_ip or not request_ua:
        return None

    try:
        keys, active_key_id = _configured_keyring()
        candidates = [_token_digest(key, token) for key in keys.values()]
    except (RuntimeError, TypeError) as exc:
        from app.auth.mfa.email_otp import MfaSecurityUnavailable

        raise MfaSecurityUnavailable() from exc

    locked_user = (
        await db.execute(
            select(User)
            .where(User.id == user.id)
            .with_for_update(nowait=False)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if locked_user is None:
        return None

    stmt = (
        select(TrustedDevice)
        .where(TrustedDevice.user_id == user.id)
        .where(TrustedDevice.token_hash.in_(candidates))
        .with_for_update(nowait=False)
    )
    result = await db.execute(stmt)
    device = result.scalars().first()

    if not device:
        return None

    key = keys.get(device.token_key_id or "")
    if (
        key is None
        or device.binding_digest is None
        or device.mfa_epoch != int(locked_user.mfa_epoch or 0)
    ):
        await db.delete(device)
        await db.flush()
        return None

    now = _utcnow()
    expires_at = device.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= now:
        await db.delete(device)
        await db.flush()
        return None

    # P1-W5-07: Soft device binding — only check when both the request context
    # and stored hashes are available.  Missing hashes indicate a pre-migration
    # device record; skip the check rather than reject.
    if not hmac.compare_digest(
        _binding_digest(key, request_ip, request_ua), device.binding_digest
    ):
        logger.warning(
            "trusted_device_binding_mismatch user_id=%s device_id=%s",
            user.id,
            device.id,
        )
        await db.delete(device)
        await db.flush()
        return None

    device.last_used_at = now
    rotated_token = token
    if rotate:
        rotated_token = secrets.token_urlsafe(48)
        active_key = keys[active_key_id]
        device.token_hash = _token_digest(active_key, rotated_token)
        device.token_key_id = active_key_id
        device.binding_digest = _binding_digest(active_key, request_ip, request_ua)
    await db.flush()
    return rotated_token
