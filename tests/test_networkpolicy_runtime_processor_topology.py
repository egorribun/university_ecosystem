"""Offline tests for optional real-processor topology receipts."""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/k8s"))

NAMESPACE = "probe-a"
REDIS = "probe-a-revocation-redis-master"
BACKEND = "probe-a-backend"
REDIS_SELECTOR = {
    "app.kubernetes.io/instance": NAMESPACE,
    "app.kubernetes.io/name": "revocation-redis",
    "app.kubernetes.io/component": "master",
}
BACKEND_SELECTOR = {"probe-role": "a-backend"}
PROCESSOR_SELECTOR = {"app.kubernetes.io/name": "file-processor"}


def uid(number):
    return f"00000000-0000-4000-8000-{number:012d}"


def key(kind, name):
    return ("-n", NAMESPACE, "get", kind, name, "-o", "json")


def pod(name, number, address, labels, *, processor=False):
    status = {"podIP": address, "conditions": [{"type": "Ready", "status": "True"}]}
    if processor:
        status["containerStatuses"] = [
            {
                "name": "file-processor",
                "ready": True,
                "containerID": f"containerd://processor-{number}",
                "imageID": "sha256:" + "a" * 64,
                "restartCount": 0,
            }
        ]
    return {
        "metadata": {
            "namespace": NAMESPACE,
            "name": name,
            "uid": uid(number),
            "labels": labels,
            "annotations": {"private": "sensitive-canary"},
        },
        "spec": {"nodeName": "worker-1"},
        "status": status,
    }


def service(name, number, address, selector, port):
    return {
        "metadata": {"namespace": NAMESPACE, "name": name, "uid": uid(number)},
        "spec": {"clusterIP": address, "selector": selector, "ports": [port]},
    }


def endpoint_slice(name, number, service_uid, target, port):
    return {
        "metadata": {
            "namespace": NAMESPACE,
            "uid": uid(number),
            "labels": {"kubernetes.io/service-name": name},
            "ownerReferences": [
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "name": name,
                    "uid": service_uid,
                    "controller": True,
                }
            ],
        },
        "addressType": "IPv4",
        "ports": [port],
        "endpoints": [
            {
                "addresses": [target["status"]["podIP"]],
                "conditions": {"ready": True, "serving": True, "terminating": False},
                "targetRef": {
                    "kind": "Pod",
                    "namespace": NAMESPACE,
                    "name": target["metadata"]["name"],
                    "uid": target["metadata"]["uid"],
                },
            }
        ],
    }


@pytest.fixture
def cluster():
    resources = {}
    replicas = []
    for number in (1, 2):
        name = f"probe-a-file-processor-{number}"
        obj = pod(
            name, number, f"10.244.0.{number}", PROCESSOR_SELECTOR, processor=True
        )
        resources[key("pod", name)] = obj
        replicas.append(
            {
                "name": name,
                "uid": uid(number),
                "ip": obj["status"]["podIP"],
                "container_id": f"containerd://processor-{number}",
                "image_id": "sha256:" + "a" * 64,
                "restarts": 0,
            }
        )
    redis_pod = pod(REDIS + "-0", 3, "10.244.0.3", REDIS_SELECTOR)
    backend_pod = pod(BACKEND, 4, "10.244.0.4", BACKEND_SELECTOR)
    pods = {
        "a-redis": SimpleNamespace(
            namespace=NAMESPACE, name=REDIS + "-0", uid=uid(3), ip="10.244.0.3"
        ),
        "a-backend": SimpleNamespace(
            namespace=NAMESPACE, name=BACKEND, uid=uid(4), ip="10.244.0.4"
        ),
    }
    resources[key("pod", REDIS + "-0")] = redis_pod
    resources[key("pod", BACKEND)] = backend_pod
    for name, number, target, selector, port in (
        (
            REDIS,
            5,
            redis_pod,
            REDIS_SELECTOR,
            {
                "name": "tcp-redis",
                "port": 6379,
                "targetPort": "redis",
                "protocol": "TCP",
            },
        ),
        (
            BACKEND,
            6,
            backend_pod,
            BACKEND_SELECTOR,
            {"port": 8000, "targetPort": 8000, "protocol": "TCP"},
        ),
    ):
        resources[key("service", name)] = service(
            name, number, f"10.96.0.{number}", selector, port
        )
        slice_port = {"name": port.get("name"), "port": port["port"], "protocol": "TCP"}
        resources[
            (
                "-n",
                NAMESPACE,
                "get",
                "endpointslices",
                "-l",
                f"kubernetes.io/service-name={name}",
                "-o",
                "json",
            )
        ] = {
            "items": [
                endpoint_slice(name, number + 10, uid(number), target, slice_port)
            ]
        }
    resources[("get", "node", "worker-1", "-o", "json")] = {
        "metadata": {
            "name": "worker-1",
            "uid": uid(20),
            "annotations": {"private": "sensitive-canary"},
        },
        "spec": {"podCIDRs": ["10.244.0.0/24"]},
        "status": {"addresses": [{"type": "InternalIP", "address": "172.18.0.2"}]},
    }
    resources[("get", "servicecidrs.networking.k8s.io", "-o", "json")] = {
        "items": [{"spec": {"cidrs": ["10.96.0.0/12"]}}]
    }
    resources[
        ("-n", "kube-system", "get", "configmap", "kubeadm-config", "-o", "json")
    ] = {
        "data": {
            "ClusterConfiguration": "networking:\n  podSubnet: 10.244.0.0/16\nprivate: sensitive-canary\n"
        }
    }
    fixture = SimpleNamespace(
        jwks_hostname=BACKEND,
        deployment={"spec": {"selector": {"matchLabels": PROCESSOR_SELECTOR}}},
    )
    return resources, fixture, pods, replicas


def capture(monkeypatch, cluster):
    topology = importlib.import_module("networkpolicy_runtime_processor_topology")
    resources, fixture, pods, replicas = cluster

    def fake_command(command, *, timeout):
        assert command[0] == "kubectl"
        assert 0 < timeout <= 10
        return SimpleNamespace(stdout=json.dumps(resources[tuple(command[1:])]))

    monkeypatch.setattr(topology, "run_command", fake_command)
    return topology, topology.capture_topology(NAMESPACE, fixture, pods, replicas)


def test_snapshot_binds_positive_services_to_actual_pod_identities(
    monkeypatch, cluster
):
    topology, before = capture(monkeypatch, cluster)
    assert before["status"] == "available"
    assert before["services"]["redis"]["name"] == REDIS
    assert before["services"]["jwks"]["name"] == BACKEND
    assert before["services"]["redis"]["target_uid"] == uid(3)
    assert before["services"]["jwks"]["target_uid"] == uid(4)
    assert "sensitive-canary" not in json.dumps(before)
    assert topology.compare_topology(before, copy.deepcopy(before))["verdict"] == "pass"


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "target",
        "unready",
        "duplicate",
        "selector",
        "pod_uid",
        "port",
        "empty",
        "empty_slice",
        "pod_unready",
        "pod_ready_missing",
        "processor_unready",
        "publish_not_ready",
        "deleting_pod",
        "deleting_service",
        "deleting_slice",
        "owner_api",
    ],
)
def test_snapshot_rejects_stale_or_ambiguous_bindings(monkeypatch, cluster, fault):
    resources, _, _, _ = cluster
    slice_key = (
        "-n",
        NAMESPACE,
        "get",
        "endpointslices",
        "-l",
        f"kubernetes.io/service-name={BACKEND}",
        "-o",
        "json",
    )
    item = resources[slice_key]["items"][0]
    if fault == "owner":
        item["metadata"]["ownerReferences"][0]["uid"] = uid(999)
    elif fault == "target":
        item["endpoints"][0]["targetRef"]["uid"] = uid(999)
    elif fault == "unready":
        item["endpoints"][0]["conditions"]["ready"] = False
    elif fault == "duplicate":
        item["endpoints"].append(copy.deepcopy(item["endpoints"][0]))
    elif fault == "selector":
        resources[key("service", BACKEND)]["spec"]["selector"] = {"probe-role": "wrong"}
    elif fault == "pod_uid":
        resources[key("pod", BACKEND)]["metadata"]["uid"] = uid(999)
    elif fault == "port":
        item["ports"][0]["port"] = 8001
    elif fault == "empty_slice":
        empty_slice = copy.deepcopy(item)
        empty_slice["metadata"]["uid"] = uid(999)
        empty_slice["endpoints"] = []
        resources[slice_key]["items"].append(empty_slice)
    elif fault == "pod_unready":
        resources[key("pod", BACKEND)]["status"]["conditions"][0]["status"] = "False"
    elif fault == "pod_ready_missing":
        del resources[key("pod", BACKEND)]["status"]["conditions"]
    elif fault == "processor_unready":
        resources[key("pod", "probe-a-file-processor-1")]["status"]["conditions"][0][
            "status"
        ] = "False"
    elif fault == "publish_not_ready":
        resources[key("service", BACKEND)]["spec"]["publishNotReadyAddresses"] = True
    elif fault == "deleting_pod":
        resources[key("pod", BACKEND)]["metadata"]["deletionTimestamp"] = (
            "2026-11-16T00:00:00Z"
        )
    elif fault == "deleting_service":
        resources[key("service", BACKEND)]["metadata"]["deletionTimestamp"] = (
            "2026-11-16T00:00:00Z"
        )
    elif fault == "deleting_slice":
        item["metadata"]["deletionTimestamp"] = "2026-11-16T00:00:00Z"
    elif fault == "owner_api":
        item["metadata"]["ownerReferences"][0]["apiVersion"] = "example.invalid/v1"
    else:
        resources[slice_key]["items"] = []
    _, snapshot = capture(monkeypatch, cluster)
    assert snapshot == {"status": "unavailable"}


def test_snapshot_detects_changed_service_between_samples(monkeypatch, cluster):
    topology, before = capture(monkeypatch, cluster)
    cluster[0][key("service", BACKEND)]["spec"]["clusterIP"] = "10.96.0.99"
    _, after = capture(monkeypatch, cluster)
    assert after["status"] == "available"
    assert topology.compare_topology(before, after)["verdict"] == "inconclusive"


@pytest.mark.parametrize(
    "fault",
    [
        "scope",
        "alias",
        "count",
        "selector",
        "container",
        "duplicate",
        "dependency",
        "nonobject",
    ],
)
def test_invalid_processor_inputs_remain_unavailable(monkeypatch, cluster, fault):
    resources, fixture, pods, replicas = cluster
    if fault == "scope":
        fixture.jwks_hostname = None
    elif fault == "alias":
        fixture.jwks_hostname = "a-backend-svc"
    elif fault == "count":
        replicas.pop()
    elif fault == "selector":
        fixture.deployment["spec"]["selector"]["matchLabels"] = {}
    elif fault == "container":
        resources[key("pod", replicas[0]["name"])]["status"]["containerStatuses"][0][
            "containerID"
        ] = "containerd://changed"
    elif fault == "duplicate":
        replicas[1] = copy.deepcopy(replicas[0])
    elif fault == "dependency":
        pods["a-redis"].name = "unexpected"
    else:
        resources[key("pod", replicas[0]["name"])] = []
    _, snapshot = capture(monkeypatch, cluster)
    assert snapshot == {"status": "unavailable"}


@pytest.mark.parametrize(
    "fault", ["empty", "malformed", "node_identity", "missing_node", "bad_config"]
)
def test_optional_cidr_failures_are_reported_without_raw_data(
    monkeypatch, cluster, fault
):
    resources, _, _, _ = cluster
    node_key = ("get", "node", "worker-1", "-o", "json")
    config_key = (
        "-n",
        "kube-system",
        "get",
        "configmap",
        "kubeadm-config",
        "-o",
        "json",
    )
    if fault == "empty":
        resources[node_key]["spec"] = {}
    elif fault == "malformed":
        resources[node_key]["spec"]["podCIDRs"] = ["not-a-cidr"]
    elif fault == "node_identity":
        resources[node_key]["metadata"]["name"] = "wrong-node"
    elif fault == "missing_node":
        del resources[node_key]
    else:
        resources[config_key]["data"]["ClusterConfiguration"] = "[invalid"
    topology, snapshot = capture(monkeypatch, cluster)
    assert snapshot["status"] == "available"
    assert (
        topology.compare_topology(snapshot, copy.deepcopy(snapshot))["verdict"]
        == "inconclusive"
    )
    assert "sensitive-canary" not in json.dumps(snapshot)


def test_unavailable_cidr_is_not_reported_as_complete(monkeypatch, cluster):
    del cluster[0][("get", "servicecidrs.networking.k8s.io", "-o", "json")]
    topology, snapshot = capture(monkeypatch, cluster)
    assert snapshot["status"] == "available"
    assert snapshot["cidrs"]["service"] is None
    assert (
        topology.compare_topology(snapshot, copy.deepcopy(snapshot))["verdict"]
        == "inconclusive"
    )


def test_service_ip_outside_authoritative_ranges_is_inconclusive(monkeypatch, cluster):
    cluster[0][("get", "servicecidrs.networking.k8s.io", "-o", "json")] = {
        "items": [{"spec": {"cidrs": ["10.64.0.0/12"]}}]
    }
    topology, snapshot = capture(monkeypatch, cluster)
    assert snapshot["status"] == "available"
    assert (
        topology.compare_topology(snapshot, copy.deepcopy(snapshot))["verdict"]
        == "inconclusive"
    )


def test_pod_ip_outside_configured_cluster_range_is_inconclusive(monkeypatch, cluster):
    cluster[0][
        ("-n", "kube-system", "get", "configmap", "kubeadm-config", "-o", "json")
    ] = {"data": {"ClusterConfiguration": "networking:\n  podSubnet: 192.0.2.0/24\n"}}
    topology, snapshot = capture(monkeypatch, cluster)
    assert snapshot["status"] == "available"
    assert (
        topology.compare_topology(snapshot, copy.deepcopy(snapshot))["verdict"]
        == "inconclusive"
    )


def test_invalid_replica_identity_does_not_call_kubernetes(monkeypatch, cluster):
    topology = importlib.import_module("networkpolicy_runtime_processor_topology")
    _, fixture, pods, replicas = cluster
    replicas[0]["uid"] = "invalid"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid input must not issue an API read")

    monkeypatch.setattr(topology, "run_command", forbidden)
    assert topology.capture_topology(NAMESPACE, fixture, pods, replicas) == {
        "status": "unavailable"
    }


def test_snapshot_uses_the_callers_existing_command_boundary(monkeypatch, cluster):
    topology = importlib.import_module("networkpolicy_runtime_processor_topology")
    resources, fixture, pods, replicas = cluster

    def forbidden(*args, **kwargs):
        pytest.fail("snapshot must use the supplied offline command boundary")

    def fake_command(command, *, timeout):
        assert command[0] == "kubectl"
        assert 0 < timeout <= 10
        return SimpleNamespace(stdout=json.dumps(resources[tuple(command[1:])]))

    monkeypatch.setattr(topology, "run_command", forbidden)
    snapshot = topology.capture_topology(
        NAMESPACE, fixture, pods, replicas, command_runner=fake_command
    )
    assert snapshot["status"] == "available"


@pytest.mark.parametrize("fault", ["capture", "comparison"])
def test_optional_snapshot_failure_does_not_change_processor_verdict(
    monkeypatch, fault
):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    deployment = {
        "metadata": {"name": "probe-a-file-processor"},
        "spec": {"replicas": 2, "selector": {"matchLabels": PROCESSOR_SELECTOR}},
    }
    fixture = SimpleNamespace(deployment=deployment, jwks_hostname=BACKEND)
    monkeypatch.setattr(
        real_fp, "bootstrap_temporal", lambda *args: {"result": "ready"}
    )
    monkeypatch.setattr(real_fp, "bootstrap_nats", lambda *args: "nats://fixture")
    monkeypatch.setattr(real_fp, "generate_signing_key", lambda *args: object())
    monkeypatch.setattr(
        real_fp, "prepare_processor_fixture", lambda *args, **kwargs: fixture
    )
    monkeypatch.setattr(real_fp, "kubectl", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        real_fp, "replica_state", lambda *args: [{"uid": uid(1)}, {"uid": uid(2)}]
    )

    def network(*args):
        args[-1].append({"check_id": "network", "verdict": "pass"})

    def authentication(*args):
        args[-2].append({"check_id": "authentication", "verdict": "pass"})

    captures = []

    def forbidden_command(*args, **kwargs):
        pytest.fail("no live Kubernetes commands are allowed")

    def unavailable(*args, **kwargs):
        assert kwargs["command_runner"] is forbidden_command
        captures.append(True)
        if fault == "capture":
            raise RuntimeError("sensitive-canary")
        return {"status": "available"}

    def failed_comparison(*args):
        raise RuntimeError("sensitive-canary")

    monkeypatch.setattr(real_fp, "check_processor_network", network)
    monkeypatch.setattr(real_fp, "verify_processor_authentication", authentication)
    monkeypatch.setattr(real_fp, "run_command", forbidden_command)
    monkeypatch.setattr(real_fp, "capture_topology", unavailable, raising=False)
    if fault == "comparison":
        monkeypatch.setattr(real_fp, "compare_topology", failed_comparison)
    receipt = real_fp.actual_processor_phase(
        ROOT,
        {NAMESPACE: ([], [])},
        {},
        {NAMESPACE: "test-password"},
        python_image="python",
        processor_image="processor",
        diagnostic_image="diagnostic",
        source_sha="a" * 40,
    )
    assert len(captures) == 2
    assert receipt["verdict"] == "pass"
    assert [check["check_id"] for check in receipt["checks"]] == [
        "network",
        "authentication",
    ]
    assert receipt["topology"]["verdict"] == "inconclusive"
    assert "sensitive-canary" not in json.dumps(receipt)
