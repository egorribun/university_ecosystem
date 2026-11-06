"""Offline negative controls for the AUD-169/188/189 evidence checker."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("aud169_188_189_evidence.py")
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
RAW = "sha256:" + "c" * 64
METHOD = "/file_processor.v1.FileProcessingService/ProcessFile"


def checker():
    if not SCRIPT.is_file():
        raise RuntimeError("the runtime evidence checker is missing")
    spec = importlib.util.spec_from_file_location("aud_evidence", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import the runtime evidence checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pod(uid: str, ip: str) -> dict:
    namespace = "net:[" + str(sum(map(ord, uid))) + "]"
    return {
        "uid": uid,
        "ip": ip,
        "node": "node-1",
        "container_id": "containerd://" + uid,
        "restart_count": 0,
        "started_at": "2026-11-05T10:00:00Z",
        "observed_at": "2026-11-05T10:00:30Z",
        "image_digest": DIGEST,
        "host_network": False,
        "diagnostic_container_id": "containerd://diag-" + uid,
        "diagnostic_image_digest": DIGEST,
        "pod_network_namespace": namespace,
        "diagnostic_network_namespace": namespace,
        "network_namespace_evidence_digest": RAW,
        "diagnostic_privileged": False,
        "diagnostic_run_as_non_root": True,
        "diagnostic_allow_privilege_escalation": False,
        "diagnostic_host_mounts": [],
        "diagnostic_added_capabilities": [],
    }


def attempt(
    source: dict, ip: str, port: int, transport: str, sec: int, ok: bool
) -> dict:
    return {
        "source_uid": source["uid"],
        "source_ip": source["ip"],
        "destination_ip": ip,
        "destination_port": port,
        "transport": transport,
        "started_at": f"2026-11-05T10:01:{sec:02}Z",
        "finished_at": f"2026-11-05T10:01:{sec + 1:02}Z",
        "exit_code": 0 if ok else 1,
        "response": "connected" if ok else "timeout",
        "raw_digest": RAW,
    }


def denial(
    name: str, ip: str, port: int, transport: str, *, canary: bool = False
) -> dict:
    src = (
        pod("isolated-canary-uid", "10.32.0.13")
        if canary
        else pod("file-processor-uid", "10.32.0.11")
    )
    control = (
        pod("canary-control-uid", "10.32.0.14")
        if canary
        else pod("control-uid", "10.32.0.12")
    )
    case = {
        "name": name,
        "family": "IPv4",
        "destination_ip": ip,
        "destination_port": port,
        "transport": transport,
        "source_before": src,
        "source_after": copy.deepcopy(src),
        "control_before": control,
        "control_after": copy.deepcopy(control),
        "listener_before": {
            "uid": "listener-uid",
            "ip": ip,
            "observed_at": "2026-11-05T10:00:30Z",
            "raw_digest": RAW,
        },
        "listener_after": {
            "uid": "listener-uid",
            "ip": ip,
            "observed_at": "2026-11-05T10:04:00Z",
            "raw_digest": RAW,
        },
        "pre": attempt(control, ip, port, transport, 0, True),
        "blocked": attempt(src, ip, port, transport, 2, False),
        "post": attempt(control, ip, port, transport, 4, True),
        "verdict": {
            "source_uid": src["uid"],
            "source_ip": src["ip"],
            "destination_ip": ip,
            "destination_port": port,
            "transport": transport,
            "timestamp": "2026-11-05T10:01:03Z",
            "direction": "egress",
            "action": "drop",
            "policy_uid": "policy-uid",
            "raw_digest": RAW,
        },
    }
    case["source_after"]["observed_at"] = "2026-11-05T10:04:00Z"
    case["control_after"]["observed_at"] = "2026-11-05T10:04:00Z"
    if transport == "UDP" or name == "dns_tcp":
        case["query"] = {"name": "probe.example", "type": "A", "answer": "192.0.2.1"}
        case["pre"]["response"] = copy.deepcopy(case["query"])
        case["post"]["response"] = copy.deepcopy(case["query"])
    return case


def grpc_event(p: dict, sec: int, status: str, key: str) -> dict:
    return {
        "pod_uid": p["uid"],
        "container_id": p["container_id"],
        "destination_ip": p["ip"],
        "method": METHOD,
        "request": "empty",
        "token_ref": key,
        "token_digest": "sha256:" + ("d" if key == "token-b" else "e") * 64,
        "status": status,
        "message": "id is required" if status == "InvalidArgument" else "invalid token",
        "timestamp": f"2026-11-05T10:02:{sec:02}Z",
        "raw_digest": RAW,
    }


def receipt() -> dict:
    p = pod("file-processor-uid", "10.32.0.11")
    p_after = {**p, "observed_at": "2026-11-05T10:04:00Z"}
    canary = denial("canary", "10.32.0.20", 8443, "TCP", canary=True)
    cases = [
        denial("dns_udp", "10.32.0.21", 53, "UDP"),
        denial("dns_tcp", "10.32.0.21", 53, "TCP"),
        denial("https_private_pod", "10.32.0.22", 443, "TCP"),
        denial("https_private_service", "10.96.0.22", 443, "TCP"),
        denial("https_link_local", "169.254.1.1", 443, "TCP"),
    ]
    # A CNI may report the destination after Service DNAT.
    cases[3]["service_endpoints"] = [
        {"ip": "10.32.0.23", "port": 8443, "uid": "listener-uid", "ready": True}
    ]
    cases[3]["listener_before"]["ip"] = "10.32.0.23"
    cases[3]["listener_after"]["ip"] = "10.32.0.23"
    cases[3]["endpoint_slice_digest"] = RAW
    cases[3]["endpoint_slice_after_digest"] = RAW
    cases[3]["verdict"]["destination_ip"] = "10.32.0.23"
    cases[3]["verdict"]["destination_port"] = 8443
    return {
        "source_sha": SHA,
        "image_source_sha": SHA,
        "image_digest": DIGEST,
        "source_tree_clean": True,
        "image_provenance_digest": RAW,
        "environment": {
            "name": "isolated-test",
            "cluster_uid": "cluster-uid",
            "cni_name": "example-cni",
            "cni_version": "1.2.3",
            "policy_inventory_digest": RAW,
            "cni_inventory_digest": RAW,
            "policy_uids": ["policy-uid"],
            "families": ["IPv4"],
            "pod_cidrs": ["10.32.0.0/16"],
            "service_cidrs": ["10.96.0.0/16"],
            "resolver_ips": ["10.96.0.10"],
        },
        "canaries": [canary],
        "egress_denials": cases,
        "jwks": {
            "key_a": "key-a",
            "key_b": "key-b",
            "configured_url": "https://backend.example/.well-known/jwks.json",
            "internal_mtls_enabled": True,
            "published_before": {
                "at": "2026-11-05T10:02:00Z",
                "keys": ["key-a"],
                "raw_digest": RAW,
            },
            "published_after": {
                "at": "2026-11-05T10:02:10Z",
                "keys": ["key-a", "key-b"],
                "raw_digest": RAW,
                "jwks_document_digest": RAW,
            },
            "refresh_interval_seconds": 10,
            "expected_issuer": "test-issuer",
            "expected_audience": "test-audience",
            "token_b": {
                "ref": "token-b",
                "token_digest": "sha256:" + "d" * 64,
                "jti_ref": "synthetic-jti",
                "key": "key-b",
                "issuer": "test-issuer",
                "audience": "test-audience",
                "issued_at": "2026-11-05T10:00:00Z",
                "not_before": "2026-11-05T10:00:00Z",
                "expires_at": "2026-11-05T10:05:00Z",
                "active": True,
                "revoked": False,
                "signature_valid": True,
                "validation_digest": RAW,
            },
            "replicas": [
                {
                    "before": p,
                    "after": p_after,
                    "key_a_before": grpc_event(p, 2, "InvalidArgument", "token-a"),
                    "key_b_before": grpc_event(p, 4, "Unauthenticated", "token-b"),
                    "fetch": {
                        "pod_uid": p["uid"],
                        "container_id": p["container_id"],
                        "source_ip": p["ip"],
                        "timestamp": "2026-11-05T10:02:15Z",
                        "url": "https://backend.example/.well-known/jwks.json",
                        "status": 200,
                        "redirected": False,
                        "tls_verified": True,
                        "client_identity_verified": True,
                        "jwks_document_digest": RAW,
                        "raw_digest": RAW,
                    },
                    "key_b_after": grpc_event(p, 16, "InvalidArgument", "token-b"),
                    "key_a_after": grpc_event(p, 18, "InvalidArgument", "token-a"),
                }
            ],
            "expected_replica_uids": [p["uid"]],
        },
    }


def expect_incomplete(item: dict) -> None:
    if not checker().assess(item, SHA):
        pytest.fail("inconsistent evidence was accepted for owner review")


def test_consistent_fixture_is_eligible_for_manual_review() -> None:
    errors = checker().assess(receipt(), SHA)
    if errors:
        pytest.fail(f"consistent synthetic evidence was rejected: {errors}")


@pytest.mark.parametrize("field", ["source_sha", "image_source_sha", "image_digest"])
def test_source_and_image_must_match_exactly(field: str) -> None:
    item = receipt()
    item[field] = "incorrect"
    expect_incomplete(item)


@pytest.mark.parametrize(
    "field",
    ["cni_name", "cni_version", "cni_inventory_digest", "policy_inventory_digest"],
)
def test_cni_and_policy_inventory_are_required(field: str) -> None:
    item = receipt()
    item["environment"][field] = ""
    expect_incomplete(item)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["post"].update(exit_code=1),
        lambda c: c["pre"].update(destination_ip="10.32.0.99"),
        lambda c: c["source_after"].update(uid="different-pod"),
        lambda c: c["verdict"].update(source_ip="10.32.0.99"),
        lambda c: c["verdict"].update(timestamp="2026-11-05T10:03:03Z"),
        lambda c: c["verdict"].update(direction="ingress"),
        lambda c: c["verdict"].update(action="allow"),
        lambda c: c["verdict"].update(policy_uid=""),
    ],
)
def test_unattributed_denial_or_missing_control_is_inconclusive(mutation) -> None:
    item = receipt()
    mutation(item["egress_denials"][0])
    expect_incomplete(item)


def test_service_verdict_requires_matching_endpoint_slice() -> None:
    item = receipt()
    item["egress_denials"][3]["service_endpoints"][0]["ip"] = "10.32.0.99"
    expect_incomplete(item)


def test_dns_controls_must_return_the_expected_answer() -> None:
    item = receipt()
    item["egress_denials"][0]["post"]["response"]["answer"] = "192.0.2.2"
    expect_incomplete(item)


def test_canary_must_be_separate_from_the_workload_under_test() -> None:
    item = receipt()
    item["canaries"][0] = denial("canary", "10.32.0.20", 8443, "TCP")
    expect_incomplete(item)


def test_service_control_requires_one_stable_ready_endpoint() -> None:
    item = receipt()
    item["egress_denials"][3]["service_endpoints"].append(
        {"ip": "10.32.0.24", "port": 8443, "uid": "other-uid", "ready": True}
    )
    expect_incomplete(item)


def test_rotation_must_use_the_same_synthetic_token_bytes() -> None:
    item = receipt()
    item["jwks"]["replicas"][0]["key_b_after"]["token_digest"] = "sha256:" + "f" * 64
    expect_incomplete(item)


def test_policy_probe_source_process_matches_the_rotation_process() -> None:
    item = receipt()
    for case in item["egress_denials"]:
        case["source_before"]["container_id"] = "containerd://different-process"
        case["source_after"]["container_id"] = "containerd://different-process"
    expect_incomplete(item)


def test_control_and_source_must_not_share_one_network_namespace() -> None:
    item = receipt()
    case = item["egress_denials"][0]
    namespace = case["source_before"]["pod_network_namespace"]
    for phase in ("control_before", "control_after"):
        case[phase]["pod_network_namespace"] = namespace
        case[phase]["diagnostic_network_namespace"] = namespace
    expect_incomplete(item)


def test_key_sets_must_be_structured_arrays() -> None:
    item = receipt()
    item["jwks"]["published_before"]["keys"] = "key-a"
    expect_incomplete(item)


def test_denial_requires_a_stable_destination_identity() -> None:
    item = receipt()
    item["egress_denials"][2]["listener_after"] = {
        "uid": "different-listener",
        "ip": "10.32.0.22",
        "observed_at": "2026-11-05T10:04:00Z",
        "raw_digest": RAW,
    }
    expect_incomplete(item)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda j: j["replicas"][0]["fetch"].update(
            url="https://unrelated.example/jwks"
        ),
        lambda j: j["replicas"][0]["fetch"].update(tls_verified=False),
        lambda j: j["replicas"][0]["fetch"].update(client_identity_verified=False),
        lambda j: j["replicas"][0]["key_b_after"].update(
            message="an unrelated invalid argument"
        ),
    ],
)
def test_refresh_observes_exact_endpoint_and_auth_boundary(mutation) -> None:
    item = receipt()
    mutation(item["jwks"])
    expect_incomplete(item)


@pytest.mark.parametrize(
    "field,value",
    [
        ("host_network", True),
        ("diagnostic_network_namespace", "net:[another]"),
        ("diagnostic_privileged", True),
        ("diagnostic_run_as_non_root", False),
        ("diagnostic_allow_privilege_escalation", True),
        ("diagnostic_host_mounts", ["/host"]),
        ("diagnostic_added_capabilities", ["NET_ADMIN"]),
    ],
)
def test_source_must_be_the_safe_actual_pod_network_namespace(field, value) -> None:
    item = receipt()
    for case in item["egress_denials"]:
        case["source_before"][field] = value
        case["source_after"][field] = value
    expect_incomplete(item)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda j: j["replicas"][0]["after"].update(
            container_id="containerd://replacement"
        ),
        lambda j: j["replicas"][0]["after"].update(restart_count=1),
        lambda j: j["replicas"][0]["after"].update(started_at="2026-11-05T10:02:11Z"),
        lambda j: j["replicas"][0]["key_b_before"].update(status="InvalidArgument"),
        lambda j: j["replicas"][0]["key_b_after"].update(
            {"token_ref": "different-token"}
        ),
        lambda j: j["replicas"][0]["fetch"].update(pod_uid="other-replica"),
        lambda j: j["replicas"][0]["fetch"].update(timestamp="2026-11-05T10:02:09Z"),
        lambda j: j["published_after"]["keys"].remove("key-a"),
        lambda j: j["token_b"].update(revoked=True),
        lambda j: j["expected_replica_uids"].append("unobserved-replica"),
    ],
)
def test_jwks_refresh_requires_same_process_and_exact_rotation_evidence(
    mutation,
) -> None:
    item = receipt()
    mutation(item["jwks"])
    expect_incomplete(item)


def test_malformed_receipt_fails_closed() -> None:
    expect_incomplete({})


def test_cli_never_prints_untrusted_receipt_values(
    tmp_path, monkeypatch, capsys
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps({"unexpected": "sensitive-synthetic-value"}), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(path), "--expected-source", SHA])
    status = checker().main()
    output = capsys.readouterr()
    if status != 1 or "sensitive-synthetic-value" in output.out + output.err:
        pytest.fail("the CLI must fail closed without echoing receipt contents")


def test_cli_success_still_requires_owner_review(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(receipt()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(path), "--expected-source", SHA])
    status = checker().main()
    output = capsys.readouterr()
    if status != 0 or "Not audit acceptance" not in output.out:
        pytest.fail("a consistent receipt must still be identified as requiring review")
