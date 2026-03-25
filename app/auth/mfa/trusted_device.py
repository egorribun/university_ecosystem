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
from app.models.models import TrustedDevice, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _base64url_encode(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data).decode("utf-8")
    return encoded.rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sha256_hex(value: str) -> str:
    """Return lowercase hex-encoded SHA-256 digest of a string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, datetime]:
    """Issue a new trusted device token for the user."""
    token = secrets.token_urlsafe(48)
    token_hash = _base64url_encode(hashlib.sha256(token.encode("utf-8")).digest())
    now = _utcnow()
    expires_at = now + timedelta(days=settings.trusted_device_expire_days)

    # P1-W5-07: Store SHA-256 hashes for constant-time binding verification.
    ip_hash = _sha256_hex(ip_address) if ip_address else None
    ua_hash = _sha256_hex(user_agent) if user_agent else None

    device = TrustedDevice(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        last_used_at=now,
        user_agent=user_agent[:512] if user_agent else None,
        ip_address=ip_address[:64] if ip_address else None,
        ip_hash=ip_hash,
        ua_hash=ua_hash,
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
    if not token:
        return False

    try:
        token_hash = _base64url_encode(hashlib.sha256(token.encode("utf-8")).digest())
    except (
        Exception
    ):  # RZ-22-01-JUSTIFIED: fail-closed auth — hash failure returns False
        return False

    stmt = (
        select(TrustedDevice)
        .where(TrustedDevice.user_id == user.id)
        .where(TrustedDevice.token_hash == token_hash)
    )
    result = await db.execute(stmt)
    device = result.scalars().first()

    if not device:
        return False

    now = _utcnow()
    expires_at = device.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= now:
        await db.delete(device)
        await db.flush()
        return False

    # P1-W5-07: Soft device binding — only check when both the request context
    # and stored hashes are available.  Missing hashes indicate a pre-migration
    # device record; skip the check rather than reject.
    if request_ip and device.ip_hash:
        ip_matches = hmac.compare_digest(
            _sha256_hex(request_ip),
            device.ip_hash,
        )
        if not ip_matches:
            logger.warning(
                "trusted_device_ip_mismatch user_id=%s device_id=%s",
                user.id,
                device.id,
            )
            return False

    if request_ua and device.ua_hash:
        ua_matches = hmac.compare_digest(
            _sha256_hex(request_ua),
            device.ua_hash,
        )
        if not ua_matches:
            logger.warning(
                "trusted_device_ua_mismatch user_id=%s device_id=%s",
                user.id,
                device.id,
            )
            return False

    device.last_used_at = now
    await db.flush()
    return True
