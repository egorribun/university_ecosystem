"""Finite child phases preserve circuit scenario failures and the outer deadline."""

import importlib
import io
import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from tests.helpers import circuit_process as helper


@pytest.mark.parametrize("mode", ["none", "monkeypatch"])
@pytest.mark.parametrize("failure", [None, "import", "scenario", "cleanup"])
def test_child_phases_preserve_scenario_and_cleanup(
    monkeypatch: pytest.MonkeyPatch, mode: str, failure: str | None
) -> None:
    output = io.StringIO()
    token = object()
    calls = []
    original = RuntimeError("synthetic phase failure")

    def scenario(*args: object) -> None:
        calls.append(args)
        if failure == "scenario":
            raise original

    def load_module(name: str) -> object:
        assert name == "owned_scenario"
        if failure == "import":
            raise original
        return SimpleNamespace(scenario=scenario)

    @contextmanager
    def context():
        try:
            yield token
        finally:
            calls.append("cleanup")
            if failure == "cleanup":
                raise original

    monkeypatch.setattr(sys, "argv", ["-c", "owned_scenario", "scenario", mode])
    monkeypatch.setattr(sys, "stderr", output)
    monkeypatch.setattr(importlib, "import_module", load_module)
    monkeypatch.setattr(pytest.MonkeyPatch, "context", staticmethod(context))
    if failure is None:
        helper._run_circuit_scenario()
    else:
        with pytest.raises(RuntimeError) as caught:
            helper._run_circuit_scenario()
        assert caught.value is original

    expected = ["helper_entered"]
    if failure != "import":
        expected.append("imports_ready")
        assert calls[0] == ((token,) if mode == "monkeypatch" else ())
        assert calls[-1] == "cleanup"
        if failure != "scenario":
            expected.append("scenario_returned")
        if failure is None:
            expected.append("cleanup_returned")
    else:
        assert calls == []
    assert output.getvalue().splitlines() == [
        "CIRCUIT_CHILD_PHASE=" + phase for phase in expected
    ]


@pytest.mark.parametrize("failure", ["write", "flush"])
def test_phase_output_failure_does_not_replace_scenario_error(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class BrokenStream:
        def write(self, text: str) -> None:
            if failure == "write":
                raise OSError("synthetic output failure")

        def flush(self) -> None:
            raise OSError("synthetic flush failure")

    original = RuntimeError("synthetic scenario failure")

    def scenario() -> None:
        raise original

    monkeypatch.setattr(sys, "argv", ["-c", "owned_scenario", "scenario", "none"])
    monkeypatch.setattr(sys, "stderr", BrokenStream())
    monkeypatch.setattr(
        importlib, "import_module", lambda name: SimpleNamespace(scenario=scenario)
    )
    with pytest.raises(RuntimeError) as caught:
        helper._run_circuit_scenario()
    assert caught.value is original


@pytest.mark.parametrize("mode", [False, True])
def test_parent_keeps_exact_deadline_and_subprocess_contract(
    monkeypatch: pytest.MonkeyPatch, mode: bool
) -> None:
    def scenario() -> None:
        pass

    def run(argv, **kwargs):
        assert argv == [
            sys.executable,
            "-c",
            helper._RUN_SCENARIO,
            scenario.__module__,
            scenario.__name__,
            "monkeypatch" if mode else "none",
        ]
        assert kwargs == {
            "capture_output": True,
            "text": True,
            "timeout": 5,
            "check": False,
        }
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(helper.subprocess, "run", run)
    helper.assert_circuit_scenario_completes(scenario, with_monkeypatch=mode)


@pytest.mark.parametrize("failure", ["timeout", "nonzero"])
def test_parent_never_accepts_failed_child(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def scenario() -> None:
        pass

    timeout = subprocess.TimeoutExpired(["owned"], 5)

    def run(argv, **kwargs):
        if failure == "timeout":
            raise timeout
        return subprocess.CompletedProcess(argv, 7, "", "")

    monkeypatch.setattr(helper.subprocess, "run", run)
    with pytest.raises(AssertionError) as caught:
        helper.assert_circuit_scenario_completes(scenario)
    if failure == "timeout":
        assert caught.value.__cause__ is timeout
        assert "across child startup, imports, scenario and shutdown" in str(
            caught.value
        )
        assert "event loop or cleanup stalled" not in str(caught.value)
    else:
        assert "exited 7" in str(caught.value)


def test_child_launcher_calls_the_tested_entrypoint() -> None:
    assert helper._RUN_SCENARIO.strip().splitlines() == [
        "from tests.helpers.circuit_process import _run_circuit_scenario",
        "_run_circuit_scenario()",
    ]
