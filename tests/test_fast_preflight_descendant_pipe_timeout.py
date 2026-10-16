"""Regression tests for bounded preflight descendant-pipe handling."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest

from scripts import fast_preflight


def test_run_check_deadline_when_descendant_inherits_output_pipes(
    tmp_path: Path,
) -> None:
    """A short-lived descendant cannot extend the check past its hard deadline."""

    marker = tmp_path / "descendant-finished.txt"
    descendant_code = (
        "import pathlib, sys, time; "
        "time.sleep(2.5); "
        "pathlib.Path(sys.argv[1]).write_text('finished', encoding='ascii')"
    )
    parent_code = (
        "import os, subprocess, sys; "
        "print('parent stdout', flush=True); "
        "print('parent stderr', file=sys.stderr, flush=True); "
        "child_options = {'start_new_session': True} if os.name != 'nt' else {}; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]], **child_options)"
    )
    check = fast_preflight.CheckSpec(
        "descendant-held-pipes",
        (sys.executable, "-c", parent_code, descendant_code, str(marker)),
    )

    result = fast_preflight.run_check(
        check,
        repo_root=tmp_path,
        timeout_seconds=0.75,
        include_output=True,
    )

    assert result.status == "timed_out"
    assert result.exit_code is None
    assert "parent stdout" in result.stdout
    assert "parent stderr" in result.stderr
    assert result.duration_seconds < 1.75
    assert not marker.exists()

    deadline = time.monotonic() + 4.0
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.exists()
    assert marker.read_text(encoding="ascii") == "finished"


class _FakePipe:
    def __init__(self, descriptor: int) -> None:
        self.descriptor = descriptor

    def fileno(self) -> int:
        return self.descriptor


class _FakeWindowsProcess:
    def __init__(self, stdout: _FakePipe, stderr: _FakePipe) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = 0

    def poll(self) -> int:
        return self.returncode


class _WindowsPipeError(OSError):
    def __init__(self, winerror: int) -> None:
        super().__init__("simulated Windows pipe error")
        self._winerror = winerror

    @property
    def winerror(self) -> int:
        return self._winerror


@pytest.mark.parametrize(
    ("stdout_steps", "stderr_steps", "expected_stdout", "expected_stderr"),
    [
        ([3, None], [None], b"out", b""),
        ([None], [2, None], b"", b"er"),
        ([3, None], [2, None], b"out", b"er"),
    ],
)
def test_windows_drain_reads_only_peeked_bytes_and_handles_eof(
    monkeypatch: Any,
    stdout_steps: list[int | None],
    stderr_steps: list[int | None],
    expected_stdout: bytes,
    expected_stderr: bytes,
) -> None:
    """Each pipe gets fair reads limited to PeekNamedPipe's available count."""

    stdout_pipe = _FakePipe(10)
    stderr_pipe = _FakePipe(11)
    process = _FakeWindowsProcess(stdout_pipe, stderr_pipe)
    counts = {10: iter(stdout_steps), 11: iter(stderr_steps)}
    read_sizes: list[tuple[int, int]] = []

    def peek(stream: _FakePipe) -> int | None:
        try:
            return next(counts[stream.fileno()])
        except StopIteration:
            return None

    def read(descriptor: int, size: int) -> bytes:
        read_sizes.append((descriptor, size))
        payload = b"out" if descriptor == 10 else b"er"
        return payload[:size]

    monkeypatch.setattr(fast_preflight, "_peek_windows_pipe_available", peek)
    monkeypatch.setattr(fast_preflight.os, "read", read)
    stdout = bytearray()
    stderr = bytearray()

    complete = fast_preflight._drain_windows_pipes(
        cast(subprocess.Popen[bytes], process),
        stdout=stdout,
        stderr=stderr,
        deadline=time.monotonic() + 0.1,
    )

    assert complete
    assert bytes(stdout) == expected_stdout
    assert bytes(stderr) == expected_stderr
    assert all(0 < size <= 3 for _, size in read_sizes)
    if expected_stdout and expected_stderr:
        assert [descriptor for descriptor, _ in read_sizes[:2]] == [10, 11]


def test_windows_drain_fails_closed_if_peeked_data_disappears(
    monkeypatch: Any,
) -> None:
    """A positive PeekNamedPipe count followed by an empty read is not EOF."""

    process = _FakeWindowsProcess(_FakePipe(20), _FakePipe(21))
    monkeypatch.setattr(
        fast_preflight, "_peek_windows_pipe_available", lambda _stream: 1
    )
    monkeypatch.setattr(fast_preflight.os, "read", lambda _descriptor, _size: b"")

    with pytest.raises(OSError, match="reported available bytes"):
        fast_preflight._drain_windows_pipes(
            cast(subprocess.Popen[bytes], process),
            stdout=bytearray(),
            stderr=bytearray(),
            deadline=time.monotonic() + 0.1,
        )


def test_windows_drain_treats_read_broken_pipe_as_eof(
    monkeypatch: Any,
) -> None:
    """A writer-close race is EOF only for the exact Win32 broken-pipe code."""

    process = _FakeWindowsProcess(_FakePipe(30), _FakePipe(31))
    counts = {30: iter([1, None]), 31: iter([None])}

    def peek(stream: _FakePipe) -> int | None:
        return next(counts[stream.fileno()])

    def read(_descriptor: int, _size: int) -> bytes:
        raise _WindowsPipeError(fast_preflight._ERROR_BROKEN_PIPE)

    monkeypatch.setattr(fast_preflight, "_peek_windows_pipe_available", peek)
    monkeypatch.setattr(fast_preflight.os, "read", read)

    complete = fast_preflight._drain_windows_pipes(
        cast(subprocess.Popen[bytes], process),
        stdout=bytearray(),
        stderr=bytearray(),
        deadline=time.monotonic() + 0.1,
    )

    assert complete


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0"])
def test_deadline_parser_rejects_nonpositive_or_unbounded_values(value: str) -> None:
    with pytest.raises(
        fast_preflight.argparse.ArgumentTypeError, match="positive number"
    ):
        fast_preflight._positive_number(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_runner_rejects_nonfinite_deadlines(value: float, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        fast_preflight.run_checks(
            (fast_preflight.CheckSpec("never-run", ("unused",)),),
            repo_root=tmp_path,
            max_workers=1,
            timeout_seconds=value,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.0, -1.0])
def test_run_check_rejects_invalid_deadlines_before_launch(
    value: float, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        fast_preflight,
        "_start_process",
        lambda *_args, **_kwargs: pytest.fail("invalid timeout must not launch"),
    )
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        fast_preflight.run_check(
            fast_preflight.CheckSpec("never-run", ("unused",)),
            repo_root=tmp_path,
            timeout_seconds=value,
            include_output=False,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_bounded_wait_never_delegates_an_unbounded_interval(value: float) -> None:
    class NeverWait:
        def wait(self, *, timeout: float) -> int:
            del timeout
            pytest.fail("invalid wait intervals must not reach Popen.wait")

    assert not fast_preflight._bounded_process_wait(
        cast(subprocess.Popen[bytes], NeverWait()), timeout_seconds=value
    )


def test_windows_drain_does_not_hide_other_pipe_errors(monkeypatch: Any) -> None:
    process = _FakeWindowsProcess(_FakePipe(40), _FakePipe(41))
    monkeypatch.setattr(
        fast_preflight, "_peek_windows_pipe_available", lambda _stream: 1
    )

    def read(_descriptor: int, _size: int) -> bytes:
        raise _WindowsPipeError(5)

    monkeypatch.setattr(fast_preflight.os, "read", read)

    with pytest.raises(_WindowsPipeError):
        fast_preflight._drain_windows_pipes(
            cast(subprocess.Popen[bytes], process),
            stdout=bytearray(),
            stderr=bytearray(),
            deadline=time.monotonic() + 0.1,
        )
