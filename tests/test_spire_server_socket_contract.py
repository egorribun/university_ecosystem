"""The SPIRE server's default local admin socket must have a confined writable mount."""

from __future__ import annotations

import copy
import re
from pathlib import Path, PurePosixPath

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "k8s/spire/spire-server.yaml"
SOCKET_PARENT = str(PurePosixPath("/") / "tmp" / "spire-server" / "private")


def _server_documents() -> tuple[dict, dict]:
    docs = list(yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")))
    config = next(doc for doc in docs if doc and doc.get("kind") == "ConfigMap")
    statefulset = next(doc for doc in docs if doc and doc.get("kind") == "StatefulSet")
    return config, statefulset


def _assert_admin_socket_is_writable_and_confined(
    config: dict, statefulset: dict
) -> None:
    # SPIRE 1.15.3 defaults both its server API and CLI to this socket path.
    assert not re.search(
        r"^\s*socket_path\s*=", config["data"]["server.conf"], re.MULTILINE
    )
    spec = statefulset["spec"]["template"]["spec"]
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["runAsUser"] == 1000
    assert spec["securityContext"]["runAsGroup"] == 1000
    assert spec["securityContext"]["fsGroup"] == 1000
    server = next(c for c in spec["containers"] if c["name"] == "spire-server")
    assert ":1.15.3@sha256:" in server["image"]
    assert server["securityContext"]["readOnlyRootFilesystem"] is True
    assert server["securityContext"]["allowPrivilegeEscalation"] is False
    assert server["securityContext"]["capabilities"]["drop"] == ["ALL"]
    mounts = [m for m in server["volumeMounts"] if m["mountPath"] == SOCKET_PARENT]
    assert len(mounts) == 1
    mount = mounts[0]
    assert mount.get("readOnly", False) is False
    assert "subPath" not in mount and "subPathExpr" not in mount
    volume = next(v for v in spec["volumes"] if v["name"] == mount["name"])
    assert set(volume) == {"name", "emptyDir"}
    assert volume["emptyDir"] == {}


def test_default_admin_socket_has_dedicated_writable_volume() -> None:
    _assert_admin_socket_is_writable_and_confined(*_server_documents())


@pytest.mark.parametrize(
    "mutation",
    ("missing", "broad", "readonly", "hostpath", "wrong_group", "writable_root"),
)
def test_admin_socket_contract_rejects_unusable_or_unconfined_mount(
    mutation: str,
) -> None:
    config, statefulset = copy.deepcopy(_server_documents())
    spec = statefulset["spec"]["template"]["spec"]
    server = next(c for c in spec["containers"] if c["name"] == "spire-server")
    mount = next(m for m in server["volumeMounts"] if m["mountPath"] == SOCKET_PARENT)
    volume = next(v for v in spec["volumes"] if v["name"] == mount["name"])
    if mutation == "missing":
        server["volumeMounts"].remove(mount)
    elif mutation == "broad":
        mount["mountPath"] = str(PurePosixPath(SOCKET_PARENT).parents[1])
    elif mutation == "readonly":
        mount["readOnly"] = True
    elif mutation == "hostpath":
        volume["hostPath"] = {"path": "/var/lib/spire"}
        del volume["emptyDir"]
    elif mutation == "wrong_group":
        spec["securityContext"]["fsGroup"] = 1
    else:
        server["securityContext"]["readOnlyRootFilesystem"] = False
    with pytest.raises((AssertionError, StopIteration)):
        _assert_admin_socket_is_writable_and_confined(config, statefulset)
