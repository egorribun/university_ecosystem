"""Stop quality gate interceptor.

Prevents the agent from terminating or self-certifying completion if any linters,
type checkers, syntax verifiers, or tests report failures.

Returns:
- {"decision": "continue", "reason": "<diagnostics>"} if any checks fail.
- {"decision": "allow", "reason": "All quality gates passed."} if all checks pass.
"""

from __future__ import annotations

import concurrent.futures
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


# Go's package analyzer compiles a substantial dependency graph for every
# workspace module.  Running all modules at once can make those independent
# processes contend for the same compiler/cache resources and hit the
# per-module timeout even though each module is healthy when run on its own.
# Keep bounded parallelism so the stop gate remains both fast and deterministic
# on developer workstations and CI runners.
GO_VET_MAX_WORKERS = 2


def check_python_subsystem(repo_root: Path) -> tuple[bool, str]:
    """Run Ruff linter and py_compile check across Python codebase."""
    app_dir = repo_root / "app"
    if not app_dir.exists():
        return True, ""

    ruff_cmd = ["uv", "run", "ruff"] if find_executable("uv") else ["ruff"]
    code, stdout, stderr = run_process(
        [*ruff_cmd, "check", "app/"],
        cwd=repo_root,
        timeout=90,
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
        timeout=90,
    )
    if code != 0:
        err_msg = stdout.strip() or stderr.strip()
        # Truncate long error output if needed
        if len(err_msg) > 2000:
            err_msg = err_msg[:2000] + "\n... [truncated]"
        return False, f"Frontend TypeScript Compilation Failures:\n{err_msg}"

    return True, ""


def _check_single_go_module(mod_dir: Path, repo_root: Path) -> str | None:
    """Run go vet for a single Go module directory."""
    code, stdout, stderr = run_process(
        ["go", "vet", "./..."],
        cwd=mod_dir,
        timeout=90,
    )
    if code != 0:
        err_msg = stderr.strip() or stdout.strip()
        rel_path = mod_dir.relative_to(repo_root).as_posix()
        return f"Go Vet Failure in '{rel_path}':\n{err_msg}"
    return None


def check_services_subsystem(repo_root: Path) -> tuple[bool, str]:
    """Run go vet across all Go microservices in services/ concurrently."""
    services_dir = repo_root / "services"
    if not services_dir.exists():
        return True, ""

    if not find_executable("go"):
        return False, "Go toolchain is required for the services quality gate."

    target_services = [
        "gateway",
        "ws-hub",
        "file-processor",
        "cmd/uni-cli",
        "pkg/spiffe",
        "pkg/spicedb",
    ]
    go_mod_dirs = [
        services_dir / svc
        for svc in target_services
        if (services_dir / svc / "go.mod").exists()
    ]
    if not go_mod_dirs:
        go_mod_dirs = [go_mod.parent for go_mod in sorted(services_dir.rglob("go.mod"))]

    if not go_mod_dirs:
        return True, ""

    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(len(go_mod_dirs), GO_VET_MAX_WORKERS)
    ) as executor:
        futures = [
            executor.submit(_check_single_go_module, mod_dir, repo_root)
            for mod_dir in go_mod_dirs
        ]
        for future in concurrent.futures.as_completed(futures):
            err = future.result()
            if err:
                errors.append(err)

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
            # A later successful edit of one file must not hide an unresolved
            # failure in another file. Resolve status per path from history and
            # inspect the latest entry for every path.
            latest_by_file: dict[str, dict[str, Any]] = {}
            for entry in data.get("history", []):
                if isinstance(entry, dict):
                    file_name = str(entry.get("file", "unknown"))
                    latest_by_file[file_name] = entry
            last = data.get("last_status", {})
            if isinstance(last, dict) and last.get("file"):
                latest_by_file[str(last["file"])] = last
            failed = next(
                (
                    entry
                    for entry in latest_by_file.values()
                    if not entry.get("passed", False)
                ),
                None,
            )
            if failed is not None:
                file_name = failed.get("file", "unknown")
                output = failed.get("output", "")
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

    # 2. Parallel evaluation of Python, Frontend, and Services subsystems
    check_functions = [
        check_python_subsystem,
        check_frontend_subsystem,
        check_services_subsystem,
    ]
    failures: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(check_functions)
    ) as executor:
        future_to_fn = {executor.submit(fn, repo_root): fn for fn in check_functions}
        for future in concurrent.futures.as_completed(future_to_fn):
            ok, err_msg = future.result()
            if not ok and err_msg:
                failures.append(err_msg)

    if failures:
        combined_reason = "\n\n".join(failures)
        return {
            "decision": "continue",
            "reason": f"[Quality Gate Block] Unresolved defects detected:\n\n{combined_reason}\n\nPlease fix the above errors before completing the session.",
        }

    return {
        "decision": "allow",
        "reason": "All configured stop checks passed (Python Ruff, frontend TypeScript, and Go vet for every workspace module).",
    }
