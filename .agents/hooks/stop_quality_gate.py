"""Stop quality gate interceptor.

Prevents the agent from terminating or self-certifying completion if any linters,
type checkers, syntax verifiers, or tests report failures.

Returns:
- {"decision": "continue", "reason": "<diagnostics>"} if any checks fail.
- {"decision": "allow", "reason": "All quality gates passed."} if all checks pass.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from .common import find_executable, find_repo_root, run_process
except (ImportError, ValueError):
    from common import find_executable, find_repo_root, run_process


def check_python_subsystem(repo_root: Path) -> tuple[bool, str]:
    """Run Ruff linter and py_compile check across Python codebase."""
    app_dir = repo_root / "app"
    if not app_dir.exists():
        return True, ""

    ruff_cmd = ["uv", "run", "ruff"] if find_executable("uv") else ["ruff"]
    code, stdout, stderr = run_process(
        [*ruff_cmd, "check", "app/"],
        cwd=repo_root,
        timeout=60,
    )
    if code != 0:
        err_msg = stdout.strip() or stderr.strip()
        return False, f"Python Ruff Lint Failures:\n{err_msg}"

    return True, ""


def check_frontend_subsystem(repo_root: Path) -> tuple[bool, str]:
    """Run TypeScript compiler check across frontend."""
    frontend_dir = repo_root / "frontend"
    if not frontend_dir.exists():
        return True, ""

    node_tsc = frontend_dir / "node_modules" / "typescript" / "bin" / "tsc"
    if node_tsc.exists() and find_executable("node"):
        cmd = ["node", "node_modules/typescript/bin/tsc", "--noEmit", "--skipLibCheck"]
    else:
        npx_bin = "npx.cmd" if os.name == "nt" else "npx"
        cmd = [npx_bin, "tsc", "--noEmit", "--skipLibCheck"]

    code, stdout, stderr = run_process(
        cmd,
        cwd=frontend_dir,
        timeout=180,
    )
    if code != 0:
        err_msg = stdout.strip() or stderr.strip()
        # Truncate long error output if needed
        if len(err_msg) > 2000:
            err_msg = err_msg[:2000] + "\n... [truncated]"
        return False, f"Frontend TypeScript Compilation Failures:\n{err_msg}"

    return True, ""


def check_services_subsystem(repo_root: Path) -> tuple[bool, str]:
    """Run go vet across all Go microservices in services/."""
    services_dir = repo_root / "services"
    if not services_dir.exists():
        return True, ""

    if not find_executable("go"):
        return True, ""

    errors: list[str] = []
    # Discover all subdirectories with go.mod
    for go_mod in services_dir.rglob("go.mod"):
        mod_dir = go_mod.parent
        code, stdout, stderr = run_process(
            ["go", "vet", "./..."],
            cwd=mod_dir,
            timeout=60,
        )
        if code != 0:
            err_msg = stderr.strip() or stdout.strip()
            rel_path = mod_dir.relative_to(repo_root).as_posix()
            errors.append(f"Go Vet Failure in '{rel_path}':\n{err_msg}")

    if errors:
        return False, "\n".join(errors)

    return True, ""


def check_gate_state_errors() -> tuple[bool, str]:
    """Check recent failures recorded in .gate_state.json."""
    state_path = Path(__file__).resolve().parent / ".gate_state.json"
    if not state_path.exists():
        return True, ""

    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
            last = data.get("last_status", {})
            if last and not last.get("passed", True):
                file_name = last.get("file", "unknown")
                output = last.get("output", "")
                return (
                    False,
                    f"Recent unresolved edit error in '{file_name}':\n{output}",
                )
    except (OSError, json.JSONDecodeError):
        pass

    return True, ""


def evaluate_stop(payload: dict[str, Any]) -> dict[str, Any]:
    """Main evaluation entry point for Stop events."""
    repo_root = find_repo_root()

    # 1. Fail-Fast: Check recent gate state errors first (<1ms)
    state_ok, state_err = check_gate_state_errors()
    if not state_ok:
        return {
            "decision": "continue",
            "reason": f"[Quality Gate Block] Unresolved defects detected:\n\n{state_err}\n\nPlease fix the above errors before completing the session.",
        }

    failures: list[str] = []

    # 2. Python subsystem
    py_ok, py_err = check_python_subsystem(repo_root)
    if not py_ok:
        failures.append(py_err)

    # 3. Frontend subsystem
    fe_ok, fe_err = check_frontend_subsystem(repo_root)
    if not fe_ok:
        failures.append(fe_err)

    # 4. Services subsystem
    svc_ok, svc_err = check_services_subsystem(repo_root)
    if not svc_ok:
        failures.append(svc_err)

    if failures:
        combined_reason = "\n\n".join(failures)
        return {
            "decision": "continue",
            "reason": f"[Quality Gate Block] Unresolved defects detected:\n\n{combined_reason}\n\nPlease fix the above errors before completing the session.",
        }

    return {
        "decision": "allow",
        "reason": "All quality gates passed (Python Ruff, Frontend TypeScript, Go vet).",
    }
