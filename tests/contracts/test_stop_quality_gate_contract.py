"""Regression tests for the lifecycle stop gate's Go-vet scheduling policy."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import threading
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPOSITORY_ROOT / ".agents" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

stop_quality_gate = importlib.import_module("stop_quality_gate")
common = importlib.import_module("common")
post_tool_linter = importlib.import_module("post_tool_linter")


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

    b_completed = threading.Event()

    def fake_run_process(
        command: list[str], *, cwd: Path, timeout: int
    ) -> tuple[int, str, str]:
        if cwd.name == "b-module":
            return 1, "", "failure b"
        assert b_completed.wait(timeout=2)
        return 1, "", "failure a"

    real_executor = stop_quality_gate.concurrent.futures.ThreadPoolExecutor

    class CompletionObservedExecutor(real_executor):
        def submit(self, function: Any, /, *args: Any, **kwargs: Any) -> Any:
            future = super().submit(function, *args, **kwargs)
            if args and Path(args[0]).name == "b-module":
                future.add_done_callback(lambda _: b_completed.set())
            return future

    monkeypatch.setattr(stop_quality_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(stop_quality_gate, "run_process", fake_run_process)
    monkeypatch.setattr(
        stop_quality_gate.concurrent.futures,
        "ThreadPoolExecutor",
        CompletionObservedExecutor,
    )

    passed, diagnostics = stop_quality_gate.check_services_subsystem(tmp_path)

    assert not passed
    failure_a = "Go Vet Failure in 'services/a-module':\nfailure a"
    failure_b = "Go Vet Failure in 'services/b-module':\nfailure b"
    assert failure_a in diagnostics
    assert failure_b in diagnostics
    assert diagnostics.index(failure_a) < diagnostics.index(failure_b)


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


def test_gate_reader_blocks_evicted_failure_without_rewriting_state(
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


def test_gate_reader_fails_closed_on_invalid_json_and_missing_state(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    assert common.load_gate_state(state_path) == {"history": [], "latest_by_file": {}}

    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "state is missing" in diagnostics
    assert "supported PostToolUse quality check" in diagnostics
    assert "do not create an empty state file manually" in diagnostics
    assert not state_path.exists()

    state_path.write_text("{invalid", encoding="utf-8")
    before = state_path.read_bytes()
    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "unreadable or malformed" in diagnostics
    assert state_path.read_bytes() == before


def test_gate_reader_denies_stop_after_failed_state_is_deleted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    failure = _gate_entry(tmp_path / "broken.py", passed=False, output="ruff failure")
    state_path = _point_stop_gate_at_state(
        tmp_path,
        monkeypatch,
        {
            "history": [failure],
            "latest_by_file": {failure["file"]: failure},
            "last_status": failure,
        },
    )
    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "ruff failure" in diagnostics

    state_path.unlink()
    monkeypatch.setattr(stop_quality_gate, "find_repo_root", lambda: tmp_path)
    for check_name in (
        "check_python_subsystem",
        "check_frontend_subsystem",
        "check_services_subsystem",
    ):
        monkeypatch.setattr(
            stop_quality_gate,
            check_name,
            lambda _: pytest.fail("subsystem checks must not run without gate state"),
        )

    result = stop_quality_gate.evaluate_stop({})

    assert result["decision"] == "continue"
    assert "Automated quality gate state is missing" in result["reason"]
    assert "missing after initialization" in result["reason"]
    assert (
        "cannot recreate it without discarding prior quality results"
        in result["reason"]
    )


def test_gate_reader_migrates_legacy_failed_state_before_it_can_be_deleted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    failure = _gate_entry(
        tmp_path / "legacy-broken.py", passed=False, output="ruff failure"
    )
    state_path = _point_stop_gate_at_state(
        tmp_path,
        monkeypatch,
        {
            "history": [failure],
            "latest_by_file": {failure["file"]: failure},
            "last_status": failure,
        },
    )
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    assert not marker_path.exists()
    before = state_path.read_bytes()

    passed, diagnostics = stop_quality_gate.check_gate_state_errors()

    assert not passed
    assert "ruff failure" in diagnostics
    assert state_path.read_bytes() == before
    assert marker_path.is_file()

    state_path.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        post_tool_linter.update_gate_state(
            str((tmp_path / "clean.py").resolve()), "ruff", True, ""
        )
    assert not state_path.exists()


def test_first_post_tool_success_initializes_state_for_stop_reader(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    assert not state_path.exists()
    missing_state_result = stop_quality_gate.check_gate_state_errors()
    assert not missing_state_result[0]

    checked_file = str((tmp_path / "clean.py").resolve())
    post_tool_linter.update_gate_state(checked_file, "ruff/py_compile", True, "")

    state = common.load_gate_state(state_path, require_existing=True)
    assert state["latest_by_file"][checked_file]["passed"]
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    assert marker_path.is_file()
    assert marker_path.name.endswith(".initialized")
    assert stop_quality_gate.check_gate_state_errors() == (True, "")


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
    monkeypatch.setattr(stop_quality_gate, "gate_state_lock", fail_to_lock)
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


def test_post_tool_writer_does_not_reinitialize_deleted_gate_state(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    failure_path = str((tmp_path / "failed.py").resolve())
    post_tool_linter.update_gate_state(failure_path, "ruff", False, "original failure")
    assert stop_quality_gate.check_gate_state_errors()[0] is False

    state_path.unlink()
    missing_state, missing_diagnostic = stop_quality_gate.check_gate_state_errors()
    assert not missing_state
    assert "missing after initialization" in missing_diagnostic

    with pytest.raises(RuntimeError, match="missing"):
        post_tool_linter.update_gate_state(
            str((tmp_path / "clean.py").resolve()), "ruff", True, ""
        )

    assert not state_path.exists()
    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "state is missing" in diagnostics


def test_stop_checks_missing_state_and_witness_under_one_lock(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)

    marker_check_entered = threading.Event()
    allow_marker_check = threading.Event()
    writer_lock_requested = threading.Event()
    writer_lock_acquired = threading.Event()
    writer_finished = threading.Event()
    stop_results: list[tuple[bool, str]] = []
    thread_errors: list[BaseException] = []

    real_marker_reader = stop_quality_gate.has_gate_state_initialization_marker

    def pause_before_marker_read(path: Path) -> bool:
        marker_check_entered.set()
        if not allow_marker_check.wait(timeout=2):
            raise AssertionError("test did not release the marker check")
        return real_marker_reader(path)

    monkeypatch.setattr(
        stop_quality_gate,
        "has_gate_state_initialization_marker",
        pause_before_marker_read,
    )

    real_lock = common.gate_state_lock

    @contextmanager
    def observe_writer_lock(path: Path) -> Any:
        writer_lock_requested.set()
        with real_lock(path):
            writer_lock_acquired.set()
            yield

    monkeypatch.setattr(post_tool_linter, "gate_state_lock", observe_writer_lock)

    def check_stop() -> None:
        try:
            stop_results.append(stop_quality_gate.check_gate_state_errors())
        except BaseException as exc:
            thread_errors.append(exc)

    def initialize_state() -> None:
        try:
            post_tool_linter.update_gate_state(
                str((tmp_path / "clean.py").resolve()), "ruff", True, ""
            )
        except BaseException as exc:
            thread_errors.append(exc)
        finally:
            writer_finished.set()

    stop_thread = threading.Thread(target=check_stop, name="quality-stop-reader")
    writer_thread = threading.Thread(
        target=initialize_state, name="quality-state-initializer"
    )
    stop_thread.start()
    try:
        assert marker_check_entered.wait(timeout=2)
        writer_thread.start()
        assert writer_lock_requested.wait(timeout=2)
        assert not writer_lock_acquired.wait(timeout=0.2), (
            "writer crossed the Stop reader's state/witness check"
        )
    finally:
        allow_marker_check.set()
        stop_thread.join(timeout=2)
        if writer_thread.ident is not None:
            writer_thread.join(timeout=2)

    assert not stop_thread.is_alive()
    assert not writer_thread.is_alive()
    assert writer_finished.is_set()
    assert not thread_errors
    assert stop_results == [
        (
            False,
            "Automated quality gate state is missing. Run a supported PostToolUse "
            "quality check on a source file to initialize it; do not create an "
            "empty state file manually.",
        )
    ]
    assert common.load_gate_state(state_path, require_existing=True)["latest_by_file"]


def test_gate_state_initialization_witness_write_failure_blocks_bootstrap(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    real_replace = post_tool_linter.os.replace

    def fail_marker_replace(source: Any, destination: Any) -> None:
        if Path(destination) == marker_path:
            raise OSError("simulated atomic witness persistence failure")
        real_replace(source, destination)

    monkeypatch.setattr(post_tool_linter.os, "replace", fail_marker_replace)

    with pytest.raises(RuntimeError, match="initialization witness"):
        post_tool_linter.update_gate_state(
            str((tmp_path / "clean.py").resolve()), "ruff", True, ""
        )

    assert not state_path.exists()
    assert not marker_path.exists()
    passed, diagnostics = stop_quality_gate.check_gate_state_errors()
    assert not passed
    assert "state is missing" in diagnostics


def test_stop_gate_fails_closed_when_initialization_witness_is_malformed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    marker_path.write_bytes(b"corrupted witness\n")
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)

    assert stop_quality_gate.check_gate_state_errors() == (
        False,
        "Automated quality gate state is unreadable or malformed.",
    )
    with pytest.raises(
        RuntimeError, match="Malformed hook gate state initialization witness"
    ):
        post_tool_linter.update_gate_state(
            str((tmp_path / "clean.py").resolve()), "ruff", True, ""
        )
    assert not state_path.exists()


def test_stop_gate_fails_closed_when_initialization_witness_cannot_be_read(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    monkeypatch.setattr(stop_quality_gate, "get_gate_state_path", lambda: state_path)
    real_read_bytes = Path.read_bytes

    def deny_witness_read(path: Path) -> bytes:
        if path == marker_path:
            raise PermissionError("simulated witness read denial")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", deny_witness_read)

    assert stop_quality_gate.check_gate_state_errors() == (
        False,
        "Automated quality gate state is unreadable or malformed.",
    )
    assert not state_path.exists()


def test_post_tool_update_fails_closed_when_state_stat_is_denied(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    real_stat = Path.stat

    def deny_state_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == state_path:
            raise PermissionError("simulated state metadata denial")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_state_stat)
    with pytest.raises(RuntimeError, match="Could not inspect hook gate state"):
        post_tool_linter.update_gate_state(
            str((tmp_path / "clean.py").resolve()), "ruff", True, ""
        )
    monkeypatch.setattr(Path, "stat", real_stat)
    assert not state_path.exists()


def test_post_tool_update_preserves_existing_initialization_witness(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    file_one = str((tmp_path / "one.py").resolve())
    file_two = str((tmp_path / "two.py").resolve())

    post_tool_linter.update_gate_state(file_one, "ruff", True, "first")
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    marker_before = marker_path.read_bytes()
    post_tool_linter.update_gate_state(file_two, "ruff", True, "second")

    state = common.load_gate_state(state_path, require_existing=True)
    assert marker_path.read_bytes() == marker_before
    assert [entry["output"] for entry in state["history"]] == ["first", "second"]
    assert set(state["latest_by_file"]) == {file_one, file_two}


def test_post_tool_witness_cleanup_error_does_not_mask_write_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    state_path = tmp_path / ".gate_state.json"
    marker_path = post_tool_linter._gate_state_initialization_marker_path(state_path)
    real_replace = post_tool_linter.os.replace
    real_unlink = Path.unlink

    def fail_marker_replace(source: Any, destination: Any) -> None:
        if Path(destination) == marker_path:
            raise OSError("simulated witness replace failure")
        real_replace(source, destination)

    def deny_marker_temp_cleanup(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name.startswith(f".{state_path.name}.initialized."):
            raise PermissionError("simulated temporary witness cleanup failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(post_tool_linter, "get_gate_state_path", lambda: state_path)
    monkeypatch.setattr(post_tool_linter.os, "replace", fail_marker_replace)
    monkeypatch.setattr(Path, "unlink", deny_marker_temp_cleanup)

    with pytest.raises(
        RuntimeError, match="Could not persist hook gate state initialization witness"
    ):
        post_tool_linter.update_gate_state(
            str((tmp_path / "clean.py").resolve()), "ruff", True, ""
        )
    temporary_witnesses = list(tmp_path.glob(f".{state_path.name}.initialized.*.tmp"))
    assert len(temporary_witnesses) == 1
    real_unlink(temporary_witnesses[0])
    assert not state_path.exists()


def test_stop_gate_supports_package_relative_imports() -> None:
    package_name = "_aud223_candidate_hooks"
    qualified_name = f"{package_name}.stop_quality_gate"
    package = types.ModuleType(package_name)
    package.__path__ = [str(HOOKS_DIR)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
    try:
        spec = importlib.util.spec_from_file_location(
            qualified_name, HOOKS_DIR / "stop_quality_gate.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified_name] = module
        spec.loader.exec_module(module)
        assert module.gate_state_lock.__module__ == f"{package_name}.common"
        assert (
            module.has_gate_state_initialization_marker.__module__
            == f"{package_name}.post_tool_linter"
        )
    finally:
        for name in tuple(sys.modules):
            if name == package_name or name.startswith(f"{package_name}."):
                del sys.modules[name]
