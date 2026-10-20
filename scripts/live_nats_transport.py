"""Signed Core metadata boundaries for a future bounded NATS transport.

The parser call performs no filesystem, lock, Docker, HTTP or database work.
It is not connected to the coordinator or CLI. Importing the existing live_stand
module retains that module's ordinary repository-path initialization.
A parsed claim is conditional on trusted caller-supplied key bytes and pins;
it does not establish file provenance or observe the current Docker daemon.
"""

from __future__ import annotations

import errno
import hmac
import importlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from scripts import live_stand
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline, DeadlineVerdict

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

MAX_OWNER_MARKER_BYTES = 65_536
_V11_OWNER_KEYS = frozenset(
    {
        "version",
        "repository",
        "worktree",
        "project_name",
        "signature",
        "published_ports",
        "daemon_fingerprint",
        "compose_resource_fingerprint",
        "resume_compose_resource_fingerprint",
        "resume_compose_resource_schema_version",
        "stack",
        "service_roots",
        "selected_services",
        "source_sha",
    }
)
_SOURCE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_HEX_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


class OwnerParseStatus(StrEnum):
    NOT_READY = "not_ready"
    SIGNED_METADATA = "signed_metadata"


@dataclass(frozen=True, slots=True)
class OwnerParseResult:
    status: OwnerParseStatus
    owner: OwnerEvidence | None = field(default=None, repr=False)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _absolute_pin(value: object) -> bool:
    # Lexical only: do not resolve, stat, or open paths.
    return type(value) is str and bool(value) and Path(value).is_absolute()


def parse_signed_owner_v11(
    marker_bytes: bytes,
    key_bytes: bytes,
    *,
    pinned_repository: str,
    pinned_state_root: str,
    pinned_source_sha: str,
) -> OwnerParseResult:
    """Parse bounded v11 bytes without inferring file or runtime ownership."""
    not_ready = OwnerParseResult(OwnerParseStatus.NOT_READY)
    try:
        if (
            type(marker_bytes) is not bytes
            or len(marker_bytes) > MAX_OWNER_MARKER_BYTES
            or type(key_bytes) is not bytes
            or len(key_bytes) != 32
            or not _absolute_pin(pinned_repository)
            or not _absolute_pin(pinned_state_root)
            or type(pinned_source_sha) is not str
            or _SOURCE_SHA_PATTERN.fullmatch(pinned_source_sha) is None
        ):
            return not_ready

        data = json.loads(
            marker_bytes.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
        if type(data) is not dict or set(data) != _V11_OWNER_KEYS:
            return not_ready
        if type(data["version"]) is not int or data["version"] != 11:
            return not_ready

        string_fields = (
            "repository",
            "worktree",
            "project_name",
            "signature",
            "daemon_fingerprint",
            "compose_resource_fingerprint",
            "stack",
            "source_sha",
        )
        if any(type(data[name]) is not str for name in string_fields):
            return not_ready
        if (
            data["repository"] != pinned_repository
            or data["worktree"] != pinned_state_root
            or data["source_sha"] != pinned_source_sha
        ):
            return not_ready

        live_stand._validate_project_name(data["project_name"])
        raw_ports = data["published_ports"]
        if type(raw_ports) is not dict or any(
            type(port) is not int for port in raw_ports.values()
        ):
            return not_ready
        ports = dict(live_stand._validate_published_ports(raw_ports))

        fingerprint_fields = (
            "daemon_fingerprint",
            "compose_resource_fingerprint",
            "signature",
        )
        if any(
            _HEX_FINGERPRINT_PATTERN.fullmatch(data[name]) is None
            for name in fingerprint_fields
        ):
            return not_ready
        if (
            data["resume_compose_resource_fingerprint"] is not None
            or data["resume_compose_resource_schema_version"] is not None
            or data["stack"] != live_stand.LIVE_STACK_CORE
            or type(data["service_roots"]) is not list
            or data["service_roots"] != list(live_stand.LIVE_CORE_SERVICE_ROOTS)
            or type(data["selected_services"]) is not list
            or data["selected_services"] != list(live_stand.LIVE_CORE_EXPECTED_SERVICES)
        ):
            return not_ready

        # Match the existing loader's validated, normalized canonical payload.
        payload = {key: value for key, value in data.items() if key != "signature"}
        payload["published_ports"] = ports
        expected_signature = live_stand._owner_signature(payload, key_bytes)
        if not hmac.compare_digest(data["signature"], expected_signature):
            return not_ready

        owner = OwnerEvidence(
            repository=pinned_repository,
            worktree=pinned_state_root,
            project_name=data["project_name"],
            published_ports=tuple(ports.items()),
            schema_version=11,
            daemon_fingerprint=data["daemon_fingerprint"],
            compose_resource_fingerprint=data["compose_resource_fingerprint"],
            resume_compose_resource_fingerprint=None,
            resume_compose_resource_schema_version=None,
            source_sha=pinned_source_sha,
            stack=live_stand.LIVE_STACK_CORE,
            service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
            selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
        )
        return OwnerParseResult(OwnerParseStatus.SIGNED_METADATA, owner)
    except (live_stand.StandError, RecursionError, TypeError, ValueError):
        return not_ready


class _ReaderNotReady(Exception):
    """Private fail-closed control flow; never exposed in a result."""


def _reader_deadline_live(deadline: Deadline) -> bool:
    return deadline.timeout_for(1.0).verdict is DeadlineVerdict.VALID


def _reader_call[T](deadline: Deadline, operation: Callable[[], T]) -> T:
    if not _reader_deadline_live(deadline):
        raise _ReaderNotReady
    result = operation()
    if not _reader_deadline_live(deadline):
        raise _ReaderNotReady
    return result


def _reader_open(
    deadline: Deadline,
    opened_fds: list[int],
    path: str,
    flags: int,
    *,
    dir_fd: int | None,
) -> int:
    if not _reader_deadline_live(deadline):
        raise _ReaderNotReady
    fd = os.open(path, flags, dir_fd=dir_fd)
    # Retain the acquired fd before a post-open expiry can interrupt the walk.
    opened_fds.append(fd)
    if not _reader_deadline_live(deadline):
        raise _ReaderNotReady
    return fd


def _reader_api_supported() -> bool:
    flags = ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC")
    if os.name != "posix" or any(
        type(getattr(os, name, None)) is not int or getattr(os, name) <= 0
        for name in flags
    ):
        return False
    relative = getattr(os, "supports_dir_fd", set())
    nofollow = getattr(os, "supports_follow_symlinks", set())
    return os.open in relative and os.stat in relative and os.stat in nofollow


def _reader_metadata(info: os.stat_result) -> tuple[int, ...]:
    # Reads can change atime without mutating the signed content.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _reader_check_directory(
    deadline: Deadline, name: str, parent_fd: int, child_fd: int
) -> None:
    info = _reader_call(deadline, lambda: os.fstat(child_fd))
    entry = _reader_call(
        deadline,
        lambda: os.stat(name, dir_fd=parent_fd, follow_symlinks=False),
    )
    if (
        not stat.S_ISDIR(info.st_mode)
        or not stat.S_ISDIR(entry.st_mode)
        or (info.st_dev, info.st_ino) != (entry.st_dev, entry.st_ino)
    ):
        raise _ReaderNotReady


def _reader_leaf_metadata(
    deadline: Deadline,
    name: str,
    parent_fd: int,
    leaf_fd: int,
    *,
    max_size: int,
    exact_size: int | None = None,
) -> tuple[int, ...]:
    info = _reader_call(deadline, lambda: os.fstat(leaf_fd))
    if (
        not stat.S_ISREG(info.st_mode)
        or not 0 <= info.st_size <= max_size
        or (exact_size is not None and info.st_size != exact_size)
    ):
        raise _ReaderNotReady
    entry = _reader_call(
        deadline,
        lambda: os.stat(name, dir_fd=parent_fd, follow_symlinks=False),
    )
    snapshot = _reader_metadata(info)
    if snapshot != _reader_metadata(entry):
        raise _ReaderNotReady
    return snapshot


def _reader_bytes(fd: int, cap: int, deadline: Deadline) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        requested = min(8_192, cap + 1 - total)
        if requested <= 0:
            raise _ReaderNotReady
        block = _reader_call(
            deadline, lambda requested=requested: os.read(fd, requested)
        )
        if not block:
            return b"".join(chunks)
        total += len(block)
        if total > cap:
            raise _ReaderNotReady
        chunks.append(block)


def read_signed_owner_v11_from_state(
    *,
    pinned_repository: str,
    pinned_state_root: str,
    pinned_source_sha: str,
    pinned_owner_uid: int,
    deadline: Deadline,
) -> OwnerParseResult:
    """Read existing fixed files into signed metadata, never runtime admission.

    Initial traversal is descriptor-relative and nofollow. Leaf checks observe
    descriptor/name metadata before and after both reads. Each ancestor edge is
    rechecked after both reads, but these observations are not an atomic file-pair
    or namespace snapshot. No lifecycle lock, key-provenance authentication or
    current daemon check is performed.
    Syscalls, including on network/FUSE mounts, cannot be hard-preempted.
    """
    # Tests-first policy input; UID/private-mode enforcement is not implemented yet.
    not_ready = OwnerParseResult(OwnerParseStatus.NOT_READY)
    if (
        type(deadline) is not Deadline
        or not _reader_api_supported()
        or not _absolute_pin(pinned_repository)
        or not _absolute_pin(pinned_state_root)
        or type(pinned_source_sha) is not str
        or _SOURCE_SHA_PATTERN.fullmatch(pinned_source_sha) is None
    ):
        return not_ready
    raw_parts = pinned_state_root.split("/")
    if "\x00" in pinned_state_root or any(part in {".", ".."} for part in raw_parts):
        return not_ready
    components = [part for part in raw_parts[1:] if part]
    if not components:
        return not_ready

    opened_fds: list[int] = []
    traversed_edges: list[tuple[str, int, int]] = []
    result = not_ready
    pending: tuple[BaseException, TracebackType | None] | None = None
    cleanup_pending: tuple[BaseException, TracebackType | None] | None = None
    cleanup_failed = False
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        parent_fd = _reader_open(
            deadline, opened_fds, "/", directory_flags, dir_fd=None
        )
        for component in [*components, ".secrets"]:
            child_fd = _reader_open(
                deadline,
                opened_fds,
                component,
                directory_flags,
                dir_fd=parent_fd,
            )
            _reader_check_directory(deadline, component, parent_fd, child_fd)
            traversed_edges.append((component, parent_fd, child_fd))
            parent_fd = child_fd
        leaf_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        marker_name = live_stand.STAND_FILE.name
        key_name = "live-stand-owner.key"
        marker_fd = _reader_open(
            deadline, opened_fds, marker_name, leaf_flags, dir_fd=parent_fd
        )
        marker_before = _reader_leaf_metadata(
            deadline, marker_name, parent_fd, marker_fd, max_size=MAX_OWNER_MARKER_BYTES
        )
        key_fd = _reader_open(
            deadline, opened_fds, key_name, leaf_flags, dir_fd=parent_fd
        )
        key_before = _reader_leaf_metadata(
            deadline, key_name, parent_fd, key_fd, max_size=32, exact_size=32
        )
        marker_bytes = _reader_bytes(marker_fd, MAX_OWNER_MARKER_BYTES, deadline)
        key_bytes = _reader_bytes(key_fd, 32, deadline)
        marker_after = _reader_leaf_metadata(
            deadline, marker_name, parent_fd, marker_fd, max_size=MAX_OWNER_MARKER_BYTES
        )
        key_after = _reader_leaf_metadata(
            deadline, key_name, parent_fd, key_fd, max_size=32, exact_size=32
        )
        if marker_before != marker_after or key_before != key_after:
            raise _ReaderNotReady
        for component, ancestor_fd, descendant_fd in traversed_edges:
            _reader_check_directory(deadline, component, ancestor_fd, descendant_fd)
        result = _reader_call(
            deadline,
            lambda: parse_signed_owner_v11(
                marker_bytes,
                key_bytes,
                pinned_repository=pinned_repository,
                pinned_state_root=pinned_state_root,
                pinned_source_sha=pinned_source_sha,
            ),
        )
    except (_ReaderNotReady, OSError, ValueError):
        result = not_ready
    except BaseException as error:
        pending = (error, error.__traceback__)
    finally:
        for fd in reversed(opened_fds):
            try:
                os.close(fd)
            except OSError:
                # EINTR can leave close outcome ambiguous; never retry the fd.
                cleanup_failed = True
            except BaseException as error:
                if cleanup_pending is None:
                    cleanup_pending = (error, error.__traceback__)

    if pending is not None:
        error, traceback = pending
        raise error.with_traceback(traceback)
    if cleanup_pending is not None:
        error, traceback = cleanup_pending
        raise error.with_traceback(traceback)
    if cleanup_failed or not _reader_deadline_live(deadline):
        return not_ready
    return result


@dataclass(slots=True, repr=False)
class LifecycleLockLease:
    """Opaque serialization lease, not ownership or runtime admission."""

    _opened_fds: list[int] = field(default_factory=list)
    _unlock: Callable[[], None] | None = None
    _released: bool = False
    _pinned_state_root: str | None = None
    _traversed_edges: tuple[tuple[str, int, int], ...] = ()
    _lock_name: str | None = None
    _lock_parent_fd: int | None = None
    _lock_fd: int | None = None
    _lock_identity: tuple[int, int] | None = None


def _lifecycle_leaf_identity(
    deadline: Deadline, name: str, parent_fd: int, lock_fd: int
) -> tuple[int, int]:
    info = _reader_call(deadline, lambda: os.fstat(lock_fd))
    entry = _reader_call(
        deadline,
        lambda: os.stat(name, dir_fd=parent_fd, follow_symlinks=False),
    )
    identity = (info.st_dev, info.st_ino)
    if (
        not stat.S_ISREG(info.st_mode)
        or not stat.S_ISREG(entry.st_mode)
        or identity != (entry.st_dev, entry.st_ino)
    ):
        raise _ReaderNotReady
    return identity


def _lifecycle_cleanup(
    lease: LifecycleLockLease, deadline: Deadline
) -> tuple[bool, tuple[BaseException, TracebackType | None] | None]:
    if lease._released:
        return False, None

    # Consume cleanup state before invoking clocks, unlock or close callbacks.
    # An ambiguous close must never be retried against a potentially reused fd.
    lease._released = True
    opened_fds, lease._opened_fds = lease._opened_fds, []
    unlock, lease._unlock = lease._unlock, None
    clean = bool(opened_fds)
    pending: tuple[BaseException, TracebackType | None] | None = None

    def observe_deadline() -> None:
        nonlocal clean, pending
        try:
            live = type(deadline) is Deadline and _reader_deadline_live(deadline)
            clean = clean and live
        except BaseException as error:
            clean = False
            if pending is None:
                pending = (error, error.__traceback__)

    def attempt(operation: Callable[[], None]) -> None:
        nonlocal clean, pending
        observe_deadline()
        try:
            operation()
        except OSError:
            clean = False
        except BaseException as error:
            clean = False
            if pending is None:
                pending = (error, error.__traceback__)
        finally:
            observe_deadline()

    observe_deadline()
    if unlock is not None:
        attempt(unlock)
    while opened_fds:
        fd = opened_fds.pop()
        attempt(lambda fd=fd: os.close(fd))
    observe_deadline()
    return clean, pending


def acquire_existing_lifecycle_lock(
    pinned_state_root: str,
    *,
    deadline: Deadline,
    sleep: Callable[[float], None],
) -> LifecycleLockLease | None:
    """Acquire the existing sibling lock without creating or modifying files.

    Traversal and revalidation are nofollow, descriptor-relative observations,
    not an atomic namespace snapshot. Flock serializes cooperating holders; it
    does not establish ownership. Syscalls and injected sleep cannot be
    hard-preempted, including on network/FUSE filesystems.
    """
    if (
        type(deadline) is not Deadline
        or not _reader_deadline_live(deadline)
        or not _reader_api_supported()
        or not _absolute_pin(pinned_state_root)
        or not callable(sleep)
    ):
        return None
    raw_parts = pinned_state_root.split("/")
    if "\x00" in pinned_state_root or any(part in {".", ".."} for part in raw_parts):
        return None
    components = [part for part in raw_parts[1:] if part]
    if not components:
        return None

    try:
        fcntl = importlib.import_module("fcntl")
    except ImportError:
        return None

    lease = LifecycleLockLease()
    traversed_edges: list[tuple[str, int, int]] = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        parent_fd = _reader_open(
            deadline, lease._opened_fds, "/", directory_flags, dir_fd=None
        )
        for component in components:
            child_fd = _reader_open(
                deadline,
                lease._opened_fds,
                component,
                directory_flags,
                dir_fd=parent_fd,
            )
            _reader_check_directory(deadline, component, parent_fd, child_fd)
            traversed_edges.append((component, parent_fd, child_fd))
            parent_fd = child_fd

        lock_parent_fd = traversed_edges[-1][1]
        lock_name = f".{components[-1]}.lifecycle.lock"
        leaf_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        lock_fd = _reader_open(
            deadline,
            lease._opened_fds,
            lock_name,
            leaf_flags,
            dir_fd=lock_parent_fd,
        )
        identity = _lifecycle_leaf_identity(
            deadline, lock_name, lock_parent_fd, lock_fd
        )

        def acquire_once() -> bool:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                    return False
                raise
            # Record success before _reader_call performs its post-call check.
            lease._unlock = lambda: fcntl.flock(lock_fd, fcntl.LOCK_UN)
            return True

        while not _reader_call(deadline, acquire_once):
            budget = deadline.timeout_for(0.05)
            if budget.verdict is not DeadlineVerdict.VALID or budget.seconds is None:
                raise _ReaderNotReady
            # This budget sample is the pre-sleep deadline check.
            sleep(budget.seconds)
            if not _reader_deadline_live(deadline):
                raise _ReaderNotReady

        for component, ancestor_fd, descendant_fd in traversed_edges:
            _reader_check_directory(deadline, component, ancestor_fd, descendant_fd)
        if identity != _lifecycle_leaf_identity(
            deadline, lock_name, lock_parent_fd, lock_fd
        ):
            raise _ReaderNotReady
        lease._pinned_state_root = pinned_state_root
        lease._traversed_edges = tuple(traversed_edges)
        lease._lock_name = lock_name
        lease._lock_parent_fd = lock_parent_fd
        lease._lock_fd = lock_fd
        lease._lock_identity = identity
        return _reader_call(deadline, lambda: lease)
    except (_ReaderNotReady, OSError, ValueError):
        pass
    except BaseException:
        # Cleanup records its own failures instead of masking this exception.
        _lifecycle_cleanup(lease, deadline)
        raise

    _clean, pending = _lifecycle_cleanup(lease, deadline)
    if pending is not None:
        error, traceback = pending
        raise error.with_traceback(traceback)
    return None


def release_lifecycle_lock(lease: LifecycleLockLease, *, deadline: Deadline) -> bool:
    """Attempt unlock and reverse-order close once, even after expiry."""
    if type(lease) is not LifecycleLockLease:
        return False
    clean, pending = _lifecycle_cleanup(lease, deadline)
    if pending is not None:
        error, traceback = pending
        raise error.with_traceback(traceback)
    return clean


def revalidate_lifecycle_lock(
    lease: LifecycleLockLease,
    *,
    pinned_state_root: str,
    deadline: Deadline,
) -> bool:
    """Observe the retained namespace without consuming or repairing the lease.

    A successful sample is not atomic namespace continuity or authentication.
    The caller owns release on both success and failure.
    """
    if (
        type(lease) is not LifecycleLockLease
        or lease._released
        or not lease._opened_fds
        or lease._unlock is None
        or type(pinned_state_root) is not str
        or pinned_state_root != lease._pinned_state_root
        or not lease._traversed_edges
        or lease._lock_name is None
        or lease._lock_parent_fd is None
        or lease._lock_fd is None
        or lease._lock_identity is None
        or type(deadline) is not Deadline
        or not _reader_deadline_live(deadline)
        or not _reader_api_supported()
    ):
        return False
    try:
        for name, parent_fd, child_fd in lease._traversed_edges:
            _reader_check_directory(deadline, name, parent_fd, child_fd)
        identity = _lifecycle_leaf_identity(
            deadline, lease._lock_name, lease._lock_parent_fd, lease._lock_fd
        )
        return identity == lease._lock_identity and _reader_deadline_live(deadline)
    except (_ReaderNotReady, OSError, ValueError):
        return False


def read_signed_owner_v11_under_lease(
    lease: LifecycleLockLease,
    *,
    pinned_repository: str,
    pinned_state_root: str,
    pinned_source_sha: str,
    pinned_owner_uid: int,
    deadline: Deadline,
) -> OwnerParseResult:
    """Compose conditional metadata with sampled lease checks, not provenance.

    The caller retains cleanup ownership; no atomicity or runtime admission is implied.
    """
    if not revalidate_lifecycle_lock(
        lease, pinned_state_root=pinned_state_root, deadline=deadline
    ):
        return OwnerParseResult(OwnerParseStatus.NOT_READY)
    result = read_signed_owner_v11_from_state(
        pinned_repository=pinned_repository,
        pinned_state_root=pinned_state_root,
        pinned_source_sha=pinned_source_sha,
        pinned_owner_uid=pinned_owner_uid,
        deadline=deadline,
    )
    if result.status is not OwnerParseStatus.SIGNED_METADATA or result.owner is None:
        return OwnerParseResult(OwnerParseStatus.NOT_READY)
    if not revalidate_lifecycle_lock(
        lease, pinned_state_root=pinned_state_root, deadline=deadline
    ):
        return OwnerParseResult(OwnerParseStatus.NOT_READY)
    return result
