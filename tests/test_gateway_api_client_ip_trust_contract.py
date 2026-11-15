"""Fail-closed release checks for operator-selected Envoy XFF CIDR trust.

Real Helm validation only: these fixtures do not establish actual proxy ranges,
client identity, CRD/controller acceptance, network topology or activation.
"""

from __future__ import annotations

import json

import pytest
import yaml

from tests.test_gateway_api_helm_contract import (
    HELM,
    _render,
    _render_gateway_template_isolated,
)
from tests.test_helm_staging_contract import _render_staging

pytestmark = pytest.mark.skipif(HELM is None, reason="Helm is not installed")
FIELD = "gatewayApi.clientIPDetection.xForwardedFor.trustedCIDRs"
SYNTAX_ERROR = "entries must use explicit IPv4 or IPv6 CIDR notation"
ADDRESS_ERROR = "entries must be valid IP addresses or CIDRs"


def _release_overrides(environment: str, mode: dict[str, object]) -> tuple[str, ...]:
    # Documentation-only peers/identities are prerequisites, never deployment defaults.
    return (
        "--set",
        "gatewayApi.enabled=true",
        "--set",
        "ingress.enabled=false",
        "--set-string",
        f"global.environment={environment}",
        "--set-string",
        f"ingress.issuer.kind={'Issuer' if environment == 'staging' else 'ClusterIssuer'}",
        "--set",
        f"internalHttpMTLS.enabled={str(environment == 'production').lower()}",
        "--set-string",
        "internalHttpMTLS.trustDomain=university.example",
        "--set-string",
        "internalHttpMTLS.backendSpiffeID=spiffe://university.example/backend",
        "--set-string",
        "internalHttpMTLS.gatewaySpiffeID=spiffe://university.example/gateway",
        "--set-string",
        "internalHttpMTLS.wsHubSpiffeID=spiffe://university.example/ws-hub",
        "--set-string",
        "internalHttpMTLS.fileProcessorSpiffeID=spiffe://university.example/file-processor",
        "--set-json",
        'gateway.config.trustedProxies=["192.0.2.7/32"]',
        "--set-json",
        'wsHub.config.trustedProxies=["192.0.2.8/32"]',
        "--set-string",
        r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
        "--set-string",
        r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
        "--set-json",
        f"gatewayApi.clientIPDetection={json.dumps(mode)}",
    )


@pytest.mark.parametrize("environment", ("staging", "production"))
@pytest.mark.parametrize(
    ("cidrs", "error"),
    [
        (["192.0.2.1"], SYNTAX_ERROR),
        (["2001:db8::1"], SYNTAX_ERROR),
        ([" 192.0.2.0/24 "], SYNTAX_ERROR),
        (["192.0.2.0 /24"], SYNTAX_ERROR),
        (["192.000.002.0/24"], SYNTAX_ERROR),
        (["64:ff9b::192.000.2.1/128"], SYNTAX_ERROR),
        (["192.0.2.0/24", " \t "], SYNTAX_ERROR),
        (["fe80::1%eth0/128"], SYNTAX_ERROR),
        (["192.0.2.0/24/1"], SYNTAX_ERROR),
        (["guard-marker.invalid/32"], SYNTAX_ERROR),
        (["999.0.2.0/24"], ADDRESS_ERROR),
        (["2001:db8:::/64"], ADDRESS_ERROR),
        (["192.0.2.0/33"], ADDRESS_ERROR),
        (["2001:db8::/129"], ADDRESS_ERROR),
        (
            ["127.0.0.0/8", "::1/128"],
            "requires explicit non-loopback ingress proxy CIDRs",
        ),
        (["0.0.0.0/0"], "must not trust 0.0.0.0/0 or ::/0"),
        (["::/0"], "must not trust 0.0.0.0/0 or ::/0"),
        (["10.0.0.0/8"], "must not trust an RFC1918 block"),
        (["172.16.0.0/12"], "must not trust an RFC1918 block"),
        (["192.168.0.0/16"], "must not trust an RFC1918 block"),
        (["128.0.0.0/1"], "must not trust an RFC1918 block"),
        (["8000::/1"], "must not trust an IPv6 /1 half-space"),
        (["fc00::/7"], "must not trust the IPv6 unique-local block"),
        (["f000::/4"], "must not trust the IPv6 unique-local block"),
        (["2000::/3"], "must not trust the IPv6 global-unicast block"),
        (["::ffff:0.0.0.0/96"], "must not trust the IPv4-mapped IPv6 all-IPv4 range"),
        (["::ffff:192.0.2.1/128"], "contains IPv4-mapped IPv6 peers"),
        (["192.0.2.0/24", "::/0"], "must not trust 0.0.0.0/0 or ::/0"),
        (["192.0.2.0/24", "2001:db8:::/64"], ADDRESS_ERROR),
    ],
)
def test_release_rejects_unsafe_envoy_cidrs_before_parity(
    environment: str, cidrs: list[str], error: str
) -> None:
    result = _render(
        *_release_overrides(environment, {"xForwardedFor": {"trustedCIDRs": cidrs}})
    )

    assert result.returncode != 0
    assert f"{FIELD} {error}" in result.stderr
    assert "gatewayApi.enabled is blocked" not in result.stderr
    assert "guard-marker" not in result.stderr


@pytest.mark.parametrize("environment", ("staging", "production"))
@pytest.mark.parametrize(
    "mode",
    [
        {"xForwardedFor": {"trustedCIDRs": ["192.0.2.0/24", "2001:db8::/32"]}},
        {"xForwardedFor": {"trustedCIDRs": ["10.42.0.0/24", "fd12:3456:789a::/48"]}},
        {"xForwardedFor": {"trustedCIDRs": ["192.0.2.7/32", "2001:db8::7/128"]}},
        {"xForwardedFor": {"trustedCIDRs": ["192.0.2.7/24", "2001:DB8:1::7/64"]}},
        {"xForwardedFor": {"trustedCIDRs": ["192.0.2.7/024", "2001:0DB8:0001::7/064"]}},
        {"directSourceIP": {}},
        {"xForwardedFor": {"numTrustedHops": 0}},
        {"xForwardedFor": {"numTrustedHops": 2}},
    ],
)
def test_valid_selected_modes_remain_blocked_by_parity(
    environment: str, mode: dict[str, object]
) -> None:
    result = _render(*_release_overrides(environment, mode))

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert FIELD not in result.stderr


@pytest.mark.parametrize("environment", ("staging", "production"))
def test_empty_cidr_list_still_fails_existing_schema(environment: str) -> None:
    result = _render(
        *_release_overrides(environment, {"xForwardedFor": {"trustedCIDRs": []}})
    )

    assert result.returncode != 0
    assert "trustedCIDRs" in result.stderr
    assert "minItems" in result.stderr


def test_development_preserves_its_existing_parity_block() -> None:
    result = _render(
        *_release_overrides("staging", {"xForwardedFor": {"trustedCIDRs": ["::/0"]}}),
        "--set-string",
        "global.environment=development",
    )

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert FIELD not in result.stderr


def test_disabled_gateway_cidr_setting_does_not_change_legacy_release() -> None:
    resources = _render_staging(
        "--set",
        "gatewayApi.enabled=false",
        "--set-json",
        'gatewayApi.clientIPDetection={"xForwardedFor":{"trustedCIDRs":["::/0"]}}',
    )

    assert any(item["kind"] == "Ingress" for item in resources)
    assert not any(item["kind"] == "ClientTrafficPolicy" for item in resources)


def test_selected_cidrs_still_reach_both_listener_policies_unchanged() -> None:
    mode = {"xForwardedFor": {"trustedCIDRs": ["192.0.2.7/32", "2001:DB8::7/128"]}}
    result = _render_gateway_template_isolated(client_ip_detection=json.dumps(mode))
    assert result.returncode == 0, result.stderr
    policies = [
        item
        for item in yaml.safe_load_all(result.stdout)
        if isinstance(item, dict) and item.get("kind") == "ClientTrafficPolicy"
    ]

    assert len(policies) == 2
    assert all(item["spec"]["clientIPDetection"] == mode for item in policies)


@pytest.mark.parametrize("environment", ("staging", "production"))
@pytest.mark.parametrize("mapped_first", (False, True))
@pytest.mark.parametrize(
    "mapped_cidr",
    [
        "::ffff:127.0.0.1/128",
        "::ffff:127.0.0.0/104",
        "::ffff:127.255.255.255/104",
        "::ffff:127.128.0.1/105",
        "::FFFF:7F00:0001/0128",
        "0000:0000:0000:0000:0000:FFFF:7F00:0001/128",
        "0:0::0:ffff:7f00:1/128",
        "::ffff:7fff:ffff/128",
    ],
)
def test_release_rejects_mapped_loopback_even_with_a_native_peer(
    environment: str, mapped_first: bool, mapped_cidr: str
) -> None:
    cidrs = [mapped_cidr, "192.0.2.7/32"]
    if not mapped_first:
        cidrs.reverse()
    result = _render(
        *_release_overrides(environment, {"xForwardedFor": {"trustedCIDRs": cidrs}})
    )

    assert result.returncode != 0
    assert f"{FIELD} contains IPv4-mapped IPv6 peers" in result.stderr
    assert "gatewayApi.enabled is blocked" not in result.stderr
    assert mapped_cidr not in result.stderr


@pytest.mark.parametrize("environment", ("staging", "production"))
@pytest.mark.parametrize(
    ("cidrs", "error"),
    [
        (
            ["::ffff:127.0.0.1/128"],
            "requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            ["::ffff:127.0.0.1/103", "192.0.2.7/32"],
            "contains IPv4-mapped IPv6 peers",
        ),
        (
            ["::ffff:127.0.0.1/96", "192.0.2.7/32"],
            "must not trust the IPv4-mapped IPv6 all-IPv4 range",
        ),
        (
            ["::ffff:127.0.0.1/0", "192.0.2.7/32"],
            "must not trust 0.0.0.0/0 or ::/0",
        ),
    ],
)
def test_existing_mapped_range_errors_keep_their_priority(
    environment: str, cidrs: list[str], error: str
) -> None:
    result = _render(
        *_release_overrides(environment, {"xForwardedFor": {"trustedCIDRs": cidrs}})
    )

    assert result.returncode != 0
    assert f"{FIELD} {error}" in result.stderr
    assert "gatewayApi.enabled is blocked" not in result.stderr


@pytest.mark.parametrize("environment", ("staging", "production"))
@pytest.mark.parametrize(
    "native_cidr",
    [
        "64:ff9b::192.0.2.1/128",
        "2001:db8::192.0.2.1/128",
        "::192.0.2.1/128",
        "::ffff:0:192.0.2.1/128",
        "::1/128",
    ],
)
def test_nonmapped_ipv6_with_native_peer_still_reaches_parity(
    environment: str, native_cidr: str
) -> None:
    mode = {"xForwardedFor": {"trustedCIDRs": [native_cidr, "192.0.2.7/32"]}}
    result = _render(*_release_overrides(environment, mode))

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert FIELD not in result.stderr


def test_mapped_release_guard_does_not_change_development() -> None:
    mode = {"xForwardedFor": {"trustedCIDRs": ["::ffff:127.0.0.1/128", "192.0.2.7/32"]}}
    result = _render(
        *_release_overrides("staging", mode),
        "--set-string",
        "global.environment=development",
    )

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert FIELD not in result.stderr


def test_legacy_application_peer_lists_remain_unchanged() -> None:
    # Compatibility only: these synthetic peers are not an approved topology.
    peers = ["::ffff:127.0.0.1/128", "192.0.2.7/32"]
    mode = {"xForwardedFor": {"trustedCIDRs": peers}}
    overrides = [
        "--set",
        "gatewayApi.enabled=false",
        "--set-json",
        f"gatewayApi.clientIPDetection={json.dumps(mode)}",
    ]
    for service in ("backend", "gateway", "wsHub"):
        overrides.extend(
            ("--set-json", f"{service}.config.trustedProxies={json.dumps(peers)}")
        )
    resources = _render_staging(*overrides)

    assert any(item["kind"] == "Ingress" for item in resources)
    assert not any(item["kind"] == "ClientTrafficPolicy" for item in resources)
    for service, variable in (
        ("backend", "TRUSTED_PROXIES"),
        ("gateway", "GATEWAY_TRUSTED_PROXIES"),
        ("ws-hub", "TRUSTED_PROXIES"),
    ):
        deployment = next(
            item
            for item in resources
            if item["kind"] == "Deployment"
            and item["metadata"]["name"].endswith(f"-{service}")
        )
        container = next(
            item
            for item in deployment["spec"]["template"]["spec"]["containers"]
            if item["name"] == service
        )
        assert [item for item in container["env"] if item["name"] == variable] == [
            {"name": variable, "value": ",".join(peers)}
        ]
