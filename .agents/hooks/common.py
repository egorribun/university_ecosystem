"""Common utilities and Protojson stdio handlers for Antigravity lifecycle hooks.

Standard-library-only implementation (OS-agnostic: Windows, Linux, macOS).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
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


def get_gate_state_path() -> Path:
    """Return the shared lifecycle-hook state file path."""
    return Path(__file__).resolve().parent / ".gate_state.json"


GATE_STATE_LOCK_TIMEOUT_SECONDS = 5.0
GATE_STATE_LOCK_POLL_SECONDS = 0.05


@contextmanager
def gate_state_lock(state_path: Path) -> Iterator[None]:
    """Acquire the cross-process lock shared by gate-state readers and writers."""
    lock_path = state_path.with_name(f"{state_path.name}.lock")
    try:
        lock_file = lock_path.open("a+b")
    except OSError as exc:
        raise RuntimeError("Could not open the hook gate state lock.") from exc

    with lock_file:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()

            deadline = time.monotonic() + GATE_STATE_LOCK_TIMEOUT_SECONDS
            while True:
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "Timed out acquiring the hook gate state lock."
                        ) from exc
                    time.sleep(GATE_STATE_LOCK_POLL_SECONDS)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            deadline = time.monotonic() + GATE_STATE_LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "Timed out acquiring the hook gate state lock."
                        ) from exc
                    time.sleep(GATE_STATE_LOCK_POLL_SECONDS)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _validate_gate_state_entry(entry: Any) -> dict[str, Any]:
    """Validate one persisted check result without discarding malformed state."""
    if not isinstance(entry, dict):
        raise RuntimeError("Malformed hook gate state entry.")
    if (
        not isinstance(entry.get("file"), str)
        or not entry["file"]
        or not isinstance(entry.get("linter"), str)
        or not entry["linter"].strip()
        or not isinstance(entry.get("passed"), bool)
        or not isinstance(entry.get("output"), str)
    ):
        raise RuntimeError("Malformed hook gate state entry.")
    return {
        "file": entry["file"],
        "linter": entry["linter"],
        "passed": entry["passed"],
        "output": entry["output"],
    }


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous duplicate keys in persisted gate state JSON."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in hook gate state.")
        result[key] = value
    return result


def load_gate_state(state_path: Path, *, acquire_lock: bool = True) -> dict[str, Any]:
    """Load shared hook state, validating and migrating its legacy shape.

    The one historical empty-success sentinel is treated as an empty state.
    All other malformed or inconsistent data raises so callers fail closed.
    """
    if acquire_lock:
        with gate_state_lock(state_path):
            return load_gate_state(state_path, acquire_lock=False)

    try:
        with state_path.open(encoding="utf-8") as state_file:
            loaded = json.load(state_file, object_pairs_hook=_unique_json_object)
    except FileNotFoundError:
        return {"history": [], "latest_by_file": {}}
    except (OSError, ValueError) as exc:
        raise RuntimeError("Could not read valid hook gate state.") from exc

    if (
        isinstance(loaded, dict)
        and set(loaded) == {"history", "last_status"}
        and loaded["history"] == []
        and isinstance(loaded["last_status"], dict)
        and set(loaded["last_status"]) == {"passed"}
        and loaded["last_status"]["passed"] is True
    ):
        return {"history": [], "latest_by_file": {}}
    if (
        isinstance(loaded, dict)
        and set(loaded) == {"history", "latest_by_file"}
        and loaded["history"] == []
        and loaded["latest_by_file"] == {}
    ):
        return {"history": [], "latest_by_file": {}}
    if not isinstance(loaded, dict) or not isinstance(loaded.get("history"), list):
        raise RuntimeError("Malformed hook gate state.")

    history = [_validate_gate_state_entry(entry) for entry in loaded["history"]]
    raw_last_status = loaded.get("last_status")
    last_status = (
        _validate_gate_state_entry(raw_last_status)
        if raw_last_status is not None
        else None
    )
    if history and last_status is not None and history[-1] != last_status:
        raise RuntimeError("Inconsistent latest hook gate state entry.")
    if last_status is None and history:
        last_status = history[-1]

    if "latest_by_file" not in loaded:
        latest_by_file = {entry["file"]: entry for entry in history}
        if last_status is not None:
            latest_by_file[last_status["file"]] = last_status
    else:
        raw_latest = loaded["latest_by_file"]
        if not isinstance(raw_latest, dict):
            raise RuntimeError("Malformed latest-by-file hook gate state.")
        latest_by_file = {}
        for file_name, raw_entry in raw_latest.items():
            entry = _validate_gate_state_entry(raw_entry)
            if not isinstance(file_name, str) or file_name != entry["file"]:
                raise RuntimeError("Mismatched latest-by-file hook gate state.")
            latest_by_file[file_name] = entry

        latest_in_history: dict[str, dict[str, Any]] = {}
        for entry in history:
            latest_in_history[entry["file"]] = entry
        if any(
            latest_by_file.get(name) != entry
            for name, entry in latest_in_history.items()
        ):
            raise RuntimeError("Inconsistent latest-by-file hook gate state.")
        if (
            last_status is not None
            and latest_by_file.get(last_status["file"]) != last_status
        ):
            raise RuntimeError("Inconsistent latest hook gate state entry.")
        if (history or latest_by_file) and last_status is None:
            raise RuntimeError("Missing latest hook gate state entry.")

    state = {"history": history, "latest_by_file": latest_by_file}
    if not history and not latest_by_file and last_status is None:
        raise RuntimeError("Empty persisted hook gate state.")
    if last_status is not None:
        state["last_status"] = last_status
    return state


def read_json_stdin() -> dict[str, Any]:
    """Read and parse camelCase JSON payload from sys.stdin."""
    try:
        if sys.stdin and sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return {"__hook_parse_error__": "Hook input must be a JSON object."}
        return payload
    except Exception as exc:
        sys.stderr.write(f"[hooks.common] Failed to parse stdin JSON: {exc}\n")
        return {"__hook_parse_error__": str(exc)}


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

    proc: subprocess.Popen[str] | None = None
    try:
        # Python 3.14 is required; these Python <3.6 compatibility findings do not apply.
        # nosemgrep: python.lang.compatibility.python36.python36-compatibility-Popen1, python.lang.compatibility.python36.python36-compatibility-Popen2
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=process_env,
            shell=False,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            cleanup_ok, cleanup_detail = _cleanup_owned_process(proc)
            diagnostic = f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
            if not cleanup_ok:
                diagnostic += " Process cleanup failed: " + cleanup_detail
            return -1, "", diagnostic
    except KeyboardInterrupt:
        if proc is not None:
            _cleanup_owned_process(proc)
        raise
    except Exception as exc:
        cleanup_detail = ""
        if proc is not None:
            cleanup_ok, detail = _cleanup_owned_process(proc)
            if not cleanup_ok:
                cleanup_detail = " Process cleanup failed: " + detail
        if proc is None and isinstance(exc, FileNotFoundError):
            return 127, "", f"Command not found: {cmd[0]} ({exc})"
        return 1, "", f"Execution error: {exc}{cleanup_detail}"


def _terminate_owned_process_tree(
    process: subprocess.Popen[str],
) -> tuple[bool, str]:
    """Terminate only the process tree created for this hook command."""
    errors: list[str] = []
    tree_termination_confirmed = False
    if os.name == "nt":
        if process.poll() is None:
            taskkill_path = shutil.which("taskkill.exe") or shutil.which("taskkill")
            if taskkill_path is None:
                errors.append(
                    "Windows process-tree termination command was unavailable."
                )
            else:
                try:
                    result = subprocess.run(  # noqa: S603 - fixed Windows process-tree command
                        [taskkill_path, "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        check=False,
                        shell=False,
                    )
                    if result.returncode != 0:
                        errors.append(
                            "Windows process-tree termination command failed."
                        )
                    else:
                        tree_termination_confirmed = True
                except subprocess.TimeoutExpired:
                    errors.append("Windows process-tree termination command timed out.")
                except OSError:
                    errors.append(
                        "Windows process-tree termination command was unavailable."
                    )
        else:
            errors.append("Owned process exited before its tree could be verified.")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            tree_termination_confirmed = True
        except ProcessLookupError:
            tree_termination_confirmed = True
        except OSError:
            errors.append("POSIX process-group termination failed.")

    if process.poll() is None and not tree_termination_confirmed:
        try:
            process.kill()
        except OSError:
            if process.poll() is None:
                errors.append("Direct owned-process termination failed.")

    return not errors, " ".join(errors)


def _cleanup_owned_process(process: subprocess.Popen[str]) -> tuple[bool, str]:
    """Terminate and reap an owned process after timeout or an unexpected error."""
    errors: list[str] = []
    try:
        tree_terminated, detail = _terminate_owned_process_tree(process)
        if not tree_terminated:
            errors.append(detail or "Could not confirm process-tree termination.")
    except Exception:
        tree_terminated = False
        errors.append("Owned process-tree termination could not be confirmed.")

    if not tree_terminated and process.poll() is None:
        try:
            process.kill()
        except OSError:
            if process.poll() is None:
                errors.append("Could not terminate the owned process.")

    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        errors.append("Timed out reaping the owned process.")
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                errors.append("Could not terminate the owned process.")
        try:
            process.wait(timeout=5)
        except Exception:
            errors.append("Could not reap the owned process.")
    except Exception:
        errors.append("Could not collect output while reaping the owned process.")
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                errors.append("Could not terminate the owned process.")
        try:
            process.wait(timeout=5)
        except Exception:
            errors.append("Could not reap the owned process.")
    finally:
        for name in ("stdout", "stderr"):
            stream = getattr(process, name)
            if stream is not None and not stream.closed:
                reader = getattr(process, f"{name}_thread", None)
                if reader is not None and reader.is_alive():
                    # Closing a buffered pipe while the Windows reader holds
                    # its lock can block forever when a descendant retains it.
                    errors.append("An owned output reader is still running.")
                    continue
                try:
                    stream.close()
                except Exception:
                    errors.append("Could not close an owned process output pipe.")

    return not errors, " ".join(errors)


def find_executable(name: str) -> str | None:
    """Find executable on system PATH."""
    return shutil.which(name)
