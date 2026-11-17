"""Fail-closed orchestration contracts for the real SSR kind proof."""

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
    import shlex

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
