"""Bounded request, metadata and collector boundaries for Docker observation.

Preparation and decoding perform no transport I/O. Composition delegates once
to the existing collector; no coordinator or CLI caller is connected.
Matching supplied daemon metadata does not prove configuration provenance,
daemon authenticity or complete container inventory.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from scripts import owned_nats_process as process
from scripts.owned_nats_outage import Deadline, DeadlineVerdict
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)

_STDOUT_LIMIT = 256
_STDERR_LIMIT = 1024
_PATH_LIMIT = 4096


@dataclass(frozen=True, slots=True)
class DockerReadPins:
    executable: str = field(repr=False)
    endpoint: str = field(repr=False)
    config_directory: str = field(repr=False)
    cwd: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    daemon_fingerprint: str = field(repr=False)


class DaemonMetadataStatus(StrEnum):
    NOT_READY = "not_ready"
    MATCHED_METADATA = "matched_metadata"


@dataclass(frozen=True, slots=True)
class DaemonMetadataResult:
    status: DaemonMetadataStatus
    fingerprint: str | None = field(default=None, repr=False)


def _live(deadline: object) -> bool:
    if type(deadline) is not Deadline:
        return False
    try:
        return deadline.timeout_for(1.0).verdict is DeadlineVerdict.VALID
    except Exception:
        # Malformed deadline internals and ordinary clock failures stay private.
        return False


def _fingerprint(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _absolute_path(value: object, *, allow_root: bool) -> bool:
    if (
        type(value) is not str
        or not 1 <= len(value) <= _PATH_LIMIT
        or not value.startswith("/")
        or not value.isprintable()
    ):
        return False
    if value == "/":
        return allow_root
    return all(component not in {"", ".", ".."} for component in value[1:].split("/"))


def _local_endpoint(value: object) -> bool:
    if (
        type(value) is not str
        or len(value) > _PATH_LIMIT + len("unix://")
        or not value.startswith("unix://")
    ):
        return False
    path = value[len("unix://") :]
    return _absolute_path(path, allow_root=False) and not any(
        character in path for character in ("?", "#", "%", "\\")
    )


def _environment(value: object) -> dict[str, str] | None:
    if type(value) is not tuple or len(value) > 2:
        return None
    environment: dict[str, str] = {}
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            return None
        name, setting = pair
        if (
            type(name) is not str
            or type(setting) is not str
            or name not in {"LANG", "LC_ALL"}
            or setting not in {"C", "C.UTF-8"}
            or name in environment
        ):
            return None
        environment[name] = setting
    return environment


def prepare_daemon_read(
    pins: DockerReadPins, *, deadline: Deadline
) -> PrivateProcessRequest | None:
    """Prepare one explicit local request without inspecting paths or executing."""
    if type(pins) is not DockerReadPins or not _live(deadline):
        return None
    try:
        if (
            not _absolute_path(pins.executable, allow_root=False)
            or not _absolute_path(pins.config_directory, allow_root=True)
            or not _absolute_path(pins.cwd, allow_root=True)
            or not _local_endpoint(pins.endpoint)
            or not _fingerprint(pins.daemon_fingerprint)
        ):
            return None
        environment = _environment(pins.environment)
        if environment is None:
            return None
        request = PrivateProcessRequest(
            argv=(
                pins.executable,
                "--config",
                pins.config_directory,
                "--host",
                pins.endpoint,
                "info",
                "--format",
                "{{.ID}}",
            ),
            cwd=pins.cwd,
            env=environment,
            stdin=b"",
            stdout_limit=_STDOUT_LIMIT,
            stderr_limit=_STDERR_LIMIT,
            input_limit=0,
        )
    except AttributeError:
        # An exact-class instance can still have uninitialized slot fields.
        return None
    return request if _live(deadline) else None


def _successful_result(result: object) -> bool:
    return (
        type(result) is PrivateProcessResult
        and result.outcome is ProcessOutcome.EXITED
        and type(result.returncode) is int
        and result.returncode == 0
        and result.local_cleanup is LocalCleanup.CONFIRMED
        and type(result.stdout) is bytes
        and 0 < len(result.stdout) <= _STDOUT_LIMIT
        and type(result.stderr) is bytes
        and len(result.stderr) <= _STDERR_LIMIT
        and result.stderr == b""
    )


def decode_daemon_read(
    result: PrivateProcessResult,
    *,
    pinned_daemon: str,
    deadline: Deadline,
) -> DaemonMetadataResult:
    """Match supplied bounded metadata, without claiming daemon authentication."""
    not_ready = DaemonMetadataResult(DaemonMetadataStatus.NOT_READY)
    if not _live(deadline) or not _fingerprint(pinned_daemon):
        return not_ready
    try:
        if not _successful_result(result):
            return not_ready
        daemon_id = result.stdout.decode("utf-8")
        if daemon_id.endswith("\r\n"):
            daemon_id = daemon_id[:-2]
        elif daemon_id.endswith("\n"):
            daemon_id = daemon_id[:-1]
        if (
            not daemon_id
            or not daemon_id.isprintable()
            or any(character.isspace() for character in daemon_id)
        ):
            return not_ready
        fingerprint = hashlib.sha256(daemon_id.encode("utf-8")).hexdigest()
    except (AttributeError, UnicodeError):
        return not_ready
    if fingerprint != pinned_daemon or not _live(deadline):
        return not_ready
    return DaemonMetadataResult(
        DaemonMetadataStatus.MATCHED_METADATA,
        fingerprint,
    )


def observe_daemon_metadata(
    pins: DockerReadPins, *, deadline: Deadline
) -> DaemonMetadataResult:
    """Collect once under the caller deadline and retain the admitted expectation."""
    request = prepare_daemon_read(pins, deadline=deadline)
    if request is None:
        return DaemonMetadataResult(DaemonMetadataStatus.NOT_READY)
    expected_fingerprint = pins.daemon_fingerprint
    result = process.run_private_process(request, deadline=deadline)
    return decode_daemon_read(
        result, pinned_daemon=expected_fingerprint, deadline=deadline
    )
