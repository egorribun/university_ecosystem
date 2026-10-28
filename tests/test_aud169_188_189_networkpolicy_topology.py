"""Render-only topology checks; these do not exercise a CNI or a live cluster.

The evaluator deliberately supports the selector/port forms in these charts and
fails on unfamiliar forms. Its IP checks describe direct-address policy intent,
not kube-proxy translation or a CNI's treatment of Service/Pod addresses.
"""

from __future__ import annotations

import copy
import ipaddress
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from tests.test_helm_staging_contract import _render_staging
from tests.test_revocation_store_security_contract import (
    CHART as REVOCATION_CHART,
)
from tests.test_revocation_store_security_contract import (
    VALUES as REVOCATION_VALUES,
)
from tests.test_revocation_store_security_contract import _helm, _resolved_args

NAMESPACE = "university-ecosystem"
FIRST = "topology-first"
SECOND = "topology-second"


@dataclass(frozen=True)
class Endpoint:
    namespace: str | None
    labels: dict[str, str]
    address: str


def _render_store(release: str) -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            f"{release}-bootstrap",
            str(REVOCATION_CHART),
            "--dependency-update=false",
            "--namespace",
            NAMESPACE,
            "--values",
            str(REVOCATION_VALUES),
            *_resolved_args(release),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def _resource(resources: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    matches = [
        resource
        for resource in resources
        if resource.get("kind") == kind and resource["metadata"]["name"] == name
    ]
    assert len(matches) == 1, (kind, name, len(matches))
    return matches[0]


def _labels_match(selector: dict[str, Any], labels: dict[str, str]) -> bool:
    assert set(selector) <= {"matchLabels"}, "unsupported selector form"
    return all(
        labels.get(key) == value
        for key, value in selector.get("matchLabels", {}).items()
    )


def _peer_matches(
    peer: dict[str, Any], policy_namespace: str, endpoint: Endpoint
) -> bool:
    assert set(peer) <= {"podSelector", "namespaceSelector", "ipBlock"}
    if not peer:
        return True
    if "ipBlock" in peer:
        assert set(peer) == {"ipBlock"}
        block = peer["ipBlock"]
        address = ipaddress.ip_address(endpoint.address)
        return address in ipaddress.ip_network(block["cidr"]) and not any(
            address in ipaddress.ip_network(exclusion)
            for exclusion in block.get("except", [])
        )
    if endpoint.namespace is None:
        return False
    if "namespaceSelector" in peer:
        namespace_labels = {"kubernetes.io/metadata.name": endpoint.namespace}
        if not _labels_match(peer["namespaceSelector"], namespace_labels):
            return False
    elif endpoint.namespace != policy_namespace:
        return False
    return "podSelector" not in peer or _labels_match(
        peer["podSelector"], endpoint.labels
    )


def _port_matches(rule: dict[str, Any], protocol: str, port: int) -> bool:
    if not rule.get("ports"):
        return True
    for entry in rule["ports"]:
        assert set(entry) <= {"protocol", "port", "endPort"}
        if entry.get("protocol", "TCP") != protocol:
            continue
        start = entry.get("port")
        if start is None:
            return True
        assert isinstance(start, int), "named ports require separate resolution"
        if start <= port <= entry.get("endPort", start):
            return True
    return False


def _allowed_side(
    resources: list[dict[str, Any]],
    selected: Endpoint,
    peer: Endpoint,
    direction: str,
    protocol: str,
    port: int,
) -> bool:
    policies = [
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"].get("namespace", NAMESPACE) == selected.namespace
        and direction in resource["spec"]["policyTypes"]
        and _labels_match(resource["spec"]["podSelector"], selected.labels)
    ]
    if not policies:
        return True  # Kubernetes default: an unselected pod is not isolated.
    rule_key, peer_key = (
        ("egress", "to") if direction == "Egress" else ("ingress", "from")
    )
    return any(
        _port_matches(rule, protocol, port)
        and (
            not rule.get(peer_key)
            or any(
                _peer_matches(
                    target, policy["metadata"].get("namespace", NAMESPACE), peer
                )
                for target in rule[peer_key]
            )
        )
        for policy in policies
        for rule in policy["spec"].get(rule_key, [])
    )


def _pod(resource: dict[str, Any], address: str) -> Endpoint:
    return Endpoint(
        NAMESPACE, resource["spec"]["template"]["metadata"]["labels"], address
    )


@pytest.fixture(scope="module")
def topology() -> tuple[list[dict[str, Any]], dict[str, Endpoint]]:
    resources: list[dict[str, Any]] = []
    endpoints: dict[str, Endpoint] = {}
    for release, host_suffix in ((FIRST, "11"), (SECOND, "12")):
        app = _render_staging(
            "--set-string",
            f"fullnameOverride={release}",
            "--set",
            "backend.service.port=8181",
            release_name=release,
        )
        store = _render_store(release)
        resources.extend(app + store)
        endpoints[f"{release}-processor"] = _pod(
            _resource(app, "Deployment", f"{release}-file-processor"),
            f"10.32.0.{host_suffix}",
        )
        endpoints[f"{release}-backend"] = _pod(
            _resource(app, "Deployment", f"{release}-backend"),
            f"10.33.0.{host_suffix}",
        )
        endpoints[f"{release}-redis"] = _pod(
            _resource(store, "StatefulSet", f"{release}-revocation-redis-master"),
            f"10.34.0.{host_suffix}",
        )
    return resources, endpoints


def test_services_and_default_jwks_bind_to_the_rendered_endpoints(
    topology: tuple[list[dict[str, Any]], dict[str, Endpoint]],
) -> None:
    resources, endpoints = topology
    for release in (FIRST, SECOND):
        backend = _resource(resources, "Deployment", f"{release}-backend")
        processor = _resource(resources, "Deployment", f"{release}-file-processor")
        redis = _resource(
            resources, "StatefulSet", f"{release}-revocation-redis-master"
        )
        for (
            service_name,
            endpoint,
            workload,
            container_name,
            target_name,
            target_port,
        ) in (
            (
                f"{release}-backend",
                endpoints[f"{release}-backend"],
                backend,
                "backend",
                "http",
                8181,
            ),
            (
                f"{release}-revocation-redis-master",
                endpoints[f"{release}-redis"],
                redis,
                "redis",
                "redis",
                6379,
            ),
        ):
            service = _resource(resources, "Service", service_name)
            assert _labels_match(
                {"matchLabels": service["spec"]["selector"]}, endpoint.labels
            )
            service_port = next(
                item for item in service["spec"]["ports"] if item["port"] == target_port
            )
            assert service_port["targetPort"] == target_name
            container = next(
                item
                for item in workload["spec"]["template"]["spec"]["containers"]
                if item["name"] == container_name
            )
            assert any(
                item["name"] == target_name and item["containerPort"] == target_port
                for item in container["ports"]
            )
        environment = {
            item["name"]: item.get("value")
            for item in processor["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        jwks = urlsplit(environment["FP_JWKS_URL"])
        assert (jwks.scheme, jwks.hostname, jwks.port, jwks.path) == (
            "http",
            f"{release}-backend",
            8181,
            "/.well-known/jwks.json",
        )
        # The Secret reference cannot prove that its runtime URL names this service.
        assert environment["FP_REVOCATION_REDIS_URL_FILE"]


def test_both_sides_of_redis_and_jwks_rules_are_release_scoped(
    topology: tuple[list[dict[str, Any]], dict[str, Endpoint]],
) -> None:
    resources, endpoints = topology
    for source_release in (FIRST, SECOND):
        for destination_release in (FIRST, SECOND):
            processor = endpoints[f"{source_release}-processor"]
            same_release = source_release == destination_release
            for component, port in (("redis", 6379), ("backend", 8181)):
                target = endpoints[f"{destination_release}-{component}"]
                assert (
                    _allowed_side(resources, processor, target, "Egress", "TCP", port)
                    is same_release
                )
                assert (
                    _allowed_side(resources, target, processor, "Ingress", "TCP", port)
                    is same_release
                )
    untrusted = Endpoint(NAMESPACE, {"app": "untrusted"}, "10.32.0.50")
    for component, port in (("redis", 6379), ("backend", 8181)):
        target = endpoints[f"{FIRST}-{component}"]
        assert not _allowed_side(resources, target, untrusted, "Ingress", "TCP", port)


def test_dns_and_443_direct_address_intent_is_scoped(
    topology: tuple[list[dict[str, Any]], dict[str, Endpoint]],
) -> None:
    resources, endpoints = topology
    processor = endpoints[f"{FIRST}-processor"]
    resolver = Endpoint("kube-system", {"k8s-app": "kube-dns"}, "10.96.0.10")
    wrong_namespace = Endpoint(NAMESPACE, resolver.labels, "10.96.0.11")
    wrong_labels = Endpoint("kube-system", {"k8s-app": "not-dns"}, "10.96.0.12")
    for protocol in ("TCP", "UDP"):
        assert _allowed_side(resources, processor, resolver, "Egress", protocol, 53)
        for destination in (wrong_namespace, wrong_labels):
            assert not _allowed_side(
                resources, processor, destination, "Egress", protocol, 53
            )
    for address in (
        "10.1.2.3",
        "100.64.0.1",
        "169.254.1.1",
        "172.16.1.1",
        "192.168.1.1",
        "fc00::1",
        "fe80::1",
    ):
        assert not _allowed_side(
            resources, processor, Endpoint(None, {}, address), "Egress", "TCP", 443
        )
    for address in ("198.51.100.1", "2001:db8::1"):
        assert _allowed_side(
            resources, processor, Endpoint(None, {}, address), "Egress", "TCP", 443
        )


def test_mutated_topology_exposes_missing_and_additive_policy_rules(
    topology: tuple[list[dict[str, Any]], dict[str, Endpoint]],
) -> None:
    resources, endpoints = topology
    processor = endpoints[f"{FIRST}-processor"]
    redis = endpoints[f"{FIRST}-redis"]
    backend = endpoints[f"{FIRST}-backend"]
    changed = copy.deepcopy(resources)
    redis_policy = _resource(changed, "NetworkPolicy", f"{FIRST}-revocation-redis")
    redis_policy["spec"]["ingress"] = []
    assert not _allowed_side(changed, redis, processor, "Ingress", "TCP", 6379)
    backend_policy = _resource(changed, "NetworkPolicy", f"{FIRST}-backend-policy")
    backend_policy["spec"]["ingress"] = []
    assert not _allowed_side(changed, backend, processor, "Ingress", "TCP", 8181)
    # NetworkPolicies are additive: another selected policy can widen the result.
    changed.append(
        {
            "kind": "NetworkPolicy",
            "metadata": {"name": "widening-negative-control", "namespace": NAMESPACE},
            "spec": {
                "podSelector": {"matchLabels": processor.labels},
                "policyTypes": ["Egress"],
                "egress": [{"ports": [{"protocol": "TCP", "port": 443}]}],
            },
        }
    )
    assert _allowed_side(
        changed, processor, Endpoint(None, {}, "10.1.2.3"), "Egress", "TCP", 443
    )


def test_an_empty_policy_peer_cannot_hide_a_cross_namespace_allowance() -> None:
    assert _peer_matches({}, NAMESPACE, Endpoint("other", {}, "10.0.0.1"))
    assert _peer_matches({}, NAMESPACE, Endpoint(None, {}, "198.51.100.1"))
