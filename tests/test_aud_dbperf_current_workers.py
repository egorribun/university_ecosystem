"""Capture retry, threaded logging, and worker-evidence aggregation."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import conftest as capture

_SIGNAL = "university_ecosystem_db_perf_capture"


def _configure_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, required: bool
) -> None:
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(capture, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(capture, "_logged_queries", set())
    monkeypatch.setattr(capture, "_require_query_capture", required, raising=False)
    monkeypatch.setattr(capture, "_required_query_log_failed", False, raising=False)
    monkeypatch.setattr(capture, "_worker_capture_failed", False, raising=False)
    monkeypatch.setattr(capture, "_worker_captured_query", False, raising=False)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)


def _capture(statement: str) -> None:
    capture._log_query_before_execute(None, None, statement, None, None, False)


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_write_failure_never_discards_a_later_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, required: bool
) -> None:
    _configure_capture(tmp_path, monkeypatch, required=required)
    log_path = tmp_path / "tests" / "queries.log"
    log_path.mkdir()
    statement = "SELECT * FROM users WHERE id = 1"

    if required:
        with pytest.raises(OSError):
            _capture(statement)
    else:
        _capture(statement)
    assert statement not in capture._logged_queries

    log_path.rmdir()
    _capture(statement)
    _capture(statement)
    assert log_path.read_text(encoding="utf-8") == statement + "\n"
    session = SimpleNamespace(config=SimpleNamespace(), exitstatus=0)
    capture.pytest_sessionfinish(session, 0)
    assert session.exitstatus == (1 if required else 0)


def test_threads_record_complete_unique_statements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_capture(tmp_path, monkeypatch, required=True)
    statements = [f"SELECT {number}" for number in range(50)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(_capture, statements + statements))

    lines = (
        (tmp_path / "tests" / "queries.log").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == len(statements)
    assert set(lines) == set(statements)


def _session_finish_after_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workers: list[tuple[object, object]],
    initial_exit: int = 0,
) -> int:
    _configure_capture(tmp_path, monkeypatch, required=True)
    node_down = getattr(capture, "pytest_testnodedown", None)
    session_finish = getattr(capture, "pytest_sessionfinish", None)
    assert callable(node_down), "capture evidence must be collected from workers"
    assert callable(session_finish), "capture evidence must affect session status"
    for output, error in workers:
        node_down(SimpleNamespace(workeroutput=output), error)
    session = SimpleNamespace(config=SimpleNamespace(), exitstatus=initial_exit)
    session_finish(session, initial_exit)
    return int(session.exitstatus)


def test_one_empty_worker_and_one_capturing_worker_are_sufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workers = [
        ({_SIGNAL: {"failed": False, "captured": False}}, None),
        ({_SIGNAL: {"failed": False, "captured": True}}, None),
    ]
    assert _session_finish_after_workers(tmp_path, monkeypatch, workers) == 0


@pytest.mark.parametrize(
    ("output", "error"),
    [
        (None, None),
        ({}, None),
        ({_SIGNAL: {"failed": "false", "captured": True}}, None),
        ({_SIGNAL: {"failed": False, "captured": True}}, "worker crashed"),
    ],
    ids=["nonmapping", "missing", "malformed", "crashed"],
)
def test_bad_worker_evidence_cannot_produce_a_successful_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: object,
    error: object,
) -> None:
    assert _session_finish_after_workers(tmp_path, monkeypatch, [(output, error)]) == 1


def test_capture_failure_preserves_an_existing_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workers = [({}, None)]
    assert _session_finish_after_workers(tmp_path, monkeypatch, workers, 2) == 2
