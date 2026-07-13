"""Request fingerprinting for MFA challenge binding.

RED-03 (audit 2026-03-14): Binds MFA challenge tokens to the originating
request's IP address and User-Agent to prevent token replay from a different
client after interception.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import Request

logger = get_logger(__name__)


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
    # Case-insensitive lookup for headers to handle both Starlette Headers and plain dicts in tests.
    headers_raw: Any = request.headers
    headers = (
        {k.lower(): v for k, v in headers_raw.items()}
        if isinstance(headers_raw, dict)
        else headers_raw
    )
    user_agent = headers.get("user-agent", "")[:512]

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

    RED-03: Fingerprints are compared at verify time via ``verify_mfa_fingerprint``.
    Both the login MFA and step-up MFA paths route through ``verify_mfa_challenge``
    which calls this function's counterpart.  A separate key is stored for every
    method so the client can freely choose which method to use without losing
    protection.

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
    except (
        RuntimeError,
        ConnectionError,
        TimeoutError,
        OSError,
    ):  # RZ-22-01: narrowed — Redis/NullCache errors
        logger.warning(
            "Could not store MFA fingerprints in Redis — replay protection degraded",
            exc_info=True,
        )


async def verify_mfa_fingerprint(
    request: Request,
    challenge_token: str,
) -> bool:
    """Verify that the current request matches the fingerprint stored at challenge issuance.

    RED-03: Called before ``mfa.consume_challenge()`` in any endpoint that consumes
    a MFA challenge token.  Both login and step-up flows route through
    ``verify_mfa_challenge`` in ``app.api.auth.login``, so a single call site
    provides full coverage.

    Returns:
        ``True``  — fingerprint matches, or Redis is unavailable (graceful degradation),
                    or no fingerprint was stored (challenge pre-dates RED-03).
        ``False`` — stored fingerprint exists AND differs from the current request.

    The caller must reject with HTTP 403 ``mfa_fingerprint_mismatch`` on ``False``.
    Graceful degradation on Redis errors is logged at WARNING (same severity as
    ``store_mfa_challenge_fingerprints``) so on-call alerts treat them equivalently.
    """
    from app.deps.cache import get_cache_client

    try:
        cache = await get_cache_client()
        stored_raw = await cache.get(f"mfa:fp:{challenge_token}")
    except (
        RuntimeError,
        ConnectionError,
        TimeoutError,
        OSError,
    ):  # RZ-22-01: narrowed — Redis/NullCache errors
        # Redis unavailable — don't block auth, but log at WARNING so both store
        # and verify degradations appear at the same alert threshold.
        logger.warning(
            "mfa.fingerprint_cache_unavailable — skipping fingerprint check",
            exc_info=True,
        )
        return True  # degrade gracefully

    if stored_raw is None:
        # No fingerprint stored — challenge pre-dates RED-03 or already expired.
        return True

    stored: str = stored_raw.decode() if isinstance(stored_raw, bytes) else stored_raw
    current = extract_request_fingerprint(request)
    if stored != current:
        logger.warning(
            "mfa.fingerprint_mismatch",
            extra={"challenge_token_prefix": challenge_token[:8]},
        )
        return False

    return True
