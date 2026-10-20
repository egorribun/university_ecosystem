"""Initial existing-lock capability tests, not runtime admission."""

from __future__ import annotations

import importlib
import os
from collections import Counter
from types import ModuleType

import pytest

from scripts import live_nats_transport as transport
from scripts import live_stand
from scripts.owned_nats_coordinator import OwnerEvidence
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


def _exercise_cleanup_fault(
    root,
    fcntl,
    deadline,
    observations,
    *,
    fault_stage,
    cleanup_error,
    primary_error=None,
):
    real_open, real_close = os.open, os.close
    guarded_flock = fcntl.flock
    real_identity = transport._lifecycle_leaf_identity
    opened, close_attempts, closed, unlocks, faults = [], [], [], [], []
    live_fds = set()
    identity_calls = []
    observations.update(
        opened=opened,
        close_attempts=close_attempts,
        closed=closed,
        unlocks=unlocks,
        faults=faults,
        identity_calls=identity_calls,
    )

    def inject(stage, fd):
        if stage == fault_stage and fd == opened[-1] and not faults:
            faults.append((stage, fd))
            raise cleanup_error

    def traced_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(fd)
        live_fds.add(fd)
        return fd

    def traced_close(fd):
        close_attempts.append(fd)
        inject("before_close", fd)
        real_close(fd)
        live_fds.remove(fd)
        closed.append(fd)
        inject("after_close", fd)

    def traced_flock(fd, operation):
        if operation == fcntl.LOCK_UN:
            unlocks.append(fd)
            inject("before_unlock", fd)
        result = guarded_flock(fd, operation)
        if operation == fcntl.LOCK_UN:
            inject("after_unlock", fd)
        return result

    def traced_identity(*args, **kwargs):
        identity = real_identity(*args, **kwargs)
        identity_calls.append(identity)
        if len(identity_calls) == 2 and primary_error is not None:
            raise primary_error
        return identity

    try:
        with pytest.MonkeyPatch.context() as guard:
            guard.setattr(os, "open", traced_open)
            guard.setattr(os, "close", traced_close)
            guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {traced_open})
            guard.setattr(fcntl, "flock", traced_flock)
            guard.setattr(transport, "_lifecycle_leaf_identity", traced_identity)
            lease = _acquire(root, deadline)
            assert lease is not None
            return transport.release_lifecycle_lock(lease, deadline=deadline)
    finally:
        observations["unclosed_fds"] = sorted(live_fds)
        # Only test-owned descriptors remain here. Instrumentation is gone,
        # and no new descriptor has been opened since acquisition.
        for fd in sorted(live_fds):
            real_close(fd)


def _assert_cleanup_fault_attempts(observations, fault_stage):
    opened = observations["opened"]
    assert len(opened) >= 2
    assert len(observations["identity_calls"]) == 2
    assert observations["unlocks"] == [opened[-1]]
    assert observations["faults"] == [(fault_stage, opened[-1])]
    assert observations["close_attempts"] == list(reversed(opened))
    assert Counter(observations["close_attempts"]) == Counter(opened)


@pytest.mark.parametrize("released", [False, True], ids=["unreleased", "released"])
@pytest.mark.parametrize("error_type", [OSError, SystemExit])
def test_unlock_fault_still_attempts_each_close_once(lock_case, released, error_type):
    root, lock, fcntl = lock_case
    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    observations = {}
    fault_stage = "after_unlock" if released else "before_unlock"
    cleanup_error = error_type("synthetic unlock failure")

    if error_type is OSError:
        result = _exercise_cleanup_fault(
            root,
            fcntl,
            deadline,
            observations,
            fault_stage=fault_stage,
            cleanup_error=cleanup_error,
        )
        assert result is False
    else:
        with pytest.raises(SystemExit) as caught:
            _exercise_cleanup_fault(
                root,
                fcntl,
                deadline,
                observations,
                fault_stage=fault_stage,
                cleanup_error=cleanup_error,
            )
        assert caught.value is cleanup_error

    _assert_cleanup_fault_attempts(observations, fault_stage)
    assert observations["closed"] == list(reversed(observations["opened"]))
    assert observations["unclosed_fds"] == []
    _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)


@pytest.mark.parametrize("released", [False, True], ids=["unreleased", "released"])
@pytest.mark.parametrize("error_type", [OSError, SystemExit])
def test_close_fault_is_not_retried_and_later_closes_continue(
    lock_case, released, error_type
):
    root, lock, fcntl = lock_case
    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    observations = {}
    fault_stage = "after_close" if released else "before_close"
    cleanup_error = error_type("synthetic close failure")

    if error_type is OSError:
        result = _exercise_cleanup_fault(
            root,
            fcntl,
            deadline,
            observations,
            fault_stage=fault_stage,
            cleanup_error=cleanup_error,
        )
        assert result is False
    else:
        with pytest.raises(SystemExit) as caught:
            _exercise_cleanup_fault(
                root,
                fcntl,
                deadline,
                observations,
                fault_stage=fault_stage,
                cleanup_error=cleanup_error,
            )
        assert caught.value is cleanup_error

    _assert_cleanup_fault_attempts(observations, fault_stage)
    opened = observations["opened"]
    expected_closed = list(reversed(opened if released else opened[:-1]))
    assert observations["closed"] == expected_closed
    assert observations["unclosed_fds"] == ([] if released else [opened[-1]])
    _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)


@pytest.mark.parametrize("released", [False, True], ids=["unreleased", "released"])
@pytest.mark.parametrize("operation", ["unlock", "close"])
def test_primary_interrupt_survives_cleanup_interrupt(lock_case, released, operation):
    root, lock, fcntl = lock_case
    deadline = Deadline.after(10.0, clock=lambda: 0.0)
    observations = {}
    primary_error = KeyboardInterrupt("synthetic revalidation interruption")
    cleanup_error = SystemExit("synthetic cleanup interruption")
    fault_stage = f"{'after' if released else 'before'}_{operation}"

    with pytest.raises(KeyboardInterrupt) as caught:
        _exercise_cleanup_fault(
            root,
            fcntl,
            deadline,
            observations,
            fault_stage=fault_stage,
            cleanup_error=cleanup_error,
            primary_error=primary_error,
        )

    assert caught.value is primary_error
    _assert_cleanup_fault_attempts(observations, fault_stage)
    opened = observations["opened"]
    leaves_open = operation == "close" and not released
    expected_closed = list(reversed(opened[:-1] if leaves_open else opened))
    assert observations["closed"] == expected_closed
    assert observations["unclosed_fds"] == ([opened[-1]] if leaves_open else [])
    _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)


@pytest.mark.parametrize(
    "scenario",
    (
        "contention-deadline",
        "contention-release",
        "post-flock-expiry",
        "replace-lock",
        "replace-root",
        "replace-ancestor",
    ),
)
def test_contention_and_post_acquisition_races_clean_original_inode(
    lock_case, scenario
):
    base, _fixture_lock, fcntl = lock_case
    ancestor = base / "ancestor"
    ancestor.mkdir()
    root = ancestor / "run-lock"
    root.mkdir()
    lock = ancestor / f".{root.name}.lifecycle.lock"
    lock.touch(mode=0o600)

    replacement = base / "replacement"
    displaced = base / "displaced"
    target = None
    if scenario == "replace-lock":
        replacement.touch(mode=0o600)
        target = lock
    elif scenario == "replace-root":
        replacement.mkdir()
        target = root
    elif scenario == "replace-ancestor":
        replacement.mkdir()
        (replacement / root.name).mkdir()
        (replacement / lock.name).touch(mode=0o600)
        target = ancestor

    real_open, real_close = os.open, os.close
    # Retains lock_case's exact-operation guard for every real flock below.
    real_flock = fcntl.flock
    ex_nb = fcntl.LOCK_EX | fcntl.LOCK_NB
    sh_nb = fcntl.LOCK_SH | fcntl.LOCK_NB
    independent = []
    independent_closed = []
    opened, closed, unlocks, sleeps = [], [], [], []
    attempts = 0
    acquired = 0
    now = [0.0]
    cap = 0.125
    deadline = Deadline.after(cap, clock=lambda: now[0])
    contended = scenario.startswith("contention-")
    attempt_limit = (
        3
        if scenario == "contention-deadline"
        else 2
        if scenario == "contention-release"
        else 1
    )

    def independent_open():
        fd = real_open(lock, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        independent.append(fd)
        return fd

    def identity(fd):
        info = os.fstat(fd)
        return info.st_dev, info.st_ino

    def traced_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(fd)
        return fd

    def traced_close(fd):
        closed.append(fd)
        return real_close(fd)

    def bounded_sleep(seconds):
        assert contended, "uncontended acquisition must not sleep"
        sleep_limit = 3 if scenario == "contention-deadline" else 1
        assert len(sleeps) < sleep_limit, "retry sleep exceeded the test budget"
        assert 0.0 < seconds <= min(0.05, cap - now[0])
        sleeps.append(seconds)
        now[0] += seconds
        if scenario == "contention-release":
            real_flock(holder, fcntl.LOCK_UN)

    def traced_flock(fd, operation):
        nonlocal attempts, acquired
        if operation == fcntl.LOCK_UN:
            unlocks.append(fd)
            return real_flock(fd, operation)

        assert operation == ex_nb
        # Assert BEFORE the real syscall, including on busy-loop regressions.
        assert attempts < attempt_limit, "flock retry exceeded the test budget"
        attempts += 1
        real_flock(fd, operation)
        acquired += 1

        # This separate open-file description must see the actual EX lock.
        with pytest.raises(BlockingIOError):
            real_flock(witness, sh_nb)

        if scenario == "post-flock-expiry":
            now[0] = cap
        elif target is not None:
            target.rename(displaced)
            replacement.rename(target)

    try:
        holder = independent_open()
        witness = independent_open()
        original_identity = identity(holder)
        assert identity(witness) == original_identity
        if contended:
            real_flock(holder, ex_nb)

        lease = None
        released = None
        with pytest.MonkeyPatch.context() as guard:
            guard.setattr(os, "open", traced_open)
            guard.setattr(os, "close", traced_close)
            guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {traced_open})
            guard.setattr(fcntl, "flock", traced_flock)
            try:
                # _acquire intentionally uses _no_sleep, so do not use it here.
                lease = transport.acquire_existing_lifecycle_lock(
                    str(root), deadline=deadline, sleep=bounded_sleep
                )
                if scenario == "contention-release":
                    assert lease is not None
                    assert closed == []
                    with pytest.raises(BlockingIOError):
                        real_flock(witness, sh_nb)
                else:
                    assert lease is None
            finally:
                if lease is not None:
                    released = transport.release_lifecycle_lock(
                        lease, deadline=deadline
                    )

        assert attempts == attempt_limit
        assert opened
        assert closed == list(reversed(opened))
        assert Counter(closed) == Counter(opened)

        if scenario == "contention-deadline":
            assert acquired == 0
            assert unlocks == []
            assert sleeps == pytest.approx([0.05, 0.05, 0.025])
            assert now[0] == cap
            # Refusal must not unlock the independent holder.
            with pytest.raises(BlockingIOError):
                real_flock(witness, sh_nb)
            real_flock(holder, fcntl.LOCK_UN)
        else:
            assert acquired == 1
            assert unlocks == [opened[-1]]
            if scenario == "contention-release":
                assert sleeps == [0.05]
                assert now[0] == 0.05
                assert released is True
            else:
                assert sleeps == []
                assert now[0] == (cap if scenario == "post-flock-expiry" else 0.0)

        assert identity(holder) == original_identity
        assert identity(witness) == original_identity
        if scenario in {"replace-lock", "replace-ancestor"}:
            current = lock.stat()
            assert (current.st_dev, current.st_ino) != original_identity

        # Probe the ORIGINAL inode, not merely the new pathname.
        real_flock(witness, ex_nb)
        real_flock(witness, fcntl.LOCK_UN)
    finally:
        # On a regression, close only still-unclosed test-owned descriptors.
        # Keep these rescue attempts separate from the production-close oracle.
        for fd in reversed(opened):
            if fd not in closed:
                real_close(fd)
        for fd in reversed(independent):
            independent_closed.append(fd)
            real_close(fd)

    assert independent_closed == list(reversed(independent))
    assert Counter(closed + independent_closed) == Counter(opened + independent)


def _revalidation_lease_snapshot(lease):
    return (
        id(lease._opened_fds),
        tuple(lease._opened_fds),
        lease._unlock,
        lease._released,
    )


def _revalidation_fd_snapshot(fd):
    info = os.fstat(fd)
    # Ancestor directory timestamps may change due to unrelated runner work.
    return info.st_dev, info.st_ino, info.st_mode


@pytest.mark.parametrize(
    "scenario",
    (
        "unchanged",
        "released",
        "wrong-raw-pin",
        "replace-root",
        "replace-ancestor",
        "replace-lock",
        "expired-before",
        "expired-after-fstat",
    ),
)
def test_retained_lease_revalidation_preserves_cleanup_ownership(lock_case, scenario):
    base, _fixture_lock, fcntl = lock_case
    ancestor = base / "revalidation-parent"
    ancestor.mkdir()
    root = ancestor / "run-lock"
    root.mkdir()
    lock = ancestor / f".{root.name}.lifecycle.lock"
    lock.touch(mode=0o600)
    displaced = base / "revalidation-displaced"

    real_open, real_stat, real_fstat = os.open, os.stat, os.fstat
    real_close, guarded_flock = os.close, fcntl.flock
    opened, observations, violations = [], [], []
    now = [0.0]
    deadline = Deadline.after(1.0, clock=lambda: now[0])
    cleanup_deadline = Deadline.after(10.0, clock=lambda: 0.0)
    no_io = scenario in {"released", "wrong-raw-pin", "expired-before"}
    lease = None
    witness = None
    recycled = None

    def traced_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append((path, flags, dir_fd, fd))
        return fd

    def forbidden(*_args, **_kwargs):
        violations.append("forbidden operation")
        raise AssertionError("revalidation must not consume or mutate the lease")

    def observed_fstat(fd):
        observations.append(("fstat", fd))
        if no_io or now[0] >= 1.0 or fd not in retained_fds:
            violations.append("unexpected fstat")
            raise AssertionError("unexpected descriptor observation")
        info = real_fstat(fd)
        if scenario == "expired-after-fstat":
            now[0] = 1.0
        return info

    def observed_stat(path, *, dir_fd=None, follow_symlinks=True):
        observations.append(("stat", path, dir_fd))
        if (
            no_io
            or now[0] >= 1.0
            or (path, dir_fd) not in retained_entries
            or follow_symlinks is not False
        ):
            violations.append("unexpected stat")
            raise AssertionError("namespace checks must be retained and nofollow")
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=False)

    try:
        # This separate open-file description survives every rename below.
        witness = real_open(lock, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        original_identity = _revalidation_fd_snapshot(witness)[:2]
        with pytest.MonkeyPatch.context() as guard:
            guard.setattr(os, "open", traced_open)
            guard.setattr(os, "supports_dir_fd", os.supports_dir_fd | {traced_open})
            lease = _acquire(root, deadline)
        assert lease is not None
        assert opened
        retained_fds = {entry[3] for entry in opened}
        retained_entries = {(entry[0], entry[2]) for entry in opened[1:]}
        assert _revalidation_fd_snapshot(opened[-1][3])[:2] == original_identity

        if scenario == "replace-root":
            root.rename(displaced)
            root.mkdir()
            assert root.stat().st_ino != displaced.stat().st_ino
        elif scenario == "replace-ancestor":
            ancestor.rename(displaced)
            ancestor.mkdir()
            root.mkdir()
            lock.touch(mode=0o600)
            assert ancestor.stat().st_ino != displaced.stat().st_ino
        elif scenario == "replace-lock":
            lock.rename(displaced)
            lock.touch(mode=0o600)
            assert _snapshot(lock)[:2] != original_identity
        elif scenario == "released":
            assert transport.release_lifecycle_lock(lease, deadline=deadline) is True
            recycled = real_open(lock, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            assert recycled in retained_fds, "exercise actual descriptor reuse"
            guarded_flock(recycled, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif scenario == "expired-before":
            now[0] = 1.0

        watched_fds = [recycled] if recycled is not None else list(retained_fds)
        descriptor_before = {fd: _revalidation_fd_snapshot(fd) for fd in watched_fds}
        lease_before = _revalidation_lease_snapshot(lease)
        paths = (ancestor, root, lock, displaced)
        entries_before = tuple(_entry_metadata(path) for path in paths)
        lock_before = _snapshot(lock)
        pin = str(root) + "/" if scenario == "wrong-raw-pin" else str(root)
        results = []

        with pytest.MonkeyPatch.context() as guard:
            for name in (
                "open",
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
                "lstat",
                "chmod",
                "truncate",
                "ftruncate",
                "fsync",
                "fdopen",
            ):
                guard.setattr(os, name, forbidden)
            guard.setattr(os, "fstat", observed_fstat)
            guard.setattr(os, "stat", observed_stat)
            guard.setattr(
                os,
                "supports_dir_fd",
                os.supports_dir_fd | {forbidden, observed_stat},
            )
            guard.setattr(
                os,
                "supports_follow_symlinks",
                os.supports_follow_symlinks | {observed_stat},
            )
            guard.setattr(fcntl, "flock", forbidden)
            guard.setattr("builtins.open", forbidden)
            guard.setattr("io.open", forbidden)
            guard.setattr(transport, "read_signed_owner_v11_from_state", forbidden)
            for _ in range(2 if scenario == "unchanged" else 1):
                results.append(
                    transport.revalidate_lifecycle_lock(
                        lease, pinned_state_root=pin, deadline=deadline
                    )
                )

        assert violations == []
        assert _revalidation_lease_snapshot(lease) == lease_before
        assert {
            fd: _revalidation_fd_snapshot(fd) for fd in watched_fds
        } == descriptor_before
        assert tuple(_entry_metadata(path) for path in paths) == entries_before
        assert _snapshot(lock) == lock_before
        assert _revalidation_fd_snapshot(witness)[:2] == original_identity

        # Both probes target the ORIGINAL inode, not a replacement pathname.
        for operation in (fcntl.LOCK_SH, fcntl.LOCK_EX):
            with pytest.raises(BlockingIOError):
                guarded_flock(witness, operation | fcntl.LOCK_NB)
        if scenario in {"replace-lock", "replace-ancestor"}:
            _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)

        if scenario == "unchanged":
            assert results == [True, True]
            expected = []
            for name, _flags, parent_fd, fd in opened[1:]:
                expected.extend([("fstat", fd), ("stat", name, parent_fd)])
            assert observations == expected * 2
        else:
            assert results == [False]
            if no_io:
                assert observations == []
            elif scenario == "expired-after-fstat":
                assert observations == [("fstat", opened[1][3])]
    finally:
        # No revalidation instrumentation is active during caller-owned cleanup.
        try:
            if lease is not None:
                transport.release_lifecycle_lock(lease, deadline=cleanup_deadline)
        finally:
            try:
                if recycled is not None:
                    real_close(recycled)
            finally:
                if witness is not None:
                    real_close(witness)


@pytest.fixture
def leased_owner_case(lock_case):
    root, lock, fcntl = lock_case
    now = [0.0]
    deadline = Deadline.after(10.0, clock=lambda: now[0])
    assert deadline.expires_at is not None
    lease = _acquire(root, deadline)
    assert lease is not None

    pins = {
        "pinned_repository": str(root.parent / "repository"),
        "pinned_state_root": str(root),
        "pinned_source_sha": "a" * 40,
    }
    ports = {
        name: 20_000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    owner = OwnerEvidence(
        repository=pins["pinned_repository"],
        worktree=pins["pinned_state_root"],
        project_name="ue-live-0123456789abcdef",
        published_ports=live_stand._validate_published_ports(ports),
        schema_version=11,
        daemon_fingerprint="1" * 64,
        compose_resource_fingerprint="2" * 64,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha=pins["pinned_source_sha"],
        stack="core",
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )
    signed = transport.OwnerParseResult(
        transport.OwnerParseStatus.SIGNED_METADATA, owner
    )
    case = {
        "lease": lease,
        "pins": pins,
        "deadline": deadline,
        "now": now,
        "signed": signed,
        "read_result": signed,
        "events": [],
        "post_drift": False,
        "expire_after_read": False,
        "raise_at": None,
        "error": None,
    }
    real_revalidate = transport.revalidate_lifecycle_lock
    real_release = transport.release_lifecycle_lock
    forbidden_calls = []

    def forbidden(*_args, **_kwargs):
        forbidden_calls.append(True)
        raise AssertionError(
            "composition must not own lifecycle, launch processes, or mutate state"
        )

    def revalidate(candidate, *, pinned_state_root, deadline):
        assert deadline is case["deadline"]
        assert pinned_state_root == case["pins"]["pinned_state_root"]
        stage = "before" if not case["events"] else "after"
        case["events"].append(stage)
        if case["raise_at"] == stage:
            raise case["error"]
        valid = real_revalidate(
            candidate,
            pinned_state_root=pinned_state_root,
            deadline=deadline,
        )
        return valid and not (stage == "after" and case["post_drift"])

    def read(*, pinned_repository, pinned_state_root, pinned_source_sha, deadline):
        assert deadline is case["deadline"]
        assert {
            "pinned_repository": pinned_repository,
            "pinned_state_root": pinned_state_root,
            "pinned_source_sha": pinned_source_sha,
        } == case["pins"]
        case["events"].append("read")
        if case["raise_at"] == "read":
            raise case["error"]
        if case["expire_after_read"]:
            now[0] = deadline.expires_at
        return case["read_result"]

    try:
        with pytest.MonkeyPatch.context() as guard:
            guard.setattr(transport, "revalidate_lifecycle_lock", revalidate)
            guard.setattr(transport, "read_signed_owner_v11_from_state", read)
            guard.setattr(transport, "acquire_existing_lifecycle_lock", forbidden)
            guard.setattr(transport, "release_lifecycle_lock", forbidden)
            guard.setattr("scripts.owned_nats_process.run_private_process", forbidden)
            guard.setattr("subprocess.Popen", forbidden)
            guard.setattr("subprocess.run", forbidden)
            for name in (
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
            ):
                guard.setattr(os, name, forbidden)
            case["release_for_test"] = real_release
            yield case
            assert forbidden_calls == []
            if not lease._released:
                _probe(lock, fcntl, fcntl.LOCK_EX, blocked=True)
    finally:
        if not lease._released:
            cleanup = Deadline.after(10.0, clock=lambda: 0.0)
            assert real_release(lease, deadline=cleanup)
        _probe(lock, fcntl, fcntl.LOCK_EX, blocked=False)


def _read_leased(case, *, lease=None):
    return transport.read_signed_owner_v11_under_lease(
        case["lease"] if lease is None else lease,
        **case["pins"],
        deadline=case["deadline"],
    )


def _leased_not_ready(result):
    assert result.status is transport.OwnerParseStatus.NOT_READY
    assert result.owner is None


def test_leased_owner_returns_signed_metadata_after_both_checks(leased_owner_case):
    case = leased_owner_case

    result = _read_leased(case)

    assert result == case["signed"]
    assert result.owner is not None
    assert case["events"] == ["before", "read", "after"]
    assert case["lease"]._released is False


@pytest.mark.parametrize("kind", ["invalid", "released", "wrong-root"])
def test_leased_owner_invalid_lease_prevents_read(leased_owner_case, kind):
    case = leased_owner_case
    candidate = case["lease"]
    if kind == "invalid":
        candidate = object()
    elif kind == "released":
        assert case["release_for_test"](candidate, deadline=case["deadline"])
    else:
        case["pins"]["pinned_state_root"] += "-other"

    _leased_not_ready(_read_leased(case, lease=candidate))

    assert "read" not in case["events"]
    assert "after" not in case["events"]
    if kind != "released":
        assert case["lease"]._released is False


def test_leased_owner_reader_rejection_stays_not_ready(leased_owner_case):
    case = leased_owner_case
    case["read_result"] = transport.OwnerParseResult(
        transport.OwnerParseStatus.NOT_READY
    )

    _leased_not_ready(_read_leased(case))

    assert case["events"][:2] == ["before", "read"]
    # Early failure may omit the second observation; it must never retry.
    assert case["events"] in (
        ["before", "read"],
        ["before", "read", "after"],
    )
    assert case["lease"]._released is False


def test_leased_owner_initial_expiry_prevents_read(leased_owner_case):
    case = leased_owner_case
    case["now"][0] = case["deadline"].expires_at

    _leased_not_ready(_read_leased(case))

    assert "read" not in case["events"]
    assert case["lease"]._released is False


def test_leased_owner_post_read_drift_rejects_signed_result(leased_owner_case):
    case = leased_owner_case
    case["post_drift"] = True

    _leased_not_ready(_read_leased(case))

    assert case["events"] == ["before", "read", "after"]
    assert case["lease"]._released is False


def test_leased_owner_post_read_expiry_rejects_signed_result(leased_owner_case):
    case = leased_owner_case
    case["expire_after_read"] = True

    _leased_not_ready(_read_leased(case))

    assert case["events"][:2] == ["before", "read"]
    assert case["events"] in (
        ["before", "read"],
        ["before", "read", "after"],
    )
    assert case["lease"]._released is False


@pytest.mark.parametrize("stage", ["before", "read", "after"])
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_leased_owner_propagates_without_consuming_lease(
    leased_owner_case, stage, error_type
):
    case = leased_owner_case
    error = error_type("synthetic private composition failure")
    case["raise_at"] = stage
    case["error"] = error

    with pytest.raises(error_type) as caught:
        _read_leased(case)

    assert caught.value is error
    expected = ["before", "read", "after"]
    assert case["events"] == expected[: expected.index(stage) + 1]
    assert case["lease"]._released is False
