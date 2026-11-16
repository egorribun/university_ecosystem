"""Offline contracts for the separate real ws-hub positive scrape phase."""

from __future__ import annotations

import copy
import errno
import http.client
import io
import json
import os
import runpy
import secrets
import socket
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/k8s"))

import networkpolicy_runtime_probe as runner
import networkpolicy_runtime_real_fp as real_fp
import networkpolicy_runtime_real_ws as ws

SHA = "a" * 40
IMAGE = f"ue-netpol-ws:{SHA}-123456abcdef"
WS_UID_1 = "11111111-1111-4111-8111-111111111111"
WS_UID_2 = "22222222-2222-4222-8222-222222222222"


@pytest.fixture(scope="module")
def rendered():
    app_contract, store_contract = runner.load_render_contracts()
    app_contract._helm()
    return runner.render_release("probe-a", app_contract, store_contract)


@pytest.fixture
def declaration(rendered):
    return ws.ws_deployment(rendered[0], IMAGE, SHA)


def values():
    shared = secrets.token_hex(32)
    return {
        "JWT_SECRET_FILE": secrets.token_hex(32),
        "WS_HUB_INTERNAL_SECRET_FILE": shared,
        "INTERNAL_AUTH_TOKEN_FILE": shared,
        "NATS_URL_FILE": "nats://fixture:4222",
        "NATS_AUTH_TOKEN_FILE": secrets.token_hex(32),
        "REDIS_URL_FILE": "redis://cache",
        "REVOCATION_REDIS_URL_FILE": "redis://revocation",
    }


def test_deployment_only_substitutes_source_bound_image_and_annotation(
    rendered, declaration
):
    original = ws.find(rendered[0], "Deployment", "probe-a-ws-hub")
    template = declaration["spec"]["template"]
    actual = template["spec"]["containers"][0]
    assert actual["image"] == IMAGE
    assert actual["imagePullPolicy"] == "Never"
    assert (
        template["metadata"]["annotations"]["university-ecosystem.io/source-sha"] == SHA
    )
    actual["image"] = original["spec"]["template"]["spec"]["containers"][0]["image"]
    actual["imagePullPolicy"] = original["spec"]["template"]["spec"]["containers"][0][
        "imagePullPolicy"
    ]
    template["metadata"]["annotations"]["university-ecosystem.io/source-sha"] = (
        original["spec"]["template"]["metadata"]["annotations"][
            "university-ecosystem.io/source-sha"
        ]
    )
    assert declaration == original


@pytest.mark.parametrize(
    "image,sha",
    [("ue-netpol-ws:other", SHA), (IMAGE, "x" * 40), (f"ue-netpol-ws:{SHA}", SHA)],
)
def test_deployment_rejects_unbound_image(rendered, image, sha):
    with pytest.raises(ValueError):
        ws.ws_deployment(rendered[0], image, sha)


@pytest.mark.parametrize(
    "name,value",
    [
        ("VITE_ENVIRONMENT", "development"),
        ("WS_HUB_METRICS_ADDR", "127.0.0.1:9108"),
        ("ENABLE_JETSTREAM", "false"),
        ("NATS_AUTH_TOKEN_FILE", ""),
        ("SPIFFE_ENABLED", "true"),
    ],
)
def test_deployment_rejects_weakened_or_unsupported_render(rendered, name, value):
    app = copy.deepcopy(rendered[0])
    container = ws.find(app, "Deployment", "probe-a-ws-hub")["spec"]["template"][
        "spec"
    ]["containers"][0]
    entry = next((entry for entry in container["env"] if entry["name"] == name), None)
    if entry is None:
        container["env"].append({"name": name, "value": value})
    else:
        entry["value"] = value
    with pytest.raises(ValueError):
        ws.ws_deployment(app, IMAGE, SHA)


def test_generated_secret_values_map_to_unchanged_rendered_mounts(declaration):
    data = values()
    objects = ws.ws_secrets(declaration, data)
    docs = {item["metadata"]["name"]: item["stringData"] for item in objects}
    assert docs["university-application"] == {
        "jwt-secret": data["JWT_SECRET_FILE"],
        "ws-hub-internal-secret": data["WS_HUB_INTERNAL_SECRET_FILE"],
    }
    assert docs["university-connections"] == {
        "nats-url": "nats://fixture:4222",
        "nats-auth-token": data["NATS_AUTH_TOKEN_FILE"],
        "redis-backend-url": "redis://cache",
        "redis-revocation-url": "redis://revocation",
    }


def test_secret_mapping_ignores_unrelated_nonsecret_volumes(declaration):
    declaration["spec"]["template"]["spec"]["volumes"].append(
        {"name": "public-config", "configMap": {"name": "public"}}
    )
    assert len(ws.ws_secrets(declaration, values())) == 2


@pytest.mark.parametrize("fault", ["missing", "empty", "conflict", "extra"])
def test_secret_mapping_fails_closed(declaration, fault):
    data = values()
    if fault == "missing":
        del data["NATS_URL_FILE"]
    elif fault == "empty":
        data["NATS_AUTH_TOKEN_FILE"] = ""
    elif fault == "conflict":
        data["INTERNAL_AUTH_TOKEN_FILE"] = "different"
    else:
        data["EXTRA"] = "extra"
    with pytest.raises(ValueError):
        ws.ws_secrets(declaration, data)


def test_cache_and_nats_fixtures_use_existing_policies_and_private_credentials(
    rendered,
):
    app, store = rendered
    original = copy.deepcopy(rendered)
    cache = ws.cache_fixture(app, store, "cache-password")
    statefulset = next(item for item in cache if item["kind"] == "StatefulSet")
    spec = statefulset["spec"]["template"]["spec"]
    assert [item["name"] for item in spec["containers"]] == ["redis"]
    assert [item["name"] for item in spec["initContainers"]] == ["redis-auth-acl"]
    assert all(
        "@sha256:" in item["image"]
        for item in [*spec["containers"], *spec["initContainers"]]
    )
    assert all(item["kind"] != "NetworkPolicy" for item in cache)
    assert "cache-password" not in json.dumps(statefulset)
    nats = ws.nats_fixture(ROOT, runner.runtime_base_image(), "private-token")
    pod = next(item for item in nats if item["kind"] == "Pod")
    assert pod["metadata"]["labels"]["app.kubernetes.io/instance"] == "probe-a"
    assert pod["metadata"]["labels"]["app.kubernetes.io/name"] == "nats"
    assert "private-token" not in json.dumps(pod)
    config = json.loads(nats[0]["stringData"]["nats.conf"])
    assert config["authorization"] == {"token": "private-token"}
    assert rendered == original


def test_cache_refuses_unpinned_image(rendered):
    app, store = copy.deepcopy(rendered)
    redis = ws.find(store, "StatefulSet", "probe-a-revocation-redis-master")
    redis["spec"]["template"]["spec"]["containers"][0]["image"] = "redis:latest"
    with pytest.raises(ValueError):
        ws.cache_fixture(app, store, "credential")


def cluster_docs(declaration):
    labels = declaration["spec"]["template"]["metadata"]["labels"]
    deployment = {"metadata": {"uid": "deployment-uid"}}
    sets = {
        "items": [
            {
                "metadata": {
                    "uid": "set-uid",
                    "ownerReferences": [
                        {
                            "controller": True,
                            "kind": "Deployment",
                            "uid": "deployment-uid",
                        }
                    ],
                }
            }
        ]
    }
    pod = {
        "metadata": {
            "name": "ws-real-1",
            "uid": "real-uid",
            "labels": labels,
            "annotations": {"university-ecosystem.io/source-sha": SHA},
            "ownerReferences": [
                {"controller": True, "kind": "ReplicaSet", "uid": "set-uid"}
            ],
        },
        "spec": {
            "containers": [
                {"name": "ws-hub", "image": IMAGE, "imagePullPolicy": "Never"}
            ]
        },
        "status": {
            "podIP": "10.1.2.3",
            "containerStatuses": [
                {
                    "name": "ws-hub",
                    "ready": True,
                    "containerID": "containerd://abc",
                    "imageID": "sha256:abc",
                    "restartCount": 0,
                }
            ],
        },
    }
    pod2 = copy.deepcopy(pod)
    pod2["metadata"]["name"] = "ws-real-2"
    pod2["metadata"]["uid"] = "real-uid-2"
    pod2["status"]["podIP"] = "10.1.2.4"
    standin = {"metadata": {"name": "stand-in", "ownerReferences": []}}
    return deployment, sets, {"items": [standin, pod, pod2]}


def test_replica_inventory_requires_owned_ready_source_bound_containers(
    declaration, monkeypatch
):
    docs = cluster_docs(declaration)
    monkeypatch.setattr(ws, "kubectl_json", Mock(side_effect=docs))
    found = ws.replicas(declaration, IMAGE, SHA)
    assert [row["uid"] for row in found] == ["real-uid", "real-uid-2"]
    assert all(row["container_id"] and row["image_id"] for row in found)


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "image",
        "pull",
        "sha",
        "ready",
        "container_id",
        "image_id",
        "address",
        "ipv6",
    ],
)
def test_replica_inventory_fails_closed(declaration, monkeypatch, fault):
    deployment, sets, pods = cluster_docs(declaration)
    pod = pods["items"][1]
    if fault == "owner":
        sets["items"][0]["metadata"]["ownerReferences"] = []
    elif fault == "image":
        pod["spec"]["containers"][0]["image"] = "different"
    elif fault == "pull":
        pod["spec"]["containers"][0]["imagePullPolicy"] = "Always"
    elif fault == "sha":
        pod["metadata"]["annotations"] = {}
    elif fault == "ready":
        pod["status"]["containerStatuses"][0]["ready"] = False
    elif fault == "address":
        pod["status"]["podIP"] = "not-an-ip"
    elif fault == "ipv6":
        pod["status"]["podIP"] = "2001:db8::1"
    else:
        key = {"container_id": "containerID", "image_id": "imageID"}[fault]
        pod["status"]["containerStatuses"][0][key] = ""
    monkeypatch.setattr(ws, "kubectl_json", Mock(side_effect=[deployment, sets, pods]))
    with pytest.raises(ValueError):
        ws.replicas(declaration, IMAGE, SHA)


@pytest.mark.parametrize(
    "fault", [None, "source", "uid", "namespace_label", "pod_label", "no_grant"]
)
def test_monitoring_source_must_match_policy_and_original_pod(
    rendered, monkeypatch, fault
):
    app = copy.deepcopy(rendered[0])
    source = ws.Pod("monitoring", "prometheus-0", uid="source-uid")
    namespace = {"metadata": {"labels": {"kubernetes.io/metadata.name": "monitoring"}}}
    pod = {
        "metadata": {
            "uid": "source-uid",
            "labels": {"app.kubernetes.io/name": "prometheus"},
        }
    }
    if fault == "source":
        source.name = "other"
    elif fault == "uid":
        pod["metadata"]["uid"] = "other"
    elif fault == "namespace_label":
        namespace["metadata"]["labels"] = {}
    elif fault == "pod_label":
        pod["metadata"]["labels"] = {}
    elif fault == "no_grant":
        ws.find(app, "NetworkPolicy", "probe-a-ws-hub-policy")["spec"]["ingress"] = []
    monkeypatch.setattr(ws, "kubectl_json", Mock(side_effect=[namespace, pod]))
    if fault is None:
        ws.authorized_source(app, source)
    else:
        with pytest.raises(ValueError):
            ws.authorized_source(app, source)


@pytest.mark.parametrize(
    "status,content_type,body,expected",
    [
        (
            200,
            "text/plain; version=0.0.4",
            b"# TYPE ws_hub_active_goroutines gauge\nws_hub_active_goroutines 4\n",
            "valid-exposition",
        ),
        (200, "text/plain", b"stand-in reply", "invalid-exposition"),
        (
            500,
            "text/plain",
            b"# TYPE ws_hub_active_goroutines gauge\nws_hub_active_goroutines 4\n",
            "invalid-exposition",
        ),
        (
            200,
            "application/json",
            b"# TYPE ws_hub_active_goroutines gauge\nws_hub_active_goroutines 4\n",
            "invalid-exposition",
        ),
        (200, "text/plain", b"x" * 2000001, "invalid-exposition"),
    ],
    ids=["valid", "standin", "status", "content-type", "oversize"],
)
def test_scrape_checks_real_gauge_without_returning_body(
    monkeypatch, capsys, tmp_path, status, content_type, body, expected
):
    response = Mock(status=status)
    response.read.return_value = body
    response.getheader.return_value = content_type
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(http.client, "HTTPConnection", Mock(return_value=connection))
    monkeypatch.setattr(sys, "argv", ["probe", "10.1.2.3"])
    program = tmp_path / "scrape.py"
    program.write_text(ws.SCRAPE, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": expected}
    connection.request.assert_called_once_with(
        "GET", "/metrics", headers={"Accept": "text/plain; version=0.0.4"}
    )


def test_authenticated_stream_setup_only_creates_empty_streams(
    monkeypatch, capsys, tmp_path
):
    stream_names = ["CHAT_EVENTS", "NOTIFICATIONS_EVENTS", "CACHE_INVALIDATIONS"]
    subjects = [["chat.*"], ["notifications.*"], ["cache.invalidate", "cache.revoke"]]
    responses = []
    for item in subjects:
        payload = json.dumps({"config": {"subjects": item}}).encode()
        responses.append(
            b"MSG _INBOX.netpolws 1 "
            + str(len(payload)).encode()
            + b"\r\n"
            + payload
            + b"\r\n"
        )
    stream = io.BytesIO(b"INFO {}\r\n" + b"".join(responses))
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.makefile.return_value = stream
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    monkeypatch.setattr(Path, "read_text", lambda self: "private-token")
    program = tmp_path / "streams.py"
    program.write_text(ws.NATS_STREAMS, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": "ready"}
    sent = b"".join(call.args[0] for call in connection.sendall.call_args_list)
    assert b"auth_token" in sent
    assert all(
        ("$JS.API.STREAM.CREATE." + name).encode() in sent for name in stream_names
    )
    assert b"PUB chat." not in sent and b"PUB cache." not in sent


@pytest.mark.parametrize(
    "keys,expected",
    [
        ([{"kty": "RSA", "kid": "key", "n": "modulus", "e": "AQAB"}], "valid"),
        ([], "invalid"),
        ([{"kty": "EC", "kid": "key"}], "invalid"),
    ],
)
def test_existing_jwks_check_only_returns_classification(
    monkeypatch, capsys, tmp_path, keys, expected
):
    program = tmp_path / "jwks-check.py"
    program.write_text(ws.VERIFY_JWKS, encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda self: json.dumps({"keys": keys}))
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": expected}


def install_phase_fakes(monkeypatch, rendered, declaration):
    pods = {
        "a-backend": ws.Pod("probe-a", "backend", uid="backend"),
        "prometheus": ws.Pod("monitoring", "prometheus-0", uid="source"),
        "a-ws": ws.Pod("probe-a", "probe-a-ws-hub", uid="fixture"),
        "ingress": ws.Pod("ingress-nginx", "ingress-controller", uid="edge-source"),
    }
    copies = [
        {
            "name": "ws-1",
            "uid": WS_UID_1,
            "ip": "10.1.2.3",
            "container_id": "containerd://a",
            "image_id": "sha256:a",
            "restarts": 0,
        },
        {
            "name": "ws-2",
            "uid": WS_UID_2,
            "ip": "10.1.2.4",
            "container_id": "containerd://b",
            "image_id": "sha256:b",
            "restarts": 0,
        },
    ]
    mocks = {
        "ws_deployment": Mock(return_value=declaration),
        "cache_fixture": Mock(return_value=[]),
        "nats_fixture": Mock(return_value=[]),
        "ws_secrets": Mock(return_value=[]),
        "apply_objects": Mock(),
        "kubectl": Mock(),
        "run_command": Mock(return_value=SimpleNamespace(stdout='{"result":"ready"}')),
        "replicas": Mock(
            side_effect=[
                copies,
                copy.deepcopy(copies),
                copy.deepcopy(copies),
                copy.deepcopy(copies),
            ]
        ),
        "authorized_source": Mock(),
        "retire_ws_fixture": Mock(),
        "prove_ws_service": Mock(
            return_value={"verdict": "pass", "service_uid": "service-uid"}
        ),
        "prove_restricted_scrapes": Mock(
            return_value=[
                {
                    "source": source,
                    "source_uid": f"{source}-uid",
                    "replica_uid": replica["uid"],
                    "verdict": "pass",
                }
                for source in ws.RESTRICTED_SCRAPE_SOURCES
                for replica in copies
            ]
        ),
        "run_in_pod": Mock(
            side_effect=[
                {"result": "valid"},
                {"result": "valid-exposition"},
                {"result": "valid-exposition"},
            ]
        ),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(ws, name, mock)
    prometheus = Mock(
        return_value={
            "verdict": "pass",
            "source": {
                "namespace": "monitoring",
                "name": "netpol-prom-123456abcdef",
                "uid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "image_id": "sha256:" + "a" * 64,
                "container_id": "containerd://" + "b" * 64,
            },
            "checks": [
                {"replica_uid": replica["uid"], "verdict": "pass"} for replica in copies
            ],
        }
    )
    monkeypatch.setitem(
        sys.modules,
        "networkpolicy_runtime_real_prometheus",
        SimpleNamespace(prove_actual_prometheus=prometheus),
    )
    mocks["prove_actual_prometheus"] = prometheus
    return {"probe-a": rendered}, pods, copies, mocks


def run_phase(rendered, pods):
    return ws.actual_ws_phase(
        ROOT,
        rendered,
        pods,
        {"probe-a": "revocation-password"},
        python_image="python-fixture",
        image=IMAGE,
        source_sha=SHA,
    )


def test_phase_scrapes_each_unchanged_replica_and_does_not_emit_private_details(
    rendered, declaration, monkeypatch
):
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    result = run_phase(tree, pods)
    assert result["verdict"] == "pass"
    assert result["source_sha"] == SHA
    assert result["source"] == "Prometheus-labelled Python probe"
    assert [check["replica_uid"] for check in result["checks"]] == [
        row["uid"] for row in copies
    ]
    assert mocks["authorized_source"].call_count == 4
    mocks["retire_ws_fixture"].assert_called_once_with(
        rendered[0], pods["a-ws"], "python-fixture"
    )
    call = mocks["prove_ws_service"].call_args
    assert mocks["prove_ws_service"].call_count == 1
    assert call.args == (rendered[0], declaration, copies, pods["ingress"])
    assert call.kwargs == {"progress": {"stage": "replica-recheck"}}
    assert result["service"] == {"verdict": "pass", "service_uid": "service-uid"}
    assert result["python_scrape"] == {
        "verdict": "pass",
        "source": "Prometheus-labelled Python probe",
    }
    source = result["prometheus"]["source"]
    assert source == {
        "namespace": "monitoring",
        "name": "netpol-prom-123456abcdef",
        "uid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    }
    assert (
        result["prometheus"]["checks"]
        == mocks["prove_actual_prometheus"].return_value["checks"]
    )
    assert "image_id" not in source and "container_id" not in source
    mocks["prove_actual_prometheus"].assert_called_once_with(ROOT, rendered[0], copies)
    assert mocks["replicas"].call_count == 4
    assert mocks["run_in_pod"].call_args_list[0].args[:2] == (
        pods["a-backend"],
        ws.VERIFY_JWKS,
    )
    assert all(
        call.args[1] == ws.SCRAPE for call in mocks["run_in_pod"].call_args_list[1:]
    )
    credentials = mocks["ws_secrets"].call_args.args[1]
    assert credentials["REDIS_URL_FILE"] != credentials["REVOCATION_REDIS_URL_FILE"]
    assert credentials["NATS_AUTH_TOKEN_FILE"]
    assert "revocation-password" not in json.dumps(result)
    assert "10.1.2." not in json.dumps(result)


def test_phase_rejects_jwks_target_drift_before_creating_fixtures(
    rendered, declaration, monkeypatch
):
    tree, pods, _, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    env = declaration["spec"]["template"]["spec"]["containers"][0]["env"]
    next(item for item in env if item["name"] == "JWKS_URL")["value"] = (
        "http://other:8000/.well-known/jwks.json"
    )
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive" and result["stage"] == "render"
    mocks["apply_objects"].assert_not_called()


@pytest.mark.parametrize(
    "fault",
    [
        "inconclusive",
        "exception",
        "missing-check",
        "wrong-uid",
        "bad-source",
        "not-pass",
        "source-type",
        "source-value",
        "image-id",
        "container-id",
        "invalid-check",
        "extra-field",
        "source-drift",
        "replica-drift",
    ],
)
def test_real_prometheus_is_required_and_prior_positive_evidence_is_retained(
    rendered, declaration, monkeypatch, fault
):
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    helper = mocks["prove_actual_prometheus"]
    if fault == "inconclusive":
        helper.return_value = {"verdict": "inconclusive", "stage": "helper-stage"}
    elif fault == "exception":
        helper.side_effect = ValueError("private exception data")
    elif fault == "missing-check":
        helper.return_value["checks"].pop()
    elif fault == "wrong-uid":
        helper.return_value["checks"][0]["replica_uid"] = "wrong"
    elif fault == "bad-source":
        helper.return_value["source"]["namespace"] = "unrelated"
    elif fault == "not-pass":
        helper.return_value["verdict"] = "inconclusive"
    elif fault == "source-type":
        helper.return_value["source"]["uid"] = None
    elif fault == "source-value":
        helper.return_value["source"]["uid"] = "invalid\nvalue"
    elif fault == "image-id":
        helper.return_value["source"]["image_id"] = "not-an-image-id"
    elif fault == "container-id":
        helper.return_value["source"]["container_id"] = "not-a-container-id"
    elif fault == "invalid-check":
        helper.return_value["checks"][0]["replica_uid"] = None
    elif fault == "extra-field":
        helper.return_value["checks"][0]["raw"] = "private endpoint response"
    elif fault == "source-drift":
        mocks["authorized_source"].side_effect = [
            None,
            None,
            None,
            ValueError("private exception data"),
        ]
    else:
        altered = copy.deepcopy(copies)
        altered[0]["restarts"] = 1
        mocks["replicas"].side_effect = [copies, copies, copies, altered]
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    assert result["stage"] == "real-prometheus"
    assert result["prometheus"] == {"verdict": "inconclusive"}
    assert result["python_scrape"]["verdict"] == "pass"
    assert result["service"]["verdict"] == "pass"
    assert all(check["verdict"] == "pass" for check in result["checks"])
    assert "private" not in json.dumps(result)
    assert "10.1.2." not in json.dumps(result)


@pytest.mark.parametrize(
    "stage",
    [
        "input",
        "targets-before",
        "create-config",
        "create-policy",
        "create-pod",
        "pod-ready",
        "source-before",
        "scrape",
        "source-after",
        "targets-after",
        "private diagnostic",
    ],
)
def test_prometheus_failure_stage_is_only_recorded_from_the_fixed_enum(
    rendered, declaration, monkeypatch, stage
):
    tree, pods, _, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    mocks["prove_actual_prometheus"].return_value = {
        "verdict": "inconclusive",
        "stage": stage,
    }
    result = run_phase(tree, pods)
    expected = {"verdict": "inconclusive"}
    if stage in ws.PROMETHEUS_FAILURE_STAGES:
        expected["stage"] = stage
    assert result["prometheus"] == expected
    assert "private diagnostic" not in json.dumps(result)


@pytest.mark.parametrize(
    "fault,stage",
    [
        ("cache_fixture", "cache-redis"),
        ("nats_fixture", "nats"),
        ("nats_result", "nats"),
        ("jwks", "jwks"),
        ("ws_secrets", "deployment"),
        ("replicas", "replicas"),
        ("authorized_source", "authorized-scrape"),
        ("scrape", "authorized-scrape"),
        ("changed_replica", "authorized-scrape"),
        ("retire_ws_fixture", "retire-fixture"),
        ("prove_ws_service", "service-health"),
        ("service_replica", "service-health"),
    ],
)
def test_phase_failures_cannot_pass_or_expose_exception_payload(
    rendered, declaration, monkeypatch, fault, stage
):
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    if fault in {
        "cache_fixture",
        "nats_fixture",
        "ws_secrets",
        "replicas",
        "authorized_source",
        "retire_ws_fixture",
        "prove_ws_service",
    }:
        mocks[fault].side_effect = ValueError("private exception data")
    elif fault == "nats_result":
        mocks["run_command"].return_value.stdout = '{"result":"failed"}'
    elif fault == "jwks":
        mocks["run_in_pod"].side_effect = [{"result": "invalid"}]
    elif fault == "scrape":
        mocks["run_in_pod"].side_effect = [
            {"result": "valid"},
            {"result": "exec-error"},
            {"result": "valid-exposition"},
        ]
    else:
        altered = copy.deepcopy(copies)
        altered[0]["restarts"] = 1
        mocks["replicas"].side_effect = (
            [copies, copies, altered]
            if fault == "service_replica"
            else [copies, altered]
        )
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    if fault != "scrape":
        assert result["stage"] == stage
    if fault == "prove_ws_service":
        assert result["substage"] == "service-start"
    if fault == "service_replica":
        assert result["substage"] == "replica-recheck"
        assert "service" not in result
    assert "private exception data" not in json.dumps(result)
    assert "revocation-password" not in json.dumps(result)
    if fault not in {"retire_ws_fixture", "prove_ws_service", "service_replica"}:
        mocks["retire_ws_fixture"].assert_not_called()


@pytest.mark.parametrize(
    "substage",
    [
        "source-before",
        "create-service",
        "endpoints-before",
        "source-pre-health",
        "health-request",
        "source-post-health",
        "endpoints-after",
        "replica-recheck",
    ],
)
def test_service_failure_receipt_reports_only_fixed_substage(
    rendered, declaration, monkeypatch, substage
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    prove = ws.prove_ws_service
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    mocks["prove_ws_service"].side_effect = prove
    failure = ValueError("private exception data")
    source = {"uid": "source", "container_id": "container", "restarts": 0}
    source_results = [source, source, source]
    source_fault = {
        "source-before": 0,
        "source-pre-health": 1,
        "source-post-health": 2,
    }
    if substage in source_fault:
        source_results[source_fault[substage]] = failure
    monkeypatch.setattr(
        ws, "authorized_ingress_source", Mock(side_effect=source_results)
    )
    create = Mock(return_value={"uid": "service", "cluster_ip": "10.96.0.42"})
    if substage == "create-service":
        create.side_effect = failure
    monkeypatch.setattr(ws, "create_ws_service", create)
    snapshot = {"service_uid": "service", "slice_uids": ["slice"]}
    snapshots = [snapshot, snapshot]
    if substage in {"endpoints-before", "endpoints-after"}:
        snapshots[0 if substage == "endpoints-before" else 1] = failure
    monkeypatch.setattr(ws, "ws_service_snapshot", Mock(side_effect=snapshots))
    mocks["run_in_pod"].side_effect = [
        {"result": "valid"},
        {"result": "valid-exposition"},
        {"result": "valid-exposition"},
        failure if substage == "health-request" else {"result": "healthy"},
    ]
    if substage == "replica-recheck":
        altered = copy.deepcopy(copies)
        altered[0]["restarts"] = 1
        mocks["replicas"].side_effect = [copies, copies, altered]

    result = run_phase(tree, pods)

    assert result["verdict"] == "inconclusive"
    assert result["stage"] == "service-health"
    assert result["substage"] == substage
    assert "private exception data" not in json.dumps(result)
    assert "10.96.0.42" not in json.dumps(result)


@pytest.mark.parametrize(
    "fault,expected", [("verdict", "service-verdict"), ("invalid", "service-unknown")]
)
def test_service_failure_substage_is_allowlisted(
    rendered, declaration, monkeypatch, fault, expected
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    tree, pods, _, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    if fault == "verdict":
        mocks["prove_ws_service"].return_value = {"verdict": "inconclusive"}
    else:

        def fail(*args, progress):
            progress["stage"] = "private exception data"
            raise ValueError("private exception data")

        mocks["prove_ws_service"].side_effect = fail
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    assert result["stage"] == "service-health"
    assert result["substage"] == expected
    assert "private exception data" not in json.dumps(result)


def runner_fixture(monkeypatch, tmp_path, fp_result, ws_result, interrupt=False):
    args = SimpleNamespace(
        receipt=tmp_path / "receipt.json",
        kubernetes_version="fixture",
        node_image="fixture",
        calico_sha256="fixture",
        real_processor_image="fp",
        diagnostic_image="diagnostic",
        real_ws_image=IMAGE,
        source_sha=SHA,
    )
    pods = {
        key: ws.Pod("probe-a", key, ip="127.0.0.1", uid=key)
        for key in ["a-fp", "a-redis", "b-redis"]
    }
    rows = [{"probe_id": str(i), "verdict": "pass"} for i in range(40)]
    replacements = {
        "runtime_base_image": "fixture",
        "render_all": {},
        "set_up_cluster": pods,
        "cluster_ip": "127.0.0.1",
        "build_targets": {},
        "make_executor": None,
        "measure_baseline": {},
        "redis_ping": {"result": "redis-pong"},
        "apply_policies": [],
        "evaluate_rows": rows,
        "resolver_status": {"verdict": "pass"},
        "run_app_checks": {"fixture": {"verdict": "pass"}},
        "policy_summary": [],
    }
    monkeypatch.setattr(runner.argparse.ArgumentParser, "parse_args", lambda self: args)
    for name, value in replacements.items():
        monkeypatch.setattr(runner, name, Mock(return_value=value))
    fp = Mock(return_value={"verdict": fp_result})
    monkeypatch.setattr(real_fp, "actual_processor_phase", fp)
    ws_receipt = {"verdict": ws_result}
    if ws_result == "pass":
        ws_receipt.update(
            {
                "python_scrape": {"verdict": "pass"},
                "replicas": [{"uid": WS_UID_1}, {"uid": WS_UID_2}],
                "prometheus": {
                    "verdict": "pass",
                    "source": {
                        "namespace": "monitoring",
                        "name": "netpol-prom-123456abcdef",
                        "uid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    },
                    "checks": [
                        {"replica_uid": WS_UID_1, "verdict": "pass"},
                        {"replica_uid": WS_UID_2, "verdict": "pass"},
                    ],
                },
            }
        )
    phase = Mock(return_value=ws_receipt)
    if interrupt:

        def interrupted(*_args, **_kwargs):
            receipt = json.loads(args.receipt.read_text())
            assert receipt["verdict"] == "inconclusive"
            assert receipt["real_processor"]["verdict"] == "pass"
            assert receipt["real_ws_hub"]["verdict"] == "in_progress"
            assert receipt["finished_utc"] is None
            raise KeyboardInterrupt

        phase.side_effect = interrupted
    monkeypatch.setattr(ws, "actual_ws_phase", phase)
    return args, phase


@pytest.mark.parametrize(
    "fp_result,ws_result,expected",
    [
        ("pass", "pass", "pass"),
        ("pass", "inconclusive", "fail"),
        ("inconclusive", "pass", "fail"),
    ],
)
def test_runner_preserves_matrix_and_distinguishes_actual_phase(
    monkeypatch, tmp_path, fp_result, ws_result, expected
):
    args, phase = runner_fixture(monkeypatch, tmp_path, fp_result, ws_result)
    assert runner.main() == (0 if expected == "pass" else 1)
    assert runner.set_up_cluster.call_args.kwargs == {"own_ws": True}
    receipt = json.loads(args.receipt.read_text())
    assert receipt["verdict"] == expected
    assert receipt["matrix_verdict"] == "pass" and len(receipt["probes"]) == 40
    assert receipt["real_processor"]["verdict"] == fp_result
    assert receipt["real_ws_hub"]["verdict"] == (
        ws_result if fp_result == "pass" else "not_run"
    )
    assert phase.called == (fp_result == "pass")
    outstanding = {item["check"] for item in receipt["not_run"]}
    assert "actual ws-hub restricted peers" in outstanding
    assert ("actual Prometheus server" in outstanding) == (expected != "pass")
    assert "actual ingress controller and public HTTP route" in outstanding
    assert ("metrics exposition content" in outstanding) == (expected != "pass")


def test_runner_retains_earlier_evidence_after_inconclusive_real_prometheus(
    monkeypatch, tmp_path
):
    args, phase = runner_fixture(monkeypatch, tmp_path, "pass", "inconclusive")
    phase.return_value = {
        "verdict": "inconclusive",
        "stage": "real-prometheus",
        "python_scrape": {"verdict": "pass"},
        "service": {"verdict": "pass"},
        "prometheus": {"verdict": "inconclusive"},
    }
    assert runner.main() == 1
    receipt = json.loads(args.receipt.read_text())
    outstanding = {item["check"] for item in receipt["not_run"]}
    assert "metrics exposition content" not in outstanding
    assert {
        "actual Prometheus server",
        "actual ws-hub restricted peers",
        "actual ingress controller and public HTTP route",
    } <= outstanding
    assert receipt["real_ws_hub"]["service"]["verdict"] == "pass"


@pytest.mark.parametrize("prometheus", [None, {"verdict": "inconclusive"}])
def test_runner_downgrades_pass_without_real_prometheus_evidence(
    monkeypatch, tmp_path, prometheus
):
    args, phase = runner_fixture(monkeypatch, tmp_path, "pass", "pass")
    phase.return_value["prometheus"] = prometheus
    assert runner.main() == 1
    receipt = json.loads(args.receipt.read_text())
    assert receipt["real_ws_hub"]["verdict"] == "inconclusive"
    assert receipt["real_ws_hub"]["stage"] == "real-prometheus"
    assert "actual Prometheus server" in {item["check"] for item in receipt["not_run"]}


@pytest.mark.parametrize(
    "fault",
    [
        "missing-source",
        "missing-row",
        "wrong-uid",
        "extra-source",
        "missing-replicas",
        "duplicate-replicas",
    ],
)
def test_runner_rejects_malformed_pass_projections(monkeypatch, tmp_path, fault):
    args, phase = runner_fixture(monkeypatch, tmp_path, "pass", "pass")
    result = phase.return_value
    if fault == "missing-source":
        del result["prometheus"]["source"]
    elif fault == "missing-row":
        result["prometheus"]["checks"].pop()
    elif fault == "wrong-uid":
        result["prometheus"]["checks"][0]["replica_uid"] = "other"
    elif fault == "extra-source":
        result["prometheus"]["source"]["image_id"] = "unexpected"
    elif fault == "missing-replicas":
        del result["replicas"]
    else:
        result["replicas"][1]["uid"] = WS_UID_1
        result["prometheus"]["checks"][1]["replica_uid"] = WS_UID_1
    assert runner.main() == 1
    receipt = json.loads(args.receipt.read_text())
    assert receipt["real_ws_hub"]["verdict"] == "inconclusive"
    assert "actual Prometheus server" in {item["check"] for item in receipt["not_run"]}


def test_prometheus_test_path_matches_the_workflow_catalog():
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/k8s-networkpolicy-runtime.yml").read_text()
    )
    guard = workflow[True]["pull_request"]
    assert "tests/test_networkpolicy_runtime_real_prometheus.py" in guard["paths"]
    assert "docker-compose.full.yml" in guard["paths"]
    catalog = json.loads((ROOT / "quality/ci-check-catalog.json").read_text())
    item = next(
        row
        for row in catalog["workflows"]
        if row["path"] == ".github/workflows/k8s-networkpolicy-runtime.yml"
    )
    assert (
        json.loads(
            next(
                event["guard"]
                for event in item["events"]
                if event["event"] == "pull_request"
            )
        )
        == guard
    )


def test_interrupted_ws_phase_preserves_nonpositive_checkpoint(monkeypatch, tmp_path):
    args, _ = runner_fixture(monkeypatch, tmp_path, "pass", "pass", interrupt=True)
    with pytest.raises(KeyboardInterrupt):
        runner.main()
    assert args.receipt.exists()
    assert not args.receipt.with_suffix(".tmp").exists()


def test_interrupted_processor_does_not_claim_ws_was_unrequested(monkeypatch, tmp_path):
    args, _ = runner_fixture(monkeypatch, tmp_path, "pass", "pass")

    def interrupted(*_args, **_kwargs):
        receipt = json.loads(args.receipt.read_text())
        assert receipt["real_ws_hub"] == {
            "verdict": "not_run",
            "reason": "awaiting successful real-processor phase",
        }
        raise KeyboardInterrupt

    monkeypatch.setattr(real_fp, "actual_processor_phase", interrupted)
    with pytest.raises(KeyboardInterrupt):
        runner.main()


def test_runner_rejects_ws_without_source_bound_processor(monkeypatch, tmp_path):
    args, _ = runner_fixture(monkeypatch, tmp_path, "pass", "pass")
    args.real_processor_image = None
    args.diagnostic_image = None
    args.source_sha = None
    with pytest.raises(SystemExit):
        runner.main()
    assert not args.receipt.exists()


def _require_native_bash() -> Path:
    bash = (
        Path("C:/Program Files/Git/bin/bash.exe")
        if os.name == "nt"
        else Path("/bin/bash")
    )
    if not bash.is_file():
        pytest.fail(
            f"native Bash is required for shell contracts: {bash}", pytrace=False
        )
    return bash


@pytest.mark.parametrize("include_ws", [False, True])
def test_source_archive_build_adds_only_requested_ws_image(
    monkeypatch, tmp_path, include_ws
):
    bash = _require_native_bash()
    archive = tmp_path / "fixture.tar"
    with tarfile.open(archive, "w") as handle:
        for name, data in [
            (
                "services/file-processor/Dockerfile",
                b"FROM scratch AS builder\nFROM scratch AS health-probe\n",
            ),
            ("services/ws-hub/Dockerfile", b"FROM scratch AS builder\n"),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            handle.addfile(info, io.BytesIO(data))
    work, archive_path = tmp_path.as_posix(), archive.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
        archive_path = "/" + archive_path[0].lower() + archive_path[2:]
    monkeypatch.setenv("WORK_DIR", work)
    monkeypatch.setenv("FIXTURE_ARCHIVE", archive_path)
    monkeypatch.setenv("UE_NETPOL_REAL_FP", "1")
    monkeypatch.setenv("UE_NETPOL_REAL_WS", "1" if include_ws else "0")
    monkeypatch.setenv("SOURCE_FIXTURE", SHA)
    proof = (ROOT / "scripts/k8s/networkpolicy_runtime_proof.sh").read_text()
    builder = proof[
        proof.index("build_real_processor_images() {") : proof.index(
            "load_real_processor_images() {"
        )
    ]
    shim = r"""
set -euo pipefail
ROOT_DIR="$WORK_DIR"
RUN_SUFFIX=123456abcdef
WS_IMAGE_CREATED=0
require_clean_source() { :; }
git() { if [[ "$*" == *rev-parse* ]]; then printf '%s' "$SOURCE_FIXTURE"; else cat "$FIXTURE_ARCHIVE"; fi; }
docker() { printf '%s\n' "$*" >> "$WORK_DIR/builds"; }
uv() { printf 'python:fixture'; }
"""
    result = ws.run_command(
        [str(bash), "-s"],
        stdin=shim
        + builder
        + '\nbuild_real_processor_images\nprintf "%s" "$WS_IMAGE_CREATED"\n',
        timeout=20,
    )
    calls = (tmp_path / "builds").read_text().splitlines()
    assert len(calls) == (3 if include_ws else 2)
    assert ("services/ws-hub/Dockerfile" in calls[-1]) == include_ws
    assert (IMAGE in calls[-1]) == include_ws
    assert result.stdout == ("1" if include_ws else "0")


@pytest.mark.parametrize(
    "include_ws,bad_ws", [(False, False), (True, False), (True, True)]
)
def test_image_loader_verifies_every_owned_tag_without_docker(
    monkeypatch, tmp_path, include_ws, bad_ws
):
    bash = _require_native_bash()
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    monkeypatch.setenv("WORK_DIR", work)
    monkeypatch.setenv("TEST_PYTHON", sys.executable)
    monkeypatch.setenv("TEST_BAD_WS", "1" if bad_ws else "0")
    monkeypatch.setenv("UE_NETPOL_REAL_WS", "1" if include_ws else "0")
    proof = (ROOT / "scripts/k8s/networkpolicy_runtime_proof.sh").read_text()
    loader = proof[
        proof.index("load_real_processor_images() {") : proof.index("main() {")
    ]
    shim = r"""
set -euo pipefail
CLUSTER_NAME=fixture
FP_IMAGE=ue-netpol-fp:fixture
DIAGNOSTIC_IMAGE=ue-netpol-diagnostic:fixture
WS_IMAGE=ue-netpol-ws:fixture
IMAGE_ID="sha256:$(printf 'a%.0s' {1..64})"
docker() {
  printf '%s\n' "$*" >> "$WORK_DIR/calls"
  case "$1 $2" in
    'save --output') printf fixture > "$3" ;;
    'exec -i') [[ "$(cat)" == fixture ]] ;;
    'image inspect') printf '%s' "$IMAGE_ID" ;;
    'exec fixture-control-plane')
      if [[ "$4" == images ]]; then
        printf '{"images":[{"id":"%s","repoTags":["docker.io/library/%s","docker.io/library/%s","docker.io/library/%s"]}]}' "$IMAGE_ID" "$FP_IMAGE" "$DIAGNOSTIC_IMAGE" "$WS_IMAGE"
      elif [[ "$TEST_BAD_WS" == 1 && "$7" == "$WS_IMAGE" ]]; then
        printf '{"status":{"id":"wrong"}}'
      else printf '{"status":{"id":"%s"}}' "$IMAGE_ID"; fi ;;
    *) return 1 ;;
  esac
}
uv() { "$TEST_PYTHON" "${@:4}"; }
"""
    if bad_ws:
        with pytest.raises(subprocess.CalledProcessError):
            ws.run_command(
                [str(bash), "-s"],
                stdin=shim + loader + "\nload_real_processor_images\n",
                timeout=20,
            )
    else:
        ws.run_command(
            [str(bash), "-s"],
            stdin=shim + loader + "\nload_real_processor_images\n",
            timeout=20,
        )
    calls = (tmp_path / "calls").read_text()
    assert calls.count("crictl inspecti --output json") == (3 if include_ws else 2)
    assert (
        "image inspect --format {{.Id}} ue-netpol-ws:fixture" in calls
    ) == include_ws
    assert ("ue-netpol-ws:fixture" in calls.splitlines()[0]) == include_ws


def test_required_native_bash_fails_when_unavailable(monkeypatch):
    with monkeypatch.context() as missing_bash:
        missing_bash.setattr(Path, "is_file", lambda _path: False)
        with pytest.raises(pytest.fail.Exception, match="native Bash is required"):
            _require_native_bash()


def test_proof_keeps_exact_calico_line_and_cleans_only_its_ws_tag():
    proof = (
        (ROOT / "scripts/k8s/networkpolicy_runtime_proof.sh").read_text().splitlines()
    )
    assert proof[33].startswith('readonly CALICO_SHA256="')
    text = "\n".join(proof)
    assert 'WS_IMAGE="ue-netpol-ws:${SOURCE_SHA}-${RUN_SUFFIX}"' in text
    assert 'docker image rm "$WS_IMAGE"' in text
    assert "docker image prune" not in text and "docker system prune" not in text


def test_create_only_ws_fixture_captures_returned_identity(monkeypatch):
    import networkpolicy_runtime_kube as kube

    uid = "01234567-89ab-cdef-0123-456789abcdef"
    fixture = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"namespace": "probe-a", "name": "probe-a-ws-hub"},
    }
    response = copy.deepcopy(fixture)
    response["metadata"]["uid"] = uid
    command = Mock(return_value=SimpleNamespace(stdout=json.dumps(response)))
    monkeypatch.setattr(kube, "run_command", command)

    created = kube.create_pod(fixture)

    assert (created.namespace, created.name, created.uid) == (
        "probe-a",
        "probe-a-ws-hub",
        uid,
    )
    assert command.call_args.args[0] == ["kubectl", "create", "-f", "-", "-o", "json"]
    assert json.loads(command.call_args.kwargs["stdin"]) == fixture
    assert command.call_args.kwargs["timeout"] <= 30
    with pytest.raises(AttributeError):
        created.uid = "different"


@pytest.mark.parametrize("owned", [False, True])
def test_setup_creates_only_ws_fixture_when_real_ws_is_requested(monkeypatch, owned):
    import networkpolicy_runtime_kube as kube

    fixture = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "namespace": "probe-a",
            "name": "probe-a-ws-hub",
            "labels": {"probe-role": "a-ws"},
        },
    }
    other = {"kind": "Pod", "metadata": {"name": "other"}}
    target = kube.Pod("probe-a", "probe-a-ws-hub")
    witness = kube.CreatedPod(
        "probe-a", "probe-a-ws-hub", "01234567-89ab-cdef-0123-456789abcdef"
    )
    applied = Mock()
    create = Mock(return_value=witness)
    monkeypatch.setattr(runner, "namespace_objects", lambda: [])
    monkeypatch.setattr(runner, "credential_secret", lambda *args: {})
    monkeypatch.setattr(runner, "apply_store_workloads", Mock())
    monkeypatch.setattr(
        runner, "standin_objects", lambda *args: ([fixture, other], {"a-ws": target})
    )
    monkeypatch.setattr(runner, "apply_objects", applied)
    monkeypatch.setattr(runner, "create_pod", create)
    monkeypatch.setattr(runner, "wait_ready", Mock())
    monkeypatch.setattr(runner, "resolve_pod", Mock())
    releases = {name: ([], []) for name in runner.RELEASES}

    result = runner.set_up_cluster(
        "fixture", releases, dict.fromkeys(runner.RELEASES, "p"), own_ws=owned
    )

    assert result["a-ws"].created == (witness if owned else None)
    if owned:
        create.assert_called_once_with(fixture)
        assert applied.call_args_list[-1].args[0] == [other]
    else:
        create.assert_not_called()
        assert applied.call_args_list[-1].args[0] == [fixture, other]


@pytest.mark.parametrize("changed", [False, True])
def test_refresh_cannot_replace_creation_witness(monkeypatch, changed):
    import networkpolicy_runtime_kube as kube

    uid = "01234567-89ab-cdef-0123-456789abcdef"
    created = kube.CreatedPod("probe-a", "probe-a-ws-hub", uid)
    pod = kube.Pod("probe-a", "probe-a-ws-hub", created=created)
    monkeypatch.setattr(
        runner,
        "kubectl_json",
        lambda *args: {
            "metadata": {"uid": "different" if changed else uid},
            "status": {"podIP": "10.1.2.3"},
        },
    )
    if changed:
        with pytest.raises(ValueError):
            runner.resolve_pod(pod)
        assert pod.uid == ""
    else:
        runner.resolve_pod(pod)
        assert pod.uid == uid and pod.ip == "10.1.2.3"
    assert pod.created is created


@pytest.mark.parametrize(
    "fault",
    [None, "missing-witness", "observed-uid", "live-uid", "role", "image", "owner"],
)
def test_retire_only_the_created_unchanged_fixture(rendered, monkeypatch, fault):
    from networkpolicy_runtime_kube import CreatedPod, Pod
    from networkpolicy_runtime_standins import stand_in_pod

    uid = "01234567-89ab-cdef-0123-456789abcdef"
    created = CreatedPod("probe-a", "probe-a-ws-hub", uid)
    fixture = Pod("probe-a", "probe-a-ws-hub", "10.1.2.3", uid, created)
    labels = ws.find(rendered[0], "Deployment", "probe-a-ws-hub")["spec"]["template"][
        "metadata"
    ]["labels"]
    live = stand_in_pod(
        "probe-a",
        "probe-a-ws-hub",
        {**labels, "probe-role": "a-ws"},
        "python-fixture",
        "8081,9108",
    )
    live["metadata"]["uid"] = uid
    live["status"] = {"podIP": fixture.ip}
    if fault == "missing-witness":
        fixture.created = None
    elif fault == "observed-uid":
        fixture.uid = "another"
    elif fault == "live-uid":
        live["metadata"]["uid"] = "another"
    elif fault == "role":
        live["metadata"]["labels"]["probe-role"] = "other"
    elif fault == "image":
        live["spec"]["containers"][0]["image"] = "other"
    elif fault == "owner":
        live["metadata"]["ownerReferences"] = [{"uid": "other"}]
    monkeypatch.setattr(ws, "kubectl_json", Mock(return_value=live))
    commands = Mock(return_value=SimpleNamespace(stdout=""))
    monkeypatch.setattr(ws, "run_command", commands)

    if fault is not None:
        with pytest.raises(ValueError):
            ws.retire_ws_fixture(rendered[0], fixture, "python-fixture")
        commands.assert_not_called()
        return

    ws.retire_ws_fixture(rendered[0], fixture, "python-fixture")
    deletion = commands.call_args_list[0]
    assert deletion.args[0] == [
        "kubectl",
        "delete",
        "--raw",
        "/api/v1/namespaces/probe-a/pods/probe-a-ws-hub",
        "-f",
        "-",
    ]
    assert json.loads(deletion.kwargs["stdin"])["preconditions"] == {"uid": uid}
    assert deletion.kwargs["timeout"] <= 30
    assert commands.call_count == 2
    assert "--ignore-not-found" in commands.call_args_list[1].args[0]


@pytest.mark.parametrize("replacement", [False, True])
def test_retirement_polls_owned_uid_and_rejects_replacement(
    rendered, monkeypatch, replacement
):
    from networkpolicy_runtime_kube import CreatedPod, Pod
    from networkpolicy_runtime_standins import stand_in_pod

    uid = "01234567-89ab-cdef-0123-456789abcdef"
    fixture = Pod(
        "probe-a",
        "probe-a-ws-hub",
        "10.1.2.3",
        uid,
        CreatedPod("probe-a", "probe-a-ws-hub", uid),
    )
    labels = ws.find(rendered[0], "Deployment", "probe-a-ws-hub")["spec"]["template"][
        "metadata"
    ]["labels"]
    live = stand_in_pod(
        "probe-a",
        "probe-a-ws-hub",
        {**labels, "probe-role": "a-ws"},
        "python-fixture",
        "8081,9108",
    )
    live["metadata"]["uid"] = uid
    live["status"] = {"podIP": fixture.ip}
    monkeypatch.setattr(ws, "kubectl_json", Mock(return_value=live))
    pending = {"metadata": {"uid": "replacement" if replacement else uid}}
    commands = Mock(
        side_effect=[
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout=json.dumps(pending)),
            SimpleNamespace(stdout=""),
        ]
    )
    monkeypatch.setattr(ws, "run_command", commands)
    monkeypatch.setattr(
        ws, "time", SimpleNamespace(monotonic=Mock(return_value=0), sleep=Mock())
    )
    if replacement:
        with pytest.raises(ValueError):
            ws.retire_ws_fixture(rendered[0], fixture, "python-fixture")
        assert commands.call_count == 2
    else:
        ws.retire_ws_fixture(rendered[0], fixture, "python-fixture")
        assert commands.call_count == 3
    assert sum("delete" in call.args[0] for call in commands.call_args_list) == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate-name"])
def test_setup_rejects_ambiguous_owned_fixture_without_creating(monkeypatch, fault):
    import networkpolicy_runtime_kube as kube

    fixture = {
        "kind": "Pod",
        "metadata": {
            "namespace": "probe-a",
            "name": "probe-a-ws-hub",
            "labels": {"probe-role": "a-ws"},
        },
    }
    objects = [] if fault == "missing" else [fixture, copy.deepcopy(fixture)]
    if objects:
        objects[1]["metadata"]["labels"]["probe-role"] = "different"
    monkeypatch.setattr(runner, "namespace_objects", lambda: [])
    monkeypatch.setattr(runner, "credential_secret", lambda *args: {})
    monkeypatch.setattr(runner, "apply_store_workloads", Mock())
    monkeypatch.setattr(
        runner,
        "standin_objects",
        lambda *args: (objects, {"a-ws": kube.Pod("probe-a", "probe-a-ws-hub")}),
    )
    monkeypatch.setattr(runner, "apply_objects", Mock())
    create = Mock()
    monkeypatch.setattr(runner, "create_pod", create)
    monkeypatch.setattr(
        runner, "wait_ready", Mock(side_effect=AssertionError("unexpected wait"))
    )
    monkeypatch.setattr(
        runner, "resolve_pod", Mock(side_effect=AssertionError("unexpected resolve"))
    )
    releases = {name: ([], []) for name in runner.RELEASES}

    with pytest.raises(ValueError):
        runner.set_up_cluster(
            "fixture", releases, dict.fromkeys(runner.RELEASES, "p"), own_ws=True
        )
    create.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["identity", "uid", "uid-format", "shape", "null", "metadata", "conflict"]
)
def test_create_only_rejects_untrusted_response_and_never_falls_back(
    monkeypatch, fault
):
    import networkpolicy_runtime_kube as kube

    fixture = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"namespace": "probe-a", "name": "probe-a-ws-hub"},
    }
    response = copy.deepcopy(fixture)
    response["metadata"]["uid"] = "01234567-89ab-cdef-0123-456789abcdef"
    if fault == "identity":
        response["metadata"]["name"] = "other"
    elif fault == "uid":
        response["metadata"]["uid"] = None
    elif fault == "uid-format":
        response["metadata"]["uid"] = "not-a-uid"
    elif fault == "shape":
        response = []
    elif fault == "null":
        response = None
    elif fault == "metadata":
        response["metadata"] = None
    command = Mock(return_value=SimpleNamespace(stdout=json.dumps(response)))
    if fault == "conflict":
        command.side_effect = subprocess.CalledProcessError(1, "kubectl create")
    monkeypatch.setattr(kube, "run_command", command)

    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        kube.create_pod(fixture)
    assert command.call_count == 1
    assert command.call_args.args[0][1] == "create"


@pytest.mark.parametrize(
    "fault", ["kind", "namespace", "name", "uid", "owner", "generated", "metadata"]
)
def test_create_rejects_wrong_fixture_before_kubectl(monkeypatch, fault):
    import networkpolicy_runtime_kube as kube

    fixture = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"namespace": "probe-a", "name": "probe-a-ws-hub"},
    }
    if fault == "kind":
        fixture["kind"] = "Service"
    elif fault == "namespace":
        fixture["metadata"]["namespace"] = "other"
    elif fault == "name":
        fixture["metadata"]["name"] = "other"
    elif fault == "metadata":
        fixture["metadata"] = None
    else:
        field = {"uid": "uid", "owner": "ownerReferences", "generated": "generateName"}[
            fault
        ]
        fixture["metadata"][field] = "not-allowed"
    command = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(kube, "run_command", command)
    with pytest.raises(ValueError):
        kube.create_pod(fixture)
    command.assert_not_called()


def test_retirement_timeout_does_not_repeat_delete(rendered, monkeypatch):
    from networkpolicy_runtime_kube import CreatedPod, Pod
    from networkpolicy_runtime_standins import stand_in_pod

    uid = "01234567-89ab-cdef-0123-456789abcdef"
    fixture = Pod(
        "probe-a",
        "probe-a-ws-hub",
        "10.1.2.3",
        uid,
        CreatedPod("probe-a", "probe-a-ws-hub", uid),
    )
    labels = ws.find(rendered[0], "Deployment", "probe-a-ws-hub")["spec"]["template"][
        "metadata"
    ]["labels"]
    live = stand_in_pod(
        "probe-a",
        "probe-a-ws-hub",
        {**labels, "probe-role": "a-ws"},
        "python-fixture",
        "8081,9108",
    )
    live["metadata"]["uid"] = uid
    live["status"] = {"podIP": fixture.ip}
    monkeypatch.setattr(ws, "kubectl_json", Mock(return_value=live))
    command = Mock(return_value=SimpleNamespace(stdout=""))
    monkeypatch.setattr(ws, "run_command", command)
    monkeypatch.setattr(
        ws, "time", SimpleNamespace(monotonic=Mock(side_effect=[0, 46]), sleep=Mock())
    )
    with pytest.raises(ValueError, match="timed out"):
        ws.retire_ws_fixture(rendered[0], fixture, "python-fixture")
    assert command.call_count == 1


def test_create_service_uses_unmodified_rendered_manifest(
    rendered, declaration, monkeypatch
):
    service = ws.find(rendered[0], "Service", "probe-a-ws-hub")
    original = copy.deepcopy(service)
    created = copy.deepcopy(service)
    created["metadata"]["uid"] = "01234567-89ab-cdef-0123-456789abcdef"
    created["spec"]["clusterIP"] = "10.96.0.42"
    command = Mock(return_value=SimpleNamespace(stdout=json.dumps(created)))
    monkeypatch.setattr(ws, "run_command", command)

    identity = ws.create_ws_service(rendered[0], declaration)

    assert identity == {"uid": created["metadata"]["uid"], "cluster_ip": "10.96.0.42"}
    assert service == original
    assert command.call_args.args[0] == ["kubectl", "create", "-f", "-", "-o", "json"]
    assert json.loads(command.call_args.kwargs["stdin"]) == original
    assert command.call_args.kwargs["timeout"] <= 30


def service_and_endpoints(rendered):
    service = copy.deepcopy(ws.find(rendered[0], "Service", "probe-a-ws-hub"))
    service["metadata"]["uid"] = "01234567-89ab-cdef-0123-456789abcdef"
    service["spec"]["clusterIP"] = "10.96.0.42"

    def endpoint(name, uid, ip):
        return {
            "addresses": [ip],
            "conditions": {"ready": True},
            "targetRef": {
                "kind": "Pod",
                "namespace": "probe-a",
                "name": name,
                "uid": uid,
            },
        }

    replicas = [
        {"name": "ws-1", "uid": "uid-1", "ip": "10.1.2.3"},
        {"name": "ws-2", "uid": "uid-2", "ip": "10.1.2.4"},
    ]
    slices = {
        "items": [
            {
                "metadata": {
                    "namespace": "probe-a",
                    "name": "slice-1",
                    "uid": "slice-uid",
                    "labels": {"kubernetes.io/service-name": "probe-a-ws-hub"},
                    "ownerReferences": [
                        {
                            "kind": "Service",
                            "name": "probe-a-ws-hub",
                            "uid": service["metadata"]["uid"],
                            "controller": True,
                        }
                    ],
                },
                "addressType": "IPv4",
                "ports": [{"name": "http", "protocol": "TCP", "port": 8081}],
                "endpoints": [
                    endpoint("ws-1", "uid-1", "10.1.2.3"),
                    endpoint("ws-2", "uid-2", "10.1.2.4"),
                ],
            }
        ]
    }
    return service, slices, replicas


def test_service_snapshot_binds_ready_slice_endpoints_to_real_replicas(
    rendered, declaration, monkeypatch
):
    service, slices, replicas = service_and_endpoints(rendered)
    reads = Mock(side_effect=[service, slices])
    monkeypatch.setattr(ws, "bounded_kubectl_json", reads)
    identity = {
        "uid": service["metadata"]["uid"],
        "cluster_ip": service["spec"]["clusterIP"],
    }

    snapshot = ws.ws_service_snapshot(declaration, identity, replicas)

    assert snapshot == {
        "service_uid": identity["uid"],
        "slice_uids": ["slice-uid"],
        "replica_uids": ["uid-1", "uid-2"],
    }
    assert reads.call_count == 2


@pytest.mark.parametrize("endpoints", ["empty", "null", "missing"])
@pytest.mark.parametrize("ports", ["empty", "null", "missing", "valid"])
def test_empty_controller_slice_waits_until_real_endpoints_are_ready(
    rendered, declaration, monkeypatch, endpoints, ports
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    service, slices, replicas = service_and_endpoints(rendered)
    ready = copy.deepcopy(slices)
    item = slices["items"][0]
    for field, value in (("endpoints", endpoints), ("ports", ports)):
        if value == "missing":
            del item[field]
        elif value == "null":
            item[field] = None
        elif value == "empty":
            item[field] = []
    reads = Mock(side_effect=[service, slices, service, ready])
    monkeypatch.setattr(ws, "bounded_kubectl_json", reads)
    identity = {
        "uid": service["metadata"]["uid"],
        "cluster_ip": service["spec"]["clusterIP"],
    }

    assert ws.ws_service_snapshot(declaration, identity, replicas) is None
    assert ws.ws_service_snapshot(declaration, identity, replicas) == {
        "service_uid": identity["uid"],
        "slice_uids": ["slice-uid"],
        "replica_uids": ["uid-1", "uid-2"],
    }
    assert reads.call_count == 4


@pytest.mark.parametrize(
    "fault",
    [
        "endpoints-false",
        "endpoints-object",
        "ports-false",
        "ports-object",
        "populated-ports-null",
        "populated-ports-missing",
        "empty-wrong-owner",
    ],
)
def test_controller_slice_still_rejects_malformed_or_unowned_data(
    rendered, declaration, monkeypatch, fault
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    service, slices, replicas = service_and_endpoints(rendered)
    item = slices["items"][0]
    if fault == "endpoints-false":
        item["endpoints"] = False
    elif fault == "endpoints-object":
        item["endpoints"] = {}
    elif fault == "ports-false":
        item["ports"] = False
    elif fault == "ports-object":
        item["ports"] = {}
    elif fault == "populated-ports-null":
        item["ports"] = None
    elif fault == "populated-ports-missing":
        del item["ports"]
    else:
        item["endpoints"] = None
        item["ports"] = None
        item["metadata"]["ownerReferences"][0]["uid"] = "other"
    monkeypatch.setattr(ws, "bounded_kubectl_json", Mock(side_effect=[service, slices]))
    identity = {
        "uid": service["metadata"]["uid"],
        "cluster_ip": service["spec"]["clusterIP"],
    }
    with pytest.raises(ValueError, match="unexpected ws-hub EndpointSlice"):
        ws.ws_service_snapshot(declaration, identity, replicas)


@pytest.mark.parametrize(
    "fault", [None, "source", "uid", "labels", "restarts", "no-grant"]
)
def test_service_source_is_original_pod_selected_by_rendered_policy(
    rendered, monkeypatch, fault
):
    app = copy.deepcopy(rendered[0])
    source = ws.Pod("ingress-nginx", "ingress-controller", "10.1.1.5", "source-uid")
    namespace = {
        "metadata": {
            "name": "ingress-nginx",
            "labels": {"kubernetes.io/metadata.name": "ingress-nginx"},
        }
    }
    pod = {
        "metadata": {
            "namespace": source.namespace,
            "name": source.name,
            "uid": source.uid,
            "labels": {"app.kubernetes.io/name": "ingress-nginx"},
        },
        "spec": {"containers": [{"name": "probe"}], "hostNetwork": False},
        "status": {
            "podIP": source.ip,
            "containerStatuses": [
                {
                    "name": "probe",
                    "ready": True,
                    "containerID": "containerd://a",
                    "restartCount": 0,
                }
            ],
        },
    }
    if fault == "source":
        source.uid = ""
    elif fault == "uid":
        pod["metadata"]["uid"] = "other"
    elif fault == "labels":
        pod["metadata"]["labels"] = {}
    elif fault == "restarts":
        pod["status"]["containerStatuses"][0]["restartCount"] = -1
    elif fault == "no-grant":
        ws.find(app, "NetworkPolicy", "probe-a-ws-hub-policy")["spec"]["ingress"] = []
    monkeypatch.setattr(ws, "bounded_kubectl_json", Mock(side_effect=[namespace, pod]))
    if fault:
        with pytest.raises(ValueError):
            ws.authorized_ingress_source(app, source)
    else:
        assert ws.authorized_ingress_source(app, source) == {
            "uid": "source-uid",
            "container_id": "containerd://a",
            "restarts": 0,
        }


@pytest.mark.parametrize(
    "fault, pending",
    [
        ("empty-list", True),
        ("empty-slice", True),
        ("unready", True),
        ("missing", True),
        ("service-uid", False),
        ("slice-owner", False),
        ("slice-port", False),
        ("endpoint-uid", False),
        ("endpoint-ip", False),
        ("duplicate", False),
        ("duplicate-replicas", False),
        ("duplicate-slice", False),
    ],
)
def test_service_snapshot_rejects_drift_and_waits_for_reconciliation(
    rendered, declaration, monkeypatch, fault, pending
):
    service, slices, replicas = service_and_endpoints(rendered)
    identity = {
        "uid": service["metadata"]["uid"],
        "cluster_ip": service["spec"]["clusterIP"],
    }
    item = slices["items"][0]
    if fault == "empty-list":
        slices["items"] = []
    elif fault == "empty-slice":
        item["endpoints"] = []
        item["ports"] = []
    elif fault == "unready":
        item["endpoints"][0]["conditions"]["ready"] = False
    elif fault == "missing":
        item["endpoints"].pop()
    elif fault == "service-uid":
        service["metadata"]["uid"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    elif fault == "slice-owner":
        item["metadata"]["ownerReferences"][0]["uid"] = "other"
    elif fault == "slice-port":
        item["ports"][0]["port"] = 9108
    elif fault == "endpoint-uid":
        item["endpoints"][0]["targetRef"]["uid"] = "stand-in"
    elif fault == "endpoint-ip":
        item["endpoints"][0]["addresses"] = ["10.9.9.9"]
    elif fault == "duplicate":
        item["endpoints"].append(copy.deepcopy(item["endpoints"][0]))
    elif fault == "duplicate-replicas":
        replicas.append(copy.deepcopy(replicas[0]))
    elif fault == "duplicate-slice":
        extra = copy.deepcopy(item)
        extra["endpoints"] = []
        slices["items"].append(extra)
    monkeypatch.setattr(ws, "bounded_kubectl_json", Mock(side_effect=[service, slices]))
    if pending:
        assert ws.ws_service_snapshot(declaration, identity, replicas) is None
    else:
        with pytest.raises(ValueError):
            ws.ws_service_snapshot(declaration, identity, replicas)


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, b'{"status":"alive"}', "healthy"),
        (503, b'{"status":"alive"}', "invalid"),
        (200, b'{"status":"other"}', "invalid"),
        (200, b"x" * 1025, "invalid"),
        (200, b"not json", "invalid"),
    ],
)
def test_service_health_probe_is_bounded_and_returns_only_verdict(
    monkeypatch, capsys, tmp_path, status, body, expected
):
    response = Mock(status=status)
    response.read.return_value = body
    connection = Mock()
    connection.getresponse.return_value = response
    factory = Mock(return_value=connection)
    monkeypatch.setattr(http.client, "HTTPConnection", factory)
    monkeypatch.setattr(sys, "argv", ["probe", "10.96.0.42"])
    program = tmp_path / "health.py"
    program.write_text(ws.HEALTH, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": expected}
    factory.assert_called_once_with("10.96.0.42", 8081, timeout=3)
    connection.request.assert_called_once_with("GET", "/health/live")
    if status == 200:
        response.read.assert_called_once_with(1025)
    else:
        response.read.assert_not_called()
    connection.close.assert_called_once()


@pytest.mark.parametrize("exhausted", [False, True])
@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError("private"),
        OSError(errno.ENETUNREACH, "private"),
        OSError(errno.EHOSTUNREACH, "private"),
    ],
)
def test_health_probe_retries_transport_only_within_fixed_window(
    monkeypatch, capsys, tmp_path, exhausted, error
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    first = Mock()
    first.request.side_effect = error
    response = Mock(status=200)
    response.read.return_value = b'{"status":"alive"}'
    second = Mock()
    second.getresponse.return_value = response
    factory = Mock(side_effect=[first, second])
    monkeypatch.setattr(http.client, "HTTPConnection", factory)
    times = [0, 0, 11] if exhausted else [0, 0, 1, 1, 2]
    clock = SimpleNamespace(monotonic=Mock(side_effect=times), sleep=Mock())
    monkeypatch.setitem(sys.modules, "time", clock)
    monkeypatch.setattr(sys, "argv", ["probe", "10.96.0.42"])
    program = tmp_path / "health.py"
    program.write_text(ws.HEALTH, encoding="utf-8")

    runpy.run_path(str(program), run_name="__main__")

    assert json.loads(capsys.readouterr().out) == {
        "result": "transport-unavailable" if exhausted else "healthy"
    }
    assert factory.call_count == (1 if exhausted else 2)
    assert first.request.call_args.args == ("GET", "/health/live")
    assert clock.sleep.call_count == (0 if exhausted else 1)


def test_health_probe_rejects_non_200_without_read_or_retry(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    response = Mock(status=503)
    response.read.side_effect = TimeoutError("private response")
    connection = Mock()
    connection.getresponse.return_value = response
    factory = Mock(return_value=connection)
    monkeypatch.setattr(http.client, "HTTPConnection", factory)
    monkeypatch.setattr(sys, "argv", ["probe", "10.96.0.42"])
    program = tmp_path / "health.py"
    program.write_text(ws.HEALTH, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": "invalid"}
    response.read.assert_not_called()
    factory.assert_called_once()


def test_direct_health_diagnostic_does_not_retry_unavailable_transport(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    connection = Mock()
    connection.request.side_effect = TimeoutError("private network detail")
    factory = Mock(return_value=connection)
    monkeypatch.setattr(http.client, "HTTPConnection", factory)
    clock = SimpleNamespace(monotonic=Mock(side_effect=[0, 0]), sleep=Mock())
    monkeypatch.setitem(sys.modules, "time", clock)
    monkeypatch.setattr(sys, "argv", ["probe", "10.1.2.3", "single"])
    program = tmp_path / "health.py"
    program.write_text(ws.HEALTH, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": "transport-unavailable"}
    factory.assert_called_once()
    clock.sleep.assert_not_called()


@pytest.mark.parametrize(
    "error,expected",
    [
        (PermissionError(13, "private"), "exec-error"),
        (http.client.BadStatusLine("private"), "invalid"),
    ],
)
def test_health_probe_does_not_retry_nontransport_errors(
    monkeypatch, capsys, tmp_path, error, expected
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    connection = Mock()
    connection.request.side_effect = error
    factory = Mock(return_value=connection)
    monkeypatch.setattr(http.client, "HTTPConnection", factory)
    monkeypatch.setattr(sys, "argv", ["probe", "10.96.0.42"])
    program = tmp_path / "health.py"
    program.write_text(ws.HEALTH, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": expected}
    factory.assert_called_once()


def test_health_probe_rejects_a_success_after_its_deadline(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    response = Mock(status=200)
    response.read.return_value = b'{"status":"alive"}'
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(http.client, "HTTPConnection", Mock(return_value=connection))
    clock = SimpleNamespace(monotonic=Mock(side_effect=[0, 0, 11]), sleep=Mock())
    monkeypatch.setitem(sys.modules, "time", clock)
    monkeypatch.setattr(sys, "argv", ["probe", "10.96.0.42"])
    program = tmp_path / "health.py"
    program.write_text(ws.HEALTH, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": "window-expired"}
    clock.sleep.assert_not_called()


@pytest.mark.parametrize(
    "direct", ["healthy", "transport-unavailable", "invalid", "exec-error"]
)
def test_vip_transport_exhaustion_records_only_bound_direct_diagnostic(
    rendered, declaration, monkeypatch, direct
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    prove = ws.prove_ws_service
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    mocks["prove_ws_service"].side_effect = prove
    source_state = {"uid": "source", "container_id": "container", "restarts": 0}
    monkeypatch.setattr(
        ws, "authorized_ingress_source", Mock(return_value=source_state)
    )
    monkeypatch.setattr(
        ws,
        "create_ws_service",
        Mock(return_value={"uid": "service", "cluster_ip": "10.96.0.42"}),
    )
    snapshot = {"service_uid": "service", "slice_uids": ["slice"]}
    monkeypatch.setattr(ws, "ws_service_snapshot", Mock(return_value=snapshot))
    mocks["run_in_pod"].side_effect = [
        {"result": "valid"},
        {"result": "valid-exposition"},
        {"result": "valid-exposition"},
        {"result": "transport-unavailable"},
        {"result": direct},
    ]

    result = run_phase(tree, pods)

    assert result["verdict"] == "inconclusive"
    assert result["stage"] == "service-health"
    assert result["substage"] == "health-transport-exhausted"
    assert result["direct_health"] == direct
    calls = mocks["run_in_pod"].call_args_list
    assert calls[-2].args == (pods["ingress"], ws.HEALTH, ["10.96.0.42"])
    assert calls[-1].args == (pods["ingress"], ws.HEALTH, [copies[0]["ip"], "single"])
    assert mocks["replicas"].call_count == 3
    assert "10.96.0.42" not in json.dumps(result)
    assert copies[0]["ip"] not in json.dumps(result)


@pytest.mark.parametrize(
    "observation,expected",
    [
        ({"result": "invalid"}, "health-invalid"),
        ({"result": "window-expired"}, "health-window-expired"),
        ({"result": "exec-error"}, "health-exec-error"),
        ({"result": "exec-timeout"}, "health-exec-error"),
        ({"result": "healthy", "unexpected": "private"}, "health-exec-error"),
    ],
)
def test_unexpected_health_or_exec_results_fail_without_direct_diagnostic(
    rendered, declaration, monkeypatch, observation, expected
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    prove = ws.prove_ws_service
    tree, pods, _, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    mocks["prove_ws_service"].side_effect = prove
    monkeypatch.setattr(
        ws, "authorized_ingress_source", Mock(return_value={"uid": "source"})
    )
    monkeypatch.setattr(
        ws,
        "create_ws_service",
        Mock(return_value={"uid": "service", "cluster_ip": "10.96.0.42"}),
    )
    monkeypatch.setattr(
        ws, "ws_service_snapshot", Mock(return_value={"slice_uids": ["slice"]})
    )
    mocks["run_in_pod"].side_effect = [
        {"result": "valid"},
        {"result": "valid-exposition"},
        {"result": "valid-exposition"},
        observation,
    ]
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    assert result["substage"] == expected
    assert mocks["run_in_pod"].call_count == 4
    assert "direct_health" not in result
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize(
    "drift,expected",
    [
        ("source", "source-post-health"),
        ("slice", "endpoints-after"),
        ("replica", "replica-recheck"),
    ],
)
def test_direct_diagnostic_is_discarded_if_identity_changes(
    rendered, declaration, monkeypatch, drift, expected
):
    monkeypatch.setattr(
        ws.subprocess, "run", Mock(side_effect=AssertionError("unexpected subprocess"))
    )
    prove = ws.prove_ws_service
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    mocks["prove_ws_service"].side_effect = prove
    source = {"uid": "source", "restarts": 0}
    altered_source = {"uid": "source", "restarts": 1}
    monkeypatch.setattr(
        ws,
        "authorized_ingress_source",
        Mock(
            side_effect=[
                source,
                source,
                altered_source if drift == "source" else source,
            ]
        ),
    )
    monkeypatch.setattr(
        ws,
        "create_ws_service",
        Mock(return_value={"uid": "service", "cluster_ip": "10.96.0.42"}),
    )
    snapshot = {"slice_uids": ["slice"]}
    monkeypatch.setattr(
        ws,
        "ws_service_snapshot",
        Mock(
            side_effect=[
                snapshot,
                {"slice_uids": ["other"]} if drift == "slice" else snapshot,
            ]
        ),
    )
    mocks["run_in_pod"].side_effect = [
        {"result": "valid"},
        {"result": "valid-exposition"},
        {"result": "valid-exposition"},
        {"result": "transport-unavailable"},
        {"result": "healthy"},
    ]
    if drift == "replica":
        altered = copy.deepcopy(copies)
        altered[0]["restarts"] = 1
        mocks["replicas"].side_effect = [copies, copies, altered]
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    assert result["substage"] == expected
    assert "direct_health" not in result


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "health",
        "source-before",
        "source-drift",
        "slice-drift",
        "timeout",
        "late-ready",
    ],
)
def test_service_proof_brackets_health_with_matching_witnesses(
    rendered, declaration, monkeypatch, fault
):
    service, _, replicas = service_and_endpoints(rendered)
    source = ws.Pod("ingress-nginx", "ingress-controller", "10.1.1.5", "source-uid")
    identity = {
        "uid": service["metadata"]["uid"],
        "cluster_ip": service["spec"]["clusterIP"],
    }
    snapshot = {
        "service_uid": identity["uid"],
        "slice_uids": ["slice-uid"],
        "replica_uids": ["uid-1", "uid-2"],
    }
    source_state = {
        "uid": "source-uid",
        "container_id": "containerd://a",
        "restarts": 0,
    }
    monkeypatch.setattr(ws, "create_ws_service", Mock(return_value=identity))
    states = [
        ({**source_state, "restarts": 1} if fault == "source-before" else source_state),
        source_state,
        ({**source_state, "restarts": 1} if fault == "source-drift" else source_state),
    ]
    monkeypatch.setattr(ws, "authorized_ingress_source", Mock(side_effect=states))
    snapshots = [
        None,
        snapshot,
        ({**snapshot, "slice_uids": ["other"]} if fault == "slice-drift" else snapshot),
    ]
    if fault == "late-ready":
        snapshots = [snapshot, snapshot]
    monkeypatch.setattr(ws, "ws_service_snapshot", Mock(side_effect=snapshots))
    probe = Mock(return_value={"result": "invalid" if fault == "health" else "healthy"})
    monkeypatch.setattr(ws, "run_in_pod", probe)
    times = [0, 31] if fault in {"timeout", "late-ready"} else [0, 1, 2]
    monkeypatch.setattr(
        ws, "time", SimpleNamespace(monotonic=Mock(side_effect=times), sleep=Mock())
    )
    if fault:
        with pytest.raises(ValueError):
            ws.prove_ws_service(rendered[0], declaration, replicas, source)
    else:
        result = ws.prove_ws_service(rendered[0], declaration, replicas, source)
        assert result == {
            **snapshot,
            "source_uid": source.uid,
            "source": "ingress-labelled Python probe",
            "request": "GET /health/live",
            "verdict": "pass",
        }
        assert "10.96.0.42" not in json.dumps(result)
        probe.assert_called_once_with(source, ws.HEALTH, ["10.96.0.42"], timeout=10)


@pytest.mark.parametrize("payload", ["{}", "null", "[]"])
def test_service_reads_have_bounded_transport_and_require_object(monkeypatch, payload):
    command = Mock(return_value=SimpleNamespace(stdout=payload))
    monkeypatch.setattr(ws, "run_command", command)
    if payload == "{}":
        assert ws.bounded_kubectl_json("get", "service") == {}
    else:
        with pytest.raises(ValueError):
            ws.bounded_kubectl_json("get", "service")
    assert command.call_args.args[0] == ["kubectl", "get", "service"]
    assert command.call_args.kwargs["timeout"] <= 10


@pytest.mark.parametrize(
    "fault",
    [
        "declaration-port",
        "target-port",
        "conflict",
        "uid",
        "ip",
        "selector",
        "extra-port",
        "shape",
    ],
)
def test_service_creation_fails_closed_on_conflict_or_drift(
    rendered, declaration, monkeypatch, fault
):
    app = copy.deepcopy(rendered[0])
    service = ws.find(app, "Service", "probe-a-ws-hub")
    response = copy.deepcopy(service)
    response["metadata"]["uid"] = "01234567-89ab-cdef-0123-456789abcdef"
    response["spec"]["clusterIP"] = "10.96.0.42"
    if fault == "declaration-port":
        service["spec"]["ports"][0]["port"] = 9108
    elif fault == "target-port":
        declaration["spec"]["template"]["spec"]["containers"][0]["ports"][0][
            "containerPort"
        ] = 9108
    elif fault == "uid":
        response["metadata"]["uid"] = "bad"
    elif fault == "ip":
        response["spec"]["clusterIP"] = "8.8.8.8"
    elif fault == "selector":
        response["spec"]["selector"] = {"different": "pod"}
    elif fault == "extra-port":
        response["spec"]["ports"].append({"name": "metrics", "port": 9108})
    elif fault == "shape":
        response = None
    command = Mock(return_value=SimpleNamespace(stdout=json.dumps(response)))
    if fault == "conflict":
        command.side_effect = subprocess.CalledProcessError(1, "kubectl create")
    monkeypatch.setattr(ws, "run_command", command)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        ws.create_ws_service(app, declaration)
    assert command.call_count == (
        0 if fault in {"declaration-port", "target-port"} else 1
    )


def test_service_proof_composes_real_helpers_with_mocked_transport(
    rendered, declaration, monkeypatch
):
    service, slices, replicas = service_and_endpoints(rendered)
    source = ws.Pod("ingress-nginx", "ingress-controller", "10.1.1.5", "source-uid")
    namespace = {
        "metadata": {
            "name": "ingress-nginx",
            "labels": {"kubernetes.io/metadata.name": "ingress-nginx"},
        }
    }
    pod = {
        "metadata": {
            "namespace": source.namespace,
            "name": source.name,
            "uid": source.uid,
            "labels": {"app.kubernetes.io/name": "ingress-nginx"},
        },
        "spec": {"containers": [{"name": "probe"}], "hostNetwork": False},
        "status": {
            "podIP": source.ip,
            "containerStatuses": [
                {
                    "name": "probe",
                    "ready": True,
                    "containerID": "containerd://a",
                    "restartCount": 0,
                }
            ],
        },
    }
    calls = []

    def transport(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv == ["kubectl", "create", "-f", "-", "-o", "json"]:
            assert json.loads(kwargs["stdin"]) == ws.find(
                rendered[0], "Service", "probe-a-ws-hub"
            )
            document = service
        elif argv == ["kubectl", "get", "namespace", "ingress-nginx", "-o", "json"]:
            document = namespace
        elif argv == [
            "kubectl",
            "-n",
            "ingress-nginx",
            "get",
            "pod",
            "ingress-controller",
            "-o",
            "json",
        ]:
            document = pod
        elif argv == [
            "kubectl",
            "-n",
            "probe-a",
            "get",
            "service",
            "probe-a-ws-hub",
            "-o",
            "json",
        ]:
            document = service
        elif argv == [
            "kubectl",
            "-n",
            "probe-a",
            "get",
            "endpointslices",
            "-l",
            "kubernetes.io/service-name=probe-a-ws-hub",
            "-o",
            "json",
        ]:
            document = slices
        else:
            raise AssertionError("unexpected transport request")
        return SimpleNamespace(stdout=json.dumps(document))

    monkeypatch.setattr(ws, "run_command", Mock(side_effect=transport))
    probe = Mock(return_value={"result": "healthy"})
    monkeypatch.setattr(ws, "run_in_pod", probe)
    monkeypatch.setattr(
        ws, "time", SimpleNamespace(monotonic=Mock(return_value=0), sleep=Mock())
    )

    result = ws.prove_ws_service(rendered[0], declaration, replicas, source)

    assert result == {
        "verdict": "pass",
        "source_uid": source.uid,
        "source": "ingress-labelled Python probe",
        "request": "GET /health/live",
        "service_uid": service["metadata"]["uid"],
        "slice_uids": ["slice-uid"],
        "replica_uids": ["uid-1", "uid-2"],
    }
    assert sum(argv[1] == "create" for argv, _ in calls) == 1
    assert all(kwargs["timeout"] <= 30 for _, kwargs in calls)
    probe.assert_called_once_with(source, ws.HEALTH, ["10.96.0.42"], timeout=10)


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("served", "served"),
        (TimeoutError("timed out"), "dropped"),
        (ConnectionRefusedError(), "refused"),
        (OSError("unreachable"), "error"),
    ],
)
def test_restricted_scrape_only_reports_a_timeout_as_dropped(
    monkeypatch, capsys, tmp_path, outcome, expected
):
    connection = Mock()
    if isinstance(outcome, BaseException):
        connection.request.side_effect = outcome
    else:
        connection.getresponse.return_value.read.return_value = b"#"
    monkeypatch.setattr(http.client, "HTTPConnection", Mock(return_value=connection))
    monkeypatch.setattr(sys, "argv", ["probe", "10.1.2.3"])
    program = tmp_path / "restricted-scrape.py"
    program.write_text(ws.RESTRICTED_SCRAPE, encoding="utf-8")
    runpy.run_path(str(program), run_name="__main__")
    assert json.loads(capsys.readouterr().out) == {"result": expected}
    http.client.HTTPConnection.assert_called_once_with("10.1.2.3", 9108, timeout=3)
    connection.close.assert_called_once_with()


def test_restricted_scrapes_cover_every_unselected_source_and_actual_replica(
    monkeypatch,
):
    pods = {
        key: ws.Pod("ns-" + key, "pod-" + key, uid=key + "-uid")
        for key in ws.RESTRICTED_SCRAPE_SOURCES
    }
    replicas = [
        {"uid": WS_UID_1, "ip": "10.1.2.3"},
        {"uid": WS_UID_2, "ip": "10.1.2.4"},
    ]
    probe = Mock(return_value={"result": "dropped"})
    monkeypatch.setattr(ws, "run_in_pod", probe)

    checks = ws.prove_restricted_scrapes(pods, replicas)

    assert ws.RESTRICTED_SCRAPE_SOURCES == ("unrelated", "monitoring-other", "ingress")
    assert [(check["source"], check["replica_uid"]) for check in checks] == [
        (source, replica["uid"])
        for source in ws.RESTRICTED_SCRAPE_SOURCES
        for replica in replicas
    ]
    assert all(check["verdict"] == "pass" for check in checks)
    assert all(check["source_uid"] == check["source"] + "-uid" for check in checks)
    assert [call.args for call in probe.call_args_list] == [
        (pods[source], ws.RESTRICTED_SCRAPE, [replica["ip"]])
        for source in ws.RESTRICTED_SCRAPE_SOURCES
        for replica in replicas
    ]
    assert all(call.kwargs == {"timeout": 8} for call in probe.call_args_list)
    assert "10.1.2.3" not in json.dumps(checks)


@pytest.mark.parametrize("observed", ["served", "refused", "error"])
def test_restricted_scrape_that_reaches_a_replica_is_inconclusive(
    monkeypatch, observed
):
    pods = {key: ws.Pod("ns", key, uid=key) for key in ws.RESTRICTED_SCRAPE_SOURCES}
    replicas = [{"uid": WS_UID_1, "ip": "10.1.2.3"}]
    monkeypatch.setattr(
        ws,
        "run_in_pod",
        Mock(
            side_effect=[
                {"result": "dropped"},
                {"result": observed},
                {"result": "dropped"},
            ]
        ),
    )
    checks = ws.prove_restricted_scrapes(pods, replicas)
    assert [check["verdict"] for check in checks] == ["pass", "inconclusive", "pass"]


def test_phase_records_dropped_restricted_scrapes_and_fails_closed(
    rendered, declaration, monkeypatch
):
    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    result = run_phase(tree, pods)
    assert result["verdict"] == "pass"
    assert (
        result["restricted_scrapes"] == mocks["prove_restricted_scrapes"].return_value
    )
    mocks["prove_restricted_scrapes"].assert_called_once_with(pods, copies)

    tree, pods, copies, mocks = install_phase_fakes(monkeypatch, rendered, declaration)
    failing = mocks["prove_restricted_scrapes"].return_value
    failing[0] = {**failing[0], "verdict": "inconclusive"}
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    assert result["stage"] == "restricted-scrape"
    mocks["retire_ws_fixture"].assert_not_called()
