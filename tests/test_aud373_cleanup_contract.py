"""Terminal success requires cleanup of all owned resources, without secret errors."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from tests.test_internal_mtls_kind_contract import (
    _bash_command,
    _bash_path,
    _shell_function,
)


@pytest.mark.parametrize("initial_status", [0, 17])
@pytest.mark.parametrize("failures", range(16))
@pytest.mark.parametrize("conditional", [False, True])
def test_cleanup_attempts_every_step_and_preserves_original_failure(
    tmp_path: Path, initial_status: int, failures: int, conditional: bool
) -> None:
    operations = ["diagnostics", "cluster", "registry", "workdir"]
    failing = [name for bit, name in enumerate(operations) if failures & (1 << bit)]
    invocation = "if terminate; then :; fi" if conditional else "terminate"
    result = _bash_command(
        f"""set -euo pipefail
{_shell_function("cleanup")}
PROOFS_PASSED=1
CLUSTER_CREATED=1
CLUSTER_NAME=owned-proof
KUBECONFIG=/owned/kubeconfig
REGISTRY_CREATED=1
REGISTRY_CONTAINER_ID={"a" * 64}
WORK_DIR=/owned/private-material
TRACE={shlex.quote(_bash_path(tmp_path / "trace"))}
operation() {{
  printf '%s\\n' "$1" >> "$TRACE"
  if [[ ' {" ".join(failing)} ' == *" $1 "* ]]; then
    printf 'synthetic-private-command-error' >&2
    return 71
  fi
}}
log() {{ printf '%s\\n' "$*" >&2; }}
collect_diagnostics() {{ operation diagnostics; }}
kind() {{ operation cluster; }}
docker() {{ operation registry; }}
timeout() {{
  shift
  case "$1" in
    kind|docker) "$@" ;;
    *) return 99 ;;
  esac
}}
rm() {{ operation workdir; }}
terminate() {{ trap cleanup EXIT; exit {initial_status}; }}
{invocation}
"""
    )
    expected_status = initial_status or (1 if failing else 0)
    assert result.returncode == expected_status, "Cleanup exit status masked failure"
    assert (tmp_path / "trace").read_text().splitlines() == [
        "diagnostics",
        "cluster",
        "registry",
        "workdir",
    ]
    if expected_status == 0:
        assert result.stdout == b"RESULT=PASS\n"
    elif initial_status == 0:
        assert result.stdout == b"RESULT=FAIL cleanup=1\n"
    else:
        assert not result.stdout
    assert b"synthetic-private-command-error" not in result.stderr
    expected_errors = {
        "diagnostics": "cleanup failed: diagnostics collection",
        "cluster": "cleanup failed: owned kind cluster",
        "registry": "cleanup failed: owned registry container",
        "workdir": "cleanup failed: private work directory",
    }
    assert result.stderr.decode().splitlines() == [
        expected_errors[key] for key in failing
    ]


def test_cleanup_never_deletes_unowned_resources_or_passes_invalid_owned_identity(
    tmp_path: Path,
) -> None:
    result = _bash_command(
        f"""set -euo pipefail
{_shell_function("cleanup")}
PROOFS_PASSED=1
CLUSTER_CREATED=0
CLUSTER_NAME=unowned
KUBECONFIG=/owned/kubeconfig
REGISTRY_CREATED=1
REGISTRY_CONTAINER_ID=invalid
WORK_DIR=/owned/private-material
TRACE={shlex.quote(_bash_path(tmp_path / "trace"))}
log() {{ printf '%s\\n' "$*" >&2; }}
collect_diagnostics() {{ :; }}
kind() {{ echo UNEXPECTED; }}
docker() {{ echo UNEXPECTED; }}
rm() {{ printf '%s' workdir > "$TRACE"; }}
trap cleanup EXIT
"""
    )
    assert result.returncode == 1
    assert b"UNEXPECTED" not in result.stdout
    assert b"RESULT=PASS" not in result.stdout
    assert (tmp_path / "trace").read_text() == "workdir"


def test_main_defers_pass_until_owned_cleanup_has_succeeded() -> None:
    assert "RESULT=PASS" not in _shell_function("main")
    assert "PROOFS_PASSED=1" in _shell_function("main")
    assert "RESULT=PASS" in _shell_function("cleanup")


@pytest.mark.parametrize(
    "blocked",
    [
        "none",
        "directory",
        "docker-daemon-endpoint.txt",
        "registry-container-id.txt",
        "registry-endpoint.txt",
    ],
)
@pytest.mark.parametrize("initial_status", [0, 17])
def test_real_collector_required_write_failure_reaches_cleanup_status(
    tmp_path: Path, blocked: str, initial_status: int
) -> None:
    diagnostic = tmp_path / "diagnostics"
    if blocked == "directory":
        diagnostic.write_text("synthetic occupied path")
    else:
        diagnostic.mkdir()
        if blocked != "none":
            (diagnostic / blocked).mkdir()
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("synthetic nonempty command-double config")
    trace = tmp_path / "trace"
    workdir = tmp_path / "private-material"
    workdir.mkdir()
    (workdir / "synthetic").write_text("owned material")
    result = _bash_command(
        f"""set -euo pipefail
{_shell_function("collect_diagnostics")}
{_shell_function("cleanup")}
# Stub backend probes in this fake-only aggregator scenario.
collect_backend_probe_diagnostics() {{ :; }}
PROOFS_PASSED=1
CLUSTER_CREATED=1
CLUSTER_NAME=owned-proof
KUBECONFIG={shlex.quote(_bash_path(kubeconfig))}
REGISTRY_CREATED=1
REGISTRY_CONTAINER_ID={"a" * 64}
WORK_DIR={shlex.quote(_bash_path(workdir))}
DIAG_DIR={shlex.quote(_bash_path(diagnostic))}
DOCKER_DAEMON_ENDPOINT=unix:///owned/docker.sock
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
NAMESPACE=owned
SPIRE_NAMESPACE=spire
TRACE={shlex.quote(_bash_path(trace))}
log() {{ printf '%s\\n' "$*" >&2; }}
hostname() {{ printf command-double; }}
# Observation failures remain best effort. They are not cleanup-operation failures.
kubectl() {{ printf 'kubectl %s\\n' "$*" >> "$TRACE"; return 71; }}
docker() {{
  if [[ "$1" == rm ]]; then printf 'registry\\n' >> "$TRACE"; else printf 'docker %s\\n' "$*" >> "$TRACE"; return 71; fi
}}
timeout() {{
  if [[ "${{1:-}}" == --kill-after=* ]]; then shift 2; else shift; fi
  "$@"
}}
kind() {{ printf 'cluster\\n' >> "$TRACE"; }}
rm() {{ printf 'workdir\\n' >> "$TRACE"; command rm "$@"; }}
trap cleanup EXIT
exit {initial_status}
"""
    )
    expected = initial_status or (0 if blocked == "none" else 1)
    assert result.returncode == expected, (
        "Real collector masked a required artifact write failure"
    )
    observations = trace.read_text().splitlines()
    assert observations[-3:] == ["cluster", "registry", "workdir"]
    assert not workdir.exists()
    if blocked != "directory":
        assert any("get all,serviceaccounts" in line for line in observations)
        assert any("auth can-i watch nodes" in line for line in observations)
        assert any("{{.NCPU}}" in line for line in observations)
        assert any("status.allocatable" in line for line in observations)
        assert any("describe nodes" in line for line in observations)
        assert any(line.startswith("docker logs ") for line in observations)
    if expected == 0:
        assert result.stdout == b"RESULT=PASS\n"
        assert not result.stderr
    else:
        assert b"RESULT=PASS" not in result.stdout
    if blocked != "none":
        assert result.stderr == b"cleanup failed: diagnostics collection\n"


@pytest.mark.parametrize("cluster_owned", [0, 1])
@pytest.mark.parametrize("registry_owned", [0, 1])
@pytest.mark.parametrize("valid_identity", [False, True])
@pytest.mark.parametrize("proofs_passed", [0, 1])
def test_cleanup_only_deletes_owned_identities_and_only_passes_completed_proofs(
    tmp_path: Path,
    cluster_owned: int,
    registry_owned: int,
    valid_identity: bool,
    proofs_passed: int,
) -> None:
    identity = "a" * 64 if valid_identity else "guessed-registry-name"
    trace = tmp_path / "trace"
    result = _bash_command(
        f"""set -euo pipefail
{_shell_function("cleanup")}
PROOFS_PASSED={proofs_passed}
CLUSTER_CREATED={cluster_owned}
CLUSTER_NAME=owned-proof
KUBECONFIG=/owned/kubeconfig
REGISTRY_CREATED={registry_owned}
REGISTRY_CONTAINER_ID={identity}
WORK_DIR=/owned/private-material
TRACE={shlex.quote(_bash_path(trace))}
log() {{ printf '%s\\n' "$*" >&2; }}
collect_diagnostics() {{ :; }}
kind() {{ printf 'kind %s\\n' "$*" >> "$TRACE"; }}
docker() {{ printf 'docker %s\\n' "$*" >> "$TRACE"; }}
timeout() {{
  shift
  case "$1" in
    kind|docker) "$@" ;;
    *) return 99 ;;
  esac
}}
rm() {{ printf 'rm %s\\n' "$*" >> "$TRACE"; }}
trap cleanup EXIT
"""
    )
    expected = []
    if cluster_owned:
        expected.append(
            "kind delete cluster --name owned-proof --kubeconfig /owned/kubeconfig"
        )
    if registry_owned and valid_identity:
        expected.append(f"docker rm --force --volumes {identity}")
    expected.append("rm -rf /owned/private-material")
    assert trace.read_text().splitlines() == expected
    failed = registry_owned and not valid_identity
    assert result.returncode == int(bool(failed))
    assert (b"RESULT=PASS" in result.stdout) == (bool(proofs_passed) and not failed)


@pytest.mark.parametrize("context", ["if", "or"])
@pytest.mark.parametrize("kubeconfig_available", [False, True])
@pytest.mark.parametrize(
    "blocked", ["none", "docker-daemon-endpoint.txt", "registry-container-id.txt"]
)
def test_real_collector_accumulates_write_failure_in_conditional_context(
    tmp_path: Path, context: str, kubeconfig_available: bool, blocked: str
) -> None:
    diagnostic = tmp_path / "diagnostics"
    diagnostic.mkdir()
    if blocked != "none":
        (diagnostic / blocked).mkdir()
    kubeconfig = tmp_path / "kubeconfig"
    if kubeconfig_available:
        kubeconfig.write_text("synthetic nonempty command-double config")
    invocation = (
        "if collect_diagnostics; then status=0; else status=$?; fi"
        if context == "if"
        else "status=0; collect_diagnostics || status=$?"
    )
    result = _bash_command(
        f"""set -euo pipefail
{_shell_function("collect_diagnostics")}
# Stub backend probes in this fake-only aggregator scenario.
collect_backend_probe_diagnostics() {{ :; }}
DIAG_DIR={shlex.quote(_bash_path(diagnostic))}
KUBECONFIG={shlex.quote(_bash_path(kubeconfig))}
DOCKER_DAEMON_ENDPOINT=unix:///owned/docker.sock
REGISTRY_CREATED=1
REGISTRY_CONTAINER_ID={"a" * 64}
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
NAMESPACE=owned
SPIRE_NAMESPACE=spire
docker() {{ printf 'synthetic docker observation\\n'; }}
hostname() {{ printf 'synthetic hostname\\n'; }}
kubectl() {{ printf 'synthetic kubectl observation\\n'; }}
timeout() {{
  if [[ "${{1:-}}" == --kill-after=* ]]; then shift 2; else shift; fi
  "$@"
}}
{invocation}
exit "$status"
"""
    )
    assert result.returncode == (0 if blocked == "none" else 1)
    assert not result.stdout
    assert not result.stderr
    assert (diagnostic / "docker-capacity.json").read_text().strip()
    assert (diagnostic / "registry-endpoint.txt").read_text() == "127.0.0.1:32768\n"
    if kubeconfig_available:
        assert (diagnostic / "node-capacity.txt").read_text().strip()
        assert (diagnostic / "spire-agent-api-authorization.txt").read_text().strip()


@pytest.mark.parametrize("observation_status", [0, 124, 127, "term-resistant"])
@pytest.mark.parametrize("initial_status", [0, 17])
def test_bounded_capacity_observations_never_prevent_owned_cleanup(
    tmp_path: Path, observation_status: int | str, initial_status: int
) -> None:
    diagnostic = tmp_path / "diagnostics"
    trace = tmp_path / "trace"
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("synthetic nonempty command-double config")
    result = _bash_command(
        f"""set -euo pipefail
{_shell_function("collect_diagnostics")}
{_shell_function("cleanup")}
# Stub backend probes in this fake-only aggregator scenario.
collect_backend_probe_diagnostics() {{ :; }}
DIAG_DIR={shlex.quote(_bash_path(diagnostic))}
TRACE={shlex.quote(_bash_path(trace))}
KUBECONFIG={shlex.quote(_bash_path(kubeconfig))}
DOCKER_DAEMON_ENDPOINT=unix:///owned/docker.sock
REGISTRY_CREATED=1
REGISTRY_CONTAINER_ID={"a" * 64}
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
CLUSTER_CREATED=1
CLUSTER_NAME=owned-proof
WORK_DIR=/owned/private-material
PROOFS_PASSED=1
NAMESPACE=owned
SPIRE_NAMESPACE=spire
log() {{ printf '%s\\n' "$*" >&2; }}
timeout() {{
  if [[ "${{2:-}}" == kind && "${{3:-}}" == delete ]] ||
     [[ "${{2:-}}" == docker && "${{3:-}}" == rm ]]; then
    shift 1
    "$@"
    return $?
  fi
  local capacity_observation=0
  if [[ "${{1:-}}" == --kill-after=5s && "${{2:-}}" == 20s ]]; then
    if [[ "${{3:-}}" == docker &&
          "${{4:-}}" == info &&
          "${{5:-}}" == --format &&
          "${{6:-}}" == '{{"cpus":'* ]] ||
       [[ "${{3:-}}" == kubectl &&
          "${{4:-}}" == --request-timeout=15s &&
          "${{5:-}}" == get &&
          "${{6:-}}" == nodes &&
          "${{7:-}}" == -o &&
          "${{8:-}}" == *".status.capacity"* &&
          "${{8:-}}" == *".status.allocatable"* ]] ||
       [[ "${{3:-}}" == kubectl &&
          "${{4:-}}" == --request-timeout=15s &&
          "${{5:-}}" == describe &&
          "${{6:-}}" == nodes ]]; then
      capacity_observation=1
    fi
  fi
  if [[ "$capacity_observation" != 1 ]]; then
    if [[ "${{1:-}}" == --kill-after=* ]]; then shift 2; else shift; fi
    "$@" || true
    return 0
  fi
  printf 'timeout %s\\n' "$*" >> "$TRACE"
  if [[ '{observation_status}' == term-resistant ]]; then
    # Exercise real TERM/KILL behavior with short test-only deadlines.
    command timeout --kill-after=0.1s 0.1s bash -c 'trap "" TERM; while :; do sleep 0.1; done'
    local status=$?
    printf 'terminated=%s\\n' "$status" >> "$TRACE"
    return "$status"
  fi
  if [[ '{observation_status}' != 0 ]]; then return {observation_status}; fi
  shift 2
  "$@"
}}
docker() {{
  case "$1" in
    rm) printf 'registry\\n' >> "$TRACE" ;;
    info) printf '%s\\n' '{{"cpus":4,"memoryBytes":8589934592}}' ;;
  esac
}}
kubectl() {{
  if [[ "$*" == *'status.allocatable'* ]]; then
    printf 'node capacity=4cpu/8Gi allocatable=3900m/7Gi\\n'
  elif [[ "$*" == *'describe nodes'* ]]; then
    printf 'Allocated resources: cpu 2000m memory 4Gi\\n'
  fi
}}
hostname() {{ printf 'synthetic hostname\\n'; }}
kind() {{ printf 'cluster\\n' >> "$TRACE"; }}
rm() {{ printf 'workdir\\n' >> "$TRACE"; }}
trap cleanup EXIT
exit {initial_status}
"""
    )
    assert result.returncode == initial_status
    assert not result.stderr
    events = trace.read_text().splitlines()
    terminated = [event for event in events if event.startswith("terminated=")]
    if observation_status == "term-resistant":
        assert terminated == ["terminated=137"] * 3
    else:
        assert not terminated
    calls = [event for event in events if not event.startswith("terminated=")]
    assert calls[-3:] == ["cluster", "registry", "workdir"]
    assert len(calls) == 6
    assert calls[0] == (
        'timeout --kill-after=5s 20s docker info --format {"cpus":{{.NCPU}},"memoryBytes":{{.MemTotal}}}'
    )
    assert calls[1].startswith(
        "timeout --kill-after=5s 20s kubectl --request-timeout=15s get nodes -o "
    )
    assert (
        calls[2]
        == "timeout --kill-after=5s 20s kubectl --request-timeout=15s describe nodes"
    )
    if observation_status == 0:
        assert json.loads((diagnostic / "docker-capacity.json").read_text()) == {
            "cpus": 4,
            "memoryBytes": 8589934592,
        }
        assert "allocatable=3900m/7Gi" in (diagnostic / "node-capacity.txt").read_text()
        assert "cpu 2000m" in (diagnostic / "node-allocated-resources.txt").read_text()
    assert (b"RESULT=PASS" in result.stdout) == (initial_status == 0)
