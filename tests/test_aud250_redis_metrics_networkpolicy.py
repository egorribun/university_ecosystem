"""Rendered NetworkPolicy contracts for cache Redis metrics ingress."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "redis-compat"
APP_VALUES = ROOT / "charts" / "university-ecosystem" / "values.yaml"
RELEASE = "aud250-cache"
APP_NAMESPACE = "university-ecosystem"
MONITORING_NAMESPACE_LABEL = {
    "kubernetes.io/metadata.name": "monitoring",
}


def _render_resources(tmp_path: Path) -> list[dict[str, Any]]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("pinned Helm 4.2.4 is required for rendered chart contracts")

    version = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [helm, "version", "--template", "{{.Version}}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    assert version == "v4.2.4"

    app_values = yaml.safe_load(APP_VALUES.read_text(encoding="utf-8"))
    values_path = tmp_path / "redis-values.yaml"
    values_path.write_text(
        yaml.safe_dump(app_values["redis"], sort_keys=False),
        encoding="utf-8",
    )
    rendered = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            helm,
            "template",
            RELEASE,
            str(CHART),
            "--namespace",
            APP_NAMESPACE,
            "--values",
            str(values_path),
            "--dependency-update=false",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [
        resource
        for resource in yaml.safe_load_all(rendered.stdout)
        if resource is not None
    ]


def _network_policy(resources: list[dict[str, Any]]) -> dict[str, Any]:
    return next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{RELEASE}-redis"
    )


def _selector_matches(selector: dict[str, Any], labels: dict[str, str]) -> bool:
    return all(
        labels.get(key) == value
        for key, value in selector.get("matchLabels", {}).items()
    )


def _peer_matches(
    peer: dict[str, Any],
    *,
    namespace: str,
    namespace_labels: dict[str, str],
    pod_labels: dict[str, str],
    policy_namespace: str,
) -> bool:
    namespace_selector = peer.get("namespaceSelector")
    pod_selector = peer.get("podSelector")
    if namespace_selector is not None:
        if not _selector_matches(namespace_selector, namespace_labels):
            return False
        return pod_selector is None or _selector_matches(pod_selector, pod_labels)
    if pod_selector is not None:
        return namespace == policy_namespace and _selector_matches(
            pod_selector, pod_labels
        )
    return True


def _policy_allows_ingress(
    policy: dict[str, Any],
    *,
    port: int,
    namespace: str,
    namespace_labels: dict[str, str],
    pod_labels: dict[str, str],
) -> bool:
    policy_namespace = policy["metadata"]["namespace"]
    for rule in policy["spec"].get("ingress", []):
        rule_ports = rule.get("ports")
        port_matches = rule_ports is None or any(
            entry.get("protocol", "TCP") == "TCP" and int(entry["port"]) == port
            for entry in rule_ports
        )
        if not port_matches:
            continue
        peers = rule.get("from")
        if peers is None or not peers:
            return True
        if any(
            _peer_matches(
                peer,
                namespace=namespace,
                namespace_labels=namespace_labels,
                pod_labels=pod_labels,
                policy_namespace=policy_namespace,
            )
            for peer in peers
        ):
            return True
    return False


def _metrics_port_rule(policy: dict[str, Any]) -> dict[str, Any]:
    return next(
        rule
        for rule in policy["spec"]["ingress"]
        if any(int(port["port"]) == 9121 for port in rule.get("ports", []))
    )


def test_redis_metrics_are_scrapeable_only_from_monitoring_namespace(
    tmp_path: Path,
) -> None:
    resources = _render_resources(tmp_path)
    policy = _network_policy(resources)
    metrics_rule = _metrics_port_rule(policy)

    assert metrics_rule == {
        "from": [{"namespaceSelector": {"matchLabels": MONITORING_NAMESPACE_LABEL}}],
        "ports": [{"protocol": "TCP", "port": 9121}],
    }
    assert _policy_allows_ingress(
        policy,
        port=9121,
        namespace="monitoring",
        namespace_labels=MONITORING_NAMESPACE_LABEL,
        pod_labels={},
    )
    assert not _policy_allows_ingress(
        policy,
        port=9121,
        namespace=APP_NAMESPACE,
        namespace_labels={"kubernetes.io/metadata.name": APP_NAMESPACE},
        pod_labels={},
    )
    assert not _policy_allows_ingress(
        policy,
        port=9121,
        namespace="untrusted-workload",
        namespace_labels={"kubernetes.io/metadata.name": "untrusted-workload"},
        pod_labels={"prometheus.io/scrape": "true"},
    )

    metrics_service = next(
        resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"]["name"] == f"{RELEASE}-redis-metrics"
    )
    assert metrics_service["spec"]["ports"] == [
        {"name": "metrics", "port": 9121, "targetPort": "metrics", "protocol": "TCP"}
    ]
    statefulset = next(
        resource
        for resource in resources
        if resource.get("kind") == "StatefulSet"
        and resource["metadata"]["name"] == f"{RELEASE}-redis-master"
    )
    pod_spec = statefulset["spec"]["template"]["spec"]
    annotations = statefulset["spec"]["template"]["metadata"]["annotations"]
    assert annotations["prometheus.io/scrape"] == "true"
    assert annotations["prometheus.io/port"] == "9121"
    containers = {container["name"]: container for container in pod_spec["containers"]}
    assert (
        containers["redis"]["livenessProbe"]["exec"]
        == containers["redis"]["readinessProbe"]["exec"]
    )
    exporter = containers["metrics"]
    assert exporter["ports"] == [
        {"name": "metrics", "containerPort": 9121, "protocol": "TCP"}
    ]
    assert exporter["livenessProbe"]["tcpSocket"] == {"port": "metrics"}
    assert exporter["readinessProbe"]["httpGet"] == {
        "path": "/",
        "port": "metrics",
    }


def test_redis_client_and_self_ingress_contract_on_6379_is_preserved(
    tmp_path: Path,
) -> None:
    resources = _render_resources(tmp_path)
    policy = _network_policy(resources)
    redis_labels = {
        "app.kubernetes.io/instance": RELEASE,
        "app.kubernetes.io/name": "redis",
    }
    client_labels = {f"{RELEASE}-redis-client": "true"}
    redis_rule = next(
        rule
        for rule in policy["spec"]["ingress"]
        if any(int(port["port"]) == 6379 for port in rule.get("ports", []))
    )
    assert redis_rule == {
        "ports": [{"protocol": "TCP", "port": 6379}],
        "from": [
            {"podSelector": {"matchLabels": client_labels}},
            {"podSelector": {"matchLabels": redis_labels}},
        ],
    }
    for source_labels in (client_labels, redis_labels):
        assert _policy_allows_ingress(
            policy,
            port=6379,
            namespace=APP_NAMESPACE,
            namespace_labels={"kubernetes.io/metadata.name": APP_NAMESPACE},
            pod_labels=source_labels,
        )
    assert not _policy_allows_ingress(
        policy,
        port=6379,
        namespace=APP_NAMESPACE,
        namespace_labels={"kubernetes.io/metadata.name": APP_NAMESPACE},
        pod_labels={},
    )
    assert not _policy_allows_ingress(
        policy,
        port=6379,
        namespace="monitoring",
        namespace_labels=MONITORING_NAMESPACE_LABEL,
        pod_labels=client_labels,
    )
