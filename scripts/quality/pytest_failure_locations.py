"""Emit bounded, parameter-free failure locations before a CI job can time out."""

from __future__ import annotations

import re
from typing import Protocol

import pytest

_SOURCE_PATH = re.compile(r"tests/(?:[A-Za-z_][A-Za-z0-9_]*/)*test_[A-Za-z0-9_]+\.py")
_PLUGIN_NAME = "bounded-failure-locations"
_MAX_FAILURES = 100


class _Terminal(Protocol):
    def write_line(self, line: str) -> None: ...

    def flush(self) -> None: ...


class FailureLocations:
    """Observe failures without inspecting their payloads or changing outcomes."""

    def __init__(self, terminal: _Terminal, sources: frozenset[str]) -> None:
        self._terminal = terminal
        self._sources = sources
        self._failures = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if not report.failed or self._failures > _MAX_FAILURES:
            return
        self._failures += 1
        if self._failures > _MAX_FAILURES:
            self._terminal.write_line("PYTEST_FAILURE diagnostic_limit_reached")
            self._terminal.flush()
            return

        phase = (
            report.when if report.when in {"setup", "call", "teardown"} else "unknown"
        )
        path, line, _domain = report.location
        source = "unavailable"
        if path in self._sources and type(line) is int and 0 <= line < 1_000_000:
            source = f"{path}:{line + 1}"
        self._terminal.write_line(f"PYTEST_FAILURE phase={phase} source={source}")
        self._terminal.flush()


def pytest_sessionstart(session: pytest.Session) -> None:
    """Use only the controller; xdist forwards worker reports to its hooks."""
    config = session.config
    if hasattr(config, "workerinput") or config.pluginmanager.hasplugin(_PLUGIN_NAME):
        return
    terminal = config.pluginmanager.getplugin("terminalreporter")
    if terminal is None:
        return
    sources = frozenset(
        relative
        for path in (config.rootpath / "tests").rglob("test_*.py")
        if path.is_file() and not path.is_symlink()
        for relative in [path.relative_to(config.rootpath).as_posix()]
        if len(relative) <= 256 and _SOURCE_PATH.fullmatch(relative)
    )
    config.pluginmanager.register(FailureLocations(terminal, sources), _PLUGIN_NAME)
