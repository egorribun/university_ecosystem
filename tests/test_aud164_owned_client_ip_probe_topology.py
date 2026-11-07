"""The inner probe accepts only a closed, versioned multi-network topology.

These tests exercise input consistency, not ownership of a Docker resource.
The outer coordinator must independently verify the inspected topology.
"""

from __future__ import annotations

import copy
import secrets
from dataclasses import replace

import pytest

from scripts import owned_client_ip_probe as probe


def _topology() -> dict[str, object]:
    network_ids = {
        name: secrets.token_hex(32)
        for name in ("public", "frontend_net", "internal", "revocation_net")
    }
    return {
        "schema": "ue-owned-client-ip-probe-input-v2",
        "source_sha": secrets.token_hex(20),
        "run_id": secrets.token_hex(32),
        "routes": [
            {
                "network": "public",
                "network_id": network_ids["public"],
                "subnet": "172.23.0.0/24",
                "source_ip": "172.23.0.10",
                "caddy_ip": "172.23.0.20",
            },
            {
                "network": "frontend_net",
                "network_id": network_ids["frontend_net"],
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
                "network_id": network_ids["public"],
                "subnet": "172.23.0.0/24",
                "address": "172.23.0.30",
            },
            {
                "network": "internal",
                "network_id": network_ids["internal"],
                "subnet": "172.25.0.0/24",
                "address": "172.25.0.30",
            },
            {
                "network": "revocation_net",
                "network_id": network_ids["revocation_net"],
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


def test_inspected_multi_network_shape_is_accepted_without_claiming_ownership():
    value = _topology()
    config = probe.parse_input(value)

    assert config.source_sha == value["source_sha"]
    assert config.run_id == value["run_id"]
    assert config.gateway_ip == value["gateway_ip"]
    assert config.ws_hub_ip == value["ws_hub_ip"]
    assert config.backend_public_ip == value["backend_public_ip"]
    assert len(config.routes) == 2


def test_ambiguous_v1_topology_is_rejected():
    value = _topology()
    routes = value["routes"]
    assert isinstance(routes, list)
    legacy = {
        "schema": "ue-owned-client-ip-probe-input-v1",
        "source_sha": value["source_sha"],
        "run_id": value["run_id"],
        "routes": [
            {key: row[key] for key in ("subnet", "source_ip", "caddy_ip")}
            for row in routes
        ],
        "gateway_ip": value["gateway_ip"],
        "ws_hub_ip": value["ws_hub_ip"],
        "trusted_proxies": [
            [routes[0]["caddy_ip"], routes[1]["caddy_ip"], value["gateway_ip"]],
            [routes[0]["caddy_ip"]],
            [routes[0]["caddy_ip"]],
        ],
    }

    with pytest.raises(probe.ProbeError, match="invalid topology"):
        probe.parse_input(legacy)


def test_direct_backend_wire_uses_the_fixed_anonymous_api_protocol():
    config = probe.parse_input(_topology())
    token = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    request = probe.Request(
        source_ip=config.routes[0].source_ip,
        target_ip=config.backend_public_ip,
        port=8000,
        method="POST",
        path="/api/v1/auth/register",
        headers=(
            ("cookie", f"csrf_token={token}; _csrf_anon_nonce={nonce}"),
            ("x-csrf-token", token),
            ("x-forwarded-for", config.routes[1].source_ip),
        ),
        body=b"{}",
    )

    wire = probe._request_bytes(request)

    assert wire.startswith(b"POST /api/v1/auth/register HTTP/1.1\r\n")
    assert b"Content-Length: 2\r\n" in wire
    assert wire.endswith(b"\r\n\r\n{}")
    assert b"Authorization:" not in wire


@pytest.mark.parametrize("defect", ["port", "method", "path", "body"])
def test_direct_backend_wire_rejects_non_protocol_requests(defect: str):
    config = probe.parse_input(_topology())
    token = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    request = probe.Request(
        source_ip=config.routes[0].source_ip,
        target_ip=config.backend_public_ip,
        port=8000,
        method="POST",
        path="/api/v1/auth/register",
        headers=(
            ("cookie", f"csrf_token={token}; _csrf_anon_nonce={nonce}"),
            ("x-csrf-token", token),
            ("x-forwarded-for", config.routes[1].source_ip),
        ),
        body=b"{}",
    )
    assert probe._request_bytes(request)
    if defect == "port":
        request = replace(request, port=8001)
    elif defect == "method":
        request = replace(request, method="GET", body=b"")
    elif defect == "path":
        request = replace(request, path="/api/v1/users")
    else:
        request = replace(request, body=b'{"extra":true}')

    with pytest.raises(probe.ProbeError):
        probe._request_bytes(request)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_network",
        "extra_network",
        "duplicate_network",
        "wrong_network",
        "duplicate_network_id",
        "public_network_id_mismatch",
        "public_subnet_mismatch",
        "public_gateway_mismatch",
        "overlapping_subnet",
        "network_address",
        "peer_outside_subnet",
        "backend_target_outside_public",
        "backend_target_equals_gateway",
        "backend_target_cidr",
        "backend_target_missing",
        "cidr_peer",
        "ipv6_peer",
        "noncanonical_peer",
        "global_peer",
        "duplicate_address",
        "missing_backend_peer",
        "extra_backend_peer",
        "duplicate_backend_peer",
        "cidr_trust",
        "missing_gateway_trust",
        "extra_gateway_trust",
        "missing_ws_trust",
        "extra_ws_trust",
        "trusted_client",
        "client_impersonates_caddy",
        "client_impersonates_gateway",
        "same_clients",
        "unknown_peer_field",
        "bad_network_id",
        "route_network_id_collision",
        "bad_source_sha",
        "unknown_key",
    ],
)
def test_inconsistent_or_unmodeled_topology_is_rejected(defect: str):
    value = _topology()
    probe.parse_input(value)  # Positive control: defects cannot pass vacuously.
    broken = copy.deepcopy(value)
    routes = broken["routes"]
    peers = broken["gateway_backend_peers"]
    trust = broken["trusted_proxies"]
    assert (
        isinstance(routes, list) and isinstance(peers, list) and isinstance(trust, list)
    )

    if defect == "missing_network":
        peers.pop()
        trust[0].pop()
    elif defect == "extra_network":
        peers.append(
            {
                "network": "unmodeled",
                "network_id": secrets.token_hex(32),
                "subnet": "172.27.0.0/24",
                "address": "172.27.0.30",
            }
        )
        trust[0].append("172.27.0.30")
    elif defect == "duplicate_network":
        peers.append(copy.deepcopy(peers[1]))
    elif defect == "wrong_network":
        peers[1]["network"] = "unmodeled"
    elif defect == "duplicate_network_id":
        peers[2]["network_id"] = peers[1]["network_id"]
    elif defect == "public_network_id_mismatch":
        peers[0]["network_id"] = secrets.token_hex(32)
    elif defect == "public_subnet_mismatch":
        peers[0]["subnet"] = "172.27.0.0/24"
    elif defect == "public_gateway_mismatch":
        peers[0]["address"] = "172.23.0.31"
    elif defect == "overlapping_subnet":
        peers[1]["subnet"] = "172.23.0.0/25"
        peers[1]["address"] = "172.23.0.31"
        trust[0][3] = "172.23.0.31"
    elif defect == "network_address":
        peers[1]["address"] = "172.25.0.0"
        trust[0][3] = peers[1]["address"]
    elif defect == "peer_outside_subnet":
        peers[1]["address"] = "172.27.0.30"
        trust[0][3] = peers[1]["address"]
    elif defect == "backend_target_outside_public":
        broken["backend_public_ip"] = routes[1]["source_ip"]
    elif defect == "backend_target_equals_gateway":
        broken["backend_public_ip"] = peers[0]["address"]
    elif defect == "backend_target_cidr":
        broken["backend_public_ip"] = peers[0]["subnet"]
    elif defect == "backend_target_missing":
        del broken["backend_public_ip"]
    elif defect == "cidr_peer":
        peers[1]["address"] = "172.25.0.0/24"
    elif defect == "ipv6_peer":
        peers[1]["address"] = "fd00::1"
    elif defect == "noncanonical_peer":
        peers[1]["address"] = "172.25.0.030"
    elif defect == "global_peer":
        peers[1]["address"] = "203.0.113.1"
    elif defect == "duplicate_address":
        peers[1]["address"] = peers[0]["address"]
    elif defect == "missing_backend_peer":
        trust[0].pop()
    elif defect == "extra_backend_peer":
        trust[0].append("172.25.0.31")
    elif defect == "duplicate_backend_peer":
        trust[0].append(trust[0][0])
    elif defect == "cidr_trust":
        trust[0].append("172.25.0.0/24")
    elif defect == "missing_gateway_trust":
        trust[1].clear()
    elif defect == "extra_gateway_trust":
        trust[1].append(routes[1]["caddy_ip"])
    elif defect == "missing_ws_trust":
        trust[2].clear()
    elif defect == "extra_ws_trust":
        trust[2].append(routes[1]["caddy_ip"])
    elif defect == "trusted_client":
        trust[0].append(routes[0]["source_ip"])
    elif defect == "client_impersonates_caddy":
        routes[0]["caddy_ip"] = routes[0]["source_ip"]
        trust[0][0] = routes[0]["source_ip"]
        trust[1][0] = routes[0]["source_ip"]
        trust[2][0] = routes[0]["source_ip"]
    elif defect == "client_impersonates_gateway":
        peers[0]["address"] = routes[0]["source_ip"]
        broken["gateway_ip"] = routes[0]["source_ip"]
        trust[0][2] = routes[0]["source_ip"]
    elif defect == "same_clients":
        routes[1]["source_ip"] = routes[0]["source_ip"]
    elif defect == "unknown_peer_field":
        peers[1]["unexpected"] = True
    elif defect == "bad_network_id":
        peers[1]["network_id"] = "invalid"
    elif defect == "route_network_id_collision":
        routes[1]["network_id"] = routes[0]["network_id"]
    elif defect == "bad_source_sha":
        broken["source_sha"] = "bad"
    else:
        broken["unexpected"] = True

    with pytest.raises(probe.ProbeError, match="invalid topology"):
        probe.parse_input(broken)
