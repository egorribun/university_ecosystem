"""Fail-closed render contracts for required HTTPS egress exclusions.

These tests inspect Helm output only. They do not exercise a cluster or CNI.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from tests.test_helm_staging_contract import _render_staging

_IPV4_EXCLUSIONS = (
    "10.0.0.0/8",
    "100.64.0.0/10",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
)
_IPV6_EXCLUSIONS = ("fc00::/7", "fe80::/10")


@pytest.mark.parametrize(
    ("family", "exclusions", "missing"),
    [
        (family, exclusions, missing)
        for family, exclusions in (
            ("IPv4", _IPV4_EXCLUSIONS),
            ("IPv6", _IPV6_EXCLUSIONS),
        )
        for missing in exclusions
    ],
)
def test_required_https_exclusion_cannot_be_removed(
    family: str, exclusions: tuple[str, ...], missing: str
) -> None:
    remaining = [cidr for cidr in exclusions if cidr != missing]
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(
            "--set-json",
            f"networkPolicy.httpsEgress.except{family}CIDRs={json.dumps(remaining)}",
        )

    assert f"networkPolicy.httpsEgress.except{family}CIDRs must include {missing}" in (
        error.value.stderr
    )


def test_cluster_specific_exclusions_remain_configurable() -> None:
    extra_ipv4 = "192.0.2.0/24"  # Documentation range, not a deployed endpoint.
    extra_ipv6 = "2001:db8::/32"
    private_endpoint = "10.42.0.10/32"  # Synthetic explicit private allowance.
    resources = _render_staging(
        "--set-json",
        "networkPolicy.httpsEgress.exceptIPv4CIDRs="
        + json.dumps([*_IPV4_EXCLUSIONS, extra_ipv4]),
        "--set-json",
        "networkPolicy.httpsEgress.exceptIPv6CIDRs="
        + json.dumps([*_IPV6_EXCLUSIONS, extra_ipv6]),
        "--set-json",
        "networkPolicy.httpsEgress.privateCIDRs=" + json.dumps([private_endpoint]),
    )
    policy = next(
        item
        for item in resources
        if item.get("kind") == "NetworkPolicy"
        and item["metadata"]["name"].endswith("-file-processor-policy")
    )
    blocks: dict[str, dict[str, Any]] = {
        peer["ipBlock"]["cidr"]: peer["ipBlock"]
        for rule in policy["spec"]["egress"]
        for peer in rule.get("to", [])
        if "ipBlock" in peer
    }
    assert set(blocks["0.0.0.0/0"]["except"]) == {*_IPV4_EXCLUSIONS, extra_ipv4}
    assert set(blocks["::/0"]["except"]) == {*_IPV6_EXCLUSIONS, extra_ipv6}
    assert blocks[private_endpoint] == {"cidr": private_endpoint}
