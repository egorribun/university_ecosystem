"""AUD-373: the SPIRE agent socket, the kind CSI install and the operator README must agree.

The chart mounts the Workload API socket into pods through the csi.spiffe.io driver. The
driver exposes the host directory of its agentSocketPath. The agent writes socket_path on
that same directory. The CSI driver itself is installed at runtime (kind script) or by an
operator (README); it is not committed here, so no new Trivy findings are introduced.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENT_MANIFEST = ROOT / "k8s" / "spire" / "spire-agent.yaml"
README = ROOT / "k8s" / "spire" / "README.md"
KIND_SCRIPT = ROOT / "scripts" / "kind" / "aud373_internal_mtls_proof.sh"
SOCKET_PATTERN = re.compile(r'socket_path = "([^"]+)"')
KIND_SOCKET_PATTERN = re.compile(
    r'^readonly AGENT_SOCKET_PATH="([^"]+)"$', re.MULTILINE
)
README_SET_PATTERN = re.compile(r"spiffe-csi-driver\.agentSocketPath=(\S+)")


def _agent_socket_path() -> str:
    agent = yaml.safe_load_all(AGENT_MANIFEST.read_text(encoding="utf-8"))
    configmap = next(doc for doc in agent if doc and doc.get("kind") == "ConfigMap")
    matches = SOCKET_PATTERN.findall(configmap["data"]["agent.conf"])
    assert len(matches) == 1
    return str(matches[0])


def _agent_socket_host_dir() -> str:
    agent = yaml.safe_load_all(AGENT_MANIFEST.read_text(encoding="utf-8"))
    daemonset = next(doc for doc in agent if doc and doc.get("kind") == "DaemonSet")
    volumes = daemonset["spec"]["template"]["spec"]["volumes"]
    socket_volume = next(v for v in volumes if v["name"] == "spire-agent-socket")
    return str(socket_volume["hostPath"]["path"])


def test_agent_socket_path_is_inside_the_mounted_host_directory() -> None:
    socket_path = _agent_socket_path()
    assert socket_path == "/run/spire/sockets/agent.sock"
    assert posixpath.dirname(socket_path) == _agent_socket_host_dir()


def test_kind_script_csi_socket_path_equals_the_agent_socket_path() -> None:
    match = KIND_SOCKET_PATTERN.search(KIND_SCRIPT.read_text(encoding="utf-8"))
    assert match is not None
    assert match.group(1) == _agent_socket_path()
    assert "spiffe-csi-driver.agentSocketPath=${AGENT_SOCKET_PATH}" in (
        KIND_SCRIPT.read_text(encoding="utf-8")
    )


def test_operator_readme_states_the_same_csi_socket_path() -> None:
    readme = README.read_text(encoding="utf-8")
    values = README_SET_PATTERN.findall(readme)
    assert values == [_agent_socket_path()]
    assert f"with `agentSocketPath={_agent_socket_path()}`" in readme


def test_no_committed_csi_driver_manifest_introduces_new_trivy_findings() -> None:
    assert not (ROOT / "k8s" / "spire" / "spiffe-csi-driver.yaml").exists()
