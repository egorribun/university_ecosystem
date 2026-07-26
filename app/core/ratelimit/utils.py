from __future__ import annotations

import ipaddress
from collections.abc import Sequence
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


def _parse_trusted_proxies(
    proxies: Sequence[
        str
        | ipaddress.IPv4Network
        | ipaddress.IPv6Network
        | ipaddress.IPv4Address
        | ipaddress.IPv6Address
    ],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse trusted proxy definitions into ipaddress network objects."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in proxies:
        if isinstance(item, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            networks.append(item)
            continue
        if isinstance(item, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            networks.append(ipaddress.ip_network(str(item), strict=False))
            continue
        raw = str(item).strip()
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except (
            ValueError,
            TypeError,
        ):  # RZ-22-01: invalid IP network or address format
            try:
                ip_addr = ipaddress.ip_address(raw)
                networks.append(ipaddress.ip_network(str(ip_addr), strict=False))
            except (ValueError, TypeError):  # RZ-22-01: invalid IP string
                pass
    return networks


def _normalize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except (ValueError, TypeError):  # RZ-22-01: invalid IP format
        return None


def _normalize_ip_obj(
    ip: str | None,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not ip:
        return None
    try:
        return ipaddress.ip_address(ip.strip())
    except (ValueError, TypeError):  # RZ-22-01: invalid IP format
        return None


def _is_ip_trusted(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    trusted_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    """Check if an IP object matches any trusted proxy network."""
    for net in trusted_networks:
        if ip_obj.version == net.version and ip_obj in net:
            return True
    return False


def _extract_ips_from_forwarded(forwarded: str) -> list[str]:
    """Extract 'for' parameters from RFC 7239 Forwarded header."""
    ips: list[str] = []
    for element in forwarded.split(","):
        for part in element.split(";"):
            part = part.strip()
            if part.lower().startswith("for="):
                ip = part[4:].strip('"[]')
                ips.append(ip)
    return ips


def _extract_ip_from_forwarded(forwarded: str) -> str | None:
    """Extract first 'for' parameter from RFC 7239 Forwarded header."""
    ips = _extract_ips_from_forwarded(forwarded)
    return ips[0] if ips else None


def resolve_client_ip(request: Request) -> str:
    """Resolve the real client IP, respecting trusted proxies.

    Traverses X-Forwarded-For / Forwarded headers from right to left (from the
    trusted proxy boundary backwards) to locate the first untrusted IP.
    """
    client_host = request.client.host if request.client else "unknown"
    client_ip_obj = _normalize_ip_obj(client_host)
    normalized_client = str(client_ip_obj) if client_ip_obj else client_host

    trusted_networks = _parse_trusted_proxies(settings.trusted_proxies_list)

    if not client_ip_obj or not _is_ip_trusted(client_ip_obj, trusted_networks):
        return normalized_client

    # Immediate socket peer is a trusted proxy. Check X-Forwarded-For
    xfwd = request.headers.get("X-Forwarded-For")
    if xfwd:
        cleaned_ips: list[
            tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address]
        ] = []
        for part in xfwd.split(","):
            obj = _normalize_ip_obj(part)
            if obj is not None:
                cleaned_ips.append((str(obj), obj))

        if cleaned_ips:
            # Traverse right to left (from the trusted proxy boundary backwards)
            for ip_str, obj in reversed(cleaned_ips):
                if not _is_ip_trusted(obj, trusted_networks):
                    return ip_str
            # All valid IPs in header are trusted proxies -> return left-most valid IP
            return cleaned_ips[0][0]

    # Check RFC 7239 Forwarded header
    fwd = request.headers.get("Forwarded")
    if fwd:
        extracted_ips = _extract_ips_from_forwarded(fwd)
        fwd_cleaned: list[
            tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address]
        ] = []
        for raw_ip in extracted_ips:
            obj = _normalize_ip_obj(raw_ip)
            if obj is not None:
                fwd_cleaned.append((str(obj), obj))

        if fwd_cleaned:
            for ip_str, obj in reversed(fwd_cleaned):
                if not _is_ip_trusted(obj, trusted_networks):
                    return ip_str
            return fwd_cleaned[0][0]

    return normalized_client


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
        from app.auth.security import decode_token

        payload = decode_token(token)
        sub = payload.get("sub") if payload else None
        return str(sub) if sub else None
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — token decode failure returns None (anonymous) (reviewed TD-27-04)
        return None
