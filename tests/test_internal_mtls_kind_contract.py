"""AUD-373: static contract for the kind SPIFFE mTLS proof workflow and script.

The kind proof itself runs only in hosted CI (ubuntu-24.04 with Docker). These tests
pin what the workflow and script must keep: triggers, action SHAs, least permissions,
tool pins, the three behavioural checks, and cleanup in the EXIT trap.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import threading
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from tests.test_spiffe_identity import IDENTITY, leaf

ROOT = Path(
    os.environ.get("AUD373_REPO_ROOT", Path(__file__).resolve().parents[1])
).resolve()
WORKFLOW = ROOT / ".github" / "workflows" / "internal-mtls-kind.yml"
SCRIPT = Path(
    os.environ.get(
        "AUD373_SCRIPT", ROOT / "scripts" / "kind" / "aud373_internal_mtls_proof.sh"
    )
).resolve()
REFERENCE_WORKFLOW = ROOT / ".github" / "workflows" / "admin-smoke-monitoring.yml"
REQUIRED_PATHS = {
    "backend.Dockerfile",
    "backend.Dockerfile.dockerignore",
    ".dockerignore",
    "app/**",
    "native/**",
    "alembic/**",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    "go.mod",
    "go.sum",
    "gen/go/**",
    "services/pkg/logging/**",
    "services/pkg/spiffe/**",
    "k8s/README.md",
    "charts/**",
    "k8s/spire/**",
    "services/gateway/**",
    "app/server/**",
    "scripts/kind/**",
    ".github/workflows/internal-mtls-kind.yml",
}
USES_LINE = re.compile(r"^\s*(?:- )?uses: (.+)$", re.MULTILINE)
ACTION_REF = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$")


def _workflow() -> dict[str, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML parses the bare key "on" as boolean True.
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert isinstance(triggers, dict)
    return triggers


def _job() -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert list(jobs) == ["aud373-kind-proof"]
    job = jobs["aud373-kind-proof"]
    assert isinstance(job, dict)
    return job


def _steps() -> list[dict[str, Any]]:
    steps = _job()["steps"]
    assert isinstance(steps, list)
    return steps


def _step(name: str) -> dict[str, Any]:
    matches = [step for step in _steps() if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def test_triggers_cover_pull_requests_nightly_and_manual_runs() -> None:
    triggers = _triggers(_workflow())
    assert set(triggers) == {"pull_request", "schedule", "workflow_dispatch"}
    assert triggers["pull_request"]["branches"] == ["main"]
    paths = triggers["pull_request"]["paths"]
    assert set(paths) == REQUIRED_PATHS
    assert len(paths) == len(REQUIRED_PATHS), "duplicate path filters are forbidden"
    assert len(triggers["schedule"]) == 1
    assert triggers["schedule"][0]["cron"] == "17 3 * * *"


def _literal_or_subtree_matches(path: str, pattern: str) -> bool:
    """Match only this contract's literal and trailing /** GitHub path subset.

    This is not a general GitHub glob implementation. Unsupported syntax fails
    closed so future filter changes require an explicit contract update.
    """
    literal = pattern.removesuffix("/**")
    assert literal and not any(char in literal for char in "*?[]!+{}")
    if pattern.endswith("/**"):
        return path.startswith(literal + "/")
    return path == literal


@pytest.mark.parametrize(
    "path",
    [
        "backend.Dockerfile",
        ".dockerignore",
        "app/main.py",
        "app/core/config/mixins/mfa_settings.py",
        "app/server/internal_mtls.py",
        "native/rust_ext/src/lib.rs",
        "native/rust_ext/Cargo.lock",
        "alembic/versions/202611020000_mvp_baseline.py",
        "alembic/env.py",
        "alembic.ini",
        "pyproject.toml",
        "uv.lock",
        "go.mod",
        "go.sum",
        "gen/go/file_processor/v1/job.pb.go",
        "services/pkg/logging/logging.go",
        "services/pkg/spiffe/go.mod",
        "services/gateway/Dockerfile",
        "services/gateway/cmd/gateway/main.go",
        "charts/university-ecosystem/templates/network-policy.yaml",
        "k8s/spire/spire-server.yaml",
        "scripts/kind/aud373_internal_mtls_proof.sh",
        "k8s/README.md",
        ".github/workflows/internal-mtls-kind.yml",
    ],
)
def test_proof_input_paths_match_pull_request_filter(path: str) -> None:
    assert (ROOT / path).is_file(), "positive case must be a present proof input"
    paths = _triggers(_workflow())["pull_request"]["paths"]
    assert any(_literal_or_subtree_matches(path, pattern) for pattern in paths)


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/App.tsx",
        "frontend.Dockerfile",
        "docs/README.md",
        "README.md",
        "Dockerfile.test",
        "Dockerfile.test.dockerignore",
        "go.work",
        "scripts/dev/check.py",
        ".agents/skills/docker-expert/SKILL.md",
        "services/file-processor/Dockerfile",
        "services/ws-hub/go.mod",
        "services/pkg/metrics/metrics.go",
        "gen/python/file_processor.py",
        "k8s/README.md.bak",
        "k8s/backend.yaml",
        "services/pkg/spiffe-extra/go.mod",
        "services/gateway-extra/main.go",
        "app-extra/main.py",
        "charts-extra/values.yaml",
        "scripts/kind-extra/proof.sh",
        ".github/workflows/ci.yml",
        "nested/backend.Dockerfile",
        "backend.Dockerfile.bak",
        "uv.lock.bak",
    ],
)
def test_unrelated_paths_do_not_match_proof_filter(path: str) -> None:
    paths = _triggers(_workflow())["pull_request"]["paths"]
    assert not any(_literal_or_subtree_matches(path, pattern) for pattern in paths)


@pytest.mark.parametrize(
    "path",
    ["backend.Dockerfile.dockerignore", "services/gateway/Dockerfile.dockerignore"],
)
def test_docker_ignore_override_creation_matches_pull_request_filter(path: str) -> None:
    # Docker selects <Dockerfile>.dockerignore over the context-root ignore file
    # when present. Creation matters even though these overrides do not yet exist.
    paths = _triggers(_workflow())["pull_request"]["paths"]
    assert any(_literal_or_subtree_matches(path, pattern) for pattern in paths)


def test_top_level_and_job_permissions_are_read_only() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert _job()["permissions"] == {"contents": "read"}


def test_concurrency_cancels_only_stale_runs_for_the_same_pull_request() -> None:
    concurrency = _workflow()["concurrency"]
    assert concurrency["group"] == (
        "${{ github.event_name == 'pull_request' "
        "&& format('aud373-kind-pr-{0}', github.event.pull_request.number) "
        "|| format('aud373-kind-{0}-{1}-{2}', github.event_name, github.run_id, github.run_attempt) }}"
    )
    assert concurrency["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    )


def test_job_runner_and_timeout_are_pinned() -> None:
    job = _job()
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 40


def test_every_action_is_pinned_by_full_sha_with_version_comment() -> None:
    # The version comment is not part of the parsed YAML value, so read the raw line.
    raw_uses = USES_LINE.findall(WORKFLOW.read_text(encoding="utf-8"))
    assert raw_uses, "workflow must use pinned actions"
    for reference in raw_uses:
        assert ACTION_REF.fullmatch(reference), reference
    assert {reference.split("@", 1)[0] for reference in raw_uses} == {
        "actions/checkout",
        "actions/upload-artifact",
    }
    reference_uses = set(
        USES_LINE.findall(REFERENCE_WORKFLOW.read_text(encoding="utf-8"))
    )
    assert set(raw_uses) <= reference_uses


def test_checkout_does_not_persist_credentials() -> None:
    checkout = _step("Check out repository")
    assert checkout["with"]["persist-credentials"] is False


def test_no_continue_on_error_anywhere() -> None:
    assert "continue-on-error" not in WORKFLOW.read_text(encoding="utf-8")


def test_proof_step_runs_the_script_with_diagnostics_directory() -> None:
    proof = _step("Run kind mTLS proof")
    assert proof["run"] == "bash scripts/kind/aud373_internal_mtls_proof.sh"
    assert proof["env"]["UE_KIND_DIAG_DIR"] == "${{ runner.temp }}/aud373-diagnostics"


def test_diagnostics_artifact_is_uploaded_always_with_fourteen_day_retention() -> None:
    upload = _step("Upload diagnostics")
    assert upload["if"] == "always()"
    assert "continue-on-error" not in upload
    assert upload["with"]["path"] == "${{ runner.temp }}/aud373-diagnostics"
    assert upload["with"]["retention-days"] == 14
    assert upload["with"]["if-no-files-found"] == "error"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _pin(name: str) -> str:
    match = re.search(rf'^readonly {name}="([^"]+)"$', _script(), re.MULTILINE)
    assert match, name
    return match.group(1)


def test_script_is_strict_and_never_traces_secrets() -> None:
    script = _script()
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script
    assert "set -x" not in script
    assert "helm get values" not in script
    assert "get secret" not in script


def test_script_pins_tools_and_images_by_version_and_digest() -> None:
    assert _pin("KIND_VERSION") == "v0.31.0"
    assert _pin("KUBECTL_VERSION") == "v1.36.4"
    assert _pin("HELM_VERSION") == "v4.2.4"
    assert re.fullmatch(r"[0-9a-f]{64}", _pin("SPIRE_CHART_SHA256"))
    assert re.fullmatch(r"registry:2\.8\.3@sha256:[0-9a-f]{64}", _pin("REGISTRY_IMAGE"))
    assert '"${ROOT_DIR}/k8s/README.md"' in _script()
    assert '"${ROOT_DIR}/charts/university-ecosystem/values.yaml"' in _script()
    assert "readonly NODE_IMAGE=" not in _script()
    assert "readonly POSTGRES_IMAGE=" not in _script()


def test_script_downloads_are_checksum_verified() -> None:
    script = _script()
    assert "sha256sum --check --status" in script
    for url in ("KIND_URL", "KUBECTL_URL", "HELM_URL"):
        assert f'download_verified "${url}"' in script, url
    assert 'download_pinned "$SPIRE_CHART_URL" "$SPIRE_CHART_SHA256"' in script
    assert '"${KIND_URL}.sha256sum"' in script
    assert '"${KUBECTL_URL}.sha256"' in script
    assert '"${HELM_URL}.sha256sum"' in script


def _bash_command(command: str) -> subprocess.CompletedProcess[bytes]:
    bash = shutil.which("bash")
    assert bash is not None
    return subprocess.run(  # noqa: S603  # Fixed shell runs repository-owned functions and fixed fixtures.
        [bash, "-s"],
        input=command.encode(),
        capture_output=True,
        check=False,
        timeout=30,
    )


def _bash_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    drive = path.drive.rstrip(":").lower()
    assert len(drive) == 1 and path.is_absolute()
    return PurePosixPath("/mnt", drive, *path.parts[1:]).as_posix()


def _shell_function(name: str) -> str:
    script = _script()
    start = script.index(f"{name}() {{")
    end = script.index("\n}\n", start) + 3
    return script[start:end]


def test_registry_push_and_pull_addresses_use_the_published_ipv4_endpoint() -> None:
    command = f"""set -euo pipefail
{_shell_function("start_local_registry")}
{_shell_function("write_values_file")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
TRACE="$work/docker-trace"
HOSTS="$work/hosts.toml"
LOCAL_REGISTRY_NAME=owned-registry
REGISTRY_IMAGE=fixture
CLUSTER_NAME=owned-cluster
IMAGE_TAG=proof
RELEASE=ue
BACKEND_SVC=ue-university-ecosystem-backend
GATEWAY_SVC=ue-university-ecosystem-gateway
FILE_PROCESSOR_SVC=ue-university-ecosystem-file-processor
TRUST_DOMAIN=university.ecosystem
BACKEND_SPIFFE_ID=backend
GATEWAY_SPIFFE_ID=gateway
WS_HUB_SPIFFE_ID=ws-hub
FILE_PROCESSOR_SPIFFE_ID=file-processor
docker() {{
  case "$1" in
    inspect) if [[ "$*" == *--format* ]]; then printf '%064d\\n' 1; else return 1; fi ;;
    run) printf '%064d\\n' 1 ;;
    port) printf '127.0.0.1:32768\\n' ;;
    exec)
      printf '%s\\n' "$*" >> "$TRACE"
      if [[ "$*" == *--interactive* ]]; then cat > "$HOSTS"; fi ;;
  esac
}}
kind() {{ printf 'kind-node\\n'; }}
verify_registry_paths() {{ :; }}
log() {{ printf '%s\\n' "$*" >&2; }}
random_hex() {{ printf fixture; }}
random_fernet() {{ printf fixture; }}
write_secret_file() {{ :; }}
openssl() {{ :; }}
start_local_registry
write_values_file
printf 'BACKEND=%s\\nGATEWAY=%s\\nFILE_PROCESSOR=%s\\nINIT_REPOSITORY=%s\\n' \\
  "$BACKEND_IMAGE" "$GATEWAY_IMAGE" "$FILE_PROCESSOR_IMAGE" "$BACKEND_INIT_IMAGE_REPOSITORY"
cat "$TRACE"
cat "$HOSTS"
printf '%s\\n' '===VALUES==='
cat "$WORK_DIR/values.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    trace, values_source = result.stdout.decode().split("===VALUES===\n", 1)
    values = yaml.safe_load(values_source)
    address = "127.0.0.1:32768"
    backend = f"{address}/university-backend"
    gateway = f"{address}/university-gateway"
    file_processor = f"{address}/university-file-processor"
    init_repository = f"{address}/aud373/fixture/backend"
    assert f"BACKEND={backend}:proof" in trace
    assert f"GATEWAY={gateway}:proof" in trace
    assert f"FILE_PROCESSOR={file_processor}:proof" in trace
    assert f"INIT_REPOSITORY={init_repository}" in trace
    assert f"/etc/containerd/certs.d/{address}/hosts.toml" in trace
    assert 'host."http://owned-registry:5000"' in trace
    assert values["backend"]["image"]["repository"] == backend
    assert values["gateway"]["image"]["repository"] == gateway
    assert values["fileProcessor"]["image"]["repository"] == file_processor
    assert values["fileProcessor"]["enabled"] is False
    assert values["redis"]["metrics"]["passwordFileInitImage"]["repository"] == backend
    # The proof cluster has no Prometheus Operator; keep partition maintenance
    # enabled by the chart default and omit only its alert custom resource.
    assert values["partitionMaintenance"] == {"alert": {"enabled": False}}


@pytest.mark.parametrize(
    "endpoint",
    ["localhost:32768", "[::1]:32768", "127.0.0.2:32768", "127.0.0.1:", ""],
)
def test_registry_rejects_an_unexpected_published_endpoint(endpoint: str) -> None:
    command = f"""set -euo pipefail
{_shell_function("start_local_registry")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
LOCAL_REGISTRY_NAME=owned-registry
REGISTRY_IMAGE=fixture
REGISTRY_CREATED=0
docker() {{
  case "$1" in
    inspect) if [[ "$*" == *--format* ]]; then printf '%064d\\n' 1; else return 1; fi ;;
    run) printf '%064d\\n' 1 ;;
    port) printf '%s' {shlex.quote(endpoint)} ;;
    network|exec) touch "$work/unexpected-network-call" ;;
  esac
}}
log() {{ :; }}
if start_local_registry; then exit 1; fi
test "$REGISTRY_CREATED" = 1
test ! -e "$work/unexpected-network-call"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr


def test_image_pins_are_read_exactly_once_from_tracked_sources() -> None:
    script = _script()
    readme = (ROOT / "k8s" / "README.md").read_text(encoding="utf-8")
    values = (ROOT / "charts" / "university-ecosystem" / "values.yaml").read_text(
        encoding="utf-8"
    )
    node_statement = next(
        line.strip()
        for line in script.splitlines()
        if line.strip().startswith('node_image="$(read_tracked_pin ')
    )
    postgres_statement = next(
        line.strip()
        for line in script.splitlines()
        if line.strip().startswith('postgres_image="$(read_tracked_pin ')
    )
    node_statement = node_statement.replace(
        '"${ROOT_DIR}/k8s/README.md"', '"$work/node"'
    )
    postgres_statement = postgres_statement.replace(
        '"${ROOT_DIR}/charts/university-ecosystem/values.yaml"', '"$work/values"'
    )
    command = f"""set -eu
{_shell_function("read_tracked_pin")}
log() {{ printf '%s\\n' "$*" >&2; }}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/node" <<'END_NODE_SOURCE'
{readme}
END_NODE_SOURCE
cat > "$work/values" <<'END_VALUES_SOURCE'
{values}
END_VALUES_SOURCE
{node_statement}
{postgres_statement}
printf '%s\\n%s\\n' "$node_image" "$postgres_image"
cat "$work/node" "$work/node" > "$work/duplicate"
if ( {node_statement.replace("$work/node", "$work/duplicate")} ); then exit 1; fi
: > "$work/empty"
if ( {node_statement.replace("$work/node", "$work/empty")} ); then exit 1; fi
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    node_matches = re.findall(r"kindest/node:v1\.36\.4@sha256:[0-9a-f]{64}", readme)
    assert len(node_matches) == 1
    assert result.stdout.decode().splitlines() == [
        node_matches[0],
        yaml.safe_load(values)["backup"]["postgresImage"],
    ]


@pytest.mark.parametrize(
    ("checksum", "succeeds"),
    [
        ('printf "%s" "$digest"', True),
        ('printf "%s  tool\\n" "$digest"', True),
        ('printf "%s *tool\\n" "$digest"', True),
        ('printf "%s  other\\n" "$digest"', False),
        ('printf "%s\\n%s\\n" "$digest" "$digest"', False),
        ('printf "%s\\n" "${digest}x"', False),
        ('printf "%s\\n" "not-a-checksum"', False),
        ("printf ''", False),
        ('printf "%064d\\n" 0', False),
    ],
)
def test_official_checksum_verification_fails_closed(
    checksum: str, succeeds: bool
) -> None:
    command = f"""{_shell_function("verify_checksum")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
printf payload > "$work/artifact"
digest=$(sha256sum "$work/artifact")
digest=${{digest%% *}}
{checksum} > "$work/checksum"
verify_checksum "$work/checksum" "$work/artifact" tool
"""
    result = _bash_command(command)
    assert (result.returncode == 0) is succeeds, result.stderr


@pytest.mark.parametrize("failing_call", [1, 2])
def test_failed_artifact_or_checksum_download_cannot_be_verified(
    failing_call: int,
) -> None:
    command = f"""set -eu
{_shell_function("download_verified")}
calls=0
curl() {{
  calls=$((calls + 1))
  if [[ "$calls" == "{failing_call}" ]]; then return 22; fi
}}
verify_checksum() {{ return 0; }}
if download_verified artifact checksum destination name; then exit 1; fi
test "$calls" = "{failing_call}"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr


def test_owned_probe_policies_are_run_scoped_and_do_not_select_services() -> None:
    from secrets import token_hex

    function = _shell_function("install_probe_access")
    template = function.split("<<EOF\n", 1)[1].split("\nEOF\n", 1)[0]
    values = {
        "RUN_SUFFIX": token_hex(6),
        "NAMESPACE": "university-ecosystem",
        "RELEASE": "ue",
        "BACKEND_PORT": "8000",
        "GATEWAY_PORT": "8080",
    }
    for name, value in values.items():
        template = template.replace("${" + name + "}", value)
    assert "${" not in template
    policies = list(yaml.safe_load_all(template))
    assert len(policies) == 2
    probe = {"university-ecosystem.io/aud373-probe": values["RUN_SUFFIX"]}
    other_probe = {
        "university-ecosystem.io/aud373-probe": f"{int(values['RUN_SUFFIX'], 16) ^ 1:012x}"
    }
    by_component = {
        policy["spec"]["podSelector"]["matchLabels"][
            "app.kubernetes.io/component"
        ]: policy
        for policy in policies
    }
    assert set(by_component) == {"backend", "gateway"}
    for component, port in (("backend", 8000), ("gateway", 8080)):
        policy = by_component[component]
        assert policy["metadata"]["namespace"] == values["NAMESPACE"]
        assert policy["spec"] == {
            "podSelector": {
                "matchLabels": {
                    "app.kubernetes.io/name": "university-ecosystem",
                    "app.kubernetes.io/instance": "ue",
                    "app.kubernetes.io/component": component,
                }
            },
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [{"podSelector": {"matchLabels": probe}}],
                    "ports": [{"protocol": "TCP", "port": port}],
                }
            ],
        }
        allowed_probe = policy["spec"]["ingress"][0]["from"][0]["podSelector"][
            "matchLabels"
        ]
        assert all(probe.get(k) == v for k, v in allowed_probe.items())
        assert not all(other_probe.get(k) == v for k, v in allowed_probe.items())
        # Service endpoints require the release and component labels, neither
        # of which is on the run-specific probe.
        assert not all(
            probe.get(k) == v
            for k, v in policy["spec"]["podSelector"]["matchLabels"].items()
        )
    assert (
        '--labels="university-ecosystem.io/aud373-probe=${RUN_SUFFIX}"'
        in _shell_function("run_probe")
    )
    script = _script()
    assert script.index("  deploy_stack\n  install_probe_access\n  run_proofs\n") > 0


def test_probe_policy_rejects_invalid_run_identity_without_kubectl() -> None:
    command = f"""set -euo pipefail
{_shell_function("install_probe_access")}
RUN_SUFFIX=not-a-run
kubectl() {{ exit 42; }}
if install_probe_access; then exit 1; fi
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("name", "connected_marker", "result_marker"),
    [
        ("NO_SVID_TLS_PY", "NO_SVID_TCP=ERROR", "NO_SVID_TLS=ERROR"),
        ("PLAINTEXT_PY", "PLAINTEXT_TCP=ERROR", "PLAINTEXT=ERROR"),
    ],
)
@pytest.mark.parametrize("failure", ["dns", "timeout", "refused"])
def test_synthetic_network_failure_is_not_a_tls_rejection(
    name: str, connected_marker: str, result_marker: str, failure: str
) -> None:
    source = _script().split(f"{name}='\n", 1)[1].split("\n'", 1)[0]
    error = {
        "dns": "socket.gaierror",
        "timeout": "TimeoutError",
        "refused": "ConnectionRefusedError",
    }[failure]
    if name == "NO_SVID_TLS_PY":
        prefix = f"import socket\ndef fail(*args, **kwargs): raise {error}()\nsocket.create_connection = fail\n"
    else:
        prefix = f"import http.client, socket\ndef fail(*args, **kwargs): raise {error}()\nhttp.client.HTTPConnection.connect = fail\n"
    env = os.environ | {
        "TARGET_BACKEND": "owned.invalid",
        "TARGET_BACKEND_PORT": "8000",
    }
    result = subprocess.run(  # noqa: S603  # Fixed interpreter and in-memory transport stub.
        [sys.executable, "-c", prefix + source],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[-2:] == [connected_marker, result_marker]
    if name == "NO_SVID_TLS_PY":
        assert lines[:2] == [
            "NO_SVID_STAGE=TCP_CONNECT",
            "NO_SVID_EVENT=" + ("TIMEOUT" if failure == "timeout" else "OS_ERROR"),
        ]


def test_negative_success_markers_require_tcp_reachability() -> None:
    command = f"""set -euo pipefail
{_shell_function("record")}
{_shell_function("sanitize_probe_output")}
{_shell_function("capture_probe")}
{_shell_function("run_proofs")}
DIAG_DIR=$(mktemp -d)
trap 'rm -rf "$DIAG_DIR"' EXIT
FAILURES=0
GATEWAY_HOP_PY=; NO_SVID_TLS_PY=; PLAINTEXT_PY=
run_probe() {{
  case "$1" in
    gateway-hop) printf 'STATUS=200\\nBODY_HAS_KEYS=True\\n' ;;
    no-svid-tls) printf 'NO_SVID_TLS=REJECTED\\n' ;;
    plaintext) printf 'PLAINTEXT=REJECTED\\n' ;;
  esac
}}
backend_logged_gateway_peer() {{ return 0; }}
run_proofs
test "$FAILURES" = 2
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count(b"PASS ") == 2
    assert result.stdout.count(b"FAIL ") == 2


@pytest.mark.parametrize(
    ("name", "behavior", "expected"),
    [
        (
            "NO_SVID_TLS_PY",
            "certificate_required",
            ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=REJECTED"],
        ),
        (
            "NO_SVID_TLS_PY",
            "wrong_alert",
            ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ERROR"],
        ),
        (
            "NO_SVID_TLS_PY",
            "response_timeout",
            ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ERROR"],
        ),
        (
            "NO_SVID_TLS_PY",
            "answered",
            ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ANSWERED"],
        ),
        ("NO_SVID_TLS_PY", "eof", ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ERROR"]),
        ("NO_SVID_TLS_PY", "reset", ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ERROR"]),
        (
            "NO_SVID_TLS_PY",
            "write_timeout",
            ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ERROR"],
        ),
        (
            "NO_SVID_TLS_PY",
            "handshake_error",
            ["NO_SVID_TCP=CONNECTED", "NO_SVID_TLS=ERROR"],
        ),
        ("PLAINTEXT_PY", "closed", ["PLAINTEXT_TCP=CONNECTED", "PLAINTEXT=REJECTED"]),
        (
            "PLAINTEXT_PY",
            "response_timeout",
            ["PLAINTEXT_TCP=CONNECTED", "PLAINTEXT=ERROR"],
        ),
        ("PLAINTEXT_PY", "answered", ["PLAINTEXT_TCP=CONNECTED", "PLAINTEXT=ANSWERED"]),
    ],
)
def test_synthetic_connected_transport_distinguishes_response_from_failure(
    name: str, behavior: str, expected: list[str]
) -> None:
    source = _script().split(f"{name}='\n", 1)[1].split("\n'", 1)[0]
    if name == "NO_SVID_TLS_PY":
        prefix = f"""import socket, ssl
BEHAVIOR={behavior!r}
class Alert(ssl.SSLError):
    def __init__(self, reason): self.reason = reason
class Raw:
    def __enter__(self): return self
    def __exit__(self, *args): return False
class TLS(Raw):
    def settimeout(self, value): pass
    def sendall(self, value):
        if BEHAVIOR == 'write_timeout': raise TimeoutError('private failure details')
    def recv(self, size):
        if BEHAVIOR in ('response_timeout', 'write_timeout'): raise TimeoutError()
        if BEHAVIOR == 'eof': return b''
        if BEHAVIOR == 'reset': raise ConnectionResetError('private failure details')
        if BEHAVIOR == 'certificate_required': raise Alert('TLSV13_ALERT_CERTIFICATE_REQUIRED')
        if BEHAVIOR == 'wrong_alert': raise Alert('OTHER_ALERT')
        return b'x'
class Context:
    def wrap_socket(self, raw, server_hostname):
        if BEHAVIOR == 'handshake_error': raise Alert('PRIVATE_UNRECOGNIZED_ALERT')
        return TLS()
socket.create_connection = lambda *args, **kwargs: Raw()
ssl.create_default_context = lambda: Context()
"""
    else:
        prefix = f"""import http.client
BEHAVIOR={behavior!r}
class Connection:
    def __init__(self, *args, **kwargs): pass
    def connect(self): pass
    def request(self, *args): pass
    def getresponse(self):
        if BEHAVIOR == 'response_timeout': raise TimeoutError()
        if BEHAVIOR == 'closed': raise http.client.RemoteDisconnected()
        return object()
    def close(self): pass
http.client.HTTPConnection = Connection
"""
    env = os.environ | {
        "TARGET_BACKEND": "owned.invalid",
        "TARGET_BACKEND_PORT": "8000",
    }
    result = subprocess.run(  # noqa: S603  # Fixed interpreter and in-memory transport stub.
        [sys.executable, "-c", prefix + source],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[-2:] == expected
    if name == "NO_SVID_TLS_PY":
        assert lines[:2] == [
            "NO_SVID_STAGE="
            + {
                "response_timeout": "READ_RESPONSE",
                "write_timeout": "WRITE_REQUEST",
                "handshake_error": "TLS_HANDSHAKE",
            }.get(behavior, "READ_ALERT"),
            "NO_SVID_EVENT="
            + {
                "certificate_required": "CERTIFICATE_REQUIRED",
                "wrong_alert": "SSL_ERROR",
                "response_timeout": "TIMEOUT",
                "answered": "DATA",
                "eof": "EOF",
                "reset": "RESET",
                "write_timeout": "TIMEOUT",
                "handshake_error": "SSL_ERROR",
            }[behavior],
        ]


def test_negative_success_requires_both_connected_and_rejected_markers() -> None:
    command = f"""set -euo pipefail
{_shell_function("record")}
{_shell_function("sanitize_probe_output")}
{_shell_function("capture_probe")}
{_shell_function("run_proofs")}
DIAG_DIR=$(mktemp -d)
trap 'rm -rf "$DIAG_DIR"' EXIT
FAILURES=0
GATEWAY_HOP_PY=; NO_SVID_TLS_PY=; PLAINTEXT_PY=
run_probe() {{
  case "$1" in
    gateway-hop) printf 'STATUS=200\\nBODY_HAS_KEYS=True\\n' ;;
    no-svid-tls) printf 'NO_SVID_TCP=CONNECTED\\nNO_SVID_TLS=REJECTED\\n' ;;
    plaintext) printf 'PLAINTEXT_TCP=CONNECTED\\nPLAINTEXT=REJECTED\\n' ;;
  esac
}}
backend_logged_gateway_peer() {{ return 0; }}
run_proofs
test "$FAILURES" = 0
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count(b"PASS ") == 4
    assert b"FAIL " not in result.stdout


def test_probe_command_failure_cannot_pass_even_with_success_markers() -> None:
    command = f"""set -eu
{_shell_function("record")}
{_shell_function("sanitize_probe_output")}
{_shell_function("capture_probe")}
{_shell_function("run_proofs")}
DIAG_DIR=$(mktemp -d)
trap 'rm -rf "$DIAG_DIR"' EXIT
FAILURES=0
GATEWAY_HOP_PY=; NO_SVID_TLS_PY=; PLAINTEXT_PY=
run_probe() {{
  case "$1" in
    gateway-hop) printf 'STATUS=200\\nBODY_HAS_KEYS=True\\n' ;;
    no-svid-tls) printf 'NO_SVID_TLS=REJECTED\\n' ;;
    plaintext) printf 'PLAINTEXT=REJECTED\\n' ;;
  esac
  return 1
}}
backend_logged_gateway_peer() {{ return 1; }}
run_proofs
test "$FAILURES" = 4
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    assert b"PASS " not in result.stdout
    assert result.stdout.count(b"FAIL ") == 4


def _probe_result(name: str, host: str, port: int) -> subprocess.CompletedProcess[str]:
    script = _script()
    source = script.split(f"{name}='\n", 1)[1].split("\n'", 1)[0]
    env = os.environ | {"TARGET_BACKEND": host, "TARGET_BACKEND_PORT": str(port)}
    result = subprocess.run(  # noqa: S603  # Fixed interpreter runs the repository-owned probe.
        [sys.executable, "-c", source],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result


def _probe(name: str, host: str, port: int) -> str:
    return _probe_result(name, host, port).stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("name", ["NO_SVID_TLS_PY", "PLAINTEXT_PY"])
def test_unreachable_backend_does_not_count_as_rejection(name: str) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    assert _probe(name, "127.0.0.1", port).endswith("=ERROR")


def test_plaintext_http_response_does_not_count_as_rejection() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def respond() -> None:
            with listener.accept()[0] as connection:
                connection.recv(4096)
                connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

        server = threading.Thread(target=respond)
        server.start()
        try:
            assert _probe("PLAINTEXT_PY", "127.0.0.1", port) == "PLAINTEXT=ANSWERED"
        finally:
            server.join(timeout=5)
        assert not server.is_alive()


def test_plaintext_peer_close_after_request_is_rejection() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def close_after_request() -> None:
            with listener.accept()[0] as connection:
                connection.recv(4096)

        server = threading.Thread(target=close_after_request)
        server.start()
        try:
            assert _probe("PLAINTEXT_PY", "127.0.0.1", port) == "PLAINTEXT=REJECTED"
        finally:
            server.join(timeout=5)
        assert not server.is_alive()


def _server_tls_context(tmp_path: Path) -> ssl.SSLContext:
    key = ec.generate_private_key(ec.SECP256R1())
    cert_file = tmp_path / "server.pem"
    key_file = tmp_path / "server-key.pem"
    cert_file.write_bytes(leaf((IDENTITY,), private_key=key).public_bytes(Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    context.load_verify_locations(cert_file)
    return context


def test_tls_reset_before_an_alert_does_not_count_as_rejection() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def reset() -> None:
            with listener.accept()[0] as connection:
                linger = struct.pack("hh" if os.name == "nt" else "ii", 1, 0)
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)

        server = threading.Thread(target=reset)
        server.start()
        try:
            assert _probe("NO_SVID_TLS_PY", "127.0.0.1", port) == "NO_SVID_TLS=ERROR"
        finally:
            server.join(timeout=5)
        assert not server.is_alive()


def test_tls_response_without_client_certificate_does_not_count_as_rejection(
    tmp_path: Path,
) -> None:
    context = _server_tls_context(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def respond() -> None:
            with listener.accept()[0] as connection:
                with context.wrap_socket(connection, server_side=True) as tls:
                    tls.recv(4096)
                    tls.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

        server = threading.Thread(target=respond)
        server.start()
        try:
            assert _probe("NO_SVID_TLS_PY", "127.0.0.1", port) == "NO_SVID_TLS=ANSWERED"
        finally:
            server.join(timeout=5)
        assert not server.is_alive()


@pytest.mark.parametrize(
    ("version", "expected_result", "expected_server_error"),
    [
        (ssl.TLSVersion.TLSv1_2, "ERROR", "UNSUPPORTED_PROTOCOL"),
        (ssl.TLSVersion.TLSv1_3, "REJECTED", "PEER_DID_NOT_RETURN_A_CERTIFICATE"),
    ],
)
def test_missing_client_certificate_requires_a_specific_tls13_alert(
    version: ssl.TLSVersion,
    expected_result: str,
    expected_server_error: str,
    tmp_path: Path,
) -> None:
    context = _server_tls_context(tmp_path)
    context.minimum_version = version
    context.maximum_version = version
    context.verify_mode = ssl.CERT_REQUIRED
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server_errors: list[str | None] = []

        def reject_missing_certificate() -> None:
            # Keep the TCP socket open after OpenSSL rejects the handshake so
            # the client can observe the alert before the server closes it.
            with listener.accept()[0] as connection, connection.dup() as alert_socket:
                try:
                    with context.wrap_socket(connection, server_side=True):
                        pass
                except ssl.SSLError as error:
                    server_errors.append(error.reason)
                alert_socket.settimeout(3)
                try:
                    while alert_socket.recv(4096):
                        pass
                except (ConnectionAbortedError, ConnectionResetError, TimeoutError):
                    pass

        server = threading.Thread(target=reject_missing_certificate)
        server.start()
        try:
            assert (
                _probe("NO_SVID_TLS_PY", "127.0.0.1", port)
                == f"NO_SVID_TLS={expected_result}"
            )
        finally:
            server.join(timeout=5)
        assert not server.is_alive()
        assert server_errors == [expected_server_error]


def test_script_checks_a_b_c_are_named_and_finite() -> None:
    script = _script()
    for check in (
        "a-gateway-to-backend-mtls-hop",
        "b-no-svid-tls-client-rejected",
        "c-plaintext-http-rejected",
        "d-backend-logs-gateway-peer-spiffe-id",
    ):
        assert f'record "{check}"' in script, check
    assert "NO_SVID_TLS=REJECTED" in script
    assert "PLAINTEXT=REJECTED" in script
    assert "STATUS=200" in script
    assert "printf 'RESULT=PASS\\n'" in script
    assert "exit 1" in script


def test_script_cleans_up_only_its_own_cluster_and_registry() -> None:
    script = _script()
    assert _pin("CLUSTER_NAME") == "ue-r9-aud373-${RUN_SUFFIX}"
    assert _pin("LOCAL_REGISTRY_NAME") == "ue-r9-aud373-registry-${RUN_SUFFIX}"
    assert "trap cleanup EXIT" in script
    assert '[[ "$CLUSTER_CREATED" == "1" ]]' in script
    assert '[[ "$REGISTRY_CREATED" == "1" &&' in script
    assert 'kind delete cluster --name "$CLUSTER_NAME"' in script
    assert 'docker rm --force --volumes "$REGISTRY_CONTAINER_ID"' in script
    assert '--publish "127.0.0.1::5000"' in script
    assert 'docker port "$REGISTRY_CONTAINER_ID" 5000/tcp' in script
    assert "docker push" in script
    assert "collect_diagnostics" in script
    assert "system prune" not in script
    assert "volume prune" not in script


def test_cluster_ownership_is_recorded_before_kind_creation() -> None:
    script = _script()
    assert script.index("CLUSTER_CREATED=1") < script.index("kind create cluster")


def test_signals_exit_through_the_cleanup_trap() -> None:
    script = _script()
    assert "trap 'exit 130' INT" in script
    assert "trap 'exit 143' TERM" in script
    assert script.index("trap 'exit 143' TERM") < script.index("trap cleanup EXIT")


def test_network_downloads_and_image_transfers_are_bounded() -> None:
    script = _script()
    curl_lines = [
        line for line in script.splitlines() if line.lstrip().startswith("curl ")
    ]
    assert len(curl_lines) == 3
    assert all("--max-time 300" in line for line in curl_lines)
    assert "timeout 1800 docker build" in script
    assert "timeout 900 docker push" in script
    assert "docker build --file" not in script.replace("timeout 1800 docker build", "")
    assert "\ndocker push" not in script


def test_backend_probe_diagnostics_use_the_chart_command() -> None:
    chart = (
        ROOT / "charts/university-ecosystem/templates/backend-deployment.yaml"
    ).read_text(encoding="utf-8")
    assert (
        '"python", "-m", "app.server.internal_mtls", "probe", "/health/ready", "--port", '
        '"{{ .Values.backend.service.port }}"'
    ) in chart
    script = _script()
    assert 'readonly BACKEND_PORT="8000"' in script
    assert (
        'python -m app.server.internal_mtls probe /health/ready --port "$BACKEND_PORT"'
        in script
    )
    assert "timeout 60 kubectl" in script
    assert "collect_backend_probe_diagnostics" in script
    body = _shell_function("collect_backend_probe_diagnostics")
    assert "-probe-ready.stderr" in body
    assert "-probe-ready.exit" in body


def _fake_kubectl_setup() -> str:
    return """fake_bin="$(mktemp -d)"
trap 'rm -rf "$fake_bin"' EXIT
cat >"$fake_bin/kubectl" <<'FAKE_KUBECTL'
#!/usr/bin/env bash
case "$*" in
  *"get pods -o name"*) printf '%s\\n' $FAKE_PODS ;;
  *" logs "*)
    printf 'internal_mtls_peer_authorized peer_spiffe_id=%s\\n' "$FAKE_GATEWAY_SPIFFE_ID"
    for ((index = 0; index < 20000; index++)); do
      printf 'internal_mtls_peer_authorized peer_spiffe_id=spiffe://other/%s\\n' "$index"
    done
    ;;
  *" exec "*)
    printf 'fake stdout\\n'
    printf '%s\\n' "$FAKE_EXEC_STDERR" >&2
    exit "$FAKE_EXEC_RC"
    ;;
esac
FAKE_KUBECTL
chmod 0700 "$fake_bin/kubectl"
PATH="$fake_bin:$PATH"
export PATH
"""


def _run_with_fake_kubectl(
    command: str, env: dict[str, str]
) -> subprocess.CompletedProcess[bytes]:
    bash = shutil.which("bash")
    assert bash is not None
    return subprocess.run(  # noqa: S603  # Fixed shell runs repository-owned functions and fixed fixtures.
        [bash, "-s"], input=command.encode(), capture_output=True, check=False, env=env
    )


def test_gateway_peer_search_survives_large_multi_match_logs() -> None:
    gateway = "spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway"
    command = "\n".join(
        [
            "set -euo pipefail",
            _fake_kubectl_setup(),
            "FAKE_PODS='pod/ue-university-ecosystem-backend-abc'",
            f"FAKE_GATEWAY_SPIFFE_ID='{gateway}'",
            "export FAKE_PODS FAKE_GATEWAY_SPIFFE_ID",
            "NAMESPACE=university-ecosystem",
            "BACKEND_SVC=ue-university-ecosystem-backend",
            f"GATEWAY_SPIFFE_ID={gateway}",
            _shell_function("backend_logged_gateway_peer"),
            "backend_logged_gateway_peer && printf 'MATCHED\\n'",
        ]
    )
    result = _run_with_fake_kubectl(command, dict(os.environ))
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"MATCHED\n"


def test_backend_probe_diagnostics_record_stdout_stderr_and_status() -> None:
    command = "\n".join(
        [
            "set -euo pipefail",
            _fake_kubectl_setup(),
            "FAKE_PODS='pod/ue-university-ecosystem-backend-abc pod/ue-university-ecosystem-gateway-def'",
            "FAKE_EXEC_STDERR='internal_mtls_probe_failed step=tls_connect error=SSLError: boom'",
            "FAKE_EXEC_RC=1",
            "export FAKE_PODS FAKE_EXEC_STDERR FAKE_EXEC_RC",
            "NAMESPACE=university-ecosystem",
            "BACKEND_SVC=ue-university-ecosystem-backend",
            "BACKEND_PORT=8000",
            'DIAG_DIR="$(mktemp -d)"',
            _shell_function("collect_backend_probe_diagnostics"),
            "collect_backend_probe_diagnostics",
            'probe_prefix="$DIAG_DIR/university-ecosystem-ue-university-ecosystem-backend-abc-probe-ready"',
            'printf "STDERR_START\\n"; cat "${probe_prefix}.stderr"',
            'printf "EXIT_START\\n"; cat "${probe_prefix}.exit"',
            'printf "STDOUT_START\\n"; cat "${probe_prefix}.stdout"',
            'printf "NO_GATEWAY_DIAGNOSTICS="; if compgen -G "$DIAG_DIR/*gateway*" >/dev/null; then printf "no\\n"; else printf "yes\\n"; fi',
        ]
    )
    result = _run_with_fake_kubectl(command, dict(os.environ))
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode().splitlines() == [
        "STDERR_START",
        "internal_mtls_probe_failed step=tls_connect error=SSLError: boom",
        "EXIT_START",
        "exit=1",
        "STDOUT_START",
        "fake stdout",
        "NO_GATEWAY_DIAGNOSTICS=yes",
    ]


def test_cleanup_continues_after_diagnostic_and_cluster_delete_timeouts() -> None:
    backend_diagnostics = _shell_function("collect_backend_probe_diagnostics")
    diagnostics = _shell_function("collect_diagnostics")
    cleanup = _shell_function("cleanup")
    assert "timeout 30 kubectl" in backend_diagnostics
    assert "timeout 30 docker info" in diagnostics
    assert "timeout 120 kind delete" in cleanup
    assert "timeout 60 docker rm" in cleanup
    functions = "\n".join(
        source.replace(
            "timeout --kill-after=5s 20s ", "timeout --kill-after=0.1s 0.1s "
        )
        .replace("timeout 30 ", "timeout 0.1 ")
        .replace("timeout 60 ", "timeout 0.1 ")
        .replace("timeout 120 ", "timeout 0.1 ")
        for source in (backend_diagnostics, diagnostics, cleanup)
    )
    command = f"""set -euo pipefail
{functions}
root="$(mktemp -d)"
on_exit() {{
  printf 'TRACE_START\\n'
  cat "$TRACE"
  if [[ ! -e "$WORK_DIR" ]]; then printf 'WORK_DIR_REMOVED\\n'; fi
  rm -rf "$root"
}}
trap on_exit EXIT
WORK_DIR="$root/work"
mkdir -p "$WORK_DIR/bin"
KUBECONFIG="$WORK_DIR/kubeconfig"
printf 'config\\n' >"$KUBECONFIG"
DIAG_DIR="$WORK_DIR/diagnostics"
TRACE="$root/trace"
export TRACE
cat >"$WORK_DIR/bin/kubectl" <<'FAKE_KUBECTL'
#!/usr/bin/env bash
printf 'kubectl %s\\n' "$*" >>"$TRACE"
exec sleep 5
FAKE_KUBECTL
cat >"$WORK_DIR/bin/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
printf 'docker %s\\n' "$*" >>"$TRACE"
if [[ "$1" == "rm" ]]; then exit 0; fi
exec sleep 5
FAKE_DOCKER
cat >"$WORK_DIR/bin/kind" <<'FAKE_KIND'
#!/usr/bin/env bash
printf 'kind %s\\n' "$*" >>"$TRACE"
exec sleep 5
FAKE_KIND
chmod 0700 "$WORK_DIR/bin/kubectl" "$WORK_DIR/bin/docker" "$WORK_DIR/bin/kind"
PATH="$WORK_DIR/bin:$PATH"
export PATH
DOCKER_DAEMON_ENDPOINT=unix:///var/run/docker.sock
NAMESPACE=university-ecosystem
SPIRE_NAMESPACE=spire
BACKEND_SVC=ue-university-ecosystem-backend
BACKEND_PORT=8000
CLUSTER_NAME=owned-cluster
CLUSTER_CREATED=1
REGISTRY_CREATED=1
REGISTRY_CONTAINER_ID="$(printf 'a%.0s' {{1..64}})"
LOCAL_REGISTRY_ADDRESS=127.0.0.1:5000
log() {{ echo "$*" >&2; }}
cleanup
"""
    bash = shutil.which("bash")
    assert bash is not None
    try:
        result = subprocess.run(  # noqa: S603  # Fixed shell runs repository-owned cleanup and fixture commands.
            [bash, "-s"],
            input=command.encode(),
            capture_output=True,
            check=False,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("bounded diagnostics and cleanup did not complete")
    assert result.returncode == 1, result.stderr.decode()
    assert result.stderr.decode().splitlines() == ["cleanup failed: owned kind cluster"]
    trace = result.stdout.decode()
    assert "RESULT=FAIL cleanup=1" in trace
    assert "docker info --format" in trace
    assert "kubectl -n university-ecosystem get all,serviceaccounts -o wide" in trace
    assert "kind delete cluster --name owned-cluster" in trace
    assert "docker rm --force --volumes" in trace
    assert "WORK_DIR_REMOVED" in trace


def test_script_proves_spire_installation_and_registration_from_repo_manifests() -> (
    None
):
    script = _script()
    assert "k8s/spire/spire-rbac.yaml" in script
    assert "k8s/spire/spire-server.yaml" in script
    assert "k8s/spire/spire-agent.yaml" in script
    assert "spiffe-csi-driver.agentSocketPath=${AGENT_SOCKET_PATH}" in script
    assert "internal_mtls_peer_authorized" in script
    assert "entry create" in script
    assert "k8s:sa:${service_account}" in script


def _generated_proof_values() -> dict[str, Any]:
    command = f"""set -euo pipefail
{_shell_function("random_hex")}
{_shell_function("random_fernet")}
{_shell_function("write_values_file")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
IMAGE_TAG=ue-r9-aud373-0123456789ab
RELEASE=ue
BACKEND_SVC=ue-university-ecosystem-backend
GATEWAY_SVC=ue-university-ecosystem-gateway
FILE_PROCESSOR_SVC=ue-university-ecosystem-file-processor
TRUST_DOMAIN=university.ecosystem
BACKEND_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-backend
GATEWAY_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway
WS_HUB_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-ws-hub
FILE_PROCESSOR_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-file-processor
write_secret_file() {{ :; }}
openssl() {{
  if [[ "$1" == genrsa ]]; then :; else command openssl "$@"; fi
}}
write_values_file
cat "$WORK_DIR/values.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, "proof value generation failed"
    try:
        return yaml.safe_load(result.stdout)
    except yaml.YAMLError:
        raise AssertionError("generated proof values are not valid YAML") from None


def test_generated_proof_http_hosts_are_finite_and_route_jwks() -> None:
    from starlette.applications import Starlette
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    allowed_hosts = _generated_proof_values()["backend"]["env"]["ALLOWED_HOSTS"].split(
        ","
    )
    assert allowed_hosts == [
        "localhost",
        "127.0.0.1",
        "testserver",
        "ue-university-ecosystem-backend",
        "ue-university-ecosystem-gateway",
    ]

    async def jwks_handler(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("JWKS handler reached")

    app = TrustedHostMiddleware(
        Starlette(routes=[Route("/.well-known/jwks.json", jwks_handler)]),
        allowed_hosts=allowed_hosts,
    )
    with TestClient(app) as client:
        for host in (
            "localhost:8000",
            "127.0.0.1:8000",
            "testserver",
            "ue-university-ecosystem-backend:8000",
            "ue-university-ecosystem-gateway:8080",
        ):
            response = client.get("/.well-known/jwks.json", headers={"host": host})
            assert response.status_code == 200
            assert response.text == "JWKS handler reached"
        for host in (
            "evil.example",
            "ue-university-ecosystem-backend.evil.example",
            "evil-ue-university-ecosystem-gateway",
        ):
            response = client.get("/.well-known/jwks.json", headers={"host": host})
            assert response.status_code == 400
            assert response.text == "Invalid host header"


def test_generated_values_enable_single_real_file_processor_and_gRPC_mtls() -> None:
    values = _generated_proof_values()
    assert values["fileProcessor"]["enabled"] is False
    assert values["fileProcessor"]["replicaCount"] == 1
    assert values["internalGrpcMTLS"] == {
        "enabled": True,
        "serverName": "ue-university-ecosystem-file-processor",
        "gatewayIdentityURI": "spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway",
        "allowedClientURIs": [
            "spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway"
        ],
        "gatewayClient": {"existingSecret": "internal-grpc-mtls-gateway"},
        "fileProcessorServer": {"existingSecret": "internal-grpc-mtls-server"},
    }
    assert values["gateway"]["config"]["grpcUseTLS"] is True


def test_generated_revocation_connection_uses_distinct_canonical_redis_password(
    tmp_path: Path,
) -> None:
    command = f"""set -euo pipefail
{_shell_function("random_hex")}
{_shell_function("random_fernet")}
{_shell_function("write_secret_file")}
{_shell_function("write_values_file")}
WORK_DIR={shlex.quote(_bash_path(tmp_path))}
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
IMAGE_TAG=proof
RELEASE=ue
BACKEND_SVC=ue-university-ecosystem-backend
GATEWAY_SVC=ue-university-ecosystem-gateway
FILE_PROCESSOR_SVC=ue-university-ecosystem-file-processor
TRUST_DOMAIN=university.ecosystem
BACKEND_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-backend
GATEWAY_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway
WS_HUB_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-ws-hub
FILE_PROCESSOR_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-file-processor
write_values_file
"""
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603  # Fixed Bash runs only the repository-owned proof helper.
        [bash, "-s"],
        input=command.encode(),
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    revocation_url = (tmp_path / "secret-files/redis-revocation-url").read_text(
        encoding="utf-8"
    )
    revocation_password = (
        tmp_path / "secret-files/revocation-redis-password"
    ).read_text(encoding="utf-8")
    cache_url = (tmp_path / "secret-files/redis-backend-url").read_text(
        encoding="utf-8"
    )
    cache_password = (tmp_path / "secret-files/redis-password").read_text(
        encoding="utf-8"
    )
    assert revocation_url.startswith("redis://:")
    assert revocation_url.endswith("@ue-revocation-redis-master:6379/0")
    assert revocation_password in revocation_url
    assert cache_url.endswith("@ue-redis-master:6379/0")
    assert cache_password in cache_url
    assert revocation_password != cache_password


def test_generated_proof_settings_validate_real_spotify_and_totp_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from secrets import token_urlsafe

    from cryptography.fernet import Fernet
    from pydantic import ValidationError

    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", token_urlsafe(48))
    from app.core.config import Settings
    from app.core.config.mixins.mfa_settings import _parse_totp_encryption_keyring

    config = _generated_proof_values()["backend"]["config"]
    try:
        settings = Settings(
            _env_file=None,
            environment="development",
            secret_key=token_urlsafe(48),
            spotify_token_secret=config["spotifyTokenSecret"],
            mfa_totp_encryption_keys=config["mfaTotpEncryptionKeys"],
            mfa_totp_active_encryption_key_id=config["mfaTotpActiveEncryptionKeyId"],
            mfa_email_otp_hmac_keys=config["mfaEmailOtpHMACKeys"],
            mfa_email_otp_active_hmac_key_id=config["mfaEmailOtpActiveHMACKeyId"],
            mfa_email_delivery_keks=config["mfaEmailDeliveryKEKs"],
            mfa_email_delivery_active_kek_id=config["mfaEmailDeliveryActiveKEKId"],
            mfa_trusted_device_hmac_keys=config["mfaTrustedDeviceHMACKeys"],
            mfa_trusted_device_active_hmac_key_id=config[
                "mfaTrustedDeviceActiveHMACKeyId"
            ],
        )
    except ValidationError:
        raise AssertionError("generated proof settings failed validation") from None
    ring = _parse_totp_encryption_keyring(settings.mfa_totp_encryption_keys)
    totp_key = ring[settings.mfa_totp_active_encryption_key_id]
    spotify_key = settings.spotify_token_secret
    keys_are_independent = totp_key != spotify_key
    assert keys_are_independent, "proof keys must be independent"
    for key in (totp_key, spotify_key):
        cipher = Fernet(key.encode())
        assert cipher.decrypt(cipher.encrypt(b"proof")) == b"proof"
    try:
        Settings(
            _env_file=None,
            environment="development",
            secret_key=token_urlsafe(48),
            spotify_token_secret=totp_key,
            mfa_totp_encryption_keys=config["mfaTotpEncryptionKeys"],
            mfa_totp_active_encryption_key_id=config["mfaTotpActiveEncryptionKeyId"],
        )
    except ValidationError as error:
        rejected_reuse = any(
            "must be independent" in item["msg"]
            for item in error.errors(include_input=False)
        )
    else:
        rejected_reuse = False
    assert rejected_reuse, "application must reject key reuse"
    from app.auth.mfa import trusted_device

    monkeypatch.setattr(trusted_device, "settings", settings)
    trusted_keys, active_id = trusted_device._configured_keyring()
    trusted_key_is_long_enough = len(trusted_keys[active_id]) >= 32
    assert trusted_key_is_long_enough


def test_generated_proof_mfa_email_keyrings_match_real_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from secrets import token_urlsafe

    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", token_urlsafe(48))
    from app.auth.mfa.email_otp import (
        EmailOtpService,
        MfaSecurityUnavailable,
        _DeliveryOnlyRateLimiter,
        _parse_key_ring,
    )

    config = _generated_proof_values()["backend"]["config"]
    try:
        hmac_keys = _parse_key_ring(config["mfaEmailOtpHMACKeys"])
        delivery_keys = _parse_key_ring(config["mfaEmailDeliveryKEKs"])
        EmailOtpService(
            hmac_keys=hmac_keys,
            active_hmac_key_id=config["mfaEmailOtpActiveHMACKeyId"],
            delivery_keks=delivery_keys,
            active_kek_id=config["mfaEmailDeliveryActiveKEKId"],
            rate_limiter=_DeliveryOnlyRateLimiter(),
        )
    except MfaSecurityUnavailable:
        raise AssertionError(
            "generated proof MFA email keys failed validation"
        ) from None
    with pytest.raises(MfaSecurityUnavailable):
        _parse_key_ring(config["mfaEmailDeliveryKEKs"] + "=")


def test_postgres_fixture_matches_backend_egress_policy() -> None:
    command = f"""set -euo pipefail
{_shell_function("deploy_stack")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
ROOT_DIR=unused
NAMESPACE=university-ecosystem
RELEASE=ue
BACKEND_SVC=ue-backend
GATEWAY_SVC=ue-gateway
FILE_PROCESSOR_SVC=ue-file-processor
BACKEND_IMAGE=fixture
read_tracked_pin() {{ printf image; }}
write_values_file() {{ :; }}
write_grpc_mtls_material() {{ :; }}
install_grpc_mtls_secrets() {{ :; }}
install_revocation_store() {{ :; }}
install_temporal_dev_server() {{ :; }}
wait_for_file_process_stream() {{ :; }}
openssl() {{ :; }}
register_workloads() {{ :; }}
helm() {{ :; }}
kubectl() {{
  case "$*" in
    *"apply -f -"*) cat > /dev/null ;;
    *"--dry-run=client"*) printf fixture ;;
    *) : ;;
  esac
}}
deploy_stack
cat "$WORK_DIR/postgres.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, "failed to render the PostgreSQL fixture"
    deployment, service = list(yaml.safe_load_all(result.stdout))
    pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert deployment["spec"]["selector"]["matchLabels"] == {"app": "ue-postgres"}
    assert service["spec"]["selector"] == {"app": "ue-postgres"}

    template = (
        ROOT / "charts/university-ecosystem/templates/network-policy.yaml"
    ).read_text(encoding="utf-8")
    backend = template.split("name: {{ .Release.Name }}-backend-policy", 1)[1]
    postgres_rule = backend.split("    # PostgreSQL.\n", 1)[1].split("    # Redis", 1)[
        0
    ]
    rule = yaml.safe_load("egress:\n" + postgres_rule)["egress"][0]
    assert {"protocol": "TCP", "port": 5432} in rule["ports"]
    peer = rule["to"][0]["podSelector"]["matchLabels"]

    def matches(labels: dict[str, str]) -> bool:
        return all(labels.get(key) == value for key, value in peer.items())

    assert matches(pod_labels), "fixture must be an allowed PostgreSQL peer"
    assert not matches({"app": "ue-postgres"})
    assert not matches({"app.kubernetes.io/name": "other"})


def test_migration_connection_targets_the_owned_database() -> None:
    command = f"""set -euo pipefail
{_shell_function("random_hex")}
{_shell_function("random_fernet")}
{_shell_function("write_values_file")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
IMAGE_TAG=proof
RELEASE=ue
BACKEND_SVC=ue-university-ecosystem-backend
GATEWAY_SVC=ue-university-ecosystem-gateway
FILE_PROCESSOR_SVC=ue-university-ecosystem-file-processor
TRUST_DOMAIN=university.ecosystem
BACKEND_SPIFFE_ID=backend
GATEWAY_SPIFFE_ID=gateway
WS_HUB_SPIFFE_ID=ws-hub
FILE_PROCESSOR_SPIFFE_ID=file-processor
postgres_password=
migration_seen=0
write_secret_file() {{
  case "$1" in
    postgres-password) postgres_password="$2" ;;
    migration-database-url)
      [[ -n "$postgres_password" ]]
      [[ "$2" == "postgresql+asyncpg://ue_app:${{postgres_password}}@ue-postgres:5432/university" ]]
      migration_seen=1 ;;
  esac
}}
openssl() {{
  if [[ "$1" == genrsa ]]; then :; else command openssl "$@"; fi
}}
write_values_file
test "$migration_seen" = 1
"""
    result = _bash_command(command)
    assert result.returncode == 0, "migration target must match the owned database"


@pytest.mark.parametrize("failure", ["none", "apply", "wait"])
def test_owned_database_schema_migrates_before_helm_and_fails_closed(
    failure: str,
) -> None:
    command = f"""set -euo pipefail
{_shell_function("deploy_stack")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
ROOT_DIR=unused
NAMESPACE=university-ecosystem
RELEASE=ue
BACKEND_SVC=ue-backend
GATEWAY_SVC=ue-gateway
FILE_PROCESSOR_SVC=ue-file-processor
BACKEND_IMAGE=fixture-image
FAILURE={failure}
TRACE="$work/trace"
: > "$TRACE"
read_tracked_pin() {{ printf image; }}
write_values_file() {{ :; }}
write_grpc_mtls_material() {{ :; }}
install_grpc_mtls_secrets() {{ :; }}
install_revocation_store() {{ :; }}
install_temporal_dev_server() {{ :; }}
wait_for_file_process_stream() {{ printf 'STREAM_READY\\n' >> "$TRACE"; }}
openssl() {{ :; }}
register_workloads() {{ printf 'REGISTRATION\\n' >> "$TRACE"; }}
helm() {{ printf 'HELM\\n' >> "$TRACE"; }}
kubectl() {{
  case "$*" in
    *"apply -f -"*) cat > /dev/null ;;
    *"--dry-run=client"*) printf fixture ;;
    *"rollout status deployment/ue-postgres"*) printf 'POSTGRES_READY\\n' >> "$TRACE" ;;
    *"apply -f"*"fixture-migration.yaml"*)
      printf 'MIGRATION_APPLIED\\n' >> "$TRACE"
      [[ "$FAILURE" != apply ]] ;;
    *"wait --for=condition=complete"*)
      printf 'MIGRATION_WAIT\\n' >> "$TRACE"
      [[ "$*" == *"job/ue-aud373-migrate --timeout=300s" ]]
      [[ "$FAILURE" != wait ]] ;;
    *) : ;;
  esac
}}
if deploy_stack; then status=0; else status=$?; fi
if [[ "$FAILURE" == none ]]; then
  test "$status" == 0
else
  test "$status" != 0
fi
printf '===TRACE===\\n'
cat "$TRACE"
printf '===JOB===\\n'
cat "$WORK_DIR/fixture-migration.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, "schema fixture did not fail closed"
    trace_source, job_source = result.stdout.decode().split("===JOB===\n", 1)
    trace = trace_source.splitlines()
    assert trace[:3] == ["===TRACE===", "POSTGRES_READY", "MIGRATION_APPLIED"]
    if failure == "apply":
        assert trace[3:] == []
    elif failure == "wait":
        assert trace[3:] == ["MIGRATION_WAIT"]
    else:
        assert trace[3:] == [
            "MIGRATION_WAIT",
            "REGISTRATION",
            "HELM",
            "STREAM_READY",
            "HELM",
        ]
    policy, job = list(yaml.safe_load_all(job_source))
    assert policy["kind"] == "NetworkPolicy"
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert policy["spec"]["ingress"] == []
    rules = policy["spec"]["egress"]
    assert rules == [
        {
            "to": [{"podSelector": {"matchLabels": {"app": "ue-postgres"}}}],
            "ports": [{"protocol": "TCP", "port": 5432}],
        },
        {
            "to": [
                {
                    "namespaceSelector": {
                        "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                    },
                    "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                }
            ],
            "ports": [
                {"protocol": "UDP", "port": 53},
                {"protocol": "TCP", "port": 53},
            ],
        },
    ]
    assert job["kind"] == "Job"
    assert (
        job["spec"]["template"]["metadata"]["labels"]
        == policy["spec"]["podSelector"]["matchLabels"]
    )
    assert job["spec"]["backoffLimit"] == 0
    assert job["spec"]["activeDeadlineSeconds"] == 300
    pod = job["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["restartPolicy"] == "Never"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert len(pod["containers"]) == 1
    container = pod["containers"][0]
    assert container["image"] == "fixture-image"
    assert container["imagePullPolicy"] == "Always"
    assert container["command"] == ["alembic", "upgrade", "head"]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["limits"] == {"cpu": "1", "memory": "1Gi"}
    assert container["volumeMounts"] == [
        {
            "name": "connections",
            "mountPath": "/run/secrets/university-connections",
            "readOnly": True,
        },
        {"name": "tmp", "mountPath": str(PurePosixPath("/") / "tmp")},
    ]
    assert container["env"] == [
        {"name": "ENVIRONMENT", "value": "development"},
        {
            "name": "DATABASE_URL_FILE",
            "value": "/run/secrets/university-connections/migration-database-url",
        },
    ]
    secret = next(volume["secret"] for volume in pod["volumes"] if "secret" in volume)
    chart_values = yaml.safe_load(
        (ROOT / "charts/university-ecosystem/values.yaml").read_text(encoding="utf-8")
    )
    assert secret["secretName"] == chart_values["connections"]["existingSecret"]
    assert secret["items"] == [
        {"key": "migration-database-url", "path": "migration-database-url"}
    ]


def _postgres_fixture_readiness_command() -> list[str]:
    command = f"""set -euo pipefail
{_shell_function("deploy_stack")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
ROOT_DIR=unused
NAMESPACE=university-ecosystem
RELEASE=ue
BACKEND_SVC=ue-backend
GATEWAY_SVC=ue-gateway
FILE_PROCESSOR_SVC=ue-file-processor
BACKEND_IMAGE=fixture-image
read_tracked_pin() {{ printf image; }}
write_values_file() {{ :; }}
write_grpc_mtls_material() {{ :; }}
install_grpc_mtls_secrets() {{ :; }}
install_revocation_store() {{ :; }}
install_temporal_dev_server() {{ :; }}
wait_for_file_process_stream() {{ :; }}
openssl() {{ :; }}
register_workloads() {{ :; }}
helm() {{ :; }}
kubectl() {{
  case "$*" in
    *"apply -f -"*) cat > /dev/null ;;
    *"--dry-run=client"*) printf fixture ;;
    *) : ;;
  esac
}}
deploy_stack
cat "$WORK_DIR/postgres.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, "failed to render PostgreSQL readiness"
    deployment, _service = list(yaml.safe_load_all(result.stdout))
    readiness = deployment["spec"]["template"]["spec"]["containers"][0][
        "readinessProbe"
    ]
    assert readiness["timeoutSeconds"] == 5
    return readiness["exec"]["command"]


@pytest.mark.parametrize(
    ("phase", "auth", "database", "psql_exit", "ready"),
    [
        ("temporary_socket", "ok", "expected", 0, False),
        ("final_tcp", "bad", "expected", 0, False),
        ("final_tcp", "ok", "wrong", 0, False),
        ("final_tcp", "ok", "expected", 1, False),
        ("final_tcp", "ok", "expected", 0, True),
    ],
)
def test_postgres_readiness_requires_final_tcp_auth_and_database(
    phase: str, auth: str, database: str, psql_exit: int, ready: bool
) -> None:
    shell, flags, probe = _postgres_fixture_readiness_command()
    assert (shell, flags) == ("sh", "-ec")
    command = f"""set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/bin"
cat > "$work/bin/pg_isready" <<'STUB'
#!/bin/sh
set -eu
: > "$PG_TRACE"
[ "$*" = "-h 127.0.0.1 -U $POSTGRES_USER -d $POSTGRES_DB" ] || exit 2
printf '%s' "$POSTGRES_PASSWORD"
printf '%s' "$POSTGRES_PASSWORD" >&2
[ "$PHASE" = final_tcp ]
STUB
cat > "$work/bin/psql" <<'STUB'
#!/bin/sh
set -eu
: > "$PSQL_TRACE"
[ "${{PGPASSWORD:-}}" = "$POSTGRES_PASSWORD" ] || exit 2
[ "${{PGCONNECT_TIMEOUT:-}}" = 2 ] || exit 2
[ "$*" = "-X -w -h 127.0.0.1 -U $POSTGRES_USER -d $POSTGRES_DB -Atqc SELECT current_database()" ] || exit 2
printf '%s' "$POSTGRES_PASSWORD" >&2
[ "$AUTH" = ok ] || exit 1
if [ "$DATABASE" = expected ]; then printf '%s\\n' "$POSTGRES_DB"; else printf 'wrong\\n'; fi
exit "$PSQL_EXIT"
STUB
chmod +x "$work/bin/pg_isready" "$work/bin/psql"
export PATH="$work/bin:$PATH"
export POSTGRES_USER=ue_app POSTGRES_DB=university
export POSTGRES_PASSWORD="$(openssl rand -hex 32)"
export PHASE={phase} AUTH={auth} DATABASE={database} PSQL_EXIT={psql_exit}
export PG_TRACE="$work/pg-trace" PSQL_TRACE="$work/psql-trace"
set +e
sh -ec {shlex.quote(probe)}
status=$?
set -e
test -f "$PG_TRACE"
if [[ "$PHASE" == temporary_socket ]]; then
  test ! -e "$PSQL_TRACE"
else
  test -f "$PSQL_TRACE"
fi
exit "$status"
"""
    result = _bash_command(command)
    assert (result.returncode == 0) is ready
    output_is_empty = not result.stdout and not result.stderr
    assert output_is_empty, "probe must not expose values"


def test_revocation_init_image_values_bind_to_one_measured_digest() -> None:
    function = _shell_function("write_revocation_store_values")
    command = f"""set -euo pipefail
{function}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
RELEASE=ue
IMAGE_TAG=proof
BACKEND_INIT_IMAGE_REPOSITORY=127.0.0.1:32768/aud373/fixture/backend
BACKEND_IMAGE_DIGEST=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
write_revocation_store_values
cat "$WORK_DIR/revocation-store-values.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    values = yaml.safe_load(result.stdout)
    digest = values["global"]["backendImageDigest"]
    repository = values["global"]["backendImageRepository"]
    assert repository == "127.0.0.1:32768/aud373/fixture/backend"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert values["applicationReleaseName"] == "ue"
    assert values["redis"]["fullnameOverride"] == "ue-revocation-redis"
    assert values["redis"]["commonLabels"] == {
        "university-ecosystem.io/revocation-store-for": "ue",
        "app.kubernetes.io/instance": "ue",
    }
    helper = values["redis"]["metrics"]["passwordFileInitImage"]
    assert helper == {
        "repository": repository,
        "tag": "proof",
        "digest": digest,
        "pullPolicy": "Always",
    }


@pytest.mark.parametrize(
    ("repository", "digest"),
    [
        ("127.0.0.1:32768/aud373/fixture/other", "sha256:" + "a" * 64),
        ("127.0.0.1:32768/aud373/fixture/backend", "sha256:bad"),
    ],
)
def test_revocation_init_image_binding_rejects_mutated_source_or_digest(
    repository: str, digest: str
) -> None:
    command = f"""set -euo pipefail
{_shell_function("write_revocation_store_values")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
RELEASE=ue
IMAGE_TAG=proof
BACKEND_INIT_IMAGE_REPOSITORY={shlex.quote(repository)}
BACKEND_IMAGE_DIGEST={shlex.quote(digest)}
if write_revocation_store_values; then exit 1; fi
test ! -e "$WORK_DIR/revocation-store-values.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("default_classes", "succeeds", "expected_class"),
    [
        ("", True, ""),
        ("kind-local-path", True, "kind-local-path"),
        ("kind-local-path\nother-class", False, None),
        ("invalid_class", False, None),
    ],
)
def test_private_revocation_volume_is_prebound_durable_and_fails_closed(
    default_classes: str, succeeds: bool, expected_class: str | None
) -> None:
    command = f"""set -euo pipefail
{_shell_function("provision_revocation_store_volume")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
CLUSTER_NAME=owned-kind
NAMESPACE=university-ecosystem
RELEASE=ue
RUN_SUFFIX=0123456789ab
DEFAULT_CLASSES={shlex.quote(default_classes)}
log() {{ :; }}
kind() {{
  [[ "$*" == "get nodes --name owned-kind" ]] || return 90
  printf 'owned-kind-control-plane\\n'
}}
docker() {{
  [[ "$*" == "exec owned-kind-control-plane mkdir -p /var/lib/ue-aud373-0123456789ab-revocation-redis" ]]
}}
timeout() {{ [[ "$1" == 30 ]] || return 92; shift; "$@"; }}
kubectl() {{
  if [[ "$1" == get && "$2" == storageclass ]]; then
    [[ -z "$DEFAULT_CLASSES" ]] || printf '%s\\n' "$DEFAULT_CLASSES"
  elif [[ "$1" == apply && "$2" == -f ]]; then
    cat "$3"
  else
    return 91
  fi
}}
if provision_revocation_store_volume; then status=0; else status=$?; fi
if [[ "{"0" if succeeds else "1"}" == 0 ]]; then
  test "$status" = 0
else
  test "$status" != 0
fi
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    if not succeeds:
        assert not result.stdout
        return
    volume = yaml.safe_load(result.stdout)
    assert volume["metadata"]["name"] == "ue-aud373-0123456789ab-revocation-redis"
    assert volume["spec"]["capacity"] == {"storage": "2Gi"}
    assert volume["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert volume["spec"]["persistentVolumeReclaimPolicy"] == "Retain"
    assert volume["spec"]["storageClassName"] == expected_class
    assert volume["spec"]["local"]["path"] == (
        "/var/lib/ue-aud373-0123456789ab-revocation-redis"
    )
    assert volume["spec"]["nodeAffinity"]["required"]["nodeSelectorTerms"][0][
        "matchExpressions"
    ] == [
        {
            "key": "kubernetes.io/hostname",
            "operator": "In",
            "values": ["owned-kind-control-plane"],
        }
    ]
    assert volume["spec"]["claimRef"] == {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "name": "redis-data-ue-revocation-redis-master-0",
        "namespace": "university-ecosystem",
    }


def test_generated_gRPC_material_has_exact_CA_DNS_URI_and_EKU(tmp_path: Path) -> None:
    from cryptography import x509
    from cryptography.x509.oid import ExtendedKeyUsageOID

    bash = shutil.which("bash")
    assert bash is not None
    command = f"""set -euo pipefail
umask 077
{_shell_function("write_grpc_mtls_material")}
WORK_DIR={shlex.quote(_bash_path(tmp_path))}
RUN_SUFFIX=0123456789ab
FILE_PROCESSOR_SVC=ue-university-ecosystem-file-processor
GATEWAY_SPIFFE_ID=spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway
TRUST_DOMAIN=university.ecosystem
NAMESPACE=university-ecosystem
RELEASE=ue
write_grpc_mtls_material
"""
    result = subprocess.run(  # noqa: S603  # Fixed Bash runs the repository-owned certificate generator.
        [bash, "-s"],
        input=command.encode(),
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    material = tmp_path / "grpc-mtls"
    ca = x509.load_pem_x509_certificate((material / "ca.crt").read_bytes())
    server = x509.load_pem_x509_certificate((material / "server.crt").read_bytes())
    client = x509.load_pem_x509_certificate((material / "client.crt").read_bytes())
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert server.issuer == ca.subject
    assert client.issuer == ca.subject
    assert server.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName) == [
        "ue-university-ecosystem-file-processor"
    ]
    assert client.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.UniformResourceIdentifier) == [
        "spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway"
    ]
    assert list(
        server.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    ) == [ExtendedKeyUsageOID.SERVER_AUTH]
    assert list(
        client.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    ) == [ExtendedKeyUsageOID.CLIENT_AUTH]


@pytest.mark.parametrize(
    ("service_name", "gateway_identity"),
    [
        (
            "ue-file-processor.evil",
            "spiffe://university.ecosystem/ns/university-ecosystem/sa/ue-gateway",
        ),
        (
            "ue-university-ecosystem-file-processor",
            "spiffe://university.ecosystem/ns/university-ecosystem/sa/other",
        ),
    ],
)
def test_gRPC_certificate_creation_rejects_mutated_dns_or_gateway_identity(
    service_name: str, gateway_identity: str, tmp_path: Path
) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    command = f"""set -euo pipefail
umask 077
{_shell_function("write_grpc_mtls_material")}
WORK_DIR={shlex.quote(_bash_path(tmp_path))}
RUN_SUFFIX=0123456789ab
FILE_PROCESSOR_SVC={shlex.quote(service_name)}
GATEWAY_SPIFFE_ID={shlex.quote(gateway_identity)}
TRUST_DOMAIN=university.ecosystem
NAMESPACE=university-ecosystem
RELEASE=ue
openssl() {{ touch "$WORK_DIR/openssl-called"; }}
if write_grpc_mtls_material; then exit 1; fi
test ! -e "$WORK_DIR/openssl-called"
test ! -e "$WORK_DIR/grpc-mtls/ca.key"
"""
    result = subprocess.run(  # noqa: S603  # Fixed Bash checks fail-closed certificate input validation.
        [bash, "-s"],
        input=command.encode(),
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_real_temporal_dev_manifest_uses_tracked_image_health_and_network_scope() -> (
    None
):
    command = f"""set -euo pipefail
{_shell_function("read_tracked_pin")}
{_shell_function("install_temporal_dev_server")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
ROOT_DIR={shlex.quote(_bash_path(ROOT))}
NAMESPACE=university-ecosystem
RELEASE=ue
log() {{ :; }}
kubectl() {{
  if [[ "$1" == apply ]]; then
    cat "$3"
  elif [[ "$1" == -n ]]; then
    [[ "$*" == "-n university-ecosystem rollout status deployment/ue-aud373-temporal-dev --timeout=120s" ]]
  else
    return 90
  fi
}}
install_temporal_dev_server
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    deployment, service, policy = list(yaml.safe_load_all(result.stdout))
    tracked_image = yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )["services"]["temporal-admin-tools"]["image"]
    assert re.fullmatch(
        r"temporalio/admin-tools:1\.30\.7@sha256:[0-9a-f]{64}", tracked_image
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert container["image"] == tracked_image
    assert container["imagePullPolicy"] == "IfNotPresent"
    assert container["command"] == ["temporal"]
    assert container["args"] == [
        "server",
        "start-dev",
        "--ip",
        "0.0.0.0",  # noqa: S104  # Isolated pod binds behind a ClusterIP and FP-only ingress policy.
        "--port",
        "7233",
        "--headless",
    ]
    health_command = [
        "temporal",
        "operator",
        "cluster",
        "health",
        "--address",
        "127.0.0.1:7233",
        "--tls=false",
        "--command-timeout",
        "2s",
    ]
    assert container["startupProbe"]["exec"]["command"] == health_command
    assert container["readinessProbe"]["exec"]["command"] == health_command
    assert container["resources"] == {
        "requests": {"cpu": "250m", "memory": "256Mi"},
        "limits": {"cpu": "1", "memory": "1Gi"},
    }
    assert pod_spec["automountServiceAccountToken"] is False
    assert service["metadata"]["name"] == "temporal"
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["selector"] == deployment["spec"]["selector"]["matchLabels"]
    assert service["spec"]["ports"] == [
        {
            "name": "frontend",
            "port": 7233,
            "targetPort": "frontend",
            "protocol": "TCP",
        }
    ]
    assert policy["spec"] == {
        "podSelector": {
            "matchLabels": {
                "app.kubernetes.io/name": "temporal",
                "university-ecosystem.io/aud373-owned": "true",
            }
        },
        "policyTypes": ["Ingress"],
        "ingress": [
            {
                "from": [
                    {
                        "podSelector": {
                            "matchLabels": {
                                "app.kubernetes.io/instance": "ue",
                                "app.kubernetes.io/component": "file-processor",
                            }
                        }
                    }
                ],
                "ports": [{"protocol": "TCP", "port": 7233}],
            }
        ],
    }


@pytest.mark.parametrize(
    "source",
    [
        "services:\n  backend:\n    image: example/backend\n",
        (
            "services:\n"
            "  temporal-admin-tools:\n"
            "    image: temporalio/admin-tools:1.31.0@sha256:"
            + "a" * 64
            + "\n  next-service:\n    image: example/next\n"
        ),
        (
            "services:\n"
            "  temporal-admin-tools:\n"
            "    image: temporalio/admin-tools:1.30.7@sha256:"
            + "a"
            * 64
            + "\n  next-service:\n    image: example/next\n"
            "  temporal-admin-tools:\n"
            "    image: temporalio/admin-tools:1.30.7@sha256:"
            + "b" * 64
            + "\n  final-service:\n    image: example/final\n"
        ),
    ],
)
def test_temporal_dev_install_rejects_missing_mutated_or_ambiguous_pin(
    source: str, tmp_path: Path
) -> None:
    (tmp_path / "docker-compose.yml").write_text(source, encoding="utf-8")
    command = f"""set -euo pipefail
{_shell_function("read_tracked_pin")}
{_shell_function("install_temporal_dev_server")}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
WORK_DIR="$work"
ROOT_DIR={shlex.quote(_bash_path(tmp_path))}
NAMESPACE=university-ecosystem
log() {{ :; }}
kubectl() {{ touch "$work/unexpected-kubectl"; }}
if install_temporal_dev_server; then exit 1; fi
test ! -e "$work/unexpected-kubectl"
test ! -e "$WORK_DIR/temporal-dev.yaml"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr


def test_file_processor_startup_and_gateway_health_keep_real_dependencies_ordered() -> (
    None
):
    script = _script()
    deploy = _shell_function("deploy_stack")
    ordered_calls = [
        "write_grpc_mtls_material || return 1",
        "install_grpc_mtls_secrets || return 1",
        "install_revocation_store || return 1",
        "install_temporal_dev_server || return 1",
        'helm upgrade --install "$RELEASE"',
        'kubectl -n "$NAMESPACE" rollout status "deployment/${BACKEND_SVC}"',
        "wait_for_file_process_stream || return 1",
        "--set fileProcessor.enabled=true",
        '"deployment/${FILE_PROCESSOR_SVC}" --timeout=600s',
        '"deployment/${GATEWAY_SVC}" --timeout=600s',
    ]
    positions = [deploy.index(call) for call in ordered_calls]
    assert positions == sorted(positions)
    assert deploy.count("--set fileProcessor.enabled=true") == 1
    assert "fileProcessor:\n  enabled: false\n" in script
    assert "internalGrpcMTLS:\n  enabled: true\n" in script
    assert "grpcUseTLS: true" in script

    main = (ROOT / "services/file-processor/cmd/file-processor/main.go").read_text(
        encoding="utf-8"
    )
    startup_order = [
        main.index(
            "jwtOptions, replayGuard, closeRevocation, err := initRevocationAndReplay"
        ),
        main.index("startTemporalWorkerFunc(ctx, cfg, logger)"),
        main.index("startNatsSubscriberFunc(ctx, cfg, c, logger, replayGuard)"),
        main.index("setupGRPCServerFunc(ctx, cfg"),
    ]
    assert startup_order == sorted(startup_order)
    auth = (ROOT / "services/file-processor/cmd/file-processor/auth.go").read_text(
        encoding="utf-8"
    )
    assert "client.Ping(pingCtx).Err()" in auth
    assert "if pingErr := client.Ping(pingCtx).Err(); pingErr != nil" in auth
    subscriber = main.split("func reconcileFileProcessConsumer", 1)[1].split("\n}", 1)[
        0
    ]
    assert "js.StreamNameBySubject(subject)" in subscriber
    assert "fileProcessSubject" in main

    handlers = (ROOT / "services/gateway/internal/handlers/handlers.go").read_text(
        encoding="utf-8"
    )
    assert 'Service: "file_processor.v1.FileProcessingService"' in handlers
    assert (
        "response.GetStatus() != grpc_health_v1.HealthCheckResponse_SERVING" in handlers
    )
    gateway_deployment = (
        ROOT / "charts/university-ecosystem/templates/gateway-deployment.yaml"
    ).read_text(encoding="utf-8")
    assert "path: /health/ready" in gateway_deployment
    gateway_main = (ROOT / "services/gateway/cmd/gateway/main.go").read_text(
        encoding="utf-8"
    )
    assert (
        'public.GET("/health/ready", handlers.ReadinessHandler(grpc_health_v1.NewHealthClient(grpcConn), 2*time.Second))'
        in gateway_main
    )
    assert '"deployment/${GATEWAY_SVC}" --timeout=600s' in deploy
    server = (ROOT / "services/file-processor/cmd/file-processor/main.go").read_text(
        encoding="utf-8"
    )
    gateway = (ROOT / "services/gateway/cmd/gateway/main.go").read_text(
        encoding="utf-8"
    )
    assert "ClientAuth:   tls.RequireAndVerifyClientCert" in server
    assert "verifyAllowedClientURI(allowedClientURIs, state)" in server
    assert "RootCAs:      roots" in gateway
    assert "ServerName:   cfg.GRPCServerName" in gateway
    assert "GRPCClientIdentityURI" in gateway
    assert "InsecureSkipVerify" not in server + gateway


@pytest.mark.parametrize(
    ("payload", "command_status", "valid"),
    [
        ("NO_SVID_TCP=CONNECTED\nNO_SVID_TLS=REJECTED\n", 0, True),
        ("NO_SVID_TCP=CONNECTED\nNO_SVID_TLS=REJECTED\n", 37, False),
        ("NO_SVID_TCP=CONNECTED\nNO_SVID_TLS=ERROR\nNO_SVID_TLS=REJECTED\n", 0, False),
        ("NO_SVID_TCP=CONNECTED\nNO_SVID_TLS=REJECTED secret\n", 0, False),
        ("NO_SVID_TLS=REJECTED\x00secret\n", 0, False),
        ("secret" * 20000 + "\n", 0, False),
        ("secret\n" * 12000, 0, False),
        ("PROBE_EXIT=0\n", 37, False),
    ],
    ids=[
        "clean",
        "command-failure",
        "duplicate",
        "suffix",
        "nul",
        "long-line",
        "noise",
        "fake-exit",
    ],
)
def test_probe_capture_is_bounded_and_preserves_real_exit(
    payload: str, command_status: int, valid: bool, tmp_path: Path
) -> None:
    raw = tmp_path / "input"
    raw.write_bytes(payload.encode())
    command = f"""set -euo pipefail
{_shell_function("sanitize_probe_output")}
{_shell_function("capture_probe")}
DIAG_DIR={shlex.quote(_bash_path(tmp_path))}
run_probe() {{ cat {shlex.quote(_bash_path(raw))}; return {command_status}; }}
status=0
capture_probe no-svid-tls ignored || status=$?
printf 'CAPTURE_STATUS=%s\\n' "$status"
cat "$DIAG_DIR/probe-no-svid-tls.txt"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    output = result.stdout.decode()
    assert "secret" not in output
    assert len(output) < 2048
    assert ("CAPTURE_STATUS=0\n" in output) is valid
    assert f"PROBE_EXIT={command_status}\n" in output


@pytest.mark.parametrize("broken_diagnostics", [False, True, None])
def test_all_probe_runs_record_diagnostics_or_fail_closed_and_continue(
    broken_diagnostics: bool | None, tmp_path: Path
) -> None:
    directory = tmp_path / "diagnostics"
    if broken_diagnostics:
        directory.write_text("not a directory", encoding="utf-8")
    elif broken_diagnostics is False:
        directory.mkdir()
    command = f"""set -euo pipefail
{_shell_function("sanitize_probe_output")}
{_shell_function("capture_probe")}
{_shell_function("record")}
{_shell_function("run_proofs")}
DIAG_DIR={shlex.quote(_bash_path(directory))}
FAILURES=0
GATEWAY_HOP_PY=; NO_SVID_TLS_PY=; PLAINTEXT_PY=
run_probe() {{
  case "$1" in
    gateway-hop) printf 'STATUS=200\\nBODY_HAS_KEYS=True\\n' ;;
    no-svid-tls) printf 'NO_SVID_TCP=CONNECTED\\nNO_SVID_TLS=REJECTED\\n' ;;
    plaintext) printf 'PLAINTEXT_TCP=CONNECTED\\nPLAINTEXT=REJECTED\\n' ;;
  esac
}}
backend_logged_gateway_peer() {{ return 0; }}
run_proofs
printf 'FAILURES=%s\\n' "$FAILURES"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    assert f"FAILURES={3 if broken_diagnostics else 0}" in result.stdout.decode()
    assert b"d-backend-logs-gateway-peer-spiffe-id" in result.stdout
    assert b"c-plaintext-http-rejected" in result.stdout
    if not broken_diagnostics:
        assert {path.name for path in directory.iterdir()} == {
            "probe-gateway-hop.txt",
            "probe-no-svid-tls.txt",
            "probe-plaintext.txt",
        }
        assert all("PROBE_EXIT=0" in path.read_text() for path in directory.iterdir())


@pytest.mark.parametrize("require_certificate", [True, False])
def test_real_uvloop_no_svid_eof_remains_error_with_stage_diagnostics(
    require_certificate: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The production uvloop transport can discard the outgoing TLS 1.3 alert.
    # Unlike the blocking-socket fixture, do not hold a duplicate TCP socket open.
    caplog.set_level(logging.DEBUG, logger="asyncio")
    context = _server_tls_context(tmp_path)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED if require_certificate else ssl.CERT_NONE

    async def exercise() -> None:
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        errors = []
        loop.set_exception_handler(lambda _loop, context: errors.append(context))
        accepted = []

        class Respond(asyncio.Protocol):
            def connection_made(self, transport: asyncio.BaseTransport) -> None:
                accepted.append(True)
                self.transport = transport

            def data_received(self, data: bytes) -> None:
                self.transport.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                self.transport.close()

        server = await loop.create_server(Respond, "127.0.0.1", 0, ssl=context)
        try:
            port = server.sockets[0].getsockname()[1]
            result = await asyncio.to_thread(
                _probe_result, "NO_SVID_TLS_PY", "127.0.0.1", port
            )
            assert result.returncode == 0, result.stderr
            lines = result.stdout.splitlines()
            if require_certificate:
                expected = [
                    "NO_SVID_STAGE=READ_ALERT",
                    "NO_SVID_EVENT=EOF",
                    "NO_SVID_TCP=CONNECTED",
                    "NO_SVID_TLS=ERROR",
                ]
                if (
                    sys.platform == "win32"
                    and "NO_SVID_EVENT=CERTIFICATE_REQUIRED" in lines
                ):
                    expected[1] = "NO_SVID_EVENT=CERTIFICATE_REQUIRED"
                    expected[3] = "NO_SVID_TLS=REJECTED"
                assert lines == expected
                assert not accepted
                handshake_errors = [
                    record.exc_info[1]
                    for record in caplog.records
                    if record.exc_info and isinstance(record.exc_info[1], ssl.SSLError)
                ]
                if sys.platform == "win32":
                    handshake_errors.extend(item["exception"] for item in errors)
                else:
                    assert not errors
                assert len(handshake_errors) == 1
                assert isinstance(handshake_errors[0], ssl.SSLError)
                assert handshake_errors[0].reason == "PEER_DID_NOT_RETURN_A_CERTIFICATE"
            else:
                assert lines == [
                    "NO_SVID_STAGE=READ_RESPONSE",
                    "NO_SVID_EVENT=DATA",
                    "NO_SVID_TCP=CONNECTED",
                    "NO_SVID_TLS=ANSWERED",
                ]
                assert accepted == [True]
                assert not errors
        finally:
            server.close()
            await server.wait_closed()

    if sys.platform == "win32":
        asyncio.run(exercise())
    else:
        import uvloop

        uvloop.run(exercise())


@pytest.mark.parametrize("require_certificate", [True, False])
def test_public_sslobject_handshake_observer(
    tmp_path, require_certificate, monkeypatch
):
    from unittest.mock import Mock

    from app.server import spiffe_transport as transport_module

    monkeypatch.setenv("AUD373_TLS_DIAGNOSTICS", "1")
    log = Mock()
    monkeypatch.setattr(transport_module, "logger", log)
    observer = transport_module.HandshakeDiagnostics()
    hellos = []
    admitted = []

    context = _server_tls_context(tmp_path)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED if require_certificate else ssl.CERT_NONE
    context.sslobject_class = observer.sslobject_class

    def client_hello(connection, name, initial):
        hellos.append((connection, name))
        observer.client_hello(connection, name)

    context.sni_callback = client_hello

    async def exercise():
        class Respond(asyncio.Protocol):
            def connection_made(self, transport):
                admitted.append(True)
                self.transport = transport

            def data_received(self, data):
                self.transport.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                self.transport.close()

        loop = asyncio.get_running_loop()
        server = await loop.create_server(Respond, "127.0.0.1", 0, ssl=context)
        try:
            result = await asyncio.to_thread(
                _probe_result,
                "NO_SVID_TLS_PY",
                "localhost",
                server.sockets[0].getsockname()[1],
            )
            assert result.returncode == 0
            assert len(hellos) == 1
            assert re.fullmatch(r"aud373-[0-9a-f]{32}\.invalid", hellos[0][1])
            assert "NO_SVID_PROBE_ID=" + hellos[0][1][7:-8] in result.stdout
            if require_certificate:
                log.warning.assert_called_once_with(
                    "internal_mtls_handshake_rejected",
                    probe_id=str(__import__("uuid").UUID(hex=hellos[0][1][7:-8])),
                    reason="PEER_DID_NOT_RETURN_A_CERTIFICATE",
                )
                assert not admitted
                if (
                    sys.platform == "win32"
                    and "NO_SVID_EVENT=CERTIFICATE_REQUIRED" in result.stdout
                ):
                    assert "NO_SVID_TLS=REJECTED" in result.stdout
                else:
                    assert "NO_SVID_EVENT=EOF" in result.stdout
                    assert "NO_SVID_TLS=ERROR" in result.stdout
            else:
                log.warning.assert_not_called()
                assert admitted == [True]
                assert "NO_SVID_TLS=ANSWERED" in result.stdout
        finally:
            server.close()
            await server.wait_closed()

    if sys.platform == "win32":
        asyncio.run(exercise())
    else:
        import uvloop

        uvloop.run(exercise())


@pytest.mark.parametrize("rollout_status", [0, 1, 124])
def test_final_backend_rollout_precedes_probes_and_fails_closed(
    rollout_status: int,
) -> None:
    deploy = _shell_function("deploy_stack")
    final_upgrade = deploy.rsplit('  helm upgrade --install "$RELEASE"', 1)[1]
    tail = final_upgrade.split('  kubectl -n "$NAMESPACE" rollout status', 1)[1]
    rollout_tail = '  kubectl -n "$NAMESPACE" rollout status' + tail
    assert rollout_tail.index('"deployment/${BACKEND_SVC}"') < rollout_tail.index(
        '"deployment/${FILE_PROCESSOR_SVC}"'
    )
    command = f"""set -euo pipefail
NAMESPACE=fixture
BACKEND_SVC=backend
FILE_PROCESSOR_SVC=file-processor
GATEWAY_SVC=gateway
kubectl() {{
  printf '%s\\n' "$*"
  case "$*" in *deployment/backend*) return {rollout_status} ;; esac
}}
finish_deploy() {{
{rollout_tail}
if finish_deploy; then printf 'PROBES_ALLOWED\\n'; else printf 'PROBES_BLOCKED\\n'; fi
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    output = result.stdout.decode("utf-8")
    assert "rollout status deployment/backend --timeout=600s" in output
    if rollout_status == 0:
        assert "PROBES_ALLOWED" in output
        assert "deployment/file-processor" in output
        assert "deployment/gateway" in output
    else:
        assert "PROBES_BLOCKED" in output
        assert "PROBES_ALLOWED" not in output
        assert "deployment/file-processor" not in output
        assert "deployment/gateway" not in output


@pytest.mark.parametrize("prepared", [True, False])
@pytest.mark.parametrize("captured", [True, False])
@pytest.mark.parametrize("verified", [True, False])
def test_server_proof_requires_prepared_successful_capture_and_verified_evidence(
    prepared, captured, verified
):
    command = f"""set -euo pipefail
{_shell_function("record")}
{_shell_function("run_proofs")}
FAILURES=0
GATEWAY_HOP_PY=; NO_SVID_TLS_PY=; PLAINTEXT_PY=
backend_logged_gateway_peer() {{ return 0; }}
prepare_no_svid_evidence() {{ return {0 if prepared else 1}; }}
verify_no_svid_evidence() {{ printf 'VERIFIER_CALLED\\n'; return {0 if verified else 1}; }}
capture_probe() {{
  case "$1" in
    gateway-hop) printf 'STATUS=200\\nBODY_HAS_KEYS=True\\n' ;;
    no-svid-tls) printf 'NO_SVID_TCP=CONNECTED\\nNO_SVID_TLS=ERROR\\n'; return {0 if captured else 1} ;;
    plaintext) printf 'PLAINTEXT_TCP=CONNECTED\\nPLAINTEXT=REJECTED\\n' ;;
  esac
}}
run_proofs
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    output = result.stdout.decode()
    assert ("VERIFIER_CALLED" in output) is (prepared and captured)
    expected = "PASS" if prepared and captured and verified else "FAIL"
    assert f"{expected} b-no-svid-tls-client-rejected" in output


def test_server_evidence_helpers_use_owned_pinned_backend_and_private_state():
    prepare = _shell_function("prepare_no_svid_evidence")
    verify = _shell_function("verify_no_svid_evidence")
    assert '--deployment "$BACKEND_SVC" --service "$BACKEND_SVC"' in prepare
    assert (
        "${LOCAL_REGISTRY_ADDRESS}/university-backend@${BACKEND_IMAGE_DIGEST}"
        in prepare
    )
    assert "${WORK_DIR}/no-svid-server-state.json" in prepare
    assert "${WORK_DIR}/no-svid-server-state.json" in verify
    assert "${DIAG_DIR}/probe-no-svid-tls.txt" in verify
    assert "${DIAG_DIR}/no-svid-server-evidence.txt" in verify
    assert 'digest: "${BACKEND_IMAGE_DIGEST:-}"' in _script()


def test_generated_proof_backend_uses_the_built_manifest_digest(monkeypatch):
    import hashlib

    digest = "sha256:" + hashlib.sha256(b"owned source image fixture").hexdigest()
    monkeypatch.setenv("BACKEND_IMAGE_DIGEST", digest)
    values = _generated_proof_values()
    assert values["backend"]["image"] == {
        "repository": "127.0.0.1:32768/university-backend",
        "digest": digest,
    }
