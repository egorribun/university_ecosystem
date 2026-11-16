"""Offline contracts for the disposable real-Prometheus proof."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import math
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = "a" * 12
sys.path.insert(0, str(ROOT / "scripts/k8s"))


def test_real_prometheus_helper_is_available():
    assert importlib.util.find_spec("networkpolicy_runtime_real_prometheus") is not None


@pytest.fixture(scope="module")
def proof():
    name = "networkpolicy_runtime_real_prometheus"
    assert importlib.util.find_spec(name) is not None
    return importlib.import_module(name)


@pytest.fixture
def replicas():
    return [
        {
            "name": f"probe-a-ws-hub-{index}",
            "uid": f"00000000-0000-4000-8000-{index:012d}",
            "ip": f"10.244.0.{index}",
            "container_id": f"containerd://{index}",
            "image_id": f"image-{index}",
            "restarts": 0,
        }
        for index in (1, 2)
    ]


@pytest.fixture
def observations(replicas):
    now = datetime.now(UTC)
    targets = []
    vectors = {key: [] for key in ("up", "up_time", "gauge", "gauge_time")}
    for replica in replicas:
        labels = {
            "job": "aud438-ws-hub",
            "instance": f"{replica['ip']}:9108",
            "replica_uid": replica["uid"],
        }
        targets.append(
            {
                "labels": labels,
                "scrapeUrl": f"http://{replica['ip']}:9108/metrics",
                "lastError": "",
                "lastScrape": now.isoformat(),
                "health": "up",
            }
        )
        for key, value in (
            ("up", "1"),
            ("up_time", str(now.timestamp())),
            ("gauge", "5"),
            ("gauge_time", str(now.timestamp())),
        ):
            vectors[key].append(
                {"metric": labels.copy(), "value": [now.timestamp(), value]}
            )
    documents = {"targets": {"status": "success", "data": {"activeTargets": targets}}}
    documents.update(
        {
            key: {
                "status": "success",
                "data": {"resultType": "vector", "result": value},
            }
            for key, value in vectors.items()
        }
    )
    return documents, now


def test_fixture_uses_only_two_bound_ips_and_confines_prometheus(proof, replicas):
    config, policy, pod = proof._fixture_objects(
        "prom/prometheus:v3.15.0@sha256:" + "a" * 64,
        replicas,
        {"app.kubernetes.io/name": "prometheus"},
        SUFFIX,
    )
    assert config["immutable"] is True
    rendered = yaml.safe_load(config["data"]["prometheus.yml"])
    assert len(rendered["scrape_configs"]) == 1
    job = rendered["scrape_configs"][0]
    assert job["target_limit"] == 2
    assert {item["targets"][0] for item in job["static_configs"]} == {
        f"{item['ip']}:9108" for item in replicas
    }
    assert {item["labels"]["replica_uid"] for item in job["static_configs"]} == {
        item["uid"] for item in replicas
    }
    rule = policy["spec"]["egress"][0]
    assert {item["ipBlock"]["cidr"] for item in rule["to"]} == {
        f"{item['ip']}/32" for item in replicas
    }
    assert rule["ports"] == [{"protocol": "TCP", "port": 9108}]
    spec = pod["spec"]
    assert spec["automountServiceAccountToken"] is False
    assert spec["hostNetwork"] is False
    assert spec["activeDeadlineSeconds"] == 360
    assert spec["restartPolicy"] == "Never"
    container = spec["containers"][0]
    assert container["command"] == ["/bin/prometheus"]
    assert "--web.listen-address=127.0.0.1:9090" in container["args"]
    assert container["resources"]["limits"]["memory"] == "512M"
    assert all("remote" not in arg for arg in container["args"])


def test_success_requires_fresh_prometheus_target_and_gauge_samples(
    proof, replicas, observations
):
    docs, now = observations
    assert proof._validate_observations(
        replicas, docs, now - timedelta(seconds=10), now
    ) == [{"replica_uid": item["uid"], "verdict": "pass"} for item in replicas]


@pytest.mark.parametrize(
    "fault",
    [
        "missing-target",
        "extra-target",
        "wrong-url",
        "wrong-uid",
        "down",
        "error",
        "stale-target",
        "missing-up",
        "up-zero",
        "missing-gauge",
        "gauge-nan",
        "stale-up",
        "stale-gauge",
        "wrong-result-type",
        "failed-api",
        "sample-uid",
        "sample-instance",
        "negative-gauge",
        "future-target",
        "naive-target",
        "future-sample",
    ],
)
def test_observations_fail_closed_on_bad_evidence(proof, replicas, observations, fault):
    docs, now = copy.deepcopy(observations)
    active = docs["targets"]["data"]["activeTargets"]
    if fault == "missing-target":
        active.pop()
    elif fault == "extra-target":
        active.append(copy.deepcopy(active[0]))
    elif fault == "wrong-url":
        active[0]["scrapeUrl"] = "http://elsewhere:9108/metrics"
    elif fault == "wrong-uid":
        active[0]["labels"]["replica_uid"] = replicas[1]["uid"]
    elif fault == "down":
        active[0]["health"] = "down"
    elif fault == "error":
        active[0]["lastError"] = "failure"
    elif fault == "stale-target":
        active[0]["lastScrape"] = (now - timedelta(minutes=1)).isoformat()
    elif fault == "missing-up":
        docs["up"]["data"]["result"].pop()
    elif fault == "up-zero":
        docs["up"]["data"]["result"][0]["value"][1] = "0"
    elif fault == "missing-gauge":
        docs["gauge"]["data"]["result"].pop()
    elif fault == "gauge-nan":
        docs["gauge"]["data"]["result"][0]["value"][1] = str(math.nan)
    elif fault == "stale-up":
        docs["up_time"]["data"]["result"][0]["value"][1] = str(
            (now - timedelta(minutes=1)).timestamp()
        )
    elif fault == "stale-gauge":
        docs["gauge_time"]["data"]["result"][0]["value"][1] = str(
            (now - timedelta(minutes=1)).timestamp()
        )
    elif fault == "wrong-result-type":
        docs["up"]["data"]["resultType"] = "matrix"
    elif fault == "sample-uid":
        docs["gauge"]["data"]["result"][0]["metric"]["replica_uid"] = "unexpected"
    elif fault == "sample-instance":
        docs["gauge"]["data"]["result"][0]["metric"]["instance"] = "unexpected"
    elif fault == "negative-gauge":
        docs["gauge"]["data"]["result"][0]["value"][1] = "-1"
    elif fault == "future-target":
        active[0]["lastScrape"] = (now + timedelta(minutes=1)).isoformat()
    elif fault == "naive-target":
        active[0]["lastScrape"] = "2026-01-01T00:00:00"
    elif fault == "future-sample":
        docs["gauge_time"]["data"]["result"][0]["value"][1] = str(
            (now + timedelta(minutes=1)).timestamp()
        )
    else:
        docs["up"]["status"] = "error"
    with pytest.raises((ValueError, KeyError, TypeError)):
        proof._validate_observations(replicas, docs, now - timedelta(seconds=10), now)


@pytest.mark.parametrize(
    "fault",
    [
        "same-ip",
        "same-uid",
        "loopback",
        "bad-uid",
        "one",
        "no-container",
        "bad-restarts",
    ],
)
def test_target_inventory_must_be_exact_and_unambiguous(proof, replicas, fault):
    if fault == "same-ip":
        replicas[1]["ip"] = replicas[0]["ip"]
    elif fault == "same-uid":
        replicas[1]["uid"] = replicas[0]["uid"]
    elif fault == "loopback":
        replicas[0]["ip"] = "127.0.0.1"
    elif fault == "bad-uid":
        replicas[0]["uid"] = "not-a-uid"
    elif fault == "no-container":
        replicas[0]["container_id"] = ""
    elif fault == "bad-restarts":
        replicas[0]["restarts"] = -1
    else:
        replicas.pop()
    with pytest.raises(ValueError):
        proof._validated_replicas(replicas)


@pytest.fixture
def rendered_policy():
    return [
        {
            "kind": "NetworkPolicy",
            "metadata": {"name": "probe-a-ws-hub-policy"},
            "spec": {
                "ingress": [
                    {
                        "ports": [{"protocol": "TCP", "port": 9108}],
                        "from": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "kubernetes.io/metadata.name": "monitoring"
                                    }
                                },
                                "podSelector": {
                                    "matchLabels": {
                                        "app.kubernetes.io/name": "prometheus"
                                    }
                                },
                            }
                        ],
                    }
                ]
            },
        }
    ]


class FakeKubernetes:
    """Replace only the process boundary; preserve fixture and API behavior."""

    def __init__(self, replicas, observations, fault=None):
        self.replicas = {item["name"]: item for item in replicas}
        self.observations = observations[0]
        self.fault = fault
        self.started = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        self.created = {}
        self.get_count = {}
        self.commands = []

    def __call__(self, *args, stdin=None, timeout=10):
        self.commands.append((args, timeout))
        if args[0] == "create":
            resource = json.loads(stdin)
            kind = resource["kind"]
            if self.fault == "create-collision" and kind == "Pod":
                raise OSError("private create error")
            resource["metadata"]["uid"] = {
                "ConfigMap": "10000000-0000-4000-8000-000000000001",
                "NetworkPolicy": "10000000-0000-4000-8000-000000000002",
                "Pod": "10000000-0000-4000-8000-000000000003",
            }[kind]
            if self.fault == "bad-create-identity":
                resource["metadata"]["uid"] = "private invalid uid"
            self.created[kind] = resource
            return json.dumps(resource)
        if args[:3] == ("get", "namespace", "monitoring"):
            if self.fault == "namespace-label":
                return json.dumps({"metadata": {"name": "monitoring", "labels": {}}})
            return json.dumps(
                {
                    "metadata": {
                        "name": "monitoring",
                        "labels": {"kubernetes.io/metadata.name": "monitoring"},
                    }
                }
            )
        if args[:4] == ("-n", "probe-a", "get", "pod"):
            replica = self.replicas[args[4]]
            self.get_count[replica["name"]] = self.get_count.get(replica["name"], 0) + 1
            uid = replica["uid"]
            if self.fault == "target-drift" and self.get_count[replica["name"]] > 1:
                uid = "20000000-0000-4000-8000-000000000001"
            restart_count = replica["restarts"] + (self.fault == "target-restart")
            return json.dumps(
                {
                    "metadata": {
                        "name": replica["name"],
                        "namespace": "probe-a",
                        "uid": uid,
                    },
                    "status": {
                        "podIP": replica["ip"],
                        "containerStatuses": [
                            {
                                "name": "ws-hub",
                                "ready": True,
                                "containerID": replica["container_id"],
                                "imageID": replica["image_id"],
                                "restartCount": restart_count,
                            }
                        ],
                    },
                }
            )
        if args[:3] == ("-n", "monitoring", "wait"):
            return "ready"
        if args[:4] == ("-n", "monitoring", "get", "networkpolicies"):
            policies = [copy.deepcopy(self.created["NetworkPolicy"])]
            if self.fault == "broader-policy":
                policies.append({"metadata": {"name": "unrelated-broad-policy"}})
            return json.dumps({"items": policies})
        if args[:3] == ("-n", "monitoring", "get"):
            kind = {
                "configmap": "ConfigMap",
                "networkpolicy": "NetworkPolicy",
                "pod": "Pod",
            }[args[3]]
            item = copy.deepcopy(self.created[kind])
            self.get_count[kind] = self.get_count.get(kind, 0) + 1
            if kind == "ConfigMap" and self.fault == "fixture-replaced":
                item["metadata"]["uid"] = "20000000-0000-4000-8000-000000000001"
            if kind == "Pod":
                # Kubernetes omits false hostNetwork from serialized PodSpec.
                item["spec"].pop("hostNetwork")
                item["status"] = {
                    "phase": "Running",
                    "startTime": self.started,
                    "containerStatuses": [
                        {
                            "name": "prometheus",
                            "ready": True,
                            "restartCount": 0,
                            "containerID": "containerd://" + "d" * 64,
                            "imageID": "docker.io/prom/prometheus@sha256:" + "e" * 64,
                        }
                    ],
                }
                if self.fault == "source-drift" and self.get_count[kind] > 1:
                    item["status"]["containerStatuses"][0]["restartCount"] = 1
                if self.fault == "source-image-drift" and self.get_count[kind] > 1:
                    item["status"]["containerStatuses"][0]["imageID"] = (
                        "sha256:" + "f" * 64
                    )
                if self.fault == "naive-start":
                    item["status"]["startTime"] = "2026-01-01T00:00:00"
                if self.fault == "wrong-image":
                    item["spec"]["containers"][0]["image"] = "wrong"
                elif self.fault == "wrong-command":
                    item["spec"]["containers"][0]["command"] = ["/bin/not-prometheus"]
                elif self.fault == "wrong-mount":
                    item["spec"]["containers"][0]["volumeMounts"].append(
                        {"name": "other", "mountPath": "/bin"}
                    )
                elif self.fault == "wrong-fsgroup":
                    item["spec"]["securityContext"]["fsGroup"] = 0
                elif self.fault == "host-network":
                    item["spec"]["hostNetwork"] = True
                elif self.fault == "missing-volume":
                    item["spec"]["volumes"].pop()
                elif self.fault == "wrong-volume":
                    item["spec"]["volumes"][0]["configMap"]["name"] = "wrong"
            elif self.fault == "config-drift" and kind == "ConfigMap":
                item["data"]["prometheus.yml"] = "changed"
            elif self.fault == "policy-drift" and kind == "NetworkPolicy":
                item["spec"]["egress"] = []
            return json.dumps(item)
        if args[:3] == ("-n", "monitoring", "exec"):
            url = urlsplit(args[-1])
            if url.path.endswith("/targets"):
                key = "targets"
            else:
                query = parse_qs(url.query)["query"][0]
                key = "gauge" if "ws_hub_active_goroutines" in query else "up"
                if query.startswith("timestamp("):
                    key += "_time"
            return json.dumps(self.observations[key])
        raise AssertionError(f"unexpected fake command: {args}")


def test_full_proof_reuses_immutable_pin_and_sanitizes_results(
    proof, replicas, observations, rendered_policy, monkeypatch
):
    fake = FakeKubernetes(replicas, observations)
    monkeypatch.setattr(proof, "_command", fake)
    monkeypatch.setattr(proof.secrets, "token_hex", lambda _: SUFFIX)
    result = proof.prove_actual_prometheus(ROOT, rendered_policy, replicas)
    assert result["verdict"] == "pass"
    assert result["source"]["name"] == f"netpol-prom-{SUFFIX}"
    assert result["source"]["namespace"] == "monitoring"
    assert {row["replica_uid"] for row in result["checks"]} == {
        r["uid"] for r in replicas
    }
    assert all(row["verdict"] == "pass" for row in result["checks"])
    text = json.dumps(result)
    assert all(replica["ip"] not in text for replica in replicas)
    assert "ws_hub_active_goroutines" not in text
    assert list(fake.created) == ["ConfigMap", "NetworkPolicy", "Pod"]
    image = fake.created["Pod"]["spec"]["containers"][0]["image"]
    assert image == proof.compose_image(ROOT, "prometheus")
    assert all(
        args[-1].startswith("http://127.0.0.1:9090/")
        for args, _ in fake.commands
        if args[:3] == ("-n", "monitoring", "exec")
    )


@pytest.mark.parametrize(
    "fault",
    [
        "target-drift",
        "source-drift",
        "wrong-image",
        "config-drift",
        "policy-drift",
        "broader-policy",
        "create-collision",
        "wrong-command",
        "wrong-mount",
        "wrong-fsgroup",
        "host-network",
        "namespace-label",
        "target-restart",
        "bad-create-identity",
        "fixture-replaced",
        "source-image-drift",
        "naive-start",
        "missing-volume",
        "wrong-volume",
    ],
)
def test_full_proof_rejects_drift_and_does_not_disclose_errors(
    proof, replicas, observations, rendered_policy, monkeypatch, fault
):
    fake = FakeKubernetes(replicas, observations, fault)
    monkeypatch.setattr(proof, "_command", fake)
    result = proof.prove_actual_prometheus(ROOT, rendered_policy, replicas)
    assert result["verdict"] == "inconclusive"
    assert set(result) == {"verdict", "stage"}
    assert "private create error" not in json.dumps(result)
    assert all(replica["ip"] not in json.dumps(result) for replica in replicas)


def test_poll_retries_transient_wget_failure_without_extending_deadline(
    proof, replicas, observations, monkeypatch
):
    docs, now = observations

    class Clock:
        elapsed = 0.0

        def monotonic(self):
            return self.elapsed

        def sleep(self, seconds):
            self.elapsed += seconds

    clock = Clock()
    calls = []

    def api(_name, path, timeout):
        calls.append((path, timeout))
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, ["kubectl"], stderr="private error")
        if path.startswith("/api/v1/targets"):
            return docs["targets"]
        query = parse_qs(urlsplit(path).query)["query"][0]
        key = "gauge" if "ws_hub_active_goroutines" in query else "up"
        if query.startswith("timestamp("):
            key += "_time"
        return docs[key]

    monkeypatch.setattr(proof, "time", clock)
    monkeypatch.setattr(proof, "_api", api)
    result = proof._poll("fixture", replicas, now - timedelta(seconds=10))
    assert len(result) == 2
    assert len(calls) == 6
    assert clock.elapsed <= proof.POLL_SECONDS


def test_poll_failure_is_bounded(proof, replicas, observations, monkeypatch):
    class Clock:
        elapsed = 0.0

        def monotonic(self):
            return self.elapsed

        def sleep(self, seconds):
            self.elapsed += seconds

    clock = Clock()
    monkeypatch.setattr(proof, "time", clock)
    monkeypatch.setattr(
        proof,
        "_api",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("private")),
    )
    with pytest.raises(TimeoutError):
        proof._poll("fixture", replicas, observations[1] - timedelta(seconds=10))
    assert clock.elapsed == proof.POLL_SECONDS


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "no-peer", "expressions", "empty-label"]
)
def test_invalid_render_returns_only_inconclusive(
    proof, replicas, rendered_policy, monkeypatch, fault
):
    if fault == "missing":
        rendered_policy.clear()
    elif fault == "duplicate":
        rendered_policy.append(copy.deepcopy(rendered_policy[0]))
    elif fault == "no-peer":
        rendered_policy[0]["spec"]["ingress"][0]["from"] = []
    elif fault == "expressions":
        selector = rendered_policy[0]["spec"]["ingress"][0]["from"][0]["podSelector"]
        selector["matchExpressions"] = [{"key": "x", "operator": "Exists"}]
    else:
        selector = rendered_policy[0]["spec"]["ingress"][0]["from"][0]["podSelector"]
        selector["matchLabels"]["app.kubernetes.io/name"] = ""
    monkeypatch.setattr(
        proof,
        "_command",
        lambda *_args, **_kwargs: pytest.fail("must not call kubectl"),
    )
    assert proof.prove_actual_prometheus(ROOT, rendered_policy, replicas) == {
        "verdict": "inconclusive",
        "stage": "input",
    }


@pytest.mark.parametrize("fault", ["image", "suffix", "label"])
def test_fixture_rejects_untrusted_image_or_ambiguous_identity(proof, replicas, fault):
    image = proof.compose_image(ROOT, "prometheus")
    suffix = SUFFIX
    labels = {"app.kubernetes.io/name": "prometheus"}
    if fault == "image":
        image = "prom/prometheus:latest"
    elif fault == "suffix":
        suffix = "not-valid"
    else:
        labels[proof.FIXTURE_LABEL] = "collision"
    with pytest.raises(ValueError):
        proof._fixture_objects(image, replicas, labels, suffix)


@pytest.mark.parametrize("response", ["[]", '"string"'])
def test_kubernetes_and_prometheus_reject_non_object_json(proof, monkeypatch, response):
    monkeypatch.setattr(proof, "_command", lambda *_args, **_kwargs: response)
    with pytest.raises(ValueError):
        proof._json_command("get", "pod")
    with pytest.raises(ValueError):
        proof._api("fixture", "/api/v1/targets", 2)


def test_kubectl_output_limit_is_enforced(proof, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="x" * (proof.MAX_OUTPUT + 1))

    monkeypatch.setattr(proof, "run_command", run)
    with pytest.raises(ValueError):
        proof._command("get", "pod", timeout=2)
    assert calls == [(["kubectl", "get", "pod"], {"stdin": None, "timeout": 2})]
    monkeypatch.setattr(
        proof, "run_command", lambda *_args, **_kwargs: SimpleNamespace(stdout="ok")
    )
    assert proof._command("get", "pod", timeout=2) == "ok"


def test_poll_stops_when_deadline_expires_between_api_calls(
    proof, replicas, observations, monkeypatch
):
    class Clock:
        def __init__(self):
            self.times = iter([0, 0, 46, 46, 46])

        def monotonic(self):
            return next(self.times)

        def sleep(self, _seconds):
            pytest.fail("no time remains for a retry")

    monkeypatch.setattr(proof, "time", Clock())
    monkeypatch.setattr(
        proof, "_api", lambda *_args, **_kwargs: pytest.fail("deadline expired")
    )
    with pytest.raises(TimeoutError):
        proof._poll("fixture", replicas, observations[1] - timedelta(seconds=10))
