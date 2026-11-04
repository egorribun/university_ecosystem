"""The owned live stand bounds every subprocess and lifecycle lock wait (AUD-309)."""

from __future__ import annotations

import ast
import errno
import importlib
import multiprocessing
import os
import subprocess
import time
from multiprocessing.connection import Connection
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


def _native_lock_contender(worktree: Path, in_place: bool, result: Connection) -> None:
    live_stand.WORKTREE = worktree
    live_stand.IN_PLACE_MODE = in_place
    live_stand.LIVE_LIFECYCLE_LOCK_TIMEOUT_SECONDS = 0.15
    try:
        with live_stand.stand_lifecycle_lock():
            result.send("acquired")
    except live_stand.StandError as error:
        result.send(str(error))
    finally:
        result.close()


@pytest.mark.parametrize("in_place", [False, True], ids=["worktree", "in-place"])
def test_native_lifecycle_lock_contends_and_recovers_after_release(
    tmp_path: Path, in_place: bool
) -> None:
    """The real OS lock serializes separate processes in either owned mode."""
    worktree = tmp_path / "temporary-owned-worktree"
    worktree.mkdir()
    assert worktree.name != live_stand.WORKTREE_NAME
    lock_name = worktree.name if in_place else live_stand.WORKTREE_NAME
    lock_path = tmp_path / f".{lock_name}.lifecycle.lock"
    lock_path.write_bytes(bytes(1))

    def contend() -> str:
        context = multiprocessing.get_context("spawn")
        reader, writer = context.Pipe(duplex=False)
        child = context.Process(
            target=_native_lock_contender, args=(worktree, in_place, writer)
        )
        child.start()
        writer.close()
        try:
            assert reader.poll(20), "native lock contender did not report within 20 s"
            outcome = reader.recv()
            child.join(timeout=5)
            assert child.exitcode == 0
            assert isinstance(outcome, str)
            return outcome
        finally:
            reader.close()
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
                if child.is_alive():
                    child.kill()
                    child.join(timeout=5)

    with lock_path.open("r+b") as owner:
        if os.name == "nt":
            native_lock = importlib.import_module("msvcrt")
            native_lock.locking(owner.fileno(), native_lock.LK_NBLCK, 1)
        else:
            native_lock = importlib.import_module("fcntl")
            native_lock.flock(owner.fileno(), native_lock.LOCK_EX | native_lock.LOCK_NB)
        try:
            blocked = contend()
        finally:
            if os.name == "nt":
                owner.seek(0)
                native_lock.locking(owner.fileno(), native_lock.LK_UNLCK, 1)
            else:
                native_lock.flock(owner.fileno(), native_lock.LOCK_UN)

    assert blocked == "timed out waiting for the live stand lifecycle lock"
    assert contend() == "acquired"
    assert lock_path.read_bytes() == bytes(1)
    assert list(tmp_path.glob(".*.lifecycle.lock")) == [lock_path]


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
