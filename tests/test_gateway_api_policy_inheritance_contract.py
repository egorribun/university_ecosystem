"""Rendered inheritance contract for the dormant Envoy buffer policy.

These tests exercise the shipped Helm template, not Envoy's policy merger or
data plane. Native translation and traffic acceptance remain separate gates.
"""

from __future__ import annotations

import json

import pytest
import yaml

from tests.test_gateway_api_helm_contract import (
    CHART,
    HELM,
    _gateway_api_overrides,
    _render,
    _render_gateway_template_isolated,
)

pytestmark = pytest.mark.skipif(HELM is None, reason="Helm is not installed")


@pytest.mark.parametrize("long_fullname", (False, True))
@pytest.mark.parametrize("internal_mtls", (False, True))
@pytest.mark.parametrize(
    ("host_layout", "buffered_hosts"),
    [
        ("default", {"api.university.example.com"}),
        ("api-first", {"api.university.example.com"}),
        (
            "both-catch-all",
            {"university.example.com", "api.university.example.com"},
        ),
        ("no-catch-all", set()),
    ],
)
def test_buffer_policies_opt_into_the_correct_gateway_rate_policy(
    long_fullname: bool,
    internal_mtls: bool,
    host_layout: str,
    buffered_hosts: set[str],
) -> None:
    hosts = yaml.safe_load((CHART / "values.yaml").read_text())["ingress"]["hosts"]
    if host_layout == "api-first":
        hosts.reverse()
    elif host_layout in {"both-catch-all", "no-catch-all"}:
        host_index = 0 if host_layout == "both-catch-all" else 1
        catch_all = next(
            path for path in hosts[host_index]["paths"] if path["path"] == "/"
        )
        catch_all["service"] = (
            "gateway" if host_layout == "both-catch-all" else "frontend"
        )
    overrides = [
        "--set-json",
        f"ingress.hosts={json.dumps(hosts)}",
        "--set",
        f"internalHttpMTLS.enabled={str(internal_mtls).lower()}",
    ]
    if long_fullname:
        overrides.extend(("--set-string", f"fullnameOverride={'a' * 63}"))
    result = _render_gateway_template_isolated(*overrides)
    assert result.returncode == 0, result.stderr
    resources = [item for item in yaml.safe_load_all(result.stdout) if item]
    gateway = next(item for item in resources if item["kind"] == "Gateway")
    routes = {
        item["metadata"]["name"]: item
        for item in resources
        if item["kind"] == "HTTPRoute"
    }
    policies = [item for item in resources if item["kind"] == "BackendTrafficPolicy"]
    parent_policies = [item for item in policies if "rateLimit" in item["spec"]]
    buffer_policies = [item for item in policies if "requestBuffer" in item["spec"]]

    assert len(parent_policies) == 1
    parent = parent_policies[0]
    assert parent["metadata"]["namespace"] == gateway["metadata"]["namespace"]
    assert parent["spec"] == {
        "targetRefs": [
            {
                "group": "gateway.networking.k8s.io",
                "kind": "Gateway",
                "name": gateway["metadata"]["name"],
            }
        ],
        "rateLimit": {
            "local": {
                "rules": [
                    {
                        "clientSelectors": [
                            {"sourceCIDR": {"type": "Distinct", "value": cidr}}
                        ],
                        "limit": {"requests": 50, "unit": "Second"},
                    }
                    for cidr in ("0.0.0.0/0", "::/0")
                ]
            }
        },
    }
    assert len(policies) == 1 + len(buffered_hosts)
    assert len(buffer_policies) == len(buffered_hosts)
    assert len({item["metadata"]["name"] for item in policies}) == len(policies)
    actual_hosts = set()
    targets = set()
    for policy in buffer_policies:
        spec = policy["spec"]
        # No child rateLimit override: the pinned merger retains the parent value.
        assert set(spec) == {"targetRefs", "mergeType", "requestBuffer"}
        assert spec["mergeType"] == "StrategicMerge"
        assert spec["requestBuffer"] == {"limit": "50Mi"}
        assert len(spec["targetRefs"]) == 1
        target = spec["targetRefs"][0]
        assert target == {
            "group": "gateway.networking.k8s.io",
            "kind": "HTTPRoute",
            "name": target["name"],
        }
        assert target["name"] not in targets
        targets.add(target["name"])
        route = routes[target["name"]]
        assert (
            policy["metadata"]["namespace"]
            == route["metadata"]["namespace"]
            == gateway["metadata"]["namespace"]
        )
        assert len(route["spec"]["hostnames"]) == 1
        host = route["spec"]["hostnames"][0]
        actual_hosts.add(host)
        listener = next(
            item
            for item in gateway["spec"]["listeners"]
            if item["hostname"] == host and item["protocol"] == "HTTPS"
        )
        assert route["spec"]["parentRefs"] == [
            {"name": gateway["metadata"]["name"], "sectionName": listener["name"]}
        ]
        assert len(route["spec"]["rules"]) == 1
        rule = route["spec"]["rules"][0]
        assert rule["matches"] == [{"path": {"type": "PathPrefix", "value": "/api/v1"}}]
        assert len(rule["backendRefs"]) == 1
        assert rule["backendRefs"][0]["name"].endswith("-gateway")
        assert rule["backendRefs"][0]["port"] == 8080
    assert actual_hosts == buffered_hosts


@pytest.mark.parametrize(
    "client_ip_detection",
    [
        {"directSourceIP": {}},
        {"xForwardedFor": {"numTrustedHops": 2}},
        {"xForwardedFor": {"trustedCIDRs": ["192.0.2.7/32"]}},
    ],
)
def test_inheritance_opt_in_does_not_unblock_chart_activation(
    client_ip_detection: dict[str, object],
) -> None:
    result = _render(
        *_gateway_api_overrides(
            "--set",
            "ingress.enabled=false",
            "--set-json",
            f"gatewayApi.clientIPDetection={json.dumps(client_ip_detection)}",
        )
    )

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert "50 requests/second with 5x per-client burst" in result.stderr
    assert "20 concurrent connections per client" in result.stderr
    assert "concurrent-buffer memory budget" in result.stderr


def test_disabled_gateway_does_not_render_inheritance_policies() -> None:
    result = _render_gateway_template_isolated("--set", "gatewayApi.enabled=false")

    assert result.returncode == 0, result.stderr
    assert not list(yaml.safe_load_all(result.stdout))
