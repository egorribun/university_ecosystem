"""Bounded, positive Prometheus scrape proof inside the disposable kind cluster.

This fixture is separate from the existing policy matrix. Its inputs are the two
source-bound ws-hub replicas already inventoried by the caller. No payloads,
addresses, command errors, or metric values are returned in the receipt.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
import secrets
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml
from networkpolicy_runtime_kube import run_command
from networkpolicy_runtime_temporal import compose_image

JOB = "aud438-ws-hub"
FIXTURE_LABEL = "netpol-real-prometheus"
MAX_OUTPUT = 131072
MAX_SCRAPE_AGE = 20.0
POLL_SECONDS = 45.0
UUID_PATTERN = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def _validated_replicas(replicas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept exactly two distinct, source-inventoried private IPv4 pods."""
    if not isinstance(replicas, list) or len(replicas) != 2:
        raise ValueError("expected two replicas")
    clean = []
    for replica in replicas:
        name, uid, address = replica["name"], replica["uid"], replica["ip"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", name)
            or len(name) > 63
            or not isinstance(uid, str)
            or not re.fullmatch(UUID_PATTERN, uid)
            or not isinstance(address, str)
        ):
            raise ValueError("invalid replica identity")
        ip = ipaddress.ip_address(address)
        if not isinstance(ip, ipaddress.IPv4Address) or not any(
            ip in network for network in PRIVATE_NETWORKS
        ):
            raise ValueError("unexpected replica address")
        if (
            not isinstance(replica["container_id"], str)
            or not replica["container_id"]
            or not isinstance(replica["image_id"], str)
            or not replica["image_id"]
            or type(replica["restarts"]) is not int
            or replica["restarts"] < 0
        ):
            raise ValueError("unbound replica container")
        clean.append(
            {
                key: replica[key]
                for key in ("name", "uid", "ip", "container_id", "image_id", "restarts")
            }
        )
    if any(len({item[key] for item in clean}) != 2 for key in ("name", "uid", "ip")):
        raise ValueError("ambiguous replicas")
    return sorted(clean, key=lambda item: item["uid"])


def _fixture_objects(
    image: str, replicas: list[dict[str, Any]], peer_labels: dict[str, str], suffix: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build only a fixed-target ConfigMap, egress policy, and Prometheus pod."""
    if not re.fullmatch(r"prom/prometheus:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", image):
        raise ValueError("untrusted image")
    if not re.fullmatch(r"[0-9a-f]{12}", suffix) or FIXTURE_LABEL in peer_labels:
        raise ValueError("ambiguous fixture identity")
    name = f"netpol-prom-{suffix}"
    labels = {**peer_labels, FIXTURE_LABEL: suffix}
    metadata = {"name": name, "namespace": "monitoring"}
    config = {
        "global": {"scrape_interval": "5s", "scrape_timeout": "3s"},
        "scrape_configs": [
            {
                "job_name": JOB,
                "metrics_path": "/metrics",
                "target_limit": 2,
                "body_size_limit": "2MB",
                "sample_limit": 10000,
                "static_configs": [
                    {
                        "targets": [f"{replica['ip']}:9108"],
                        "labels": {"replica_uid": replica["uid"]},
                    }
                    for replica in replicas
                ],
            }
        ],
    }
    config_map = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": dict(metadata),
        "immutable": True,
        "data": {"prometheus.yml": yaml.safe_dump(config, sort_keys=True)},
    }
    policy = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": dict(metadata),
        "spec": {
            "podSelector": {"matchLabels": {FIXTURE_LABEL: suffix}},
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {"ipBlock": {"cidr": f"{replica['ip']}/32"}}
                        for replica in replicas
                    ],
                    "ports": [{"protocol": "TCP", "port": 9108}],
                }
            ],
        },
    }
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {**metadata, "labels": labels},
        "spec": {
            "automountServiceAccountToken": False,
            "enableServiceLinks": False,
            "hostNetwork": False,
            "restartPolicy": "Never",
            "activeDeadlineSeconds": 360,
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 65534,
                "runAsGroup": 65534,
                "fsGroup": 65534,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [
                {
                    "name": "prometheus",
                    "image": image,
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["/bin/prometheus"],
                    "args": [
                        "--config.file=/etc/prometheus/prometheus.yml",
                        "--storage.tsdb.path=/prometheus",
                        "--web.listen-address=127.0.0.1:9090",
                    ],
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                    "resources": {
                        "requests": {
                            "cpu": "50m",
                            "memory": "128Mi",
                            "ephemeral-storage": "32Mi",
                        },
                        "limits": {
                            "cpu": "250m",
                            "memory": "512M",
                            "ephemeral-storage": "384Mi",
                        },
                    },
                    "volumeMounts": [
                        {
                            "name": "config",
                            "mountPath": "/etc/prometheus",
                            "readOnly": True,
                        },
                        {"name": "data", "mountPath": "/prometheus"},
                    ],
                }
            ],
            "volumes": [
                {"name": "config", "configMap": {"name": name}},
                {"name": "data", "emptyDir": {"sizeLimit": "256Mi"}},
            ],
        },
    }
    return config_map, policy, pod


def _command(*args: str, stdin: str | None = None, timeout: float = 10) -> str:
    result = run_command(["kubectl", *args], stdin=stdin, timeout=timeout)
    if len(result.stdout.encode("utf-8")) > MAX_OUTPUT:
        raise ValueError("oversized response")
    return result.stdout


def _json_command(
    *args: str, stdin: str | None = None, timeout: float = 10
) -> dict[str, Any]:
    result = json.loads(_command(*args, stdin=stdin, timeout=timeout))
    if not isinstance(result, dict):
        raise ValueError("invalid response")
    return result


def _monitoring_peer(
    app: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    matches = [
        item
        for item in app
        if item.get("kind") == "NetworkPolicy"
        and item.get("metadata", {}).get("name") == "probe-a-ws-hub-policy"
    ]
    if len(matches) != 1:
        raise ValueError("ambiguous metrics policy")
    policy = matches[0]
    grants = [
        peer
        for rule in policy["spec"]["ingress"]
        if {"protocol": "TCP", "port": 9108} in rule.get("ports", [])
        for peer in rule.get("from", [])
    ]
    if len(grants) != 1 or set(grants[0]) != {"namespaceSelector", "podSelector"}:
        raise ValueError("ambiguous metrics grant")
    selectors = []
    for key in ("namespaceSelector", "podSelector"):
        selector = grants[0][key]
        if set(selector) != {"matchLabels"} or not selector["matchLabels"]:
            raise ValueError("unsupported metrics selector")
        labels = selector["matchLabels"]
        if not isinstance(labels, dict) or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or not v
            for k, v in labels.items()
        ):
            raise ValueError("invalid metrics selector")
        selectors.append(dict(labels))
    return selectors[0], selectors[1]


def _namespace_matches(labels: dict[str, str]) -> None:
    namespace = _json_command("get", "namespace", "monitoring", "-o", "json")
    metadata = namespace["metadata"]
    if metadata["name"] != "monitoring" or any(
        metadata["labels"].get(key) != value for key, value in labels.items()
    ):
        raise ValueError("monitoring namespace changed")


def _check_targets(replicas: list[dict[str, Any]]) -> None:
    for replica in replicas:
        pod = _json_command(
            "-n", "probe-a", "get", "pod", replica["name"], "-o", "json"
        )
        metadata, status = pod["metadata"], pod["status"]
        matches = [
            item for item in status["containerStatuses"] if item["name"] == "ws-hub"
        ]
        if (
            metadata.get("namespace") != "probe-a"
            or metadata.get("name") != replica["name"]
            or metadata.get("uid") != replica["uid"]
            or metadata.get("deletionTimestamp") is not None
            or status.get("podIP") != replica["ip"]
            or len(matches) != 1
        ):
            raise ValueError("replica identity changed")
        container = matches[0]
        if (
            container.get("ready") is not True
            or container.get("containerID") != replica["container_id"]
            or container.get("imageID") != replica["image_id"]
            or container.get("restartCount") != replica["restarts"]
        ):
            raise ValueError("replica container changed")


def _create(resource: dict[str, Any]) -> str:
    created = _json_command(
        "create", "-f", "-", "-o", "json", stdin=json.dumps(resource)
    )
    metadata, expected = created["metadata"], resource["metadata"]
    uid = metadata.get("uid")
    if (
        created.get("apiVersion") != resource["apiVersion"]
        or created.get("kind") != resource["kind"]
        or metadata.get("namespace") != expected["namespace"]
        or metadata.get("name") != expected["name"]
        or not isinstance(uid, str)
        or not re.fullmatch(UUID_PATTERN, uid)
    ):
        raise ValueError("invalid created identity")
    return uid


def _fixture_unchanged(resource: dict[str, Any], uid: str) -> None:
    kind = {"ConfigMap": "configmap", "NetworkPolicy": "networkpolicy"}[
        resource["kind"]
    ]
    live = _json_command(
        "-n", "monitoring", "get", kind, resource["metadata"]["name"], "-o", "json"
    )
    if live["metadata"].get("uid") != uid:
        raise ValueError("fixture replaced")
    if kind == "configmap":
        if live.get("immutable") is not True or live.get("data") != resource["data"]:
            raise ValueError("config changed")
    else:
        if live.get("spec") != resource["spec"]:
            raise ValueError("policy changed")
        policies = _json_command(
            "-n", "monitoring", "get", "networkpolicies", "-o", "json"
        )
        if (
            len(policies["items"]) != 1
            or policies["items"][0]["metadata"].get("uid") != uid
        ):
            raise ValueError("additional monitoring policies")


def _source_snapshot(pod: dict[str, Any], uid: str) -> dict[str, Any]:
    expected = pod["spec"]
    live = _json_command(
        "-n", "monitoring", "get", "pod", pod["metadata"]["name"], "-o", "json"
    )
    metadata, spec, status = live["metadata"], live["spec"], live["status"]
    if (
        metadata.get("name") != pod["metadata"]["name"]
        or metadata.get("namespace") != "monitoring"
        or metadata.get("uid") != uid
        or metadata.get("deletionTimestamp") is not None
        or metadata.get("labels") != pod["metadata"]["labels"]
        or spec.get("hostNetwork", False) is not False
        or any(
            spec.get(key) != expected[key]
            for key in (
                "automountServiceAccountToken",
                "enableServiceLinks",
                "restartPolicy",
                "activeDeadlineSeconds",
            )
        )
        or any(
            spec.get("securityContext", {}).get(key) != value
            for key, value in expected["securityContext"].items()
        )
        or status.get("phase") != "Running"
        or len(spec["containers"]) != 1
        or len(status["containerStatuses"]) != 1
    ):
        raise ValueError("source pod changed")
    container, wanted = spec["containers"][0], expected["containers"][0]
    if any(
        container.get(key) != wanted[key]
        for key in (
            "name",
            "image",
            "imagePullPolicy",
            "command",
            "args",
            "securityContext",
            "resources",
        )
    ):
        raise ValueError("source process changed")
    mounts = container.get("volumeMounts", [])
    if len(mounts) != 2 or {
        (item.get("name"), item.get("mountPath"), item.get("readOnly", False))
        for item in mounts
    } != {("config", "/etc/prometheus", True), ("data", "/prometheus", False)}:
        raise ValueError("source mounts changed")
    volumes = spec.get("volumes", [])
    if len(volumes) != 2:
        raise ValueError("source volumes changed")
    by_name = {volume["name"]: volume for volume in volumes}
    if (
        set(by_name) != {"config", "data"}
        or by_name["config"].get("configMap", {}).get("name") != pod["metadata"]["name"]
        or "items" in by_name["config"].get("configMap", {})
        or by_name["data"].get("emptyDir", {}).get("sizeLimit") != "256Mi"
    ):
        raise ValueError("source volumes changed")
    current = status["containerStatuses"][0]
    image_id = current.get("imageID", "")
    container_id = current.get("containerID", "")
    digest = re.search(r"sha256:[0-9a-f]{64}$", image_id)
    if (
        current.get("name") != "prometheus"
        or current.get("ready") is not True
        or current.get("restartCount") != 0
        or not digest
        or not re.fullmatch(r"(?:containerd|docker)://[0-9a-f]{64}", container_id)
    ):
        raise ValueError("source container changed")
    started = datetime.fromisoformat(status["startTime"].replace("Z", "+00:00"))
    if started.tzinfo is None:
        raise ValueError("invalid source start")
    return {
        "namespace": "monitoring",
        "name": metadata["name"],
        "uid": uid,
        "image_id": digest.group(),
        "container_id": container_id,
        "started": started,
    }


def _fresh(timestamp: float, started: datetime, now: datetime) -> bool:
    return (
        math.isfinite(timestamp)
        and started.timestamp() <= timestamp <= now.timestamp() + 2
        and now.timestamp() - timestamp <= MAX_SCRAPE_AGE
    )


def _validate_observations(
    replicas: list[dict[str, Any]],
    documents: dict[str, Any],
    started: datetime,
    now: datetime,
) -> list[dict[str, str]]:
    expected = {item["uid"]: f"{item['ip']}:9108" for item in replicas}
    target_doc = documents["targets"]
    if (
        target_doc["status"] != "success"
        or len(target_doc["data"]["activeTargets"]) != 2
    ):
        raise ValueError("invalid targets")
    seen = set()
    for target in target_doc["data"]["activeTargets"]:
        labels = target["labels"]
        uid = labels["replica_uid"]
        if (
            uid not in expected
            or uid in seen
            or labels.get("job") != JOB
            or labels.get("instance") != expected[uid]
            or target.get("scrapeUrl") != f"http://{expected[uid]}/metrics"
            or target.get("health") != "up"
            or target.get("lastError") != ""
        ):
            raise ValueError("unexpected target")
        last = datetime.fromisoformat(target["lastScrape"].replace("Z", "+00:00"))
        if last.tzinfo is None or not _fresh(last.timestamp(), started, now):
            raise ValueError("stale target")
        seen.add(uid)
    for key in ("up", "up_time", "gauge", "gauge_time"):
        document = documents[key]
        if (
            document["status"] != "success"
            or document["data"]["resultType"] != "vector"
        ):
            raise ValueError("invalid query")
        vector = document["data"]["result"]
        if len(vector) != 2:
            raise ValueError("incomplete query")
        seen = set()
        for series in vector:
            labels = series["metric"]
            uid = labels["replica_uid"]
            if (
                uid not in expected
                or uid in seen
                or labels.get("job") != JOB
                or labels.get("instance") != expected[uid]
            ):
                raise ValueError("unexpected sample")
            value = float(series["value"][1])
            if (
                not math.isfinite(value)
                or (key == "up" and value != 1)
                or (key == "gauge" and value < 0)
            ):
                raise ValueError("invalid sample")
            if key.endswith("_time") and not _fresh(value, started, now):
                raise ValueError("stale sample")
            seen.add(uid)
    return [{"replica_uid": item["uid"], "verdict": "pass"} for item in replicas]


def _api(name: str, path: str, timeout: float) -> dict[str, Any]:
    # A fixed shell program bounds captured stdout; the URL is a positional
    # argument, never shell-interpolated. The image is the tracked BusyBox image.
    result = _command(
        "-n",
        "monitoring",
        "exec",
        name,
        "-c",
        "prometheus",
        "--",
        "/bin/sh",
        "-ec",
        'set -o pipefail; wget -q -T 2 -O - "$1" | head -c 131073',
        "--",
        f"http://127.0.0.1:9090{path}",
        timeout=timeout,
    )
    value = json.loads(result)
    if not isinstance(value, dict):
        raise ValueError("invalid API response")
    return value


def _poll(
    name: str, replicas: list[dict[str, Any]], started: datetime
) -> list[dict[str, str]]:
    deadline = time.monotonic() + POLL_SECONDS
    metric = f'ws_hub_active_goroutines{{job="{JOB}"}}'
    up = f'up{{job="{JOB}"}}'
    paths = {
        "targets": "/api/v1/targets?state=active",
        "up": "/api/v1/query?" + urlencode({"query": up}),
        "up_time": "/api/v1/query?" + urlencode({"query": f"timestamp({up})"}),
        "gauge": "/api/v1/query?" + urlencode({"query": metric}),
        "gauge_time": "/api/v1/query?" + urlencode({"query": f"timestamp({metric})"}),
    }
    while time.monotonic() < deadline:
        try:
            documents = {}
            for key, path in paths.items():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("scrape deadline")
                documents[key] = _api(name, path, timeout=min(10.0, remaining))
            return _validate_observations(
                replicas, documents, started, datetime.now(UTC)
            )
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(1.0, remaining))
    raise TimeoutError("scrape deadline")


def prove_actual_prometheus(
    root: Path, app: list[dict[str, Any]], replicas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return fixed, sanitized evidence or an inconclusive stage; kind owns cleanup."""
    stage = "input"
    try:
        targets = _validated_replicas(replicas)
        image = compose_image(root, "prometheus")
        ns_labels, peer_labels = _monitoring_peer(app)
        config, policy, pod = _fixture_objects(
            image, targets, peer_labels, secrets.token_hex(6)
        )
        stage = "targets-before"
        _check_targets(targets)
        _namespace_matches(ns_labels)
        stage = "create-config"
        config_uid = _create(config)
        stage = "create-policy"
        policy_uid = _create(policy)
        _fixture_unchanged(policy, policy_uid)
        stage = "create-pod"
        pod_uid = _create(pod)
        stage = "pod-ready"
        _command(
            "-n",
            "monitoring",
            "wait",
            "--for=condition=Ready",
            f"pod/{pod['metadata']['name']}",
            "--timeout=120s",
            timeout=125,
        )
        stage = "source-before"
        _namespace_matches(ns_labels)
        _fixture_unchanged(config, config_uid)
        _fixture_unchanged(policy, policy_uid)
        source = _source_snapshot(pod, pod_uid)
        stage = "scrape"
        checks = _poll(pod["metadata"]["name"], targets, source["started"])
        stage = "source-after"
        _namespace_matches(ns_labels)
        _fixture_unchanged(config, config_uid)
        _fixture_unchanged(policy, policy_uid)
        if _source_snapshot(pod, pod_uid) != source:
            raise ValueError("source identity changed")
        stage = "targets-after"
        _check_targets(targets)
        return {
            "verdict": "pass",
            "source": {key: value for key, value in source.items() if key != "started"},
            "checks": checks,
        }
    except Exception:
        return {"verdict": "inconclusive", "stage": stage}
