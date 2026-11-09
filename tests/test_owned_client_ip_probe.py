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
        "schema": "ue-owned-client-ip-probe-input-v3",
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
        "caddy_internal_ip": "172.25.0.20",
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
                "172.25.0.20",
                "172.23.0.30",
                "172.25.0.30",
                "172.26.0.30",
            ],
            ["172.23.0.20", "172.25.0.20"],
            ["172.23.0.20", "172.25.0.20"],
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
            "/ws": 120,
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
    assert len(network.requests) == 229
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
    assert injected and len(network.requests) == 229
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


class _RefillingNetwork(_SimulatedNetwork):
    """Offline simulation, not execution or acceptance of the Go service.

    Models config.DefaultWSUpgradeRatePerMinute and tokenBucket.allow in
    services/ws-hub/pkg/hub/ratelimit.go: capacity 120, elapsed * (120/60)
    refill, consume one token only when at least one token remains.
    """

    def __init__(self, latency: float, *, never_exhaust: bool = False) -> None:
        super().__init__()
        self.now = 0.0
        self.latency = latency
        self.never_exhaust = never_exhaust
        self.buckets: dict[str, tuple[float, float]] = {}

    def __call__(self, request: probe.Request, timeout: float) -> probe.Response:
        if request.path not in ("/ws/chat", "/ws"):
            return super().__call__(request, timeout)
        assert 0 < timeout <= 5
        self.requests.append(request)
        self.now += self.latency
        tokens, last_seen = self.buckets.get(request.source_ip, (120.0, self.now))
        tokens = min(120.0, tokens + (self.now - last_seen) * (120 / 60))
        allowed = self.never_exhaust or tokens >= 1
        if allowed:
            tokens -= 1
        self.buckets[request.source_ip] = (tokens, self.now)
        return probe.Response(
            401 if allowed else 429,
            (("content-type", "text/plain; charset=utf-8"),),
            b"Unauthorized\n" if allowed else b"Too Many Requests\n",
            True,
            True,
        )


def _decode_produced_frame(frame):
    return decode_observations(
        PrivateProcessResult(
            ProcessOutcome.EXITED,
            0,
            (json.dumps(frame, separators=(",", ":")) + "\n").encode(),
            b"",
            LocalCleanup.CONFIRMED,
        ),
        expected_source_sha="a" * 40,
        expected_run_id="b" * 64,
        now_ms=1000,
        deadline_ms=121000,
    )


@pytest.mark.parametrize("latency", [0.0, 0.005, 0.01, 0.03])
def test_elapsed_refill_depletes_within_derived_budget(monkeypatch, latency):
    network = _RefillingNetwork(latency)
    monkeypatch.setattr(probe.time, "monotonic", lambda: network.now)
    frame = probe._collect(probe.parse_input(_input()), network)
    observed = _decode_produced_frame(frame)
    assert observed is not None
    assert evaluate_observations(observed).ws_hub
    allowed = len(observed.cases[4].allowed)
    assert 120 <= allowed <= 130
    assert (allowed > 120) == (latency > 0)
    assert observed.http_requests == len(network.requests) == 229 + allowed - 120
    assert observed.http_requests <= 239
    assert observed.cases[4].elapsed_ms < 5000
    assert len(json.dumps(frame).encode()) + 1 <= 4096


@pytest.mark.parametrize("latency,never_exhaust", [(0.04, False), (0.0, True)])
def test_slow_or_non_exhausting_bucket_cannot_emit_frame(
    monkeypatch, latency, never_exhaust
):
    network = _RefillingNetwork(latency, never_exhaust=never_exhaust)
    monkeypatch.setattr(probe.time, "monotonic", lambda: network.now)
    with pytest.raises(probe.ProbeError):
        probe._collect(probe.parse_input(_input()), network)
    assert len(network.requests) <= 239


@pytest.mark.parametrize("defect", ["other_client", "spoofed", "direct_untrusted"])
def test_ws_isolation_remains_strict_with_refill(monkeypatch, defect):
    network = _RefillingNetwork(0.01)
    monkeypatch.setattr(probe.time, "monotonic", lambda: network.now)
    frame = probe._collect(probe.parse_input(_input()), network)
    case = frame["cases"][4]
    if defect == "spoofed":
        case[defect][0] = 401
    else:
        case[defect] = 429 if defect == "other_client" else 401
    observed = _decode_produced_frame(frame)
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend and not verdict.ws_hub


def test_producer_refuses_frame_outside_its_declared_request_budget(monkeypatch):
    network = _SimulatedNetwork()
    monkeypatch.setattr(probe, "_BASE_REQUESTS", 230)
    with pytest.raises(probe.ProbeError, match="invalid observation frame"):
        probe._collect(probe.parse_input(_input()), network)
    assert len(network.requests) == 229


@pytest.mark.parametrize("address", [None, "", "not-an-ip", "192.168.001.1", "8.8.8.8"])
def test_address_decoder_rejects_non_private_or_noncanonical_values(address):
    with pytest.raises(probe.ProbeError, match="invalid address"):
        probe._address(address)


@pytest.mark.parametrize(
    "network", [None, "", "invalid", "172.23.0.1/24", "8.8.8.0/24"]
)
def test_network_decoder_rejects_non_private_or_noncanonical_values(network):
    with pytest.raises(probe.ProbeError, match="invalid topology"):
        probe._topology_network(network)


@pytest.mark.parametrize(
    "defect",
    [
        "route_shape",
        "external_service",
        "peer_shape",
        "peer_host",
        "public_peer",
        "network_identity",
        "duplicate_service",
        "trust_shape",
    ],
)
def test_topology_inventory_inconsistencies_fail_closed(defect):
    value = _input()
    if defect == "route_shape":
        value["routes"][0]["network"] = "unexpected"
    elif defect == "external_service":
        value["ws_hub_ip"] = "172.24.0.40"
    elif defect == "peer_shape":
        value["gateway_backend_peers"][1]["network"] = "unexpected"
    elif defect == "peer_host":
        value["gateway_backend_peers"][1]["address"] = "172.25.0.0"
    elif defect == "public_peer":
        value["gateway_backend_peers"][0]["address"] = "172.23.0.31"
    elif defect == "network_identity":
        value["gateway_backend_peers"][1]["network_id"] = "c" * 64
    elif defect == "duplicate_service":
        value["ws_hub_ip"] = value["backend_public_ip"]
    else:
        value["trusted_proxies"] = []
    with pytest.raises(probe.ProbeError, match="invalid topology"):
        probe.parse_input(value)


@pytest.mark.parametrize(
    "headers",
    [
        [],
        (("name",),),
        (("bad name", "value"),),
        (("name", "x" * 16384),),
        (("upgrade", "websocket"),),
    ],
)
def test_header_map_rejects_unsafe_or_unbounded_headers(headers):
    with pytest.raises(probe.ProbeError):
        probe._header_map(headers)


def test_checked_response_rejects_compressed_representation():
    response = probe.Response(200, (("content-encoding", "gzip"),), b"", True, True)
    with pytest.raises(probe.ProbeError, match="encoded response"):
        probe._checked_response(response)


@pytest.mark.parametrize(
    "config,transport", [(None, lambda *_: None), ("config", None)]
)
def test_collect_requires_parsed_configuration_and_callable_transport(
    config, transport
):
    with pytest.raises(probe.ProbeError, match="invalid producer input"):
        probe._collect(config, transport)


def test_collect_enforces_absolute_request_budget(monkeypatch):
    # Shrink only the probe's own budget to exercise exhaustion at its send seam.
    # No production service or limiter configuration is changed.
    monkeypatch.setattr(probe, "_MAX_REQUESTS", 1)
    network = _SimulatedNetwork()
    with pytest.raises(probe.ProbeError, match="request budget exhausted"):
        probe._collect(probe.parse_input(_input()), network)
    assert len(network.requests) == 1


@pytest.mark.parametrize("error", [OSError, ValueError, TypeError])
def test_collect_redacts_transport_exceptions(error):
    def failed_request(_request, _timeout):
        raise error("transport-private-detail")

    with pytest.raises(probe.ProbeError, match=r"^request failed$"):
        probe._collect(probe.parse_input(_input()), failed_request)


def _encoder_request():
    return probe.Request("172.23.0.10", "172.23.0.20", 80, "GET", "/ws/chat", (), b"")


@pytest.mark.parametrize(
    "defect",
    [
        "wrong_type",
        "mixed_loopback",
        "route",
        "pair",
        "forwarded_prefix",
        "csrf_value",
        "multiple_forwarding",
        "csrf_get",
        "csrf_mismatch",
    ],
)
def test_encoder_rejects_invalid_request_shapes(defect):
    request = _encoder_request()
    if defect == "wrong_type":
        request = None
    elif defect == "mixed_loopback":
        request = replace(request, source_ip="127.0.0.1")
    elif defect == "route":
        request = replace(request, path="/unapproved")
    elif defect == "pair":
        request = replace(request, headers=(("forwarded",),))
    elif defect == "forwarded_prefix":
        request = replace(request, headers=(("forwarded", "172.23.0.11"),))
    elif defect == "csrf_value":
        request = replace(request, headers=(("x-csrf-token", "invalid value"),))
    elif defect == "multiple_forwarding":
        request = replace(
            request,
            headers=(("x-forwarded-for", "172.23.0.11"), ("x-real-ip", "172.23.0.12")),
        )
    elif defect == "csrf_get":
        request = replace(request, headers=(("x-csrf-token", "fixture"),))
    else:
        request = replace(
            request,
            method="POST",
            path="/api/v1/auth/login/json",
            body=b"{}",
            headers=(
                ("cookie", "csrf_token=one; _csrf_anon_nonce=two"),
                ("x-csrf-token", "three"),
            ),
        )
    with pytest.raises(probe.ProbeError, match="invalid request"):
        probe._request_bytes(request)


@pytest.mark.parametrize(
    "header,value",
    [
        ("forwarded", "for=172.23.0.11"),
        ("x-real-ip", "172.23.0.11"),
        ("x-forwarded-for", "172.23.0.11"),
    ],
)
def test_encoder_accepts_each_individual_forwarding_control(header, value):
    request = replace(_encoder_request(), headers=((header, value),))
    assert f"{header}: {value}\r\n".encode() in probe._request_bytes(request)


def test_encoder_fails_closed_if_cookie_parser_contract_regresses(monkeypatch):
    # Fault injection of an incomplete helper result. The real parser currently
    # rejects this condition earlier; keep the caller's defensive check tested.
    monkeypatch.setattr(probe, "_cookies", lambda _headers: {"csrf_token": "one"})
    request = replace(
        _encoder_request(),
        headers=(("cookie", "csrf_token=one; _csrf_anon_nonce=two"),),
    )
    with pytest.raises(probe.ProbeError, match="invalid request"):
        probe._request_bytes(request)


class _ByteSocket:
    """Deterministic finite wire source, obeying socket recv's size contract."""

    def __init__(self, wire=b""):
        self.wire = wire
        self.closed = False

    def settimeout(self, timeout):
        assert timeout > 0

    def recv(self, size):
        chunk, self.wire = self.wire[:size], self.wire[size:]
        return chunk

    def bind(self, address):
        self.source = address

    def connect(self, address):
        self.target = address

    def getsockname(self):
        return self.source

    def getpeername(self):
        return self.target

    def sendall(self, wire):
        assert wire.startswith(b"GET / HTTP/1.1")

    def close(self):
        self.closed = True

    def fileno(self):
        return -1 if self.closed else 3


def _wire_reader(wire):
    return probe._Reader(_ByteSocket(wire), probe.time.monotonic() + 5)


@pytest.mark.parametrize(
    "wire,error",
    [
        (b"invalid\r\n", "invalid response status"),
        (b"HTTP/1.1 200 OK\r\n" + b"X: y\r\n" * 65, "response header count"),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nxyz\r\n",
            "invalid response chunk",
        ),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nX: y\r\n",
            "response trailers not supported",
        ),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1001\r\n",
            "response body limit",
        ),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nxzz",
            "invalid response chunk",
        ),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + b"1\r\nx\r\n" * 128,
            "response chunk count",
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Length: invalid\r\n\r\n",
            "invalid response length",
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\nextra",
            "unexpected response bytes",
        ),
    ],
)
def test_wire_parser_rejects_malformed_finite_responses(wire, error):
    with pytest.raises(probe.ProbeError, match=error):
        probe._read_response(_wire_reader(wire))


def test_reader_limits_wire_allocation_even_across_many_small_reads():
    reader = _wire_reader(b"x" * (probe._MAX_WIRE + 1))
    with pytest.raises(probe.ProbeError, match="response wire limit"):
        while reader.fill():
            reader.buffer.clear()
    assert reader.received == probe._MAX_WIRE + 1


def test_reader_limits_complete_header_line():
    reader = _wire_reader(b"abcd\r\n")
    with pytest.raises(probe.ProbeError, match="response header limit"):
        reader.line(5)


def test_reader_limits_close_delimited_body():
    with pytest.raises(probe.ProbeError, match="response body limit"):
        probe._read_response(_wire_reader(b"HTTP/1.1 200 OK\r\n\r\n" + b"x" * 4097))


@pytest.mark.parametrize(
    "failure", ["create", "attribution", "close", "still_open", "missing_response"]
)
def test_request_socket_failure_and_closure_contracts(monkeypatch, failure):
    from types import SimpleNamespace

    connection = _ByteSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

    def create(*_args):
        if failure == "create":
            raise OSError("socket creation failed")
        return connection

    def close_failed():
        raise OSError("socket closure failed")

    if failure == "attribution":
        monkeypatch.setattr(connection, "getsockname", lambda: ("127.0.0.3", 1))
    elif failure == "close":
        monkeypatch.setattr(connection, "close", close_failed)
    elif failure == "still_open":
        monkeypatch.setattr(connection, "close", lambda: None)
    elif failure == "missing_response":
        # Inject a missing parser result to test the caller's defensive guard.
        monkeypatch.setattr(probe, "_read_response", lambda _reader: None)
    guarded = SimpleNamespace(**vars(probe.socket))
    guarded.socket = create
    monkeypatch.setattr(probe, "socket", guarded)
    messages = {
        "create": "transport failed",
        "attribution": "socket attribution failed",
        "close": "socket closure failed",
        "still_open": "socket closure unconfirmed",
        "missing_response": "missing response",
    }
    with pytest.raises(probe.ProbeError, match=messages[failure]):
        probe._request(
            probe.Request("127.0.0.2", "127.0.0.1", 80, "GET", "/", (), b""), 5
        )
    if failure in {"attribution", "missing_response"}:
        assert connection.closed


@pytest.mark.parametrize("stage", ["bind", "connect", "sendall", "recv"])
def test_request_closes_socket_after_primary_io_failure(monkeypatch, stage):
    from types import SimpleNamespace

    connection = _ByteSocket()

    def io_failed(*_args):
        raise OSError("private transport detail")

    monkeypatch.setattr(connection, stage, io_failed)
    guarded = SimpleNamespace(**vars(probe.socket))
    guarded.socket = lambda *_args: connection
    monkeypatch.setattr(probe, "socket", guarded)
    with pytest.raises(probe.ProbeError, match=r"^transport failed$"):
        probe._request(
            probe.Request("127.0.0.2", "127.0.0.1", 80, "GET", "/", (), b""), 5
        )
    assert connection.closed
