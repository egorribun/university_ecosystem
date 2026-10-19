"""Signed Core metadata boundaries for a future bounded NATS transport.

The parser call performs no filesystem, lock, Docker, HTTP or database work.
It is not connected to the coordinator or CLI. Importing the existing live_stand
module retains that module's ordinary repository-path initialization.
A parsed claim is conditional on trusted caller-supplied key bytes and pins;
it does not establish file provenance or observe the current Docker daemon.
"""

from __future__ import annotations

import hmac
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
        block = _reader_call(deadline, lambda: os.read(fd, requested))
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
    deadline: Deadline,
) -> OwnerParseResult:
    """Read existing fixed files into signed metadata, never runtime admission.

    Initial traversal is descriptor-relative and nofollow. Leaf checks observe
    descriptor/name metadata before and after both reads, not an atomic pair
    snapshot or post-read binding of the full ancestor pathname. No lifecycle
    lock, key-provenance authentication or current daemon check is performed.
    Syscalls, including on network/FUSE mounts, cannot be hard-preempted.
    """
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
