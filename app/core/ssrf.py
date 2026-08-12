"""RZ-W16-08 / RZ-W17-01: SSRF blocklist for outbound HTTP requests.

Validates that target URLs do not resolve to internal/private networks,
preventing Server-Side Request Forgery against cloud metadata services
(169.254.169.254), localhost, and RFC-1918 ranges.

RZ-W17-01 (Wave 17): fail-closed on DNS errors + ``validate_and_resolve``
to prevent DNS rebinding (TOCTOU between validation and HTTP request).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC-1918 Class A
    ipaddress.ip_network("172.16.0.0/12"),  # RFC-1918 Class B
    ipaddress.ip_network("192.168.0.0/16"),  # RFC-1918 Class C
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS IMDS
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598)
    ipaddress.ip_network("0.0.0.0/8"),  # "this" network
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
)


def _is_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # IPv4-mapped IPv6 literals (for example ``::ffff:127.0.0.1``) carry the
    # same trust-boundary semantics as their IPv4 address.  Normalize them
    # before applying the network table so an alternate textual family cannot
    # bypass the SSRF guard.
    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped
        if mapped is not None:
            return _is_blocked(mapped)
    return any(addr in net for net in _BLOCKED_NETWORKS)


def validate_public_https_url(url: str) -> None:
    """Validate syntax and local-address safety for a public HTTPS URL.

    Push endpoints are supplied by browsers, so a provider allow-list is not
    appropriate.  This check is safe before persistence; callers should also
    resolve and validate the hostname immediately before an outbound request.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must not be empty")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https":
        raise ValueError("URL must use https scheme")
    if not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("URL must include a host and no credentials")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL has an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("URL has an invalid port")

    normalized_hostname = hostname.rstrip(".").lower()
    if normalized_hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("URL hostname is local")
    try:
        address = ipaddress.ip_address(normalized_hostname)
    except ValueError:
        return
    if _is_blocked(address):
        raise ValueError(f"URL resolves to a private/reserved address: {address}")


def _check_ip_literal(
    hostname: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the parsed IP if *hostname* is an IP literal, else ``None``."""
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if _is_blocked(addr):
        raise ValueError(f"SSRF blocked: {hostname} is in a private/reserved network")
    return addr


def _check_resolved(
    hostname: str,
    resolved: list[
        tuple[
            socket.AddressFamily,
            int,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ],
) -> None:
    """Raise ``ValueError`` if any resolved address falls into a blocked network.

    RZ-W19-02 (audit 2026-03-24 Wave 19): IP parsing errors are now fail-closed.
    If ``ipaddress.ip_address()`` raises ``ValueError`` on malformed sockaddr data
    (e.g., from a custom DNS resolver), the request is rejected rather than allowed.
    """
    for _, _, _, _, sockaddr in resolved:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            # TD-27-03: Distinguish DNS resolver malformat from blocked IP
            raise ValueError(
                f"SSRF blocked: {hostname} resolved to address {sockaddr[0]!r} "
                f"which is not a valid IP (possible DNS resolver misconfiguration) "
                f"— fail-closed per RZ-W19-02"
            ) from None
        if _is_blocked(addr):
            raise ValueError(f"SSRF blocked: {hostname} resolves to internal IP {addr}")


def validate_url_not_internal(url: str) -> None:
    """Raise ``ValueError`` if *url* resolves to a blocked internal network.

    Call at service-init time (not per-request) for config-driven base URLs.

    .. warning:: **Do NOT call from async context.**
        This function calls ``socket.getaddrinfo()`` which is a blocking
        syscall.  Calling it inside an asyncio coroutine blocks the entire
        event loop for the duration of the DNS query (potentially hundreds of
        milliseconds).  Use :func:`validate_url_not_internal_async` for any
        per-request or async code path instead.  MED-W19

    RZ-W17-01: DNS failures are now **fail-closed** (raise ``ValueError``).
    Previously DNS errors silently passed, allowing SSRF when an attacker
    controlled a hostname with intermittent DNS responses.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    # Fast path: hostname is an IP literal.
    if _check_ip_literal(hostname) is not None:
        return

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        # RZ-W17-01: Fail-closed — DNS failure MUST NOT silently pass.
        raise ValueError(f"SSRF blocked: DNS resolution failed for {hostname}") from exc

    _check_resolved(hostname, resolved)  # type: ignore[arg-type]


async def validate_url_not_internal_async(url: str) -> None:
    """Async variant of :func:`validate_url_not_internal`.

    PERF-W17-01: Uses ``loop.getaddrinfo`` to avoid blocking the event loop
    during DNS resolution.  Suitable for per-request validation paths.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if _check_ip_literal(hostname) is not None:
        return

    loop = asyncio.get_running_loop()
    try:
        resolved = await loop.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"SSRF blocked: DNS resolution failed for {hostname}") from exc

    _check_resolved(hostname, resolved)  # type: ignore[arg-type]


def validate_and_resolve(url: str) -> list[tuple[str, int]]:
    """Validate *url* and return resolved ``(ip, port)`` pairs.

    RZ-W17-01: Callers **MUST** use the returned addresses for the actual
    HTTP connection to prevent DNS rebinding (TOCTOU between validation and
    request).  The resolved IPs can be passed to httpx via a custom transport
    or by rewriting the URL to an IP literal with an explicit ``Host`` header.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not hostname:
        raise ValueError("URL has no hostname")

    # Fast path: hostname is an IP literal.
    literal = _check_ip_literal(hostname)
    if literal is not None:
        return [(str(literal), port)]

    try:
        resolved = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"SSRF blocked: DNS resolution failed for {hostname}") from exc

    safe_addrs: list[tuple[str, int]] = []
    for _, _, _, _, sockaddr in resolved:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            # RZ-26-06: fail-closed on unparseable sockaddr (parity with _check_resolved)
            raise ValueError(
                f"SSRF blocked: unparseable address from DNS for {hostname}"
            ) from exc
        if _is_blocked(addr):
            raise ValueError(f"SSRF blocked: {hostname} resolves to internal IP {addr}")
        safe_addrs.append((str(addr), sockaddr[1]))  # type: ignore[arg-type]  # sockaddr[1] is always int for AF_INET/AF_INET6

    if not safe_addrs:
        raise ValueError(f"SSRF blocked: no valid addresses for {hostname}")
    return safe_addrs
