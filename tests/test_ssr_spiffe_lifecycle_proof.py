"""Unit contracts do not substitute for the hosted live SPIRE proof."""

import argparse
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/kind/ssr_spiffe_lifecycle_proof.py"
SPEC = importlib.util.spec_from_file_location("ssr_lifecycle", PATH)
assert SPEC is not None and SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


def valid_receipt() -> dict:
    return {
        "selfID": "spiffe://example.org/frontend",
        "leafSHA256": "a" * 64,
        "leafNotAfterUnix": 4102444800,
        "issuerKeyID": "ab",
        "roots": ["ab", "cd"],
    }


def test_public_receipt_accepts_only_exact_identity_and_live_material() -> None:
    value = valid_receipt()
    assert proof.receipt(json.dumps(value), value["selfID"]) == value
    with pytest.raises(proof.ProofError):
        proof.receipt(json.dumps(value), "spiffe://example.org/other")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("leafSHA256", "private-key"),
        ("leafNotAfterUnix", 1),
        ("leafNotAfterUnix", True),
        ("issuerKeyID", "ff"),
        ("roots", []),
        ("roots", ["ab", "ab"]),
        ("roots", ["not-hex"]),
        ("privateKey", "must-not-be-accepted"),
    ],
)
def test_receipt_rejects_invalid_or_secret_bearing_payload(key, value) -> None:
    payload = valid_receipt()
    payload[key] = value
    with pytest.raises(proof.ProofError):
        proof.receipt(json.dumps(payload), payload["selfID"])


@pytest.mark.parametrize("value", [None, "", "null", "AA", "a-b", 123])
def test_authority_id_rejects_invalid_cli_response(value) -> None:
    with pytest.raises(proof.ProofError):
        proof.authority_id(value)


def lifecycle():
    return proof.Lifecycle(argparse.Namespace(
        namespace="proof", spire_namespace="spire", release="ue",
        trust_domain="example.org", image="fixture",
    ))


def test_routing_replaces_whole_selector_instead_of_merging() -> None:
    item = lifecycle()
    item.kubectl = Mock(return_value="")
    item.route({proof.LABEL: "frozen"})
    args = item.kubectl.call_args.args
    patch = json.loads(args[-1])
    assert "--type=json" in args
    assert patch == [{
        "op": "replace", "path": "/spec/selector",
        "value": {proof.LABEL: "frozen"},
    }]


def test_fixture_has_no_privileged_security_or_production_image() -> None:
    item = lifecycle()
    item.kubectl = Mock(return_value="")
    item.fixture("client", "ue-frontend", item.self_id, "idle", item.peer_id)
    manifest = json.loads(item.kubectl.call_args_list[0].kwargs["data"])
    spec = manifest["spec"]
    container = spec["containers"][0]
    assert container["image"] == "fixture"
    assert container["ports"] == [{"name": "http", "containerPort": 8000, "protocol": "TCP"}]
    assert spec["automountServiceAccountToken"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert dict((v["name"], v["value"]) for v in container["env"])["FIXTURE_URL"].endswith("/health/ready")


def test_proxy_observation_does_not_treat_any_output_as_success() -> None:
    item = lifecycle()
    item.kubectl = Mock(return_value="STATUS=200\n")
    assert item.proxy_status() == 200
    for value in ("200", "STATUS=200\nSTATUS=502\n", "STATUS=000\n"):
        item.kubectl.return_value = value
        with pytest.raises(proof.ProofError):
            item.proxy_status()


def test_failure_restores_backend_service_selector() -> None:
    item = lifecycle()
    selector = {"app.kubernetes.io/component": "backend"}
    item.kubectl = Mock(return_value=json.dumps({"spec": {"selector": selector}}))
    item.identities = Mock(return_value={"baseline": []})
    item.fixture = Mock(side_effect=proof.ProofError("fixture unavailable"))
    item.route = Mock()
    with pytest.raises(proof.ProofError):
        item.run()
    item.route.assert_called_once_with(selector)


def test_source_outage_restores_selector_even_when_stream_fails() -> None:
    item = lifecycle()
    original = {"kubernetes.io/os": "linux"}
    item.command = Mock(return_value=json.dumps({
        "spec": {"template": {"spec": {"nodeSelector": original}}},
    }))
    item.stream = Mock(side_effect=proof.ProofError("stream unavailable"))
    with pytest.raises(proof.ProofError):
        item.source_failure("client")
    patch_calls = [
        call for call in item.command.call_args_list
        if "patch" in call.args
    ]
    assert len(patch_calls) == 1
    restored = json.loads(patch_calls[0].args[-1])
    assert restored["spec"]["template"]["spec"]["nodeSelector"] == {
        **original, proof.LABEL: None,
    }
