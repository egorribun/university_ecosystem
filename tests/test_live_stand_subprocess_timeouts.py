"""The owned live stand bounds every subprocess and lifecycle lock wait (AUD-309)."""

from __future__ import annotations

import ast
import errno
import importlib
import os
import subprocess
import time
from pathlib import Path

import pytest

from scripts import live_stand

ROOT = Path(__file__).resolve().parents[1]
LIVE_STAND = ROOT / "scripts" / "live_stand.py"
_TIMEOUT_CAPABLE_CALLS = frozenset({"run", "check_call", "check_output", "call"})


def _unbounded_subprocess_lines() -> list[int]:
    tree = ast.parse(LIVE_STAND.read_text(encoding="utf-8"), filename=str(LIVE_STAND))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        function = node.func
        if not (
            isinstance(function.value, ast.Name)
            and function.value.id == "subprocess"
            and function.attr in _TIMEOUT_CAPABLE_CALLS | {"Popen"}
        ):
            continue
        if not any(keyword.arg == "timeout" for keyword in node.keywords):
            lines.append(node.lineno)
    return sorted(lines)


def test_every_live_stand_subprocess_call_declares_a_timeout() -> None:
    assert _unbounded_subprocess_lines() == []


def test_generic_live_stand_command_timeout_becomes_a_stand_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expire(*_args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == live_stand.LIVE_COMMAND_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

    monkeypatch.setattr(live_stand.subprocess, "run", expire)

    with pytest.raises(live_stand.StandError, match="timed out"):
        live_stand._run(["docker", "compose", "up"], cwd=ROOT)


def test_git_probe_timeout_becomes_a_stand_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expire(*_args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == live_stand.LIVE_PROBE_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(live_stand.subprocess, "run", expire)

    with pytest.raises(live_stand.StandError, match="timed out"):
        live_stand._git("rev-parse", "HEAD")


def test_playwright_timeout_becomes_a_stand_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def expire(*_args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == live_stand.LIVE_E2E_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(cmd="playwright", timeout=1)

    monkeypatch.setattr(live_stand.subprocess, "run", expire)

    with pytest.raises(live_stand.StandError, match="timed out"):
        live_stand._run_live_playwright(
            cwd=tmp_path,
            environment={},
            mode="full",
            specs=(),
        )


def _lock_test_worktree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)


@pytest.mark.skipif(os.name != "nt", reason="native Windows msvcrt lock path")
def test_windows_lifecycle_lock_wait_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    msvcrt = importlib.import_module("msvcrt")
    _lock_test_worktree(monkeypatch, tmp_path)
    clock = [1_000.0]
    attempts = [0]

    def locked(_fileno: int, _mode: int, _nbytes: int) -> None:
        attempts[0] += 1
        if attempts[0] > 50:
            raise AssertionError("the lifecycle lock wait was not bounded")
        raise OSError(errno.EACCES, "locked by another operation")

    def sleep_past_any_deadline(seconds: float) -> None:
        assert seconds > 0
        clock[0] += 10_000_000.0

    monkeypatch.setattr(msvcrt, "locking", locked)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", sleep_past_any_deadline)

    with (
        pytest.raises(live_stand.StandError, match="lifecycle lock"),
        live_stand.stand_lifecycle_lock(),
    ):
        pass
    assert attempts[0] <= 3


@pytest.mark.skipif(os.name == "nt", reason="POSIX fcntl lock path")
def test_posix_lifecycle_lock_wait_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fcntl = importlib.import_module("fcntl")
    _lock_test_worktree(monkeypatch, tmp_path)
    clock = [1_000.0]
    attempts = [0]

    def locked(_fileno: int, flags: int) -> None:
        attempts[0] += 1
        assert flags & fcntl.LOCK_NB
        if attempts[0] > 50:
            raise AssertionError("the lifecycle lock wait was not bounded")
        raise BlockingIOError(errno.EAGAIN, "locked by another operation")

    def sleep_past_any_deadline(seconds: float) -> None:
        assert seconds > 0
        clock[0] += 10_000_000.0

    monkeypatch.setattr(fcntl, "flock", locked)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", sleep_past_any_deadline)

    with (
        pytest.raises(live_stand.StandError, match="lifecycle lock"),
        live_stand.stand_lifecycle_lock(),
    ):
        pass
    assert attempts[0] <= 3
