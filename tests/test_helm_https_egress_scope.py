"""Helm render contract for TCP 443 egress scope of the workload NetworkPolicies (AUD-189)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import _render_staging

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
STAGING_VALUES = CHART / "values-staging.yaml"

HTTPS_EGRESS_POLICIES = (
    "-backup-policy",
    "-backend-policy",
    "-file-processor-policy",
    "-outbox-worker-policy",
)
# Reserved TEST-NET fixture only; never a deployment CIDR.
TEST_NET_PRIVATE_CIDR = "198.51.100.0/24"


def _render_https_egress(*extra: str) -> list[dict[str, Any]]:
    # The backup policy renders only when backup is enabled, and staging requires
    # an HTTPS MinIO endpoint for it.
    return _render_staging(
        "--set",
        "backup.enabled=true",
        "--set-string",
        "backup.minioEndpoint=https://minio.staging.internal:443",
        *extra,
        chart_path=CHART,
        values_path=STAGING_VALUES,
    )


def _network_policies(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in resources if item.get("kind") == "NetworkPolicy"]


def _allows_port_443(rule: dict[str, Any]) -> bool:
    return any(int(port.get("port", 0)) == 443 for port in rule.get("ports", []))


def _policy(resources: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    return next(
        item
        for item in _network_policies(resources)
        if item["metadata"]["name"].endswith(suffix)
    )


def _ip_blocks(rule: dict[str, Any]) -> list[dict[str, Any]]:
    return [peer["ipBlock"] for peer in rule.get("to", []) if "ipBlock" in peer]


def test_no_network_policy_allows_tcp_443_without_a_destination() -> None:
    resources = _render_https_egress()

    unscoped = [
        (policy["metadata"]["name"], rule)
        for policy in _network_policies(resources)
        for rule in policy["spec"].get("egress", [])
        if _allows_port_443(rule) and not rule.get("to")
    ]

    assert unscoped == []


@pytest.mark.parametrize("suffix", HTTPS_EGRESS_POLICIES)
def test_public_https_egress_excludes_cluster_private_and_link_local_ranges(
    suffix: str,
) -> None:
    policy = _policy(_render_https_egress(), suffix)
    rules = [rule for rule in policy["spec"]["egress"] if _allows_port_443(rule)]

    assert len(rules) == 1
    blocks = {block["cidr"]: block.get("except", []) for block in _ip_blocks(rules[0])}
    assert set(blocks) == {"0.0.0.0/0", "::/0"}
    assert {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"} <= set(
        blocks["0.0.0.0/0"]
    )
    assert {"fc00::/7", "fe80::/10"} <= set(blocks["::/0"])
    assert all(":" not in cidr for cidr in blocks["0.0.0.0/0"])
    assert all(":" in cidr for cidr in blocks["::/0"])


def test_owner_verified_private_https_destinations_are_allowed_explicitly() -> None:
    resources = _render_https_egress(
        "--set-json",
        f"networkPolicy.httpsEgress.privateCIDRs={json.dumps([TEST_NET_PRIVATE_CIDR])}",
    )

    for suffix in HTTPS_EGRESS_POLICIES:
        rules = [
            rule
            for rule in _policy(resources, suffix)["spec"]["egress"]
            if _allows_port_443(rule)
        ]
        destinations = [block["cidr"] for rule in rules for block in _ip_blocks(rule)]
        assert TEST_NET_PRIVATE_CIDR in destinations


def test_default_https_egress_renders_no_private_destination_allowance() -> None:
    resources = _render_https_egress()

    for suffix in HTTPS_EGRESS_POLICIES:
        destinations = [
            block["cidr"]
            for rule in _policy(resources, suffix)["spec"]["egress"]
            if _allows_port_443(rule)
            for block in _ip_blocks(rule)
        ]
        assert destinations == ["0.0.0.0/0", "::/0"]


def test_default_route_private_https_destination_is_rejected() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_https_egress(
            "--set-json",
            'networkPolicy.httpsEgress.privateCIDRs=["0.0.0.0/0"]',
        )

    assert "must not be a /0 range" in error.value.stderr
