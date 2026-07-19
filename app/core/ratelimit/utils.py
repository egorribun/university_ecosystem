from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import Request

_TIME_UNITS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
}


def parse_rate_limit(
    value: str | None,
    *,
    fallback: tuple[int, int],
) -> tuple[int, int]:
    """Parse a rate limit definition (e.g., '5 per minute' or '10/60')."""
    if not value:
        return fallback

    normalized = value.strip().lower()
    if not normalized:
        return fallback

    normalized = normalized.replace("per", "/")
    parts = normalized.split("/", 1) if "/" in normalized else normalized.split()

    if len(parts) != 2:
        return fallback

    count_raw, unit_raw = (part.strip() for part in parts)

    try:
        count = int(count_raw)
    except ValueError:
        return fallback

    unit_key = unit_raw.rstrip("s")
    seconds = _TIME_UNITS.get(unit_raw) or _TIME_UNITS.get(unit_key)
    if seconds is None:
        try:
            seconds = int(unit_raw)
        except ValueError:
            return fallback

    if count <= 0 or seconds <= 0:
        return fallback

    return count, seconds


def _normalize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def _extract_ip_from_forwarded(forwarded: str) -> str | None:
    """Extract 'for' parameter from RFC 7239 Forwarded header."""
    for part in forwarded.split(";"):
        part = part.strip()
        if part.lower().startswith("for="):
            ip = part[4:].strip('"[]')
            return ip
    return None


def resolve_client_ip(request: Request) -> str:
    """Resolve the real client IP, respecting trusted proxies."""
    client_host = request.client.host if request.client else "unknown"
    normalized_client = _normalize_ip(client_host) or "unknown"
    trusted = {_normalize_ip(proxy) for proxy in settings.trusted_proxies_list}
    trusted.discard(None)

    ip: str | None = None
    if normalized_client in trusted:
        # Check X-Forwarded-For
        xfwd = request.headers.get("X-Forwarded-For")
        if xfwd:
            for part in xfwd.split(","):
                candidate = _normalize_ip(part)
                if candidate:
                    ip = candidate
                    break

        # Check RFC 7239 Forwarded
        if not ip:
            fwd = request.headers.get("Forwarded")
            if fwd:
                ip = _normalize_ip(_extract_ip_from_forwarded(fwd))

    return ip or normalized_client


def compose_identifier(namespace: str, identifier: str) -> str:
    ident = identifier.strip() or "unknown"
    ns = namespace.strip()
    return f"{ns}:{ident}" if ns else ident


def extract_user_id_for_ratelimit(request: Request) -> str | None:
    """Extract the authenticated user's sub claim for per-user rate limiting.

    D-08 (audit 2026-03-08): Uses a lightweight JWT decode (no DB calls) to
    retrieve the ``sub`` claim so that ``sensitive_route_limit`` can key on
    user identity rather than IP.  This is safe for rate-limiting purposes:
    we are not granting access based on this claim, only bucketing requests.

    Falls back to ``None`` when the token is absent or unparseable — the
    caller should then fall back to an IP-based key.
    """
    token: str | None = None

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip() or None

    if not token:
        token = request.cookies.get("access_token_v2")

    if not token:
        return None

    try:
        import sys

        from app.auth.security import decode_token

        print(
            f"DEBUG UTILS: sys.modules['app.auth.security'] id={id(sys.modules.get('app.auth.security'))}",
            file=sys.stderr,
        )
        print(
            f"DEBUG UTILS: decode_token={decode_token} id={id(decode_token)}",
            file=sys.stderr,
        )

        payload = decode_token(token)
        sub = payload.get("sub") if payload else None
        return str(sub) if sub else None
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — token decode failure returns None (anonymous) (reviewed TD-27-04)
        return None
