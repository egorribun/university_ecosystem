"""Unit contracts do not substitute for the hosted live SPIRE proof."""

import argparse
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

PATH = (
    Path(__file__).resolve().parents[1] / "scripts/kind/ssr_spiffe_lifecycle_proof.py"
)
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
    return proof.Lifecycle(
        argparse.Namespace(
            namespace="proof",
            spire_namespace="spire",
            release="ue",
            trust_domain="example.org",
            image="fixture",
        )
    )


def test_routing_replaces_whole_selector_instead_of_merging() -> None:
    item = lifecycle()
    item.kubectl = Mock(return_value="")
    item.route({proof.LABEL: "frozen"})
    args = item.kubectl.call_args.args
    patch = json.loads(args[-1])
    assert "--type=json" in args
    assert patch == [
        {
            "op": "replace",
            "path": "/spec/selector",
            "value": {proof.LABEL: "frozen"},
        }
    ]


def test_fixture_has_no_privileged_security_or_production_image() -> None:
    item = lifecycle()
    item.kubectl = Mock(return_value="")
    item.fixture("client", "ue-frontend", item.self_id, "idle", item.peer_id)
    manifest = json.loads(item.kubectl.call_args_list[0].kwargs["data"])
    spec = manifest["spec"]
    container = spec["containers"][0]
    assert container["image"] == "fixture"
    assert container["ports"] == [
        {"name": "http", "containerPort": 8000, "protocol": "TCP"}
    ]
    assert spec["automountServiceAccountToken"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert dict((v["name"], v["value"]) for v in container["env"])[
        "FIXTURE_URL"
    ].endswith("/health/ready")


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
    item.command = Mock(
        return_value=json.dumps(
            {
                "spec": {"template": {"spec": {"nodeSelector": original}}},
            }
        )
    )
    item.stream = Mock(side_effect=proof.ProofError("stream unavailable"))
    with pytest.raises(proof.ProofError):
        item.source_failure("client")
    patch_calls = [call for call in item.command.call_args_list if "patch" in call.args]
    assert len(patch_calls) == 1
    restored = json.loads(patch_calls[0].args[-1])
    assert restored["spec"]["template"]["spec"]["nodeSelector"] == {
        **original,
        proof.LABEL: None,
    }


@pytest.mark.parametrize(
    ("failure", "last_check"),
    [
        ("peer", "ssr-live-production-peer-renewal"),
        ("cleanup", "ssr-live-fixture-cleanup"),
        ("retirement", "ssr-live-serving-fixture-retirement"),
        ("restart", "ssr-live-application-restart-invariant"),
        (None, None),
    ],
)
def test_final_lifecycle_diagnostics_keep_failures_fatal(
    monkeypatch, capsys, failure, last_check
) -> None:
    from contextlib import nullcontext

    item = lifecycle()
    state = {"issuer": "ab", "roots": ["ab"]}
    original = {"backend": "production"}
    active = set()
    production_observations = []
    retirement_failed = False

    def material(identity):
        return {
            "selfID": identity,
            "leafSHA256": ("a" if state["issuer"] == "ab" else "b") * 64,
            "leafNotAfterUnix": 4102444800,
            "issuerKeyID": state["issuer"],
            "roots": list(state["roots"]),
        }

    frozen = material(item.peer_id)

    def command(*args, **kwargs):
        nonlocal retirement_failed
        if args[0] == "get":
            return json.dumps({"spec": {"selector": original}})
        if args[0] == "logs":
            return json.dumps(frozen)
        if args[0] == "delete":
            if (
                failure == "retirement"
                and args[2] == "frozen"
                and not retirement_failed
            ):
                retirement_failed = True
                raise proof.ProofError("fixture retirement failed")
            if failure == "cleanup" and args[2] == "client":
                raise proof.ProofError("secret-bearing command output")
            active.remove(args[2])
        return "CHECK=200"

    def ca(action, *args):
        if action == "prepare":
            state["roots"] = ["ab", "cd"]
            return {"prepared_authority": {"authority_id": "cd"}}
        if action == "activate":
            state["issuer"] = "cd"
        if action == "revoke":
            state["roots"] = ["cd"]
        return {"active": {"authority_id": state["issuer"]}}

    def fixture(name, *args):
        item.pods.append(name)
        active.add(name)
        return name

    def peer(client):
        if state["issuer"] == "cd":
            # Both post-rotation samples must exclude all serving fixtures,
            # while retaining the observer used for the authenticated request.
            assert active == {"client", "backend-client", "control"}
            production_observations.append(client)
        value = material(item.peer_id)
        if failure == "peer" and state["issuer"] == "cd":
            value["leafSHA256"] = "a" * 64
        return value

    def wait(check, **kwargs):
        value = check()
        assert value
        return value

    item.kubectl = Mock(side_effect=command)
    item.fixture = Mock(side_effect=fixture)
    item.route = Mock()
    item.source_failure = Mock()
    item.stream = Mock(side_effect=lambda: nullcontext())
    item.inspect = Mock(side_effect=lambda pod, identity: material(identity))
    item.peer = Mock(side_effect=peer)
    item.ca = Mock(side_effect=ca)
    item.proxy_status = Mock(side_effect=[200, 502, 200, 200, 502, 200, 200, 200])
    item.identities = Mock(
        side_effect=[
            {"pods": []},
            {"pods": []},
            {"pods": ["restarted"]} if failure == "restart" else {"pods": []},
        ]
    )
    monkeypatch.setattr(proof, "wait_for", wait)

    if failure:
        with pytest.raises(proof.ProofError):
            item.run()
    else:
        item.run()
    output = capsys.readouterr().out
    assert "secret-bearing" not in output
    if failure:
        assert f"CHECK {last_check}\n" in output
        assert "PASS ssr-live-production-backend-recovered" not in output
    else:
        assert "PASS ssr-live-production-backend-recovered" in output
    if failure != "cleanup":
        assert "PASS ssr-live-fixture-cleanup" in output
    item.route.assert_called_with(original)
    if failure != "cleanup":
        assert not active
    assert production_observations == (
        [] if failure == "retirement" else ["client", "client"]
    )


def test_fixture_retirement_tracks_success_and_retries_failures() -> None:
    item = lifecycle()
    item.pods = ["client", "frozen", "fresh"]
    item.kubectl = Mock(side_effect=[proof.ProofError("delete failed"), ""])
    with pytest.raises(proof.ProofError):
        item.delete_fixture("frozen")
    assert item.pods == ["client", "frozen", "fresh"]
    item.delete_fixture("frozen")
    assert item.pods == ["client", "fresh"]
    assert item.kubectl.call_args.args == (
        "delete",
        "pod",
        "frozen",
        "--wait=true",
        "--timeout=60s",
    )
    assert item.kubectl.call_args.kwargs == {"timeout": 70}
