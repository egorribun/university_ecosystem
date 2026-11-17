"""Fail-closed orchestration contracts for the real SSR kind proof."""

import shlex
from pathlib import Path

import pytest

from tests.test_internal_mtls_kind_contract import (
    _bash_command,
    _bash_path,
    _shell_function,
)
from tests.test_k8s_networkpolicy_runtime_contract import _rows_by_id


def test_ssr_network_matrix_has_live_positive_and_isolation_controls() -> None:
    rows = _rows_by_id()
    for name in ("ssr-backend-pod", "ssr-backend-service"):
        assert rows[name].source == "a-frontend"
        assert rows[name].expect_allow is True
    cross = rows["ssr-backend-cross-release"]
    assert cross.target == "b-backend-pod"
    assert cross.expect_allow is False
    assert cross.control == ("b-fp", "b-backend-pod", "http", 8000)
    unrelated = rows["ssr-backend-unrelated"]
    assert unrelated.expect_allow is False
    assert unrelated.control == ("a-frontend", "a-backend-pod", "http", 8000)


@pytest.mark.parametrize(
    ("rollout", "receipt", "peer", "expected_failures"),
    [
        (0, "SSR_MTLS_AUTH=PASS", "frontend", 0),
        (1, "SSR_MTLS_AUTH=PASS", "frontend", 1),
        (0, "SSR_MTLS_AUTH=FAIL", "frontend", 1),
        (0, "SSR_MTLS_AUTH=PASS", "gateway", 1),
        (0, "SSR_MTLS_AUTH=PASS", "frontend-attacker", 1),
        (0, "incomplete", "gateway", 2),
    ],
)
def test_ssr_kind_receipt_requires_ready_runtime_auth_and_exact_peer(
    rollout: int,
    receipt: str,
    peer: str,
    expected_failures: int,
    tmp_path: Path,
) -> None:
    script_dir = tmp_path / "scripts" / "kind"
    script_dir.mkdir(parents=True)
    (script_dir / "ssr_mtls_request_proof.mjs").write_text(
        "// fixture", encoding="utf-8"
    )
    (tmp_path / "jwt-private.pem").write_text("fixture", encoding="utf-8")
    command = f"""set -euo pipefail
{_shell_function("run_ssr_proof")}
{_shell_function("record")}
ROOT_DIR={shlex.quote(_bash_path(tmp_path))}
WORK_DIR="$ROOT_DIR"
NAMESPACE=proof
FRONTEND_SVC=frontend
BACKEND_SVC=backend
FRONTEND_SPIFFE_ID=spiffe://proof/frontend
FAILURES=0
timeout() {{ shift; "$@"; }}
kubectl() {{
  case "$*" in
    *"rollout status"*) return {rollout} ;;
    *" exec "*) cat >/dev/null; printf '%s\\n' {shlex.quote(receipt)} ;;
    *"get pods"*) printf 'pod/backend-one\\n' ;;
    *" logs "*) printf 'internal_mtls_peer_authorized spiffe://proof/{peer}\\n' ;;
    *) return 95 ;;
  esac
}}
run_ssr_proof
printf 'FAILURES=%s\\n' "$FAILURES"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    assert f"FAILURES={expected_failures}\n" in result.stdout.decode()


@pytest.mark.parametrize("status", [0, 1, 124])
def test_live_lifecycle_gate_cannot_ignore_failure(status: int) -> None:
    command = f"""set -euo pipefail
{_shell_function("run_ssr_lifecycle_proof")}
{_shell_function("record")}
ROOT_DIR=/proof
NAMESPACE=proof
SPIRE_NAMESPACE=spire
RELEASE=ue
TRUST_DOMAIN=example.org
SSR_FIXTURE_IMAGE=fixture
FAILURES=0
timeout() {{ return {status}; }}
run_ssr_proof() {{ printf 'POST_ROTATION_SSR=RUN\\n'; }}
run_ssr_lifecycle_proof
printf 'FAILURES=%s\\n' "$FAILURES"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    assert f"FAILURES={int(status != 0)}\n" in result.stdout.decode()


@pytest.mark.parametrize("status", [0, 1, 124])
def test_ssr_proof_container_preserves_import_layout_and_failure_gate(
    status: int,
) -> None:
    command = f"""set -euo pipefail
{_shell_function("build_images")}
ROOT_DIR="/repo with spaces"
FRONTEND_IMAGE=frontend
BACKEND_IMAGE=backend
GATEWAY_IMAGE=gateway
SSR_FIXTURE_IMAGE=fixture
FILE_PROCESSOR_IMAGE=processor
timeout() {{ shift; "$@"; }}
docker() {{
  if [[ "$1" == run ]]; then
    printf 'ARG=%s\\n' "$@"
    return {status}
  fi
  printf 'BUILD=%s\\n' "$*"
}}
if build_images; then result=0; else result=$?; fi
printf 'RESULT=%s\\n' "$result"
"""
    result = _bash_command(command)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.decode().splitlines()
    args = [line.removeprefix("ARG=") for line in lines if line.startswith("ARG=")]
    assert args == [
        "run",
        "--rm",
        "--init",
        "--network",
        "none",
        "--read-only",
        "--volume",
        "/repo with spaces/scripts/kind:/proof/scripts/kind:ro",
        "--volume",
        "/repo with spaces/frontend/scripts/server-csp.mjs:"
        "/proof/frontend/scripts/server-csp.mjs:ro",
        "--entrypoint",
        "node",
        "frontend",
        "--test",
        "/proof/scripts/kind/ssr_mtls_request_proof.test.mjs",
    ]
    assert f"RESULT={int(status != 0)}" in lines
    builds = [line for line in lines if line.startswith("BUILD=")]
    assert len(builds) == (5 if status == 0 else 1)
