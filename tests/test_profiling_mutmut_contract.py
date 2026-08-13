from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.profiling import PyroscopeProfiler


def test_pyroscope_profiler_initializes_and_configures_with_optional_sdk(
    monkeypatch,
) -> None:
    """Keep the optional profiler constructor mapped in the mutmut population."""

    configure = Mock()
    monkeypatch.setitem(sys.modules, "pyroscope", SimpleNamespace(configure=configure))
    monkeypatch.setenv("PYROSCOPE_SERVER_ADDRESS", "http://localhost:4040")

    profiler = PyroscopeProfiler(application_name="quality-tests")
    profiler.configure()

    assert profiler.application_name == "quality-tests"
    assert profiler.server_address == "http://localhost:4040"
    configure.assert_called_once_with(
        application_name="quality-tests",
        server_address="http://localhost:4040",
    )
