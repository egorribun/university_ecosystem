"""Regression tests for the lifecycle stop gate's Go-vet scheduling policy."""

from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPOSITORY_ROOT / ".agents" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

stop_quality_gate = importlib.import_module("stop_quality_gate")


GO_MODULES = (
    "gateway",
    "ws-hub",
    "file-processor",
    "cmd/uni-cli",
    "pkg/spiffe",
    "pkg/spicedb",
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
