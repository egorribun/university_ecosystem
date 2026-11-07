"""Failure diagnostics never echo test parameters or change test outcomes."""

from io import StringIO
from types import SimpleNamespace

import pytest

from scripts.quality.pytest_failure_locations import (
    FailureLocations,
    pytest_sessionstart,
)


class TerminalSink:
    def __init__(self):
        self.output = StringIO()
        self.flushes = 0

    def write_line(self, line):
        self.output.write(line + "\n")

    def flush(self):
        self.flushes += 1


def report(*, outcome="failed", phase="call", path="tests/test_example.py", line=41):
    private = "private-" + "parameter-value"
    return pytest.TestReport(
        nodeid=f"tests/test_example.py::test_example[{private}]",
        location=(path, line, private),
        keywords={},
        outcome=outcome,
        longrepr=private,
        when=phase,
        sections=[("Captured stdout call", private)],
    )


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_failure_location_is_flushed_without_waiting_for_session_end(phase):
    terminal = TerminalSink()
    diagnostic = FailureLocations(terminal, frozenset({"tests/test_example.py"}))
    result = report(phase=phase)
    before = dict(vars(result))
    diagnostic.pytest_runtest_logreport(result)
    assert terminal.output.getvalue() == (
        f"PYTEST_FAILURE phase={phase} source=tests/test_example.py:42\n"
    )
    assert terminal.flushes == 1
    assert vars(result) == before


@pytest.mark.parametrize("outcome", ["passed", "skipped"])
def test_nonfailure_reports_do_not_consume_diagnostic_budget(outcome):
    terminal = TerminalSink()
    diagnostic = FailureLocations(terminal, frozenset({"tests/test_example.py"}))
    for _ in range(101):
        diagnostic.pytest_runtest_logreport(report(outcome=outcome))
    assert terminal.output.getvalue() == ""
    assert terminal.flushes == 0
    diagnostic.pytest_runtest_logreport(report())
    assert "source=tests/test_example.py:42" in terminal.output.getvalue()


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("tests/test_missing.py", 0),
        ("/tests/test_example.py", 0),
        ("tests/../test_example.py", 0),
        ("tests/test_example.py\ncommand", 0),
        ("tests/test_example.py[private]", 0),
        ("tests/test_example.py", -1),
        ("tests/test_example.py", True),
        ("tests/test_example.py", None),
        ("tests/test_example.py", 1_000_000),
    ],
)
def test_invalid_location_never_echoes_rejected_input(path, line):
    terminal = TerminalSink()
    diagnostic = FailureLocations(terminal, frozenset({"tests/test_example.py"}))
    diagnostic.pytest_runtest_logreport(report(path=path, line=line))
    assert terminal.output.getvalue() == (
        "PYTEST_FAILURE phase=call source=unavailable\n"
    )


def test_unknown_phase_is_not_echoed_and_failure_output_is_bounded():
    terminal = TerminalSink()
    diagnostic = FailureLocations(terminal, frozenset({"tests/test_example.py"}))
    for _ in range(105):
        diagnostic.pytest_runtest_logreport(report(phase="private-phase"))
    lines = terminal.output.getvalue().splitlines()
    assert len(lines) == 101
    assert set(lines[:-1]) == {
        "PYTEST_FAILURE phase=unknown source=tests/test_example.py:42"
    }
    assert lines[-1] == "PYTEST_FAILURE diagnostic_limit_reached"
    assert terminal.flushes == 101


@pytest.mark.parametrize("worker", [False, True])
def test_registration_is_controller_only_and_uses_real_test_paths(tmp_path, worker):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text("def test_example(): pass\n")
    (tests / "test_bad[parameter].py").write_text("def test_example(): pass\n")
    manager = pytest.PytestPluginManager()
    terminal = TerminalSink()
    manager.register(terminal, "terminalreporter")
    config = SimpleNamespace(rootpath=tmp_path, pluginmanager=manager)
    if worker:
        config.workerinput = {}
    pytest_sessionstart(SimpleNamespace(config=config))
    pytest_sessionstart(SimpleNamespace(config=config))
    manager.hook.pytest_runtest_logreport(report=report(line=0))
    if worker:
        assert terminal.output.getvalue() == ""
    else:
        assert terminal.output.getvalue() == (
            "PYTEST_FAILURE phase=call source=tests/test_example.py:1\n"
        )
        manager.hook.pytest_runtest_logreport(
            report=report(path="tests/test_bad[parameter].py", line=0)
        )
        assert terminal.output.getvalue().endswith("source=unavailable\n")


def test_absent_terminal_reporter_does_not_register_diagnostics(tmp_path):
    manager = pytest.PytestPluginManager()
    config = SimpleNamespace(rootpath=tmp_path, pluginmanager=manager)
    pytest_sessionstart(SimpleNamespace(config=config))
    assert not manager.hasplugin("bounded-failure-locations")
