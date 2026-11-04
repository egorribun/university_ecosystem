"""Offline AUD-251 source contract; this does not establish live authorization.

The named role deliberately retains nodes/proxy GET for kubelet compatibility.
That permission may also authorize WebSocket exec and is not a read-only grant.
This test cannot detect other live bindings or establish kubelet behavior.

Acceptance still requires, for every target cluster, a namespace-aware review
of the service account's effective grants (including group and other bindings),
live authorization checks, and successful agent/workload attestation. Replacing
the compatibility grant with nodes/pods additionally requires proof on every
deployed kubelet that /pods works with the narrow grant and nodes/proxy denied.
Otherwise the remaining GET exposure needs an explicit risk decision.
"""

import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPIRE = ROOT / "k8s" / "spire"


def _load(name: str) -> list[dict]:
    return list(yaml.safe_load_all((SPIRE / name).read_text(encoding="utf-8")))


def _one(documents: list[dict], kind: str, name: str) -> dict:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind and document["metadata"]["name"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_source_contract(
    rbac: list[dict], agent_documents: list[dict], server_documents: list[dict]
) -> None:
    role = _one(rbac, "ClusterRole", "spire-agent-role")
    assert "aggregationRule" not in role
    assert role["rules"] == [
        {"apiGroups": [""], "resources": ["nodes/proxy"], "verbs": ["get"]}
    ]

    account = _one(rbac, "ServiceAccount", "spire-agent")
    daemonset = _one(agent_documents, "DaemonSet", "spire-agent")
    pod = daemonset["spec"]["template"]["spec"]
    assert (
        account["metadata"]["namespace"]
        == daemonset["metadata"]["namespace"]
        == "spire"
    )
    assert pod["serviceAccountName"] == account["metadata"]["name"]

    binding = _one(rbac, "ClusterRoleBinding", "spire-agent-binding")
    assert binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "ClusterRole",
        "name": "spire-agent-role",
    }
    assert binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "spire-agent", "namespace": "spire"}
    ]

    agent = next(
        container
        for container in pod["containers"]
        if container["name"] == "spire-agent"
    )
    assert re.fullmatch(
        r"ghcr\.io/spiffe/spire-agent:1\.15\.3@sha256:[0-9a-f]{64}", agent["image"]
    )
    assert not agent.get("command")
    assert agent["args"] == ["-config", "/run/spire/config/agent.conf"]
    assert any(
        mount["name"] == "spire-config" and mount["mountPath"] == "/run/spire/config"
        for mount in agent["volumeMounts"]
    )
    assert any(
        volume["name"] == "spire-config"
        and volume.get("configMap", {}).get("name") == "spire-agent-config"
        for volume in pod["volumes"]
    )
    assert any(
        mount["name"] == "spire-token"
        and mount["mountPath"] == "/var/run/secrets/tokens"
        for mount in agent["volumeMounts"]
    )
    token_volume = next(
        volume for volume in pod["volumes"] if volume["name"] == "spire-token"
    )
    assert token_volume["projected"]["sources"] == [
        {
            "serviceAccountToken": {
                "path": "spire-agent-token",
                "expirationSeconds": 7200,
                "audience": "spire-server",
            }
        }
    ]

    agent_config_map = _one(agent_documents, "ConfigMap", "spire-agent-config")
    assert agent_config_map["metadata"]["namespace"] == "spire"
    agent_config = agent_config_map["data"]["agent.conf"]
    server_config_map = _one(server_documents, "ConfigMap", "spire-server-config")
    assert server_config_map["metadata"]["namespace"] == "spire"
    server_config = server_config_map["data"]["server.conf"]
    statefulset = _one(server_documents, "StatefulSet", "spire-server")
    assert statefulset["metadata"]["namespace"] == "spire"
    server_pod = statefulset["spec"]["template"]["spec"]
    server = next(
        container
        for container in server_pod["containers"]
        if container["name"] == "spire-server"
    )
    assert re.fullmatch(
        r"ghcr\.io/spiffe/spire-server:1\.15\.3@sha256:[0-9a-f]{64}",
        server["image"],
    )
    assert not server.get("command")
    assert server["args"] == ["-config", "/run/spire/config/server.conf"]
    assert any(
        mount["name"] == "spire-config" and mount["mountPath"] == "/run/spire/config"
        for mount in server["volumeMounts"]
    )
    assert any(
        volume["name"] == "spire-config"
        and volume.get("configMap", {}).get("name") == "spire-server-config"
        for volume in server_pod["volumes"]
    )
    assert re.findall(r'(?m)^\s*NodeAttestor\s+"([^"]+)"', agent_config) == ["k8s_psat"]
    assert re.findall(r'(?m)^\s*WorkloadAttestor\s+"([^"]+)"', agent_config) == ["k8s"]
    assert (
        'NodeAttestor "k8s_psat" { plugin_data { cluster = "university-cluster" '
        'token_path = "/var/run/secrets/tokens/spire-agent-token" } }'
        in " ".join(agent_config.split())
    )
    assert 'WorkloadAttestor "k8s" { plugin_data {} }' in " ".join(agent_config.split())
    assert re.findall(r'(?m)^\s*NodeAttestor\s+"([^"]+)"', server_config) == [
        "k8s_psat"
    ]
    assert (
        'NodeAttestor "k8s_psat" { plugin_data { clusters = { "university-cluster" = { '
        'service_account_allow_list = ["spire:spire-agent"] } } } }'
        in " ".join(server_config.split())
    )


def _sources() -> tuple[list[dict], list[dict], list[dict]]:
    return (
        _load("spire-rbac.yaml"),
        _load("spire-agent.yaml"),
        _load("spire-server.yaml"),
    )


def test_aud251_named_role_and_service_account_match_attestors() -> None:
    _assert_source_contract(*_sources())


@pytest.mark.parametrize(
    "change", ["namespace", "role_ref", "extra_verb", "workload_options", "allowlist"]
)
def test_aud251_contract_rejects_identity_or_permission_drift(change: str) -> None:
    rbac, agent, server = deepcopy(_sources())
    if change == "namespace":
        _one(rbac, "ClusterRoleBinding", "spire-agent-binding")["subjects"][0][
            "namespace"
        ] = "default"
    elif change == "role_ref":
        _one(rbac, "ClusterRoleBinding", "spire-agent-binding")["roleRef"]["name"] = (
            "other"
        )
    elif change == "extra_verb":
        _one(rbac, "ClusterRole", "spire-agent-role")["rules"][0]["verbs"].append(
            "watch"
        )
    elif change == "workload_options":
        config = _one(agent, "ConfigMap", "spire-agent-config")["data"]
        original = 'WorkloadAttestor "k8s" {\n    plugin_data {}'
        assert original in config["agent.conf"]
        config["agent.conf"] = config["agent.conf"].replace(
            original,
            'WorkloadAttestor "k8s" {\n    plugin_data { use_new_feature = true }',
        )
    else:
        config = _one(server, "ConfigMap", "spire-server-config")["data"]
        config["server.conf"] = config["server.conf"].replace(
            "spire:spire-agent", "default:spire-agent"
        )

    with pytest.raises(AssertionError):
        _assert_source_contract(rbac, agent, server)
