"""Request fingerprinting for MFA challenge binding.

RED-03 (audit 2026-03-14): Binds MFA challenge tokens to the originating
request's IP address and User-Agent to prevent token replay from a different
client after interception.
"""

from __future__ import annotations

import hashlib
import hmac
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
    # Trust proxy metadata only through the central resolver, which validates
    # the direct peer against the configured trusted-proxy boundary.
    from app.core.ratelimit import resolve_client_ip

    ip = resolve_client_ip(request)

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
