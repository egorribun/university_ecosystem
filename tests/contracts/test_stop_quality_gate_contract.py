"""Regression tests for the lifecycle stop gate's Go-vet scheduling policy."""

from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPOSITORY_ROOT / ".agents" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

stop_quality_gate = importlib.import_module("stop_quality_gate")
common = importlib.import_module("common")


GO_MODULES = (
    "gateway",
    "ws-hub",
    "file-processor",
    "cmd/uni-cli",
    "pkg/logging",
    "pkg/spiffe",
    "pkg/spicedb",
    # A newly introduced module must be discovered without updating a
    # production allowlist.
    "pkg/new-module",
)


def test_go_vet_uses_bounded_parallelism_and_preserves_module_contract(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Run every Go module with the 90-second timeout and no more than two workers.

    A real ``go vet`` invocation compiles a large dependency graph.  Four
    simultaneous invocations previously contended for compiler resources and
    all expired at the 90-second per-module timeout, making a clean stop gate
    report false failures.  The fake process below keeps the test deterministic
    while asserting the production scheduling and timeout contract.
    """

    services_dir = tmp_path / "services"
    for module in GO_MODULES:
        module_dir = services_dir / module
        module_dir.mkdir(parents=True)
        (module_dir / "go.mod").write_text(
            "module example.invalid/" + module.replace("/", "-") + "\n\ngo 1.22\n",
            encoding="utf-8",
        )

    lock = threading.Lock()
    first_started = threading.Event()
    second_started = threading.Event()
    active = 0
    max_active = 0
    calls: list[tuple[tuple[str, ...], Path, int]] = []

    def fake_run_process(
        command: list[str], *, cwd: Path, timeout: int
    ) -> tuple[int, str, str]:
        nonlocal active, max_active
        with lock:
            call_index = len(calls)
            active += 1
            max_active = max(max_active, active)
            calls.append((tuple(command), cwd, timeout))

        # Synchronize the first two calls without an unbounded sleep.  If the
        # implementation regresses to one worker, the bounded wait releases
        # and the max_active assertion below fails instead of hanging tests.
        if call_index == 0:
            first_started.set()
            second_started.wait(timeout=2)
        elif call_index == 1:
            second_started.set()
            first_started.wait(timeout=2)

        with lock:
            active -= 1
        return 0, "", ""

    monkeypatch.setattr(stop_quality_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(stop_quality_gate, "run_process", fake_run_process)

    passed, diagnostics = stop_quality_gate.check_services_subsystem(tmp_path)

    assert passed, diagnostics
    assert max_active == stop_quality_gate.GO_VET_MAX_WORKERS == 2
    assert len(calls) == len(GO_MODULES)
    assert {path.relative_to(tmp_path).as_posix() for _, path, _ in calls} == {
        f"services/{module}" for module in GO_MODULES
    }
    assert {command for command, _, _ in calls} == {("go", "vet", "./...")}
    assert {timeout for _, _, timeout in calls} == {90}


def test_go_vet_diagnostics_are_sorted_independent_of_completion_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    services_dir = tmp_path / "services"
    for module in ("a-module", "b-module"):
        module_dir = services_dir / module
        module_dir.mkdir(parents=True)
        (module_dir / "go.mod").write_text("module example.invalid\n", encoding="utf-8")

    b_finished = threading.Event()

    def fake_run_process(
        command: list[str], *, cwd: Path, timeout: int
    ) -> tuple[int, str, str]:
        if cwd.name == "b-module":
            b_finished.set()
            return 1, "", "failure b"
        assert b_finished.wait(timeout=2)
        time.sleep(0.02)
        return 1, "", "failure a"

    monkeypatch.setattr(stop_quality_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(stop_quality_gate, "run_process", fake_run_process)

    passed, diagnostics = stop_quality_gate.check_services_subsystem(tmp_path)

    assert not passed
    assert diagnostics.index("services/a-module") < diagnostics.index(
        "services/b-module"
    )


def test_go_vet_shares_one_deadline_and_fails_for_unvisited_modules(
    tmp_path: Path, monkeypatch: Any
) -> None:
    services_dir = tmp_path / "services"
    for module in ("a-module", "b-module", "c-module", "d-module"):
        module_dir = services_dir / module
        module_dir.mkdir(parents=True)
        (module_dir / "go.mod").write_text("module example.invalid\n", encoding="utf-8")

    clock = [0.0]
    clock_lock = threading.Lock()
    calls: list[tuple[str, int]] = []

    def fake_monotonic() -> float:
        with clock_lock:
            return clock[0]

    def fake_run_process(
        command: list[str], *, cwd: Path, timeout: int
    ) -> tuple[int, str, str]:
        module = cwd.relative_to(services_dir).as_posix()
        calls.append((module, timeout))
        with clock_lock:
            if timeout == stop_quality_gate.GO_VET_MODULE_TIMEOUT_SECONDS:
                clock[0] += 60.0
                return 0, "", ""
            clock[0] += timeout
        return -1, "", f"Command timed out after {timeout} seconds"

    monkeypatch.setattr(stop_quality_gate, "GO_VET_MAX_WORKERS", 1)
    monkeypatch.setattr(stop_quality_gate, "GO_VET_TOTAL_BUDGET_SECONDS", 95)
    monkeypatch.setattr(stop_quality_gate, "monotonic", fake_monotonic)
    monkeypatch.setattr(stop_quality_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(stop_quality_gate, "run_process", fake_run_process)

    passed, diagnostics = stop_quality_gate.check_services_subsystem(tmp_path)

    assert not passed
    assert calls == [("a-module", 90), ("b-module", 35)]
    assert "services/b-module" in diagnostics
    assert "services/c-module" in diagnostics
    assert "services/d-module" in diagnostics
    assert "Not Run" in diagnostics


def _gate_entry(path: Path, *, passed: bool, output: str = "") -> dict[str, Any]:
    return {
        "file": str(path.resolve()),
        "linter": "ruff/py_compile",
        "passed": passed,
        "output": output,
    }


def _point_stop_gate_at_state(tmp_path: Path, monkeypatch: Any, state: Any) -> Path:
    state_path = tmp_path / ".gate_state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    return state_path


def test_gate_reader_blocks_failure_evicted_from_bounded_history_without_writing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    stale_failure = _gate_entry(
        tmp_path / "old-failure.py", passed=False, output="lint failure"
    )
    history = [
        _gate_entry(tmp_path / f"success-{index:02}.py", passed=True)
        for index in range(50)
    ]
    latest_by_file = {stale_failure["file"]: stale_failure}
    latest_by_file.update({entry["file"]: entry for entry in history})
    state_path = _point_stop_gate_at_state(
        tmp_path,
        monkeypatch,
        {
            "history": history,
            "latest_by_file": latest_by_file,
            "last_status": history[-1],
        },
    )
    before = state_path.read_bytes()

    passed, diagnostics = stop_quality_gate.check_gate_state_errors()

    assert not passed
    assert stale_failure["file"] in diagnostics
    assert "lint failure" in diagnostics
    assert state_path.read_bytes() == before


def test_gate_reader_selects_failure_deterministically_across_map_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    first = _gate_entry(tmp_path / "z-first.py", passed=False, output="z failure")
    second = _gate_entry(tmp_path / "a-second.py", passed=False, output="a failure")
    for ordered_entries in ((first, second), (second, first)):
        latest_by_file = {entry["file"]: entry for entry in ordered_entries}
        _point_stop_gate_at_state(
            tmp_path,
            monkeypatch,
            {
                "history": [first, second],
                "latest_by_file": latest_by_file,
                "last_status": second,
            },
        )

        passed, diagnostics = stop_quality_gate.check_gate_state_errors()

        assert not passed
        assert diagnostics.startswith(
            f"Recent unresolved edit error in '{second['file']}'"
        )


def test_gate_reader_uses_latest_success_for_same_file_and_supports_legacy_state(
    tmp_path: Path, monkeypatch: Any
) -> None:
    file_path = tmp_path / "fixed.py"
    failure = _gate_entry(file_path, passed=False, output="old failure")
    success = _gate_entry(file_path, passed=True)
    _point_stop_gate_at_state(
        tmp_path,
        monkeypatch,
        {
            "history": [failure, success],
            "latest_by_file": {success["file"]: success},
            "last_status": success,
        },
    )

    assert stop_quality_gate.check_gate_state_errors() == (True, "")

    legacy_failure = _gate_entry(file_path, passed=False, output="legacy failure")
    _point_stop_gate_at_state(
        tmp_path,
        monkeypatch,
        {"history": [legacy_failure], "last_status": legacy_failure},
    )
    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "legacy failure" in diagnostics


def test_gate_reader_accepts_current_empty_state_and_legacy_sentinel(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _point_stop_gate_at_state(
        tmp_path, monkeypatch, {"history": [], "last_status": {"passed": True}}
    )

    assert stop_quality_gate.check_gate_state_errors() == (True, "")

    _point_stop_gate_at_state(
        tmp_path, monkeypatch, {"history": [], "latest_by_file": {}}
    )
    assert stop_quality_gate.check_gate_state_errors() == (True, "")


@pytest.mark.parametrize(
    "malformation",
    (
        "root-not-object",
        "history-not-list",
        "entry-not-object",
        "passed-not-bool",
        "latest-key-mismatch",
        "latest-disagrees-with-history",
        "last-status-mismatch",
        "sentinel-not-bool",
        "empty-state-without-sentinel",
    ),
)
def test_gate_reader_fails_closed_on_malformed_or_inconsistent_state(
    tmp_path: Path, monkeypatch: Any, malformation: str
) -> None:
    entry = _gate_entry(tmp_path / "state.py", passed=False, output="failed")
    state: Any = {"history": [entry], "last_status": entry}
    if malformation == "root-not-object":
        state = [entry]
    elif malformation == "history-not-list":
        state["history"] = "not-a-list"
    elif malformation == "entry-not-object":
        state["history"] = ["not-an-entry"]
    elif malformation == "passed-not-bool":
        invalid_entry = {**entry, "passed": "false"}
        state = {"history": [invalid_entry], "last_status": invalid_entry}
    elif malformation == "latest-key-mismatch":
        state["latest_by_file"] = {str(tmp_path / "other.py"): entry}
    elif malformation == "latest-disagrees-with-history":
        success = {**entry, "passed": True, "output": ""}
        state["latest_by_file"] = {entry["file"]: success}
    elif malformation == "last-status-mismatch":
        state["last_status"] = {
            **entry,
            "passed": True,
            "output": "",
        }
    elif malformation == "sentinel-not-bool":
        state = {"history": [], "last_status": {"passed": 1}}
    elif malformation == "empty-state-without-sentinel":
        state = {"history": []}

    state_path = _point_stop_gate_at_state(tmp_path, monkeypatch, state)
    before = state_path.read_bytes()

    passed, diagnostics = stop_quality_gate.check_gate_state_errors()

    assert not passed
    assert "unreadable or malformed" in diagnostics
    assert state_path.read_bytes() == before


def test_gate_reader_fails_closed_on_invalid_json_and_allows_missing_state(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    assert stop_quality_gate.check_gate_state_errors() == (True, "")

    state_path.write_text("{invalid", encoding="utf-8")
    before = state_path.read_bytes()
    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "unreadable or malformed" in diagnostics
    assert state_path.read_bytes() == before


def test_gate_reader_fails_closed_when_shared_state_lock_is_unavailable(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(stop_quality_gate, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        stop_quality_gate,
        "get_gate_state_path",
        lambda: tmp_path / ".gate_state.json",
    )

    def fail_to_lock(_: Path) -> Any:
        raise RuntimeError("bounded lock acquisition failed")

    monkeypatch.setattr(common, "gate_state_lock", fail_to_lock)
    for check_name in (
        "check_python_subsystem",
        "check_frontend_subsystem",
        "check_services_subsystem",
    ):
        monkeypatch.setattr(
            stop_quality_gate,
            check_name,
            lambda _: pytest.fail(
                "subsystem checks must not run after state-lock failure"
            ),
        )

    result = stop_quality_gate.evaluate_stop({})

    assert result["decision"] == "continue"
    assert "state is unreadable or malformed" in result["reason"]


def test_gate_reader_rejects_duplicate_json_status_keys(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    file_name = json.dumps(str((tmp_path / "duplicate.py").resolve()))
    entry = (
        "{"
        f'"file":{file_name},"linter":"ruff/py_compile",'
        '"passed":false,"passed":true,"output":""}'
    )
    state_path.write_text(
        f'{{"history":[{entry}],"last_status":{entry}}}', encoding="utf-8"
    )
    before = state_path.read_bytes()

    passed, diagnostics = stop_quality_gate.check_gate_state_errors()

    assert not passed
    assert "unreadable or malformed" in diagnostics
    assert state_path.read_bytes() == before
