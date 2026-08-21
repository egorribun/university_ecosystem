"""PostToolUse automated linter and in-place formatter.

Executes language-specific linters and formatters immediately after file edits:
- Python (.py): uv run ruff check --fix & uv run ruff format
- TypeScript (.ts/.tsx): npx tsc --noEmit in frontend/
- Go (.go): gofmt -w & go vet in services/

Always returns an empty dict `{}` on stdout per Antigravity contract.
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
    from .common import find_executable, find_repo_root, get_field, run_process
except (ImportError, ValueError):
    from common import find_executable, find_repo_root, get_field, run_process

STATE_FILE_NAME = ".gate_state.json"


def get_gate_state_path() -> Path:
    """Return path to .gate_state.json in .agents/hooks directory."""
    return Path(__file__).resolve().parent / STATE_FILE_NAME


def update_gate_state(file_path: str, linter: str, passed: bool, output: str) -> None:
    """Record linter and syntax audit results to persistent gate state."""
    state_path = get_gate_state_path()
    state: dict[str, Any] = {"history": []}

    if state_path.exists():
        try:
            with open(state_path, encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    state = loaded
        except Exception:
            state = {"history": []}

    history = state.get("history", [])
    history.append(
        {
            "file": file_path,
            "linter": linter,
            "passed": passed,
            "output": output.strip()[:1000],
        }
    )
    # Keep last 50 entries
    state["history"] = history[-50:]
    state["last_status"] = {
        "file": file_path,
        "linter": linter,
        "passed": passed,
        "output": output.strip()[:1000],
    }

    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        sys.stderr.write(
            f"[hooks.post_tool_linter] Warning: Failed to write state: {exc}\n"
        )


def format_and_lint_python(file_path: Path, repo_root: Path) -> tuple[bool, str]:
    """Run Ruff auto-fix, format, and syntax compilation on Python file."""
    diagnostics: list[str] = []
    all_passed = True

    # 1. Syntax check via py_compile
    code, stdout, stderr = run_process(
        [sys.executable, "-m", "py_compile", str(file_path)],
        cwd=repo_root,
        timeout=10,
    )
    if code != 0:
        diagnostics.append(f"Python syntax error: {stderr.strip() or stdout.strip()}")
        all_passed = False

    # 2. Ruff check --fix
    ruff_cmd = ["uv", "run", "ruff"] if find_executable("uv") else ["ruff"]
    check_code, check_out, check_err = run_process(
        [*ruff_cmd, "check", "--fix", str(file_path)],
        cwd=repo_root,
        timeout=15,
    )
    if check_code != 0:
        diagnostics.append(
            f"Ruff check issues: {check_out.strip() or check_err.strip()}"
        )
        all_passed = False

    # 3. Ruff format
    fmt_code, fmt_out, fmt_err = run_process(
        [*ruff_cmd, "format", str(file_path)],
        cwd=repo_root,
        timeout=15,
    )
    if fmt_code != 0:
        diagnostics.append(f"Ruff format issues: {fmt_out.strip() or fmt_err.strip()}")
        all_passed = False

    output = "\n".join(diagnostics)
    return all_passed, output


def check_typescript(file_path: Path, repo_root: Path) -> tuple[bool, str]:
    """Run TypeScript compiler check inside frontend/."""
    frontend_dir = repo_root / "frontend"
    if not frontend_dir.exists():
        return True, "No frontend directory found."

    node_tsc = frontend_dir / "node_modules" / "typescript" / "bin" / "tsc"
    if node_tsc.exists() and find_executable("node"):
        cmd = ["node", "node_modules/typescript/bin/tsc", "--noEmit", "--skipLibCheck"]
    else:
        npx_bin = "npx.cmd" if os.name == "nt" else "npx"
        cmd = [npx_bin, "tsc", "--noEmit", "--skipLibCheck"]

    code, stdout, stderr = run_process(
        cmd,
        cwd=frontend_dir,
        timeout=30,
    )
    if code == -1:
        # Graceful fallback: do not mark as defect on fast post-tool timeout; aggregate check in Stop gate
        return (
            True,
            "TypeScript check timed out in PostToolUse; deferred to Stop quality gate.",
        )
    passed = code == 0
    output = stdout.strip() if stdout else stderr.strip()
    return passed, output


def format_and_check_go(file_path: Path, repo_root: Path) -> tuple[bool, str]:
    """Run gofmt -w and go vet on Go file."""
    diagnostics: list[str] = []
    all_passed = True

    # 1. gofmt -w
    fmt_code, fmt_out, fmt_err = run_process(
        ["gofmt", "-w", str(file_path)],
        cwd=repo_root,
        timeout=10,
    )
    if fmt_code != 0:
        diagnostics.append(f"gofmt failed: {fmt_err.strip() or fmt_out.strip()}")
        all_passed = False

    # 2. go vet in file's package dir
    pkg_dir = file_path.parent
    vet_code, vet_out, vet_err = run_process(
        ["go", "vet", "."],
        cwd=pkg_dir,
        timeout=60,
    )
    if vet_code != 0 and vet_code != -1:
        diagnostics.append(f"go vet failed: {vet_err.strip() or vet_out.strip()}")
        all_passed = False

    output = "\n".join(diagnostics)
    return all_passed, output


def evaluate_post_tool(payload: dict[str, Any]) -> dict[str, Any]:
    """Main evaluation entry point for PostToolUse events."""
    tool_call = get_field(payload, "toolCall", "tool_call", default={})
    if not isinstance(tool_call, dict):
        return {}

    args = get_field(tool_call, "args", "arguments", default={})
    if not isinstance(args, dict):
        args = {}

    target_file = get_field(
        args, "TargetFile", "target_file", "path", "file", default=""
    )
    if not target_file:
        return {}

    repo_root = find_repo_root()
    target_path = Path(target_file)
    if not target_path.is_absolute():
        target_path = (repo_root / target_path).resolve()

    if not target_path.exists():
        return {}

    suffix = target_path.suffix.lower()

    if suffix == ".py":
        passed, output = format_and_lint_python(target_path, repo_root)
        update_gate_state(str(target_path), "ruff/py_compile", passed, output)
    elif suffix in (".ts", ".tsx", ".js", ".jsx"):
        passed, output = check_typescript(target_path, repo_root)
        update_gate_state(str(target_path), "tsc", passed, output)
    elif suffix == ".go":
        passed, output = format_and_check_go(target_path, repo_root)
        update_gate_state(str(target_path), "gofmt/govet", passed, output)

    return {}
