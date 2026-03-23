"""RZ-W16-08: SSRF blocklist for outbound HTTP requests.

Validates that target URLs do not resolve to internal/private networks,
preventing Server-Side Request Forgery against cloud metadata services
(169.254.169.254), localhost, and RFC-1918 ranges.
"""

from __future__ import annotations

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
    return any(addr in net for net in _BLOCKED_NETWORKS)


def validate_url_not_internal(url: str) -> None:
    """Raise ``ValueError`` if *url* resolves to a blocked internal network.

    Call at service-init time (not per-request) for config-driven base URLs.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    # Fast path: hostname is an IP literal.
    try:
        addr = ipaddress.ip_address(hostname)
        if _is_blocked(addr):
            raise ValueError(
                f"SSRF blocked: {hostname} is in a private/reserved network"
            )
        return
    except ValueError:
        pass  # Not an IP literal — resolve via DNS below.

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # DNS failure is not an SSRF concern — let the caller handle it.
        return

    for _, _, _, _, sockaddr in resolved:
        addr = ipaddress.ip_address(sockaddr[0])
        if _is_blocked(addr):
            raise ValueError(f"SSRF blocked: {hostname} resolves to internal IP {addr}")
