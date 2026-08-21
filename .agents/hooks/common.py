"""Common utilities and Protojson stdio handlers for Antigravity lifecycle hooks.

Standard-library-only implementation (OS-agnostic: Windows, Linux, macOS).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def find_repo_root(start_path: Path | None = None) -> Path:
    """Traverse upwards to find the repository root directory."""
    if start_path is None:
        start_path = Path(__file__).resolve().parent

    current = start_path.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
        if (parent / ".agents" / "hooks.json").exists():
            return parent

    # Fallback to current working directory
    return Path.cwd().resolve()


def read_json_stdin() -> dict[str, Any]:
    """Read and parse camelCase JSON payload from sys.stdin."""
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
        return {"data": payload}
    except Exception as exc:
        sys.stderr.write(f"[hooks.common] Warning: Failed to parse stdin JSON: {exc}\n")
        return {}


def write_json_stdout(data: dict[str, Any]) -> None:
    """Serialize and write camelCase JSON payload to sys.stdout."""
    output = json.dumps(data, ensure_ascii=False, indent=2)
    sys.stdout.write(output)
    sys.stdout.write("\n")
    sys.stdout.flush()


def get_field(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Retrieve the first matching key from dictionary (supports camelCase and snake_case)."""
    for key in keys:
        if key in data:
            return data[key]
    return default


def run_process(
    cmd: list[str],
    cwd: Path | str | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Execute a subprocess command with timeout and captured output."""
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=process_env,
            shell=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return 127, "", f"Command not found: {cmd[0]} ({exc})"
    except Exception as exc:
        return 1, "", f"Execution error: {exc}"


def find_executable(name: str) -> str | None:
    """Find executable on system PATH."""
    return shutil.which(name)
