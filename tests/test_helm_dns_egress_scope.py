"""Rendered contracts for release-wide DNS NetworkPolicy egress scope."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.test_helm_staging_contract import (
    CHART as _STAGING_CONTRACT_CHART,
)
from tests.test_helm_staging_contract import (
    _render_staging,
)

ROOT = Path(__file__).resolve().parents[1]
_NETWORK_POLICY_TEMPLATE = (
    ROOT / "charts" / "university-ecosystem" / "templates" / "network-policy.yaml"
)

_COMPONENT_POLICY_SUFFIXES = (
    "gateway-policy",
    "ws-hub-policy",
    "backup-policy",
    "migration-policy",
    "backend-policy",
    "file-processor-policy",
    "frontend-policy",
    "outbox-worker-policy",
)
_DNS_PORTS = {
    ("UDP", 53),
    ("TCP", 53),
}


def _network_policy_by_name(
    resources: list[dict[str, Any]], name: str
) -> dict[str, Any]:
    matches = [
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1, f"expected exactly one rendered NetworkPolicy {name}"
    return matches[0]


def _dns_egress_rules(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        rule
        for rule in policy.get("spec", {}).get("egress", [])
        if any(
            (port.get("protocol"), port.get("port")) in _DNS_PORTS
            for port in rule.get("ports", [])
        )
    ]


def test_release_workload_dns_egress_uses_customized_resolver_selectors() -> None:
    # The shared renderer must target the chart template whose egress is under test.
    assert _STAGING_CONTRACT_CHART / "templates" / "network-policy.yaml" == (
        _NETWORK_POLICY_TEMPLATE
    )
    assert _NETWORK_POLICY_TEMPLATE.is_file()

    release_name = "dns-egress-scope-contract"
    resources = _render_staging(
        "--set",
        "backup.enabled=true",
        "--set-string",
        "backup.minioEndpoint=https://backup.staging.internal:443",
        "--set-string",
        "networkPolicy.dns.namespaceSelector.dns-zone=contract-resolvers",
        "--set-string",
        "networkPolicy.dns.podSelector.dns-role=resolver",
        release_name=release_name,
    )
    expected_peers = [
        {
            "namespaceSelector": {
                "matchLabels": {
                    "kubernetes.io/metadata.name": "kube-system",
                    "dns-zone": "contract-resolvers",
                }
            },
            "podSelector": {
                "matchLabels": {
                    "k8s-app": "kube-dns",
                    "dns-role": "resolver",
                }
            },
        }
    ]

    for suffix in _COMPONENT_POLICY_SUFFIXES:
        policy = _network_policy_by_name(resources, f"{release_name}-{suffix}")
        dns_rules = _dns_egress_rules(policy)
        assert dns_rules, f"{suffix} must permit both DNS transports"

        seen_ports = {
            (port.get("protocol"), port.get("port"))
            for rule in dns_rules
            for port in rule.get("ports", [])
            if (port.get("protocol"), port.get("port")) in _DNS_PORTS
        }
        assert seen_ports == _DNS_PORTS, f"{suffix} must allow UDP and TCP DNS"
        assert all(rule.get("to") == expected_peers for rule in dns_rules), (
            f"{suffix} DNS egress must target only the configured resolver selectors"
        )
