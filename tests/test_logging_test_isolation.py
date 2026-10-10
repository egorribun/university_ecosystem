"""Logging configuration tests must leave later pytest consumers unchanged."""

from __future__ import annotations

import os
import subprocess
import sys
from inspect import getsource
from pathlib import Path


def _run_logging_isolation_probe() -> None:
    import logging

    import pytest
    import structlog

    class LoggingStateProbe:
        def __init__(self):
            self.expected = []
            self.checked = []

        def pytest_collection_finish(self, session):
            self.expected = [item.nodeid for item in session.items]

        @pytest.hookimpl(wrapper=True, trylast=True)
        def pytest_runtest_setup(self, item):
            result = yield
            import app.core.logging as logging_mod

            self.handlers = tuple(logging.getLogger().handlers)
            self.formatters = tuple(h.formatter for h in self.handlers)
            self.levels = tuple(h.level for h in self.handlers)
            self.root_level = logging.getLogger().level
            self.configuration = structlog.get_config().copy()
            self.structlog_configured = structlog.is_configured()
            self.configured = logging_mod._configured
            return result

        @pytest.hookimpl(wrapper=True, trylast=True)
        def pytest_runtest_teardown(self, item):
            result = yield
            import app.core.logging as logging_mod

            assert tuple(logging.getLogger().handlers) == self.handlers
            assert tuple(h.formatter for h in self.handlers) == self.formatters, (
                f"{item.nodeid} leaked logging formatters"
            )
            assert tuple(h.level for h in self.handlers) == self.levels
            assert logging.getLogger().level == self.root_level
            assert structlog.get_config() == self.configuration
            assert structlog.is_configured() == self.structlog_configured
            assert logging_mod._configured == self.configured
            capture = item.config.pluginmanager.get_plugin("logging-plugin")
            logging.getLogger("logging-isolation-probe").warning(
                "capture still receives records after logging restoration"
            )
            assert any(
                r.getMessage()
                == ("capture still receives records after logging restoration")
                for r in capture.caplog_handler.records
            )
            self.checked.append(item.nodeid)
            return result

    probe = LoggingStateProbe()
    result = pytest.main(
        [
            "-q",
            "--tb=short",
            "-n0",
            "tests/test_logging_core.py",
            "tests/test_logging_contract_closure.py",
            "tests/test_backend_dependency_injection.py::test_configure_logging_non_json",
        ],
        plugins=[probe],
    )
    assert probe.expected, "no logging isolation cases were collected"
    assert probe.checked == probe.expected, "logging state checks did not run"
    raise SystemExit(result)


def test_logging_tests_restore_capture_handlers_and_structlog_configuration():
    environment = os.environ.copy()
    for name in (
        "DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_DIR",
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET",
        "UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE",
        "UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
        "PYTEST_ADDOPTS",
    ):
        environment.pop(name, None)

    probe = (
        getsource(_run_logging_isolation_probe) + "\n_run_logging_isolation_probe()\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and local pytest probe
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
