"""Synthetic application contract for valid client-IP chains before migration.

C is the actual client, F a forged prefix, P an upstream L7 proxy, E the edge,
and G the Go gateway. Every role uses a distinct documentation-only address.
The cases exercise configure_middleware, its ProxyHeadersMiddleware rewrite,
resolve_client_ip, and the real in-memory limiter, not a helper-only model.

These are supplied ASGI peers and ordered headers, NOT Envoy/nginx/Caddy/CNI
runtime transport evidence or deployment acceptance. They open no listeners,
do not prove which headers a deployed proxy emits, and approve no trust range.
Malformed headers and production parser or configuration changes are outside
this contract. Incomplete trust is a negative control, not a target topology.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.middleware.setup import configure_middleware
from app.core.ratelimit import resolve_client_ip

_OBSERVE_PATH = "/api/v1/envoy-topology/observe"
_LIMITED_PATH = "/api/v1/auth/login/json"
_CSRF_PATH = "/api/v1/auth/csrf-cookie"

_ADDRESS_FAMILIES = (
    pytest.param(
        {
            "client_a": "192.0.2.10",
            "client_b": "198.51.100.10",
            "forged_a": "203.0.113.10",
            "forged_b": "203.0.113.11",
            "P": "192.0.2.20",
            "E": "198.51.100.20",
            "G": "203.0.113.20",
        },
        id="ipv4",
    ),
    pytest.param(
        {
            "client_a": "2001:db8:1::10",
            "client_b": "2001:db8:2::10",
            "forged_a": "2001:db8:3::10",
            "forged_b": "2001:db8:3::11",
            "P": "2001:db8:4::20",
            "E": "2001:db8:5::20",
            "G": "2001:db8:6::20",
        },
        id="ipv6",
    ),
)


@dataclass(frozen=True)
class _Topology:
    name: str
    peer: str
    chain: tuple[str, ...]
    trusted: tuple[str, ...]
    expected: str


_TOPOLOGIES = (
    _Topology(
        "gateway-trust-G-only-incomplete", "G", ("F", "C", "P", "E"), ("G",), "E"
    ),
    _Topology(
        "gateway-trust-G-E-incomplete",
        "G",
        ("F", "C", "P", "E"),
        ("G", "E"),
        "P",
    ),
    _Topology("gateway-trust-G-E-P", "G", ("F", "C", "P", "E"), ("G", "E", "P"), "C"),
    # The Director-based gateway appends E after nginx canonicalizes the chain to C.
    _Topology("legacy-canonical-client-via-gateway", "G", ("C", "E"), ("G", "E"), "C"),
    _Topology("legacy-canonical-client-via-edge", "E", ("C",), ("E",), "C"),
    _Topology("direct-edge-trust-E-only-incomplete", "E", ("F", "C", "P"), ("E",), "P"),
    _Topology("direct-edge-trust-E-P", "E", ("F", "C", "P"), ("E", "P"), "C"),
    _Topology("direct-edge-without-upstream-L7", "E", ("F", "C"), ("E",), "C"),
    _Topology("untrusted-direct-client", "C", ("F",), ("G", "E", "P"), "C"),
)


@dataclass(frozen=True)
class _Observation:
    ingress_peer: tuple[str, int]
    ingress_headers: tuple[tuple[bytes, bytes], ...]
    post_middleware_peer: tuple[str, int]
    post_middleware_headers: tuple[tuple[bytes, bytes], ...]
    resolved_client: str


class _CaptureIngress:
    """Snapshot the supplied ASGI scope before the configured stack mutates it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.observations: list[_Observation] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        assert scope["type"] == "http"
        ingress_peer = tuple(scope["client"])
        ingress_headers = tuple(scope["headers"])
        await self.app(scope, receive, send)
        self.observations.append(
            _Observation(
                ingress_peer=ingress_peer,
                ingress_headers=ingress_headers,
                post_middleware_peer=tuple(scope["client"]),
                post_middleware_headers=tuple(scope["headers"]),
                resolved_client=resolve_client_ip(Request(scope)),
            )
        )


def _configured_app(
    monkeypatch: pytest.MonkeyPatch, trusted: list[str]
) -> _CaptureIngress:
    # Match the existing AUD-164 memory setup and retain the repository's normal
    # autouse fixtures, including clear_redis_between_tests. Do not stub checks.
    monkeypatch.setattr(settings, "trusted_proxies_list", trusted)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    monkeypatch.setattr(settings, "rate_limit_default_list", ["200/minute"])
    monkeypatch.setattr(settings, "rate_limit_headers_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_login", "2/minute")
    monkeypatch.setattr(settings, "allowed_hosts_list", ["testserver"])
    monkeypatch.setattr(settings, "csrf_hmac_secret", secrets.token_urlsafe(32))
    app = FastAPI()

    @app.get(_CSRF_PATH)
    async def csrf_cookie() -> dict[str, bool]:
        return {"ok": True}

    @app.get(_OBSERVE_PATH)
    @app.post(_LIMITED_PATH)
    async def observed(request: Request) -> dict[str, object]:
        return {
            "scope_client": list(request.scope["client"]),
            "resolved_client": resolve_client_ip(request),
        }

    configure_middleware(app, settings)
    return _CaptureIngress(app)


def _roles(addresses: dict[str, str], client: str, forged: str) -> dict[str, str]:
    assert len(set(addresses.values())) == len(addresses)
    return {**addresses, "C": addresses[client], "F": addresses[forged]}


def _xff_headers(
    topology: _Topology, roles: dict[str, str], *, repeated: bool
) -> list[tuple[str, str]]:
    chain = [roles[role] for role in topology.chain]
    if repeated:
        # Singleton chains remain one field; only multi-hop rows test splitting.
        return [("X-Forwarded-For", hop) for hop in chain]
    return [("X-Forwarded-For", ", ".join(chain))]


def _assert_observation(
    app: _CaptureIngress,
    response: httpx.Response,
    topology: _Topology,
    roles: dict[str, str],
    headers: list[tuple[str, str]],
) -> None:
    observation = app.observations[-1]
    assert observation.ingress_peer == (roles[topology.peer], 50001)
    assert [
        (name, value)
        for name, value in observation.ingress_headers
        if name == b"x-forwarded-for"
    ] == [(name.lower().encode(), value.encode()) for name, value in headers]
    # Uvicorn joins repeated fields for selection; it leaves the actual ordered
    # fields intact. An immutable input snapshot prevents a vacuous before/after.
    assert observation.post_middleware_headers == observation.ingress_headers
    expected_port = 50001 if topology.peer == "C" else 0
    assert observation.post_middleware_peer == (roles[topology.expected], expected_port)
    assert observation.resolved_client == roles[topology.expected]
    if response.status_code == 200:
        # Also observe from inside the real stack, rather than assuming that the
        # wrapper's post-call scope is necessarily what the endpoint received.
        assert response.json() == {
            "scope_client": list(observation.post_middleware_peer),
            "resolved_client": observation.resolved_client,
        }


@pytest.mark.parametrize("addresses", _ADDRESS_FAMILIES)
@pytest.mark.parametrize("topology", _TOPOLOGIES, ids=lambda row: row.name)
@pytest.mark.parametrize("repeated", [False, True], ids=["joined-XFF", "repeated-XFF"])
@pytest.mark.asyncio
async def test_valid_topology_observes_ingress_and_rewritten_client(
    monkeypatch: pytest.MonkeyPatch,
    addresses: dict[str, str],
    topology: _Topology,
    repeated: bool,
) -> None:
    app = _configured_app(monkeypatch, [addresses[role] for role in topology.trusted])
    for client in ("client_a", "client_b"):
        roles = _roles(addresses, client, "forged_a")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app, client=(roles[topology.peer], 50001)
            ),
            base_url="https://testserver",
        ) as requester:
            for forged in ("forged_a", "forged_b"):
                roles = _roles(addresses, client, forged)
                headers = _xff_headers(topology, roles, repeated=repeated)
                response = await requester.get(_OBSERVE_PATH, headers=headers)
                assert response.status_code == 200
                _assert_observation(app, response, topology, roles, headers)


@pytest.mark.parametrize("addresses", _ADDRESS_FAMILIES)
@pytest.mark.parametrize("topology", _TOPOLOGIES, ids=lambda row: row.name)
@pytest.mark.asyncio
async def test_real_limiter_isolation_requires_the_complete_trusted_suffix(
    monkeypatch: pytest.MonkeyPatch,
    addresses: dict[str, str],
    topology: _Topology,
) -> None:
    app = _configured_app(monkeypatch, [addresses[role] for role in topology.trusted])
    client_isolated = topology.expected == "C"
    for client in ("client_a", "client_b"):
        roles = _roles(addresses, client, "forged_a")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app, client=(roles[topology.peer], 50001)
            ),
            base_url="https://testserver",
        ) as requester:
            setup = await requester.get(
                _CSRF_PATH, headers=_xff_headers(topology, roles, repeated=False)
            )
            assert setup.status_code == 200
            csrf = requester.cookies.get("csrf_token")
            assert csrf
            requester.headers["X-CSRF-Token"] = csrf

            responses = []
            for forged, repeated in (
                ("forged_a", False),
                ("forged_b", True),
                ("forged_a", True),
            ):
                roles = _roles(addresses, client, forged)
                headers = _xff_headers(topology, roles, repeated=repeated)
                response = await requester.post(_LIMITED_PATH, headers=headers)
                responses.append(response)
                _assert_observation(app, response, topology, roles, headers)

        # A new client gets its own budget only when attribution reaches C.
        # Trusting G alone attributes both clients to E; trusting G,E stops at P.
        expected = (
            [200, 200, 429] if client == "client_a" or client_isolated else [429] * 3
        )
        assert [response.status_code for response in responses] == expected
        assert all(
            response.headers["X-RateLimit-Limit"] == "2" for response in responses
        )
        expected_remaining = ["1", "0", "0"] if expected[0] == 200 else ["0"] * 3
        assert [
            response.headers["X-RateLimit-Remaining"] for response in responses
        ] == expected_remaining
