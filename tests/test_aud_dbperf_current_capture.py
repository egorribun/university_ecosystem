"""Real pytest-process contracts for DB-performance query capture."""

import os
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _prepare_capture_case(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    *,
    scenario: str,
    required: bool,
) -> Path:
    capture_root = pytester.path / "capture"
    log_directory = capture_root / "tests"
    log_directory.mkdir(parents=True)
    if scenario == "write-failure":
        (log_directory / "queries.log").mkdir()
        (log_directory / "queries_gw0.log").mkdir()

    monkeypatch.setenv(
        "PYTHONPATH",
        str(_PROJECT_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    monkeypatch.setenv("AUD_DBPERF_CAPTURE_ROOT", str(capture_root))
    monkeypatch.setenv("AUD_DBPERF_CAPTURE_SCENARIO", scenario)
    if required:
        monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_DB_PERF_CAPTURE_REQUIRED", "1")
    else:
        monkeypatch.delenv(
            "UNIVERSITY_ECOSYSTEM_DB_PERF_CAPTURE_REQUIRED", raising=False
        )

    pytester.makepyfile(
        test_capture="""
        import os
        from pathlib import Path
        from sqlalchemy import create_engine, text
        from tests import conftest as capture

        def test_application_catches_event_error():
            capture.PROJECT_ROOT = Path(os.environ['AUD_DBPERF_CAPTURE_ROOT'])
            scenario = os.environ['AUD_DBPERF_CAPTURE_SCENARIO']
            if scenario == 'empty':
                return
            if scenario in ('short-write', 'close-failure'):
                class IncompleteFile:
                    def __enter__(self):
                        return self

                    def write(self, line):
                        return len(line) - (scenario == 'short-write')

                    def __exit__(self, exc_type, exc, traceback):
                        if scenario == 'close-failure':
                            raise OSError('close failed')
                        return False

                capture.open = lambda *args, **kwargs: IncompleteFile()
            engine = create_engine('sqlite://')
            try:
                with engine.connect() as connection:
                    connection.execute(text('SELECT 1'))
            except OSError:
                (capture.PROJECT_ROOT / 'caught-event-error').write_text('caught')
            finally:
                engine.dispose()
        """
    )
    return capture_root


def _run_capture_case(pytester: pytest.Pytester, workers: int, *extra: str):
    return pytester.runpytest_subprocess(
        "--noconftest",
        "-p",
        "tests.conftest",
        "-q",
        "-n",
        str(workers),
        "-o",
        "addopts=",
        "-o",
        "asyncio_mode=auto",
        "-o",
        "asyncio_default_fixture_loop_scope=session",
        "-o",
        "asyncio_default_test_loop_scope=session",
        *extra,
        timeout=30,
    )


@pytest.mark.parametrize(
    ("workers", "scenario"),
    [
        (0, "write-failure"),
        (0, "short-write"),
        (0, "close-failure"),
        (0, "healthy"),
        (0, "empty"),
        (1, "write-failure"),
        (1, "healthy"),
        (1, "empty"),
    ],
)
def test_required_capture_fails_on_incomplete_evidence(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    workers: int,
    scenario: str,
) -> None:
    capture_root = _prepare_capture_case(
        pytester, monkeypatch, scenario=scenario, required=True
    )

    result = _run_capture_case(pytester, workers)

    result.assert_outcomes(passed=1)
    if scenario == "healthy":
        assert result.ret == 0
        filename = "queries_gw0.log" if workers else "queries.log"
        assert (capture_root / "tests" / filename).read_text(encoding="utf-8") == (
            "SELECT 1\n"
        )
    else:
        assert result.ret != 0
        if scenario != "empty":
            assert (capture_root / "caught-event-error").is_file()


def test_optional_capture_keeps_best_effort_behavior(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture_root = _prepare_capture_case(
        pytester, monkeypatch, scenario="write-failure", required=False
    )

    result = _run_capture_case(pytester, 0)

    result.assert_outcomes(passed=1)
    assert result.ret == 0
    assert not (capture_root / "caught-event-error").exists()


@pytest.mark.parametrize("signal", ["missing", "malformed", "failed"])
def test_worker_capture_signal_must_be_present_and_valid(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, signal: str
) -> None:
    _prepare_capture_case(pytester, monkeypatch, scenario="healthy", required=True)
    monkeypatch.setenv("AUD_DBPERF_SIGNAL", signal)
    pytester.makepyfile(
        dbperf_signal_injector="""
        import os
        import pytest

        @pytest.hookimpl(hookwrapper=True, trylast=True)
        def pytest_sessionfinish(session):
            yield
            output = getattr(session.config, 'workeroutput', None)
            if output is None:
                return
            key = 'university_ecosystem_db_perf_capture'
            if os.environ['AUD_DBPERF_SIGNAL'] == 'missing':
                output.pop(key, None)
            elif os.environ['AUD_DBPERF_SIGNAL'] == 'malformed':
                output[key] = {'failed': 'no', 'captured': True}
            else:
                output[key] = {'failed': True, 'captured': True}
        """
    )

    result = _run_capture_case(pytester, 1, "-p", "dbperf_signal_injector")

    result.assert_outcomes(passed=1)
    assert result.ret != 0
