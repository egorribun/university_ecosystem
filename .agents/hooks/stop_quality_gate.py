"""Stop quality gate interceptor.

Prevents the agent from terminating or self-certifying completion if any linters,
type checkers, syntax verifiers, or tests report failures.

Returns:
- {"decision": "continue", "reason": "<diagnostics>"} if any checks fail.
- {"decision": "allow", "reason": "All quality gates passed."} if all checks pass.
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
from concurrent.futures import FIRST_COMPLETED, Future, wait
from pathlib import Path
from time import monotonic
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from .common import (
        find_executable,
        find_repo_root,
        get_gate_state_path,
        load_gate_state,
        run_process,
    )
except (ImportError, ValueError):
    from common import (
        find_executable,
        find_repo_root,
        get_gate_state_path,
        load_gate_state,
        run_process,
    )


# Go's package analyzer compiles a substantial dependency graph for every
# workspace module.  Running all modules at once can make those independent
# processes contend for the same compiler/cache resources and hit the
# per-module timeout even though each module is healthy when run on its own.
# Keep bounded parallelism so the stop gate remains both fast and deterministic
# on developer workstations and CI runners.
GO_VET_MAX_WORKERS = 2
GO_VET_TOTAL_BUDGET_SECONDS = 95
GO_VET_MODULE_TIMEOUT_SECONDS = 90
GO_VET_MIN_START_BUDGET_SECONDS = 1


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


def _check_single_go_module(
    mod_dir: Path, repo_root: Path, *, deadline: float | None = None
) -> str | None:
    """Run go vet for a single Go module directory."""
    timeout = GO_VET_MODULE_TIMEOUT_SECONDS
    if deadline is not None:
        remaining = deadline - monotonic()
        if remaining < GO_VET_MIN_START_BUDGET_SECONDS:
            rel_path = mod_dir.relative_to(repo_root).as_posix()
            return (
                f"Go Vet Not Run for '{rel_path}': shared stop-gate deadline "
                "expired before this module could start."
            )
        timeout = min(timeout, int(remaining))

    code, stdout, stderr = run_process(
        ["go", "vet", "./..."],
        cwd=mod_dir,
        timeout=timeout,
    )
    rel_path = mod_dir.relative_to(repo_root).as_posix()
    if deadline is not None and monotonic() >= deadline:
        return (
            f"Go Vet Deadline Exceeded in '{rel_path}': result was not available "
            "within the shared stop-gate budget."
        )
    if code != 0:
        err_msg = stderr.strip() or stdout.strip()
        return f"Go Vet Failure in '{rel_path}':\n{err_msg}"
    return None


def check_services_subsystem(repo_root: Path) -> tuple[bool, str]:
    """Run go vet across all Go microservices in services/ concurrently."""
    services_dir = repo_root / "services"
    if not services_dir.exists():
        return True, ""

    if not find_executable("go"):
        return False, "Go toolchain is required for the services quality gate."

    # Discover every module, including newly added packages.  A partially
    # populated legacy allowlist must never silently omit a valid module.
    go_mod_dirs = sorted(
        (go_mod.parent for go_mod in services_dir.rglob("go.mod")),
        key=lambda path: path.relative_to(repo_root).as_posix(),
    )

    if not go_mod_dirs:
        return True, ""

    errors: list[tuple[str, str]] = []
    deadline = monotonic() + GO_VET_TOTAL_BUDGET_SECONDS
    max_workers = min(len(go_mod_dirs), GO_VET_MAX_WORKERS)
    next_module = 0
    pending: dict[Future[str | None], Path] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        while next_module < len(go_mod_dirs) or pending:
            while next_module < len(go_mod_dirs) and len(pending) < max_workers:
                if deadline - monotonic() < GO_VET_MIN_START_BUDGET_SECONDS:
                    break
                mod_dir = go_mod_dirs[next_module]
                next_module += 1
                future = executor.submit(
                    _check_single_go_module,
                    mod_dir,
                    repo_root,
                    deadline=deadline,
                )
                pending[future] = mod_dir

            if not pending:
                break

            remaining = max(0.0, deadline - monotonic())
            completed, _ = wait(
                pending,
                timeout=remaining,
                return_when=FIRST_COMPLETED,
            )
            if not completed:
                break

            for future in completed:
                mod_dir = pending.pop(future)
                rel_path = mod_dir.relative_to(repo_root).as_posix()
                try:
                    err = future.result()
                except Exception as exc:
                    err = (
                        f"Go Vet Failure in '{rel_path}': execution raised "
                        f"{type(exc).__name__}."
                    )
                if err:
                    errors.append((rel_path, err))

        # Any in-flight command was given no more than the shared deadline's
        # remaining time.  Collect its bounded result before returning.
        for future, mod_dir in pending.items():
            rel_path = mod_dir.relative_to(repo_root).as_posix()
            try:
                err = future.result()
            except Exception as exc:
                err = (
                    f"Go Vet Failure in '{rel_path}': execution raised "
                    f"{type(exc).__name__}."
                )
            if err:
                errors.append((rel_path, err))

    for mod_dir in go_mod_dirs[next_module:]:
        rel_path = mod_dir.relative_to(repo_root).as_posix()
        errors.append(
            (
                rel_path,
                f"Go Vet Not Run for '{rel_path}': shared stop-gate deadline "
                "expired before this module could start.",
            )
        )

    if errors:
        return False, "\n".join(message for _, message in sorted(errors))

    return True, ""


def check_gate_state_errors() -> tuple[bool, str]:
    """Check recent failures recorded in .gate_state.json."""
    state_path = get_gate_state_path()
    try:
        state = load_gate_state(state_path)
    except FileNotFoundError:
        return True, ""
    except (OSError, RuntimeError, UnicodeError, RecursionError):
        return False, "Automated quality gate state is unreadable or malformed."

    if not isinstance(state, dict):
        return False, "Automated quality gate state is unreadable or malformed."
    latest_by_file = state.get("latest_by_file")
    if not isinstance(latest_by_file, dict):
        return False, "Automated quality gate state is unreadable or malformed."

    failed_paths = sorted(
        file_name for file_name, entry in latest_by_file.items() if not entry["passed"]
    )
    if failed_paths:
        failed = latest_by_file[failed_paths[0]]
        return (
            False,
            f"Recent unresolved edit error in '{failed_paths[0]}':\n{failed['output']}",
        )

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
