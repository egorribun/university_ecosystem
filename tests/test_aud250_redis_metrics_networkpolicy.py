"""Rendered NetworkPolicy contracts for cache Redis metrics ingress."""

from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from tests.test_helm_staging_contract import _render_staging

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
    assert helm is not None, (
        "pinned Helm 4.2.4 is required for rendered chart contracts"
    )

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
    assert set(selector) <= {"matchLabels"}, "unsupported selector form"
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
    assert set(peer) <= {"namespaceSelector", "podSelector"}, "unsupported peer form"
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


def _allows_tcp_port(rule: dict[str, Any], port: int) -> bool:
    assert set(rule) <= {"from", "ports"}, "unsupported ingress rule"
    rule_ports = rule.get("ports")
    if not rule_ports:
        return True
    for entry in rule_ports:
        assert set(entry) <= {"protocol", "port", "endPort"}
        start = entry.get("port")
        assert start is None or isinstance(start, int), "unsupported named port"
        if entry.get("protocol", "TCP") == "TCP" and (
            start is None or start <= port <= entry.get("endPort", start)
        ):
            return True
    return False


def _policy_allows_ingress(
    policy: dict[str, Any],
    *,
    port: int,
    namespace: str,
    namespace_labels: dict[str, str],
    pod_labels: dict[str, str],
) -> bool:
    policy_namespace = policy["metadata"].get("namespace", APP_NAMESPACE)
    for rule in policy["spec"].get("ingress", []):
        if not _allows_tcp_port(rule, port):
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


def _select_ingress_policies(
    resources: list[dict[str, Any]], target_labels: dict[str, str]
) -> list[dict[str, Any]]:
    return [
        policy
        for policy in resources
        if policy.get("kind") == "NetworkPolicy"
        and policy["metadata"].get("namespace", APP_NAMESPACE) == APP_NAMESPACE
        and (
            not policy["spec"].get("policyTypes")
            or "Ingress" in policy["spec"]["policyTypes"]
        )
        and _selector_matches(policy["spec"]["podSelector"], target_labels)
    ]


def _effective_ingress(
    resources: list[dict[str, Any]],
    *,
    target_labels: dict[str, str],
    source_namespace: str,
    source_labels: dict[str, str],
    port: int,
) -> bool:
    selected = _select_ingress_policies(resources, target_labels)
    # Kubernetes leaves ingress unrestricted when no policy selects the target.
    if not selected:
        return True
    return any(
        _policy_allows_ingress(
            policy,
            port=port,
            namespace=source_namespace,
            namespace_labels={"kubernetes.io/metadata.name": source_namespace},
            pod_labels=source_labels,
        )
        for policy in selected
    )


def _metrics_only_from_monitoring(
    resources: list[dict[str, Any]], target_labels: dict[str, str]
) -> bool:
    selected = _select_ingress_policies(resources, target_labels)
    if not selected:
        return False
    for policy in selected:
        for rule in policy["spec"].get("ingress", []):
            if not _allows_tcp_port(rule, 9121):
                continue
            peers = rule.get("from")
            if not peers:
                return False
            for peer in peers:
                if set(peer) - {"namespaceSelector", "podSelector"}:
                    return False
                namespace_selector = peer.get("namespaceSelector")
                if (
                    namespace_selector is None
                    or set(namespace_selector) - {"matchLabels"}
                    or namespace_selector.get("matchLabels", {}).get(
                        "kubernetes.io/metadata.name"
                    )
                    != "monitoring"
                ):
                    return False
    return True


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


def test_parent_chart_metrics_ingress_considers_all_selecting_policies() -> None:
    resources = _render_staging(release_name=RELEASE)
    redis = next(
        item
        for item in resources
        if item.get("kind") == "StatefulSet"
        and item["metadata"]["name"] == f"{RELEASE}-redis-master"
    )
    target_labels = redis["spec"]["template"]["metadata"]["labels"]
    metrics = next(
        item
        for item in resources
        if item.get("kind") == "Service"
        and item["metadata"]["name"] == f"{RELEASE}-redis-metrics"
    )
    assert _selector_matches(
        {"matchLabels": metrics["spec"]["selector"]}, target_labels
    )
    assert metrics["spec"]["ports"] == [
        {"name": "metrics", "port": 9121, "targetPort": "metrics", "protocol": "TCP"}
    ]
    exporter = next(
        container
        for container in redis["spec"]["template"]["spec"]["containers"]
        if container["name"] == "metrics"
    )
    assert exporter["ports"] == [
        {"name": "metrics", "containerPort": 9121, "protocol": "TCP"}
    ]
    assert _metrics_only_from_monitoring(resources, target_labels)
    assert _effective_ingress(
        resources,
        target_labels=target_labels,
        source_namespace="monitoring",
        source_labels={},
        port=9121,
    )
    for source_namespace, source_labels in (
        (APP_NAMESPACE, {}),
        (APP_NAMESPACE, {f"{RELEASE}-redis-client": "true"}),
        (APP_NAMESPACE, target_labels),
        ("untrusted-workload", {"prometheus.io/scrape": "true"}),
    ):
        assert not _effective_ingress(
            resources,
            target_labels=target_labels,
            source_namespace=source_namespace,
            source_labels=source_labels,
            port=9121,
        )
    app_workloads = [
        item
        for item in resources
        if item.get("kind") == "Deployment"
        and item["spec"]["template"]["metadata"]["labels"].get(
            "app.kubernetes.io/instance"
        )
        == RELEASE
    ]
    assert {"backend", "gateway", "file-processor", "ws-hub", "frontend"} <= {
        item["spec"]["template"]["metadata"]["labels"].get(
            "app.kubernetes.io/component"
        )
        for item in app_workloads
    }
    for workload in app_workloads:
        assert not _effective_ingress(
            resources,
            target_labels=target_labels,
            source_namespace=APP_NAMESPACE,
            source_labels=workload["spec"]["template"]["metadata"]["labels"],
            port=9121,
        )

    # A different selecting policy is additive and must defeat the deny check.
    widened = copy.deepcopy(resources)
    widened.append(
        {
            "kind": "NetworkPolicy",
            "metadata": {"name": "widening-control", "namespace": APP_NAMESPACE},
            "spec": {
                "podSelector": {"matchLabels": target_labels},
                "policyTypes": ["Ingress"],
                "ingress": [{"ports": [{"protocol": "TCP", "port": 9121}]}],
            },
        }
    )
    assert _effective_ingress(
        widened,
        target_labels=target_labels,
        source_namespace=APP_NAMESPACE,
        source_labels={},
        port=9121,
    )
    assert not _metrics_only_from_monitoring(widened, target_labels)
    # Sampling a generic source would miss a rule for a different pod label.
    widened[-1]["spec"]["ingress"][0]["from"] = [
        {"podSelector": {"matchLabels": {"access": "special"}}}
    ]
    assert not _effective_ingress(
        widened,
        target_labels=target_labels,
        source_namespace=APP_NAMESPACE,
        source_labels={},
        port=9121,
    )
    assert _effective_ingress(
        widened,
        target_labels=target_labels,
        source_namespace=APP_NAMESPACE,
        source_labels={"access": "special"},
        port=9121,
    )
    assert not _metrics_only_from_monitoring(widened, target_labels)
    assert _effective_ingress(
        [item for item in resources if item.get("kind") != "NetworkPolicy"],
        target_labels=target_labels,
        source_namespace=APP_NAMESPACE,
        source_labels={},
        port=9121,
    )
    assert not _metrics_only_from_monitoring(
        [item for item in resources if item.get("kind") != "NetworkPolicy"],
        target_labels,
    )
