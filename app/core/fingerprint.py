"""Request fingerprinting for MFA challenge binding.

RED-03 (audit 2026-03-14): Binds MFA challenge tokens to the originating
request's IP address and User-Agent to prevent token replay from a different
client after interception.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)


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


async def store_mfa_challenge_fingerprints(
    request: Request,
    methods: Sequence[Any],
) -> None:
    """Store a request fingerprint in Redis for each pending MFA challenge token.

    RED-03: Fingerprints are compared at verify time (``verify_mfa_challenge``
    and ``verify_step_up``) to detect token replay from a different client after
    interception.  A separate key is stored for every method so the client can
    freely choose which method to use without losing protection.

    Args:
        request:  The current FastAPI ``Request`` (used to extract IP + UA).
        methods:  A sequence of objects with ``challenge_token: str`` and
                  ``challenge_expires_at: datetime`` attributes.  Duck-typed so
                  that ``app.core`` remains independent of ``app.auth.schemas``.

    Graceful degradation: if Redis is unavailable the function logs a warning
    and returns without raising, so callers do not need to handle errors.
    """
    from datetime import UTC, datetime

    from app.deps.cache import get_cache_client

    fp = extract_request_fingerprint(request)
    try:
        cache = await get_cache_client()
        for method in methods:
            # TTL = remaining seconds until challenge expiry, min 30 s for clock skew.
            remaining = max(
                30,
                int((method.challenge_expires_at - datetime.now(UTC)).total_seconds()),
            )
            await cache.setex(f"mfa:fp:{method.challenge_token}", remaining, fp)
    except Exception:
        logger.warning(
            "Could not store MFA fingerprints in Redis — replay protection degraded",
            exc_info=True,
        )
