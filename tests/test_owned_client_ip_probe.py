"""Tests for the inner client-IP producer, not deployment acceptance.

The fake transport below verifies the fixed protocol and decoder integration.
It is not evidence about any Caddy, gateway, backend, or ws-hub deployment.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts import owned_client_ip_probe as probe
from scripts.owned_client_ip_acceptance import (
    decode_observations,
    evaluate_observations,
)
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessResult,
    ProcessOutcome,
)


def _input() -> dict[str, object]:
    return {
        "schema": "ue-owned-client-ip-probe-input-v2",
        "source_sha": "a" * 40,
        "run_id": "b" * 64,
        "routes": [
            {
                "network": "public",
                "network_id": "c" * 64,
                "subnet": "172.23.0.0/24",
                "source_ip": "172.23.0.10",
                "caddy_ip": "172.23.0.20",
            },
            {
                "network": "frontend_net",
                "network_id": "d" * 64,
                "subnet": "172.24.0.0/24",
                "source_ip": "172.24.0.10",
                "caddy_ip": "172.24.0.20",
            },
        ],
        "gateway_ip": "172.23.0.30",
        "ws_hub_ip": "172.23.0.40",
        "backend_public_ip": "172.23.0.50",
        "gateway_backend_peers": [
            {
                "network": "public",
                "network_id": "c" * 64,
                "subnet": "172.23.0.0/24",
                "address": "172.23.0.30",
            },
            {
                "network": "internal",
                "network_id": "e" * 64,
                "subnet": "172.25.0.0/24",
                "address": "172.25.0.30",
            },
            {
                "network": "revocation_net",
                "network_id": "f" * 64,
                "subnet": "172.26.0.0/24",
                "address": "172.26.0.30",
            },
        ],
        "trusted_proxies": [
            [
                "172.23.0.20",
                "172.24.0.20",
                "172.23.0.30",
                "172.25.0.30",
                "172.26.0.30",
            ],
            ["172.23.0.20"],
            ["172.23.0.20"],
        ],
    }


class _SimulatedNetwork:
    """A fake target; its output is useful only for exercising the protocol."""

    def __init__(self) -> None:
        self.requests: list[probe.Request] = []
        self.counts: dict[tuple[str, str], int] = {}

    def __call__(self, request: probe.Request, timeout: float) -> probe.Response:
        assert 0 < timeout <= 5
        self.requests.append(request)
        if request.path == "/api/v1/auth/csrf-cookie":
            return probe.Response(
                200,
                (
                    ("set-cookie", "csrf_token=token; Path=/"),
                    ("set-cookie", "_csrf_anon_nonce=nonce; Path=/"),
                ),
                b"{}",
                True,
                True,
            )
        path = "/ws" if request.path == "/ws/chat" else request.path
        limits = {
            "/api/v1/auth/login/json": 60,
            "/api/v1/auth/register": 5,
            "/api/v1/auth/mfa/verify": 5,
            "/api/v1/password/forgot": 3,
            "/ws": 10,
        }
        limit = limits[path]
        key = (request.source_ip, path)
        self.counts[key] = self.counts.get(key, 0) + 1
        blocked = self.counts[key] > limit
        if path == "/ws":
            return probe.Response(
                429 if blocked else 401,
                (("content-type", "text/plain; charset=utf-8"),),
                b"Too Many Requests\n" if blocked else b"Unauthorized\n",
                True,
                True,
            )
        header_limit = 200 if path == "/api/v1/auth/mfa/verify" else limit
        return probe.Response(
            429 if blocked else 422,
            (
                ("x-ratelimit-limit", str(header_limit)),
                (
                    "content-type",
                    "application/problem+json" if blocked else "application/json",
                ),
            ),
            b"{}",
            True,
            True,
        )


def test_fixed_protocol_yields_a_decodable_bounded_frame_without_secrets():
    network = _SimulatedNetwork()
    frame = probe._collect(probe.parse_input(_input()), network)
    encoded = (json.dumps(frame, separators=(",", ":")) + "\n").encode()
    result = PrivateProcessResult(
        ProcessOutcome.EXITED, 0, encoded, b"", LocalCleanup.CONFIRMED
    )
    observed = decode_observations(
        result,
        expected_source_sha="a" * 40,
        expected_run_id="b" * 64,
        now_ms=1000,
        deadline_ms=121000,
    )
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert (verdict.backend, verdict.ws_hub, verdict.gateway, verdict.deployment) == (
        True,
        True,
        "not_assessed",
        "not_assessed",
    )
    assert len(network.requests) == 119
    assert frame["http_requests"] == len(network.requests)
    assert b"token" not in encoded and b"nonce" not in encoded
    for address in (
        "172.23.0.10",
        "172.24.0.10",
        "172.23.0.20",
        "172.24.0.20",
        "172.23.0.30",
        "172.25.0.30",
        "172.26.0.30",
        "172.23.0.40",
        "172.23.0.50",
    ):
        assert address.encode() not in encoded

    cases = [
        request
        for request in network.requests
        if request.path != "/api/v1/auth/csrf-cookie"
    ]
    assert not any("authorization" in dict(request.headers) for request in cases)
    assert all(request.body == b"{}" for request in cases if request.method == "POST")
    assert all(request.source_ip in {"172.23.0.10", "172.24.0.10"} for request in cases)
    non_caddy = [
        request
        for request in cases
        if request.target_ip not in {"172.23.0.20", "172.24.0.20"}
    ]
    assert len(non_caddy) == 9
    assert {request.target_ip for request in non_caddy} == {
        "172.23.0.30",
        "172.23.0.40",
        "172.23.0.50",
    }
    direct = [
        request
        for request in non_caddy
        if request.target_ip in {"172.23.0.30", "172.23.0.40"}
    ]
    assert len(direct) == 5
    assert all(request.source_ip == "172.23.0.10" for request in direct)
    assert all(
        dict(request.headers)["x-forwarded-for"] == "172.24.0.10" for request in direct
    )
    backend_direct = [
        request for request in non_caddy if request.target_ip == "172.23.0.50"
    ]
    assert len(backend_direct) == 4
    assert {request.path for request in backend_direct} == {
        "/api/v1/auth/login/json",
        "/api/v1/auth/register",
        "/api/v1/auth/mfa/verify",
        "/api/v1/password/forgot",
    }
    assert all(request.source_ip == "172.23.0.10" for request in backend_direct)
    assert all(request.port == 8000 for request in backend_direct)
    assert all(
        dict(request.headers)["x-forwarded-for"] == "172.24.0.10"
        for request in backend_direct
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/login/json",
        "/api/v1/auth/register",
        "/api/v1/auth/mfa/verify",
        "/api/v1/password/forgot",
    ],
)
def test_direct_backend_spoof_bypass_cannot_pass_backend_verdict(path):
    config = probe.parse_input(_input())
    network = _SimulatedNetwork()
    injected = False

    def bypass(request: probe.Request, timeout: float) -> probe.Response:
        nonlocal injected
        response = network(request, timeout)
        if request.target_ip == config.backend_public_ip and request.path == path:
            assert response.status == 429
            assert request.port == 8000
            assert request.source_ip == config.routes[0].source_ip
            assert (
                dict(request.headers)["x-forwarded-for"] == config.routes[1].source_ip
            )
            injected = True
            return replace(
                response,
                status=422,
                headers=tuple(
                    (name, "application/json" if name == "content-type" else value)
                    for name, value in response.headers
                ),
            )
        return response

    frame = probe._collect(config, bypass)
    assert injected and len(network.requests) == 119
    result = PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        (json.dumps(frame, separators=(",", ":")) + "\n").encode(),
        b"",
        LocalCleanup.CONFIRMED,
    )
    observed = decode_observations(
        result,
        expected_source_sha="a" * 40,
        expected_run_id="b" * 64,
        now_ms=1000,
        deadline_ms=121000,
    )

    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend is False
    assert verdict.ws_hub is True
    assert verdict.gateway == verdict.deployment == "not_assessed"


@pytest.mark.parametrize(
    "mutation",
    [
        "same_source",
        "public_target",
        "trusted_client",
        "wrong_caddy",
        "wrong_backend",
        "overlap",
        "bad_sha",
        "unknown_field",
    ],
)
def test_input_rejects_invalid_topology_before_any_request(mutation):
    probe.parse_input(_input())
    value = _input()
    routes = value["routes"]
    trust = value["trusted_proxies"]
    assert isinstance(routes, list) and isinstance(trust, list)
    if mutation == "same_source":
        routes[1]["source_ip"] = routes[0]["source_ip"]
    elif mutation == "public_target":
        routes[0]["caddy_ip"] = "203.0.113.20"
    elif mutation == "trusted_client":
        trust[0].append(routes[0]["source_ip"])
    elif mutation == "wrong_caddy":
        trust[1] = ["172.23.0.21"]
    elif mutation == "wrong_backend":
        trust[0].remove(value["gateway_ip"])
    elif mutation == "overlap":
        routes[1]["subnet"] = routes[0]["subnet"]
    elif mutation == "bad_sha":
        value["source_sha"] = "invalid"
    else:
        value["extra"] = True
    with pytest.raises(probe.ProbeError):
        probe.parse_input(value)


@pytest.mark.parametrize(
    "defect",
    [
        "unverified_source",
        "open_socket",
        "wrong_backend_response",
        "wrong_ws_response",
        "no_csrf",
        "authenticated_cookie",
        "wrong_mfa_layer",
        "wrong_validation_media_type",
        "wrong_limit_media_type",
    ],
)
def test_incomplete_or_misattributed_observation_cannot_emit_a_frame(defect):
    config = probe.parse_input(_input())
    network = _SimulatedNetwork()
    injected = False

    def broken(request: probe.Request, timeout: float) -> probe.Response:
        nonlocal injected
        response = network(request, timeout)
        if defect == "unverified_source":
            injected = True
            return replace(response, source_verified=False)
        if defect == "open_socket":
            injected = True
            return replace(response, closed=False)
        if defect == "no_csrf" and request.path == "/api/v1/auth/csrf-cookie":
            injected = True
            return replace(response, headers=())
        if defect == "wrong_backend_response" and request.method == "POST":
            injected = True
            return replace(response, status=429, headers=())
        if defect == "wrong_ws_response" and request.path == "/ws/chat":
            injected = True
            return replace(response, body=b"a proxy returned this response")
        if defect == "authenticated_cookie":
            injected = True
            return replace(
                response,
                headers=(*response.headers, ("set-cookie", "session_id=fixture")),
            )
        wrong_status = {
            "wrong_validation_media_type": 422,
            "wrong_limit_media_type": 429,
        }.get(defect)
        if request.method == "POST" and response.status == wrong_status:
            injected = True
            wrong_type = (
                "application/problem+json"
                if response.status == 422
                else "application/json"
            )
            return replace(
                response,
                headers=tuple(
                    (name, wrong_type if name == "content-type" else value)
                    for name, value in response.headers
                ),
            )
        if defect == "wrong_mfa_layer" and request.path == "/api/v1/auth/mfa/verify":
            injected = True
            return replace(
                response,
                headers=(
                    ("x-ratelimit-limit", "5"),
                    ("content-type", "application/json"),
                ),
            )
        return response

    with pytest.raises(probe.ProbeError):
        probe._collect(config, broken)
    assert injected and network.requests


def test_http_transport_uses_and_closes_its_real_bound_local_socket():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.client_address[0].encode())

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, name="peer-proof-test-server"
    )
    thread.start()
    try:
        request = probe.Request(
            "127.0.0.1", "127.0.0.1", server.server_port, "GET", "/", (), b""
        )
        response = probe._request(request, 5)
        assert response.status == 200
        assert response.body == b"127.0.0.1"
        assert response.source_verified and response.closed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
