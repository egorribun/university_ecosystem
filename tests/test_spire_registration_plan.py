"""Offline plan contracts: selectors come from render, never inferred defaults."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.plan_spire_registration import (
    COMPONENT,
    IDENTITY_FIELDS,
    INSTANCE,
    MAX_RENDER_BYTES,
    build_plan,
    main,
)

PARENT = "spiffe://university.ecosystem/spire/agent/k8s_psat/university-cluster/00000000-0000-4000-8000-000000000001"
NAMESPACE = "university-ecosystem"
RELEASE = "reviewed-release"


def _documents() -> list[dict[str, Any]]:
    identities = {
        component: f"spiffe://university.ecosystem/ns/{NAMESPACE}/sa/{'app' if component == 'backend' else component}"
        for component in IDENTITY_FIELDS
    }
    documents = []
    for component, (flag, field) in IDENTITY_FIELDS.items():
        environ = {flag: "true", field: identities[component]}
        if component == "backend":
            environ["INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS"] = ",".join(
                identities.values()
            )
        else:
            peer = (
                "FP_BACKEND_SPIFFE_ID"
                if component == "file-processor"
                else "BACKEND_SPIFFE_ID"
            )
            environ[peer] = identities["backend"]
        documents.append(
            {
                "kind": "Deployment",
                "metadata": {
                    "namespace": NAMESPACE,
                    "labels": {COMPONENT: component, INSTANCE: RELEASE},
                },
                "spec": {
                    "template": {
                        "spec": {
                            "serviceAccountName": f"{RELEASE}-{component}",
                            "containers": [
                                {
                                    "env": [
                                        {"name": key, "value": value}
                                        for key, value in environ.items()
                                    ]
                                    + [
                                        {
                                            "name": "UNRELATED_REFERENCE",
                                            "valueFrom": {
                                                "secretKeyRef": {"name": "private"}
                                            },
                                        }
                                    ]
                                }
                            ],
                        }
                    }
                },
            }
        )
    return documents


def _plan(documents: list[Any]) -> dict[str, Any]:
    return build_plan(documents, namespace=NAMESPACE, release=RELEASE, parent_id=PARENT)


def _environment(document: dict[str, Any]) -> list[dict[str, Any]]:
    return document["spec"]["template"]["spec"]["containers"][0]["env"]


def test_plan_binds_logical_backend_id_to_actual_rendered_service_account() -> None:
    plan = _plan([*_documents(), None, {"kind": "ConfigMap"}])
    assert plan["mode"] == "plan-only"
    assert len(plan["entries"]) == 4
    backend = next(item for item in plan["entries"] if item["component"] == "backend")
    assert backend["spiffe_id"].endswith("/sa/app")
    assert backend["service_account"] == f"{RELEASE}-backend"
    assert backend["argv"] == [
        "/opt/spire/bin/spire-server",
        "entry",
        "create",
        "-parentID",
        PARENT,
        "-spiffeID",
        backend["spiffe_id"],
        "-selector",
        f"k8s:ns:{NAMESPACE}",
        "-selector",
        f"k8s:sa:{RELEASE}-backend",
        "-x509SVIDTTL",
        "3600",
    ]
    assert "private" not in json.dumps(plan)
    assert "-admin" not in json.dumps(plan)


@pytest.mark.parametrize(
    "parent",
    [
        PARENT.rsplit("/", 1)[0],
        PARENT.replace("university.ecosystem", "another.example"),
        PARENT + "\n",
        PARENT.replace("/university-cluster/", "/../"),
    ],
)
def test_parent_is_explicit_concrete_and_same_domain(parent: str) -> None:
    with pytest.raises(ValueError):
        build_plan(_documents(), namespace=NAMESPACE, release=RELEASE, parent_id=parent)


@pytest.mark.parametrize("field", ["namespace", "release"])
def test_no_default_selector_scope(field: str) -> None:
    arguments = {"namespace": NAMESPACE, "release": RELEASE, "parent_id": PARENT}
    arguments[field] = ""
    with pytest.raises(ValueError):
        build_plan(_documents(), **arguments)


@pytest.mark.parametrize(
    "mutation",
    [
        "namespace",
        "duplicate",
        "missing",
        "account",
        "containers",
        "flag",
        "peer",
        "extra_allowed",
        "duplicate_env",
        "reference_identity",
        "same_account",
    ],
)
def test_ambiguous_or_incomplete_render_is_rejected(mutation: str) -> None:
    documents = _documents()
    first = documents[0]
    spec = first["spec"]["template"]["spec"]
    if mutation == "namespace":
        first["metadata"]["namespace"] = "default"
    elif mutation == "duplicate":
        documents.append(copy.deepcopy(first))
    elif mutation == "missing":
        documents.pop(0)
    elif mutation == "account":
        spec.pop("serviceAccountName")
    elif mutation == "containers":
        spec["containers"] = []
    elif mutation == "flag":
        _environment(first)[0]["value"] = "false"
    elif mutation == "peer":
        _environment(documents[1])[2]["value"] += "/other"
    elif mutation == "extra_allowed":
        _environment(first)[2]["value"] += ",spiffe://university.ecosystem/other"
    elif mutation == "duplicate_env":
        _environment(first).append(copy.deepcopy(_environment(first)[0]))
    elif mutation == "reference_identity":
        _environment(first)[1].pop("value")
    elif mutation == "same_account":
        documents[1]["spec"]["template"]["spec"]["serviceAccountName"] = spec[
            "serviceAccountName"
        ]
    with pytest.raises(ValueError):
        _plan(documents)


def test_public_file_processor_does_not_receive_a_registration() -> None:
    documents = _documents()
    inactive_id = _environment(documents[-1])[1]["value"]
    documents[-1]["spec"]["template"]["spec"]["containers"][0]["env"] = []
    allowlist = _environment(documents[0])[2]
    allowlist["value"] = ",".join(
        value for value in allowlist["value"].split(",") if value != inactive_id
    )
    assert len(_plan(documents)["entries"]) == 3


def test_disabled_ws_hub_has_no_inferred_registration() -> None:
    documents = _documents()
    ws_hub = documents.pop(2)
    identity = _environment(ws_hub)[1]["value"]
    allowlist = _environment(documents[0])[2]
    allowlist["value"] = ",".join(
        value for value in allowlist["value"].split(",") if value != identity
    )
    assert {entry["component"] for entry in _plan(documents)["entries"]} == {
        "backend",
        "gateway",
        "file-processor",
    }


def test_rendered_service_account_uses_dns_subdomain_not_short_label_limit() -> None:
    documents = _documents()
    account = "a" * 53 + "-file-processor"
    documents[-1]["spec"]["template"]["spec"]["serviceAccountName"] = account
    processor = next(
        item
        for item in _plan(documents)["entries"]
        if item["component"] == "file-processor"
    )
    assert processor["service_account"] == account


def test_cli_writes_only_hash_bound_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rendered = tmp_path / "rendered.yaml"
    rendered.write_text(yaml.safe_dump_all(_documents()), encoding="utf-8")
    arguments = [
        "--rendered",
        str(rendered),
        "--namespace",
        NAMESPACE,
        "--release",
        RELEASE,
        "--parent-id",
        PARENT,
    ]
    assert main(arguments) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["rendered_sha256"]) == 64
    assert len(plan["entries"]) == 4
    with pytest.raises(SystemExit):
        main([*arguments, "--apply"])


@pytest.mark.parametrize(
    "content",
    [
        b"kind: Deployment\nkind: ConfigMap\n",
        b"\xff",
        b"x" * (MAX_RENDER_BYTES + 1),
        b"secret: [private-value",
    ],
)
def test_cli_rejects_unsafe_input_without_echoing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes
) -> None:
    rendered = tmp_path / "rendered.yaml"
    rendered.write_bytes(content)
    assert (
        main(
            [
                "--rendered",
                str(rendered),
                "--namespace",
                NAMESPACE,
                "--release",
                RELEASE,
                "--parent-id",
                PARENT,
            ]
        )
        == 2
    )
    result = capsys.readouterr()
    assert result.out == ""
    assert "private-value" not in result.err


def test_registration_wrapper_contains_no_cluster_mutation() -> None:
    script = (
        Path(__file__).resolve().parents[1] / "k8s/spire/register-workloads.sh"
    ).read_text()
    assert "exec python" in script
    assert "plan_spire_registration.py" in script
    assert "kubectl exec" not in script
    assert "entry create" not in script
    assert "ns/default" not in script
