"""Trusted device token issuance and verification."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import settings
from app.models.models import TrustedDevice, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _base64url_encode(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data).decode("utf-8")
    return encoded.rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


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

    device = TrustedDevice(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        last_used_at=now,
        user_agent=user_agent[:512] if user_agent else None,
        ip_address=ip_address[:64] if ip_address else None,
    )
    db.add(device)
    await db.flush()
    return token, expires_at


async def verify_trusted_device_token(
    db: AsyncSession,
    *,
    user: User,
    token: str,
) -> bool:
    """Check if the provided token is valid for the user."""
    if not token:
        return False

    try:
        token_hash = _base64url_encode(hashlib.sha256(token.encode("utf-8")).digest())
    except Exception:
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

    device.last_used_at = now
    await db.flush()
    return True
