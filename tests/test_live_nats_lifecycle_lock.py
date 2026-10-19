"""Initial existing-lock capability tests, not runtime admission."""

from __future__ import annotations

import importlib
import os
from collections import Counter
from types import ModuleType

import pytest

from scripts import live_nats_transport as transport
from scripts.owned_nats_outage import Deadline

_fcntl: ModuleType | None
try:
    _fcntl = importlib.import_module("fcntl")
except ImportError:
    _fcntl = None


@pytest.fixture
def lock_case(tmp_path):
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC")
    if (
        _fcntl is None
        or os.name != "posix"
        or any(getattr(os, name, 0) <= 0 for name in required)
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        pytest.skip("requires POSIX nofollow descriptor-relative flock support")
    root = tmp_path.resolve() / "run-lock"
    root.mkdir()
    lock = root.parent / f".{root.name}.lifecycle.lock"
    lock.touch(mode=0o600)
    return root, lock, _fcntl


def _no_sleep(_seconds):
    raise AssertionError("uncontended acquisition must not sleep")


def _acquire(root, deadline, fcntl):
    real_flock = fcntl.flock

    def nonblocking(fd, operation):
        if not operation & fcntl.LOCK_UN:
            assert operation & fcntl.LOCK_NB, "blocking flock is forbidden"
        return real_flock(fd, operation)

    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(fcntl, "flock", nonblocking)
        return transport.acquire_existing_lifecycle_lock(
            str(root), deadline=deadline, sleep=_no_sleep
        )


def _probe(lock, fcntl, operation, *, blocked):
    fd = os.open(lock, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if blocked:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, operation | fcntl.LOCK_NB)
        else:
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def _snapshot(lock):
    info = lock.stat()
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        lock.read_bytes(),
    )


def test_existing_empty_lock_holds_exclusive_without_mutation(lock_case):
    root, lock, fcntl = lock_case
    before = _snapshot(lock)
    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    lease = _acquire(root, deadline, fcntl)
    assert lease is not None
    try:
        shown = repr(lease)
        for private in (str(root), str(lock), root.name, lock.name):
            assert private not in shown
        _probe(lock, fcntl, fcntl.LOCK_SH, blocked=True)
        _probe(lock, fcntl, fcntl.LOCK_EX, blocked=True)
        assert _snapshot(lock) == before
    finally:
        released = transport.release_lifecycle_lock(lease, deadline=deadline)
    assert released is True
    _probe(lock, fcntl, fcntl.LOCK_SH, blocked=False)
    _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)
    assert _snapshot(lock) == before


def test_nofollow_relative_walk_and_each_acquired_fd_closed_once(lock_case):
    root, lock, fcntl = lock_case
    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    real_open, real_close = os.open, os.close
    opened, closed = [], []
    released = False

    def traced_open(path, flags, mode=0o777, *, dir_fd=None):
        assert not flags & (
            os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_RDWR | os.O_APPEND
        )
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append((path, flags, dir_fd, fd))
        return fd

    def traced_close(fd):
        closed.append(fd)
        return real_close(fd)

    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(os, "open", traced_open)
        guard.setattr(os, "close", traced_close)
        guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {traced_open})
        lease = _acquire(root, deadline, fcntl)
        if lease is not None:
            released = transport.release_lifecycle_lock(lease, deadline=deadline)
    assert lease is not None
    assert released is True
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    leaf_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    directories = [entry for entry in opened if entry[0] != lock.name]
    leaves = [entry for entry in opened if entry[0] == lock.name]
    assert len(directories) == len(root.parts)
    parent_fd = None
    for name, entry in zip(root.parts, directories, strict=True):
        path, flags, relative_to, fd = entry
        assert (path, flags, relative_to) == (name, directory_flags, parent_fd)
        parent_fd = fd
    assert len(leaves) == 1
    path, flags, relative_to, _fd = leaves[0]
    assert (path, flags, relative_to) == (
        lock.name,
        leaf_flags,
        directories[-2][3],
    )
    assert Counter(closed) == Counter(entry[3] for entry in opened)


def test_expired_before_open_performs_no_os_or_flock_calls(lock_case):
    root, _lock, fcntl = lock_case
    now = [0.0]
    deadline = Deadline.after(1.0, clock=lambda: now[0])
    now[0] = 1.0
    attempted = []

    def forbidden(*_args, **_kwargs):
        attempted.append(True)
        raise AssertionError("expired acquisition must not perform I/O")

    with pytest.MonkeyPatch.context() as guard:
        for name in (
            "open",
            "stat",
            "lstat",
            "fstat",
            "close",
            "read",
            "write",
            "mkdir",
            "makedirs",
            "unlink",
            "remove",
            "rename",
            "replace",
            "listdir",
            "scandir",
            "readlink",
            "chmod",
            "truncate",
            "ftruncate",
            "fsync",
            "fdopen",
        ):
            guard.setattr(os, name, forbidden)
        guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {forbidden})
        guard.setattr(
            os,
            "supports_follow_symlinks",
            os.supports_follow_symlinks | {forbidden},
        )
        guard.setattr(fcntl, "flock", forbidden)
        result = transport.acquire_existing_lifecycle_lock(
            str(root), deadline=deadline, sleep=forbidden
        )
    assert result is None
    assert attempted == []
