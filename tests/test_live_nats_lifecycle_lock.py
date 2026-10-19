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
def lock_case(tmp_path, monkeypatch):
    """Require real POSIX primitives on the hosted Ubuntu contract runner."""
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC")
    assert _fcntl is not None, "this contract requires fcntl"
    assert os.name == "posix", "this contract requires a POSIX host"
    assert all(getattr(os, name, 0) > 0 for name in required)
    assert os.open in os.supports_dir_fd
    assert os.stat in os.supports_dir_fd
    assert os.stat in os.supports_follow_symlinks
    real_flock = _fcntl.flock
    allowed = {
        _fcntl.LOCK_UN,
        _fcntl.LOCK_SH | _fcntl.LOCK_NB,
        _fcntl.LOCK_EX | _fcntl.LOCK_NB,
    }

    def nonblocking(fd, operation):
        assert operation in allowed, "blocking or malformed flock is forbidden"
        return real_flock(fd, operation)

    monkeypatch.setattr(_fcntl, "flock", nonblocking)
    root = tmp_path.resolve() / "run-lock"
    root.mkdir()
    lock = root.parent / f".{root.name}.lifecycle.lock"
    lock.touch(mode=0o600)
    return root, lock, _fcntl


def _no_sleep(_seconds):
    raise AssertionError("uncontended acquisition must not sleep")


def _acquire(root, deadline):
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
    lease = _acquire(root, deadline)
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
    root, lock, _lock_api = lock_case
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
        lease = _acquire(root, deadline)
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


@pytest.mark.parametrize("expired", [False, True])
def test_release_closes_once_even_expired_and_never_touches_reused_fd(
    lock_case, expired
):
    root, lock, fcntl = lock_case
    now = [0.0]
    deadline = Deadline.after(1.0, clock=lambda: now[0])
    real_open, real_close, real_flock = os.open, os.close, fcntl.flock
    opened, events = [], []
    repeated = False

    def traced_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(fd)
        return fd

    def traced_close(fd):
        assert not repeated, "repeated release must not close any descriptor"
        events.append(("close", fd))
        return real_close(fd)

    def traced_flock(fd, operation):
        assert not repeated, "repeated release must not operate on a reused fd"
        events.append(("flock", fd, operation))
        return real_flock(fd, operation)

    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(os, "open", traced_open)
        guard.setattr(os, "close", traced_close)
        guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {traced_open})
        guard.setattr(fcntl, "flock", traced_flock)
        lease = _acquire(root, deadline)
        assert lease is not None
        assert opened

        events.clear()
        if expired:
            now[0] = 1.0
        released = transport.release_lifecycle_lock(lease, deadline=deadline)
        assert released is (not expired)
        expected = [
            ("flock", opened[-1], fcntl.LOCK_UN),
            *(("close", fd) for fd in reversed(opened)),
        ]
        assert events == expected

        # Bypass tracing for the independent owner of the recycled descriptor.
        reused_fd = real_open(lock, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            assert reused_fd in opened, "the oracle must exercise actual fd reuse"
            real_flock(reused_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = os.fstat(reused_fd)
            repeated = True
            assert transport.release_lifecycle_lock(lease, deadline=deadline) is False
            assert events == expected
            after = os.fstat(reused_fd)
            assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
        finally:
            real_close(reused_fd)

    _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)


def _entry_metadata(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


@pytest.mark.parametrize(
    "obstacle",
    ("missing-lock", "symlink-root", "symlink-lock", "fifo-lock"),
)
def test_unsafe_lock_paths_refuse_without_mutation(lock_case, obstacle):
    root, lock, _lock_api = lock_case
    target = root.with_name("original-entry")
    if obstacle == "missing-lock":
        lock.unlink()
    elif obstacle == "symlink-root":
        root.rename(target)
        root.symlink_to(target, target_is_directory=True)
    elif obstacle == "symlink-lock":
        lock.rename(target)
        lock.symlink_to(target)
    else:
        lock.unlink()
        os.mkfifo(lock, mode=0o600)

    paths = (root, lock, target)
    before = tuple(_entry_metadata(path) for path in paths)
    regular = target if obstacle == "symlink-lock" else lock
    content_before = (
        _snapshot(regular) if obstacle in {"symlink-root", "symlink-lock"} else None
    )
    real_open, real_close = os.open, os.close
    opened, closed, violations = [], [], []
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    leaf_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC

    def guarded_open(path, flags, mode=0o777, *, dir_fd=None):
        if flags not in {directory_flags, leaf_flags}:
            violations.append("unsafe open flags")
            raise AssertionError("unsafe open flags")
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(fd)
        return fd

    def traced_close(fd):
        closed.append(fd)
        return real_close(fd)

    def forbidden(*_args, **_kwargs):
        violations.append("unexpected read or mutation")
        raise AssertionError("lock refusal must not read or mutate files")

    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(os, "open", guarded_open)
        guard.setattr(os, "close", traced_close)
        guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {guarded_open})
        for name in (
            "read",
            "write",
            "mkdir",
            "makedirs",
            "unlink",
            "remove",
            "rename",
            "replace",
            "chmod",
            "truncate",
            "ftruncate",
            "fsync",
            "fdopen",
        ):
            guard.setattr(os, name, forbidden)
        lease = _acquire(root, deadline)
        if lease is not None:
            transport.release_lifecycle_lock(lease, deadline=deadline)

    assert lease is None
    assert violations == []
    assert Counter(closed) == Counter(opened)
    assert tuple(_entry_metadata(path) for path in paths) == before
    if content_before is not None:
        assert _snapshot(regular) == content_before


@pytest.mark.parametrize(
    "capability",
    ("nofollow-flag", "descriptor-relative", "nofollow-stat"),
)
def test_unsupported_lock_capability_refuses_before_io(capability):
    attempted = []

    def forbidden(*_args, **_kwargs):
        attempted.append(True)
        raise AssertionError("unsupported acquisition must not perform I/O")

    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    with pytest.MonkeyPatch.context() as guard:
        # Keep wrappers advertised as supported except for the capability
        # deliberately removed by this case.
        relative = set(getattr(os, "supports_dir_fd", ()))
        nofollow = set(getattr(os, "supports_follow_symlinks", ()))
        relative.add(forbidden)
        nofollow.add(forbidden)
        guard.setattr(os, "supports_dir_fd", relative, raising=False)
        guard.setattr(os, "supports_follow_symlinks", nofollow, raising=False)
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
        if _fcntl is not None:
            guard.setattr(_fcntl, "flock", forbidden)
        if capability == "nofollow-flag":
            guard.setattr(os, "O_NOFOLLOW", 0, raising=False)
        elif capability == "descriptor-relative":
            guard.setattr(os, "supports_dir_fd", set())
        else:
            guard.setattr(os, "supports_follow_symlinks", set())
        result = transport.acquire_existing_lifecycle_lock(
            "/unsupported-lock-contract",
            deadline=deadline,
            sleep=forbidden,
        )

    assert result is None
    assert attempted == []
