"""Offline contracts for the separate real ws-hub positive scrape phase."""

from __future__ import annotations

import copy
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
    }
    copies = [
        {
            "name": "ws-1",
            "uid": "uid-1",
            "ip": "10.1.2.3",
            "container_id": "containerd://a",
            "image_id": "sha256:a",
            "restarts": 0,
        },
        {
            "name": "ws-2",
            "uid": "uid-2",
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
        "replicas": Mock(side_effect=[copies, copy.deepcopy(copies)]),
        "authorized_source": Mock(),
        "retire_ws_fixture": Mock(),
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
    assert mocks["authorized_source"].call_count == 2
    mocks["retire_ws_fixture"].assert_called_once_with(
        rendered[0], pods["a-ws"], "python-fixture"
    )
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
        mocks["replicas"].side_effect = [copies, altered]
    result = run_phase(tree, pods)
    assert result["verdict"] == "inconclusive"
    if fault != "scrape":
        assert result["stage"] == stage
    assert "private exception data" not in json.dumps(result)
    assert "revocation-password" not in json.dumps(result)
    if fault != "retire_ws_fixture":
        mocks["retire_ws_fixture"].assert_not_called()


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
    phase = Mock(return_value={"verdict": ws_result})
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
    assert "actual ws-hub restricted peers and Prometheus server" in outstanding
    assert "actual ingress controller and public HTTP route" in outstanding
    assert ("metrics exposition content" in outstanding) == (expected != "pass")


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


@pytest.mark.parametrize("include_ws", [False, True])
def test_source_archive_build_adds_only_requested_ws_image(
    monkeypatch, tmp_path, include_ws
):
    bash = (
        Path("C:/Program Files/Git/bin/bash.exe")
        if os.name == "nt"
        else Path("/bin/bash")
    )
    if not bash.is_file():
        pytest.skip("native Bash is unavailable")
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
    bash = (
        Path("C:/Program Files/Git/bin/bash.exe")
        if os.name == "nt"
        else Path("/bin/bash")
    )
    if not bash.is_file():
        pytest.skip("native Bash is unavailable")
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
