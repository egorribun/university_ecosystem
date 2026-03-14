"""Request fingerprinting for MFA challenge binding.

RED-03 (audit 2026-03-14): Binds MFA challenge tokens to the originating
request's IP address and User-Agent to prevent token replay from a different
client after interception.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import Request


def extract_request_fingerprint(request: Request) -> str:
    """Compute a stable HMAC fingerprint for the originating request.

    Uses HMAC-SHA256 keyed by SECRET_KEY so that the fingerprint cannot be
    forged without knowledge of the server secret.  The raw IP+UA combination
    is not stored — only the keyed digest.

    Returns a 64-character hex string.
    """
    # Prefer the real client IP from the first X-Forwarded-For entry (Caddy
    # sets this reliably).  Fall back to the direct connection host.
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not ip and request.client:
        ip = request.client.host or ""

    # Cap User-Agent length to 512 bytes to prevent DoS via huge UA strings.
    user_agent = request.headers.get("User-Agent", "")[:512]

    raw = f"{ip}|{user_agent}"
    key = (
        settings.SECRET_KEY.encode()
        if isinstance(settings.SECRET_KEY, str)
        else settings.SECRET_KEY
    )
    return hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
