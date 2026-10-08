"""Runtime contracts for the shared developer-hook helpers."""

from __future__ import annotations

import importlib
import io
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPOSITORY_ROOT / ".agents" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

common = importlib.import_module("common")
post_tool_linter = importlib.import_module("post_tool_linter")


@pytest.fixture(autouse=True)
def isolate_gate_state_path(monkeypatch: Any, tmp_path: Path) -> None:
    """Keep hook runtime tests away from the developer's persistent state file."""
    monkeypatch.setattr(
        post_tool_linter, "get_gate_state_path", lambda: tmp_path / ".gate_state.json"
    )


def _reap_test_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    """Ensure a test-owned child does not survive a failed assertion or timeout."""
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
        return process.communicate(timeout=5)


def test_go_vet_timeout_is_a_failed_post_tool_check(monkeypatch: Any) -> None:
    """A timed-out go vet must not be recorded as a successful quality check."""
    results = iter(((0, "", ""), (-1, "", "timed out")))
    monkeypatch.setattr(
        post_tool_linter, "run_process", lambda *args, **kwargs: next(results)
    )

    passed, diagnostic = post_tool_linter.format_and_check_go(
        REPOSITORY_ROOT / "services" / "gateway" / "main.go", REPOSITORY_ROOT
    )

    assert not passed
    assert "timed out" in diagnostic.lower()


def test_gate_state_path_defaults_to_hook_directory() -> None:
    assert common.get_gate_state_path() == HOOKS_DIR / ".gate_state.json"


def test_gate_state_migrates_legacy_empty_success_sentinel(tmp_path: Path) -> None:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text(
        '{"history": [], "last_status": {"passed": true}}', encoding="utf-8"
    )

    assert common.load_gate_state(state_path) == {"history": [], "latest_by_file": {}}


def test_gate_state_accepts_complete_current_empty_shape(tmp_path: Path) -> None:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text('{"history": [], "latest_by_file": {}}', encoding="utf-8")

    assert common.load_gate_state(state_path) == {"history": [], "latest_by_file": {}}


def test_gate_state_does_not_treat_integer_as_legacy_success(tmp_path: Path) -> None:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text(
        '{"history": [], "last_status": {"passed": 1}}', encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="gate state"):
        common.load_gate_state(state_path)


def test_gate_state_rejects_empty_linter_name(tmp_path: Path) -> None:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text(
        '{"history": [{"file": "C:/repo/file.py", "linter": "  ", '
        '"passed": true, "output": ""}]}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="gate state"):
        common.load_gate_state(state_path)


@pytest.mark.parametrize(
    "serialized_state",
    ('{"history": []}',),
)
def test_gate_state_rejects_other_persisted_empty_shapes(
    tmp_path: Path, serialized_state: str
) -> None:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text(serialized_state, encoding="utf-8")

    with pytest.raises(RuntimeError, match="gate state"):
        common.load_gate_state(state_path)


def test_gate_state_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text(
        '{"history": [], "last_status": {"passed": false, "passed": true}}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="gate state"):
        common.load_gate_state(state_path)


def test_gate_state_inaccessible_file_does_not_look_empty(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    original_open = Path.open

    def deny_state_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == state_path:
            raise PermissionError("simulated inaccessible state")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_state_open)

    with pytest.raises(RuntimeError, match="gate state"):
        common.load_gate_state(state_path)


@pytest.mark.parametrize("payload", ("[]", "null", '"text"', "17"))
def test_hook_stdin_rejects_valid_non_object_json(
    monkeypatch: Any, payload: str
) -> None:
    monkeypatch.setattr(common.sys, "stdin", io.StringIO(payload))

    parsed = common.read_json_stdin()

    assert parsed == {"__hook_parse_error__": "Hook input must be a JSON object."}


def test_hook_stdin_keeps_empty_input_compatibility(monkeypatch: Any) -> None:
    monkeypatch.setattr(common.sys, "stdin", io.StringIO(" \n"))

    assert common.read_json_stdin() == {}


def test_run_process_decodes_invalid_utf8_with_replacement() -> None:
    code, stdout, stderr = common.run_process(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'\\xff'); "
            "sys.stderr.buffer.write(b'\\xfe')",
        ],
        timeout=5,
    )

    assert code == 0
    assert stdout == "\ufffd"
    assert stderr == "\ufffd"


def test_run_process_timeout_terminates_owned_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "grandchild-survived"
    grandchild_code = (
        "import pathlib,time; time.sleep(1.2); "
        f"pathlib.Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild_code!r}])\n"
        "print('child-ready', flush=True)\n"
        "time.sleep(30)\n"
    )

    code, stdout, stderr = common.run_process(
        [sys.executable, "-c", parent_code], timeout=0.3
    )

    assert code == -1
    assert stdout == ""
    assert "timed out" in stderr.lower()
    assert "process cleanup failed" not in stderr.lower()
    time.sleep(1.4)
    assert not marker.exists(), "timed-out command left its grandchild running"


def test_run_process_reports_unconfirmed_tree_cleanup(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        common,
        "_terminate_owned_process_tree",
        lambda _process: (False, "simulated tree cleanup failure"),
    )

    code, stdout, stderr = common.run_process(
        [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.1
    )

    assert code == -1
    assert stdout == ""
    assert "process cleanup failed" in stderr.lower()
    assert "simulated tree cleanup failure" in stderr


def test_run_process_cleans_owned_child_after_communication_error(
    monkeypatch: Any,
) -> None:
    real_popen = subprocess.Popen
    process_holder: dict[str, subprocess.Popen[str]] = {}
    cleanup_called = False

    def popen_with_communication_error(
        *args: Any, **kwargs: Any
    ) -> subprocess.Popen[str]:
        process = real_popen(*args, **kwargs)
        process_holder["process"] = process
        original_communicate = process.communicate
        first_call = True

        def fail_once(*, timeout: float | None = None) -> tuple[str, str]:
            nonlocal first_call
            if first_call:
                first_call = False
                raise OSError("simulated output read failure")
            return original_communicate(timeout=timeout)

        process.communicate = fail_once  # type: ignore[method-assign]
        return process

    def terminate_owned_process(
        process: subprocess.Popen[str],
    ) -> tuple[bool, str]:
        nonlocal cleanup_called
        cleanup_called = True
        if process.poll() is None:
            process.kill()
        return True, ""

    monkeypatch.setattr(subprocess, "Popen", popen_with_communication_error)
    monkeypatch.setattr(
        common, "_terminate_owned_process_tree", terminate_owned_process
    )

    try:
        code, stdout, stderr = common.run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=5
        )
    finally:
        if "process" in process_holder:
            _reap_test_process(process_holder["process"])

    assert code == 1
    assert stdout == ""
    assert "Execution error" in stderr
    assert cleanup_called
    assert process_holder["process"].poll() is not None


def test_gate_state_keeps_latest_result_for_files_beyond_recent_history(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)

    post_tool_linter.update_gate_state("C:/repo/failed.py", "ruff", False, "failed")
    for index in range(55):
        post_tool_linter.update_gate_state(
            f"C:/repo/other-{index}.py", "ruff", True, ""
        )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state["history"]) == 50
    assert state["latest_by_file"]["C:/repo/failed.py"]["passed"] is False
    assert state["last_status"]["file"] == "C:/repo/other-54.py"


def test_gate_state_rejects_malformed_json_without_overwriting_it(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    original = b"{broken"
    state_path.write_bytes(original)
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)

    with pytest.raises(RuntimeError, match="gate state"):
        post_tool_linter.update_gate_state("C:/repo/file.py", "ruff", True, "")

    assert state_path.read_bytes() == original


def test_gate_state_write_failure_is_reported_and_preserves_previous_state(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    post_tool_linter.update_gate_state("C:/repo/file.py", "ruff", True, "")
    original = state_path.read_bytes()

    def fail_replace(
        source: str | os.PathLike[str], destination: str | os.PathLike[str]
    ) -> None:
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(post_tool_linter.os, "replace", fail_replace)
    with pytest.raises(RuntimeError, match="gate state"):
        post_tool_linter.update_gate_state("C:/repo/file.py", "ruff", False, "failed")

    assert state_path.read_bytes() == original


def test_gate_state_lock_timeout_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    state_path = tmp_path / ".gate_state.json"
    ready_path = tmp_path / "lock-held"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    worker = f"""
import pathlib
import sys
import time

sys.path.insert(0, {str(HOOKS_DIR)!r})
import common

with common.gate_state_lock(pathlib.Path({str(state_path)!r})):
    pathlib.Path({str(ready_path)!r}).write_text("ready", encoding="utf-8")
    time.sleep(0.5)
"""
    process = subprocess.Popen(  # noqa: S603 - fixed interpreter and test-owned worker
        [sys.executable, "-c", worker],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    deadline = time.monotonic() + 10
    while (
        not ready_path.exists()
        and process.poll() is None
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)

    try:
        assert ready_path.exists(), process.communicate(timeout=5)
        monkeypatch.setattr(common, "GATE_STATE_LOCK_TIMEOUT_SECONDS", 0.1)
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="Timed out acquiring"):
            post_tool_linter.update_gate_state(
                "C:/repo/file.py", "ruff", False, "failed"
            )
        assert time.monotonic() - started < 2
        assert not state_path.exists()
    finally:
        stdout, stderr = _reap_test_process(process)

    assert process.returncode == 0, (stdout, stderr)


def test_post_tool_state_uses_canonical_target_path(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo_root = tmp_path / "repo"
    nested = repo_root / "nested"
    nested.mkdir(parents=True)
    target = repo_root / "example.py"
    target.write_text("x = 1\n", encoding="utf-8")
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "find_repo_root", lambda: repo_root)
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(
        post_tool_linter, "format_and_lint_python", lambda *_: (True, "")
    )

    response = post_tool_linter.evaluate_post_tool(
        {"toolCall": {"args": {"TargetFile": str(nested / ".." / "example.py")}}}
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert response == {}
    assert list(state["latest_by_file"]) == [str(target.resolve())]


def test_concurrent_hook_processes_preserve_each_file_status(
    tmp_path: Path,
) -> None:
    """Concurrent hook writers must not lose each other's latest-file entries."""
    state_path = tmp_path / ".gate_state.json"
    worker = f"""
import pathlib
import sys
import time

sys.path.insert(0, {str(HOOKS_DIR)!r})
import post_tool_linter as hook

hook.get_gate_state_path = lambda: pathlib.Path({str(state_path)!r})
original_load = hook.load_gate_state

def delayed_load(path, *, acquire_lock=True):
    state = original_load(path, acquire_lock=acquire_lock)
    if not acquire_lock:
        time.sleep(0.1)
    return state

hook.load_gate_state = delayed_load
hook.update_gate_state(sys.argv[1], 'ruff', sys.argv[2] == 'pass', sys.argv[2])
"""
    processes = [
        subprocess.Popen(  # noqa: S603 - fixed interpreter and test-owned inline worker
            [
                sys.executable,
                "-c",
                worker,
                f"C:/repo/file-{index}.py",
                "fail" if index % 2 else "pass",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
        )
        for index in range(8)
    ]

    try:
        with ThreadPoolExecutor(max_workers=len(processes)) as executor:
            results = list(
                executor.map(lambda process: process.communicate(timeout=20), processes)
            )
    finally:
        for process in processes:
            _reap_test_process(process)

    assert [process.returncode for process in processes] == [0] * len(processes), (
        results
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state["latest_by_file"]) == 8
    assert {
        name: entry["passed"] for name, entry in state["latest_by_file"].items()
    } == {f"C:/repo/file-{index}.py": index % 2 == 0 for index in range(8)}


def test_cleanup_does_not_close_a_pipe_with_a_live_reader(monkeypatch: Any) -> None:
    """An inherited pipe cannot turn bounded cleanup into a blocking close."""

    class Pipe:
        closed = False

        def close(self) -> None:
            raise AssertionError("must not close a pipe held by a live reader")

    class Reader:
        def is_alive(self) -> bool:
            return True

    class Process:
        stdout = Pipe()
        stderr = None
        stdout_thread = Reader()

        def poll(self) -> int:
            return 0

        def communicate(self, *, timeout: int) -> tuple[str, str]:
            raise subprocess.TimeoutExpired("fixture", timeout)

        def wait(self, *, timeout: int) -> int:
            return 0

    monkeypatch.setattr(
        common,
        "_terminate_owned_process_tree",
        lambda _: (False, "unconfirmed fixture tree"),
    )
    passed, diagnostic = common._cleanup_owned_process(Process())
    assert not passed
    assert "reader is still running" in diagnostic
