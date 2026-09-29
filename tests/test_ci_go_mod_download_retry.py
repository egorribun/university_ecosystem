"""Fail-closed tests for the bounded Go module download retry helper."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ci" / "go_mod_download.py"


def _load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("go_mod_download", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load Go retry helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "verifying github.com/aws/aws-sdk-go-v2 against "
            "sum.golang.org: stream error: stream ID 83; INTERNAL_ERROR; "
            "received from peer",
            True,
        ),
        ("proxy.golang.org: unexpected EOF", True),
        ("dial tcp: i/o timeout", True),
        ("received HTTP 503 Service Unavailable", True),
        ("401 Unauthorized", False),
        ("404 Not Found", False),
        ("verifying module: checksum mismatch", False),
        ("invalid version: unknown revision", False),
        ("malformed module path", False),
        (
            "unexpected EOF followed by checksum mismatch for downloaded module",
            False,
        ),
    ],
)
def test_go_failure_classifier_is_narrow(output: str, expected: bool) -> None:
    helper = _load_helper()

    assert helper.is_transient_failure(output) is expected


def test_go_helper_retries_transient_failure_and_keeps_first_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    helper = _load_helper()
    outcomes = iter(
        [
            subprocess.CompletedProcess(
                ["go", "mod", "download"],
                1,
                stdout="",
                stderr="first: stream error: INTERNAL_ERROR\n",
            ),
            subprocess.CompletedProcess(
                ["go", "mod", "download"],
                0,
                stdout="ok\n",
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(
        helper.subprocess, "run", lambda *args, **kwargs: next(outcomes)
    )
    sleeps: list[float] = []

    assert helper.run(tmp_path, backoff_seconds=5, sleep_fn=sleeps.append) == 0
    assert sleeps == [5]
    output = capsys.readouterr().out
    assert "first: stream error: INTERNAL_ERROR" in output
    assert "attempt 2" in output


def test_go_helper_fails_fast_on_permanent_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    helper = _load_helper()
    calls = 0

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            ["go", "mod", "download"], 1, stdout="", stderr="401 Unauthorized\n"
        )

    monkeypatch.setattr(helper.subprocess, "run", run)

    assert helper.run(tmp_path, backoff_seconds=0) == 1
    assert calls == 1
    assert "non-transient" in capsys.readouterr().err


def test_go_helper_exhausts_transient_attempts_and_preserves_first_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    helper = _load_helper()
    calls = 0

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            ["go", "mod", "download"],
            1,
            stdout="",
            stderr=f"attempt {calls}: i/o timeout\n",
        )

    monkeypatch.setattr(helper.subprocess, "run", run)
    sleeps: list[float] = []

    assert helper.run(tmp_path, backoff_seconds=5, sleep_fn=sleeps.append) == 1
    assert calls == 3
    assert sleeps == [5, 10]
    error = capsys.readouterr().err
    assert "after three transient attempts" in error
    assert "attempt 1: i/o timeout" in error


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"backoff_seconds": 61}, "backoff must be between"),
        ({"timeout_seconds": 901}, "timeout must be between"),
    ],
)
def test_go_helper_rejects_unbounded_retry_controls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kwargs: dict[str, int],
    message: str,
) -> None:
    helper = _load_helper()

    assert helper.run(tmp_path, **kwargs) == 2
    assert message in capsys.readouterr().err


def test_go_workflows_use_helper_for_every_module_download() -> None:
    workflow_paths = (
        ROOT / ".github" / "workflows" / "reusable-go-tests.yml",
        ROOT / ".github" / "workflows" / "reusable-go-integration-tests.yml",
        ROOT / ".github" / "workflows" / "contract-tests.yml",
    )
    for path in workflow_paths:
        source = path.read_text(encoding="utf-8")
        assert "scripts/ci/go_mod_download.py" in source, path
        assert "go mod download" not in source, path
