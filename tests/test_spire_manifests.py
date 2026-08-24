"""Security and startup contracts for the SPIRE Kubernetes manifests."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPIRE_VERSION = "1.15.2"


def _document(path: str, kind: str) -> dict:
    documents = yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8"))
    return next(document for document in documents if document.get("kind") == kind)


def _documents(path: str, kind: str) -> list[dict]:
    documents = yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8"))
    return [
        document for document in documents if document and document.get("kind") == kind
    ]


def test_spire_agent_uses_a_shell_capable_init_image_and_least_privilege() -> None:
    daemonset = _document("k8s/spire/spire-agent.yaml", "DaemonSet")
    pod = daemonset["spec"]["template"]["spec"]
    init = pod["initContainers"][0]
    agent = pod["containers"][0]

    assert init["image"].startswith("busybox:1.37.0-musl@sha256:")
    assert "spire-agent" not in init["image"]
    assert init["securityContext"]["allowPrivilegeEscalation"] is False
    assert init["securityContext"]["readOnlyRootFilesystem"] is True
    assert init["securityContext"]["capabilities"]["drop"] == ["ALL"]

    assert f"spire-agent:{SPIRE_VERSION}@sha256:" in agent["image"]
    assert agent["securityContext"]["allowPrivilegeEscalation"] is False
    assert agent["securityContext"]["readOnlyRootFilesystem"] is True
    assert agent["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert agent["securityContext"].get("privileged", False) is False
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert any(
        mount["name"] == "spire-agent-data" and mount["mountPath"] == "/run/spire/data"
        for mount in agent["volumeMounts"]
    )
    assert any(volume["name"] == "spire-agent-data" for volume in pod["volumes"])


def test_spire_server_runs_as_the_pinned_image_non_root_user() -> None:
    statefulset = _document("k8s/spire/spire-server.yaml", "StatefulSet")
    pod = statefulset["spec"]["template"]["spec"]
    server = pod["containers"][0]

    assert f"spire-server:{SPIRE_VERSION}@sha256:" in server["image"]
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "runAsGroup": 1000,
        "fsGroup": 1000,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    assert server["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }


def test_spire_uses_a_published_pem_bundle_for_secure_agent_bootstrap() -> None:
    server_config = _document("k8s/spire/spire-server.yaml", "ConfigMap")["data"][
        "server.conf"
    ]
    agent_config = _document("k8s/spire/spire-agent.yaml", "ConfigMap")["data"][
        "agent.conf"
    ]

    assert 'BundlePublisher "k8s_configmap"' in server_config
    assert 'configmap_name = "spire-bundle"' in server_config
    assert 'configmap_key = "bundle.crt"' in server_config
    assert 'namespace = "spire"' in server_config
    assert 'format = "pem"' in server_config
    assert "UpstreamAuthority" not in server_config
    assert 'trust_bundle_path = "/run/spire/bundle/bundle.crt"' in agent_config
    assert "insecure_bootstrap" not in agent_config

    bundle = next(
        config_map
        for config_map in _documents("k8s/spire/spire-rbac.yaml", "ConfigMap")
        if config_map["metadata"]["name"] == "spire-bundle"
    )
    assert bundle["metadata"]["namespace"] == "spire"


def test_spire_bundle_rbac_and_agent_mount_are_least_privilege() -> None:
    roles = _documents("k8s/spire/spire-rbac.yaml", "Role")
    bundle_role = next(
        role for role in roles if role["metadata"]["name"] == "spire-server-bundle-role"
    )
    assert bundle_role["metadata"]["namespace"] == "spire"
    assert bundle_role["rules"] == [
        {
            "apiGroups": [""],
            "resources": ["configmaps"],
            "resourceNames": ["spire-bundle"],
            "verbs": ["get", "patch"],
        }
    ]

    role_bindings = _documents("k8s/spire/spire-rbac.yaml", "RoleBinding")
    bundle_binding = next(
        binding
        for binding in role_bindings
        if binding["metadata"]["name"] == "spire-server-bundle-binding"
    )
    assert bundle_binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "spire-server", "namespace": "spire"}
    ]
    assert bundle_binding["roleRef"]["name"] == "spire-server-bundle-role"

    daemonset = _document("k8s/spire/spire-agent.yaml", "DaemonSet")
    pod = daemonset["spec"]["template"]["spec"]
    init = pod["initContainers"][0]
    agent = pod["containers"][0]
    assert any(
        volume.get("configMap", {}).get("name") == "spire-bundle"
        for volume in pod["volumes"]
    )
    for container in (init, agent):
        assert any(
            mount["name"] == "spire-bundle"
            and mount["mountPath"] == "/run/spire/bundle"
            and mount["readOnly"] is True
            for mount in container["volumeMounts"]
        )
    assert "/run/spire/bundle/bundle.crt" in init["command"][-1]
