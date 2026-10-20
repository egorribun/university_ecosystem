"""Bounded request, metadata and collector boundaries for Docker observation.

Preparation and decoding perform no transport I/O. Composition delegates once
to the existing collector; no coordinator or CLI caller is connected.
Matching supplied daemon metadata does not prove configuration provenance,
daemon authenticity or complete container inventory.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from scripts import live_stand
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline, DeadlineVerdict
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)

if TYPE_CHECKING:
    from scripts.live_stand import ComposeResourceEvidence

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


@dataclass(frozen=True, slots=True)
class ComposeConfigPins:
    project_directory: str = field(repr=False)
    env_file: str = field(repr=False)
    compose_files: tuple[str, ...] = field(repr=False)


class ComposeMetadataStatus(StrEnum):
    NOT_READY = "not_ready"
    MATCHED_METADATA = "matched_metadata"


@dataclass(frozen=True, slots=True)
class ComposeMetadataResult:
    status: ComposeMetadataStatus
    evidence: ComposeResourceEvidence | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CoordinatorMetadataPair:
    """Owner-bound metadata pins for the later coordinator inventory check."""

    owner: OwnerEvidence = field(repr=False)
    daemon_fingerprint: str = field(repr=False)
    resource_fingerprint: str = field(repr=False)
    service_roots: tuple[str, ...] = field(repr=False)
    selected_services: tuple[str, ...] = field(repr=False)


def compose_coordinator_metadata(
    owner: OwnerEvidence,
    daemon: DaemonMetadataResult,
    compose: ComposeMetadataResult,
) -> CoordinatorMetadataPair | None:
    """Bind matched daemon and Compose metadata to one admitted Core owner.

    The returned pins are the metadata portion of coordinator preflight. They
    do not establish runtime identity, container inventory or health.
    """
    admitted = _compose_owner(owner)
    if (
        admitted is None
        or type(daemon) is not DaemonMetadataResult
        or type(compose) is not ComposeMetadataResult
    ):
        return None

    try:
        daemon_status = daemon.status
        daemon_fingerprint = daemon.fingerprint
        compose_status = compose.status
        evidence = compose.evidence
    except AttributeError:
        return None
    if (
        daemon_status is not DaemonMetadataStatus.MATCHED_METADATA
        or compose_status is not ComposeMetadataStatus.MATCHED_METADATA
        or type(daemon_fingerprint) is not str
        or daemon_fingerprint != admitted.daemon_fingerprint
    ):
        return None
    if type(evidence) is not live_stand.ComposeResourceEvidence:
        return None
    try:
        snapshot = replace(evidence)
        if (
            type(snapshot.fingerprint) is not str
            or snapshot.fingerprint != admitted.compose_resource_fingerprint
            or type(snapshot.stack) is not str
            or snapshot.stack != admitted.stack
            or type(snapshot.service_roots) is not tuple
            or any(type(name) is not str for name in snapshot.service_roots)
            or snapshot.service_roots != admitted.service_roots
            or type(snapshot.selected_services) is not tuple
            or any(type(name) is not str for name in snapshot.selected_services)
            or snapshot.selected_services != admitted.selected_services
        ):
            return None
    except AttributeError:
        return None
    return CoordinatorMetadataPair(
        owner=admitted,
        daemon_fingerprint=daemon_fingerprint,
        resource_fingerprint=snapshot.fingerprint,
        service_roots=admitted.service_roots,
        selected_services=admitted.selected_services,
    )


_COMPOSE_STDOUT_LIMIT = 1_048_576
_COMPOSE_STDERR_LIMIT = 16_384
_COMPOSE_JSON_MAX_DEPTH = 64


def _compose_owner(owner: object) -> OwnerEvidence | None:
    if type(owner) is not OwnerEvidence:
        return None
    try:
        snapshot = replace(owner)
        source_sha = snapshot.source_sha
        if type(source_sha) is not str:
            return None
        string_fields = (
            snapshot.repository,
            snapshot.worktree,
            snapshot.project_name,
            snapshot.daemon_fingerprint,
            snapshot.compose_resource_fingerprint,
            snapshot.stack,
        )
        if any(type(value) is not str for value in string_fields):
            return None
        if (
            type(snapshot.schema_version) is not int
            or snapshot.schema_version != 11
            or not _absolute_path(snapshot.repository, allow_root=False)
            or not _absolute_path(snapshot.worktree, allow_root=False)
            or not _fingerprint(snapshot.daemon_fingerprint)
            or not _fingerprint(snapshot.compose_resource_fingerprint)
            or len(source_sha) != 40
            or any(character not in "0123456789abcdef" for character in source_sha)
            or snapshot.resume_compose_resource_fingerprint is not None
            or snapshot.resume_compose_resource_schema_version is not None
            or snapshot.stack != live_stand.LIVE_STACK_CORE
        ):
            return None
        for actual, expected in (
            (snapshot.service_roots, live_stand.LIVE_CORE_SERVICE_ROOTS),
            (snapshot.selected_services, live_stand.LIVE_CORE_EXPECTED_SERVICES),
        ):
            if (
                type(actual) is not tuple
                or len(actual) != len(expected)
                or any(type(name) is not str for name in actual)
                or actual != expected
            ):
                return None
        pairs = snapshot.published_ports
        if type(pairs) is not tuple or len(pairs) != len(live_stand.LIVE_PORT_SPECS):
            return None
        ports: dict[str, int] = {}
        for pair in pairs:
            if type(pair) is not tuple or len(pair) != 2:
                return None
            name, port = pair
            if type(name) is not str or type(port) is not int or name in ports:
                return None
            ports[name] = port
        live_stand._validate_project_name(snapshot.project_name)
        normalized = live_stand._validate_published_ports(ports)
        return replace(snapshot, published_ports=normalized)
    except (AttributeError, live_stand.StandError):
        return None


def _compose_layout(owner: OwnerEvidence, compose: ComposeConfigPins) -> bool:
    expected_files = (
        f"{owner.repository}/{live_stand.COMPOSE_FILES[0]}",
        f"{owner.repository}/{live_stand.OVERLAY}",
        f"{owner.worktree}/{live_stand.IN_PLACE_OVERLAY}",
    )
    return (
        _absolute_path(compose.project_directory, allow_root=False)
        and compose.project_directory == owner.repository
        and _absolute_path(compose.env_file, allow_root=False)
        and compose.env_file == f"{owner.worktree}/.env.docker"
        and type(compose.compose_files) is tuple
        and len(compose.compose_files) == len(expected_files)
        and all(
            _absolute_path(path, allow_root=False) for path in compose.compose_files
        )
        and compose.compose_files == expected_files
    )


def prepare_compose_config(
    owner: OwnerEvidence,
    pins: DockerReadPins,
    compose: ComposeConfigPins,
    *,
    deadline: Deadline,
) -> PrivateProcessRequest | None:
    """Prepare the reviewed Core in-place config request without transport I/O."""
    admitted = _compose_owner(owner)
    if (
        admitted is None
        or type(pins) is not DockerReadPins
        or type(compose) is not ComposeConfigPins
    ):
        return None
    try:
        pinned = replace(pins)
        layout = replace(compose)
        if not _compose_layout(admitted, layout):
            return None
        daemon_request = prepare_daemon_read(pinned, deadline=deadline)
        if (
            daemon_request is None
            or pinned.cwd != admitted.worktree
            or pinned.daemon_fingerprint != admitted.daemon_fingerprint
        ):
            return None
        ports = dict(admitted.published_ports)
        environment = dict(daemon_request.env)
        environment.update(
            {
                "COMPOSE_PROJECT_NAME": admitted.project_name,
                "LIVE_BASE_URL": f"http://localhost:{ports['CADDY_HTTP']}",
                "LIVE_VAPID_PUBLIC_KEY": live_stand.COMPOSE_INSPECTION_PLACEHOLDER,
                "LIVE_VAPID_PRIVATE_KEY": live_stand.COMPOSE_INSPECTION_PLACEHOLDER,
                "LIVE_STAND_STATE_ROOT": admitted.worktree,
                # Admission checked the optional legacy field as an exact string.
                "LIVE_STAND_SOURCE_SHA": cast(str, admitted.source_sha),
            }
        )
        for name in live_stand.LIVE_TRUSTED_PROXY_SETTINGS:
            environment[name] = ""
        for name, port in admitted.published_ports:
            key = "LIVE_MAILPIT_PORT" if name == "MAILPIT" else f"LIVE_HOST_PORT_{name}"
            environment[key] = str(port)
        argv = [
            *daemon_request.argv[:5],
            "compose",
            "--project-directory",
            layout.project_directory,
            "-p",
            admitted.project_name,
            "--env-file",
            layout.env_file,
        ]
        for path in layout.compose_files:
            argv.extend(("-f", path))
        argv.extend(("config", "--format", "json"))
        request = PrivateProcessRequest(
            argv=tuple(argv),
            cwd=admitted.worktree,
            env=environment,
            stdin=b"",
            stdout_limit=_COMPOSE_STDOUT_LIMIT,
            stderr_limit=_COMPOSE_STDERR_LIMIT,
            input_limit=0,
        )
    except AttributeError:
        return None
    return request if _live(deadline) else None


def _compose_stdout(result: object) -> bytes | None:
    if type(result) is not PrivateProcessResult:
        return None
    try:
        if (
            result.outcome is not ProcessOutcome.EXITED
            or type(result.returncode) is not int
            or result.returncode != 0
            or result.local_cleanup is not LocalCleanup.CONFIRMED
            or type(result.stdout) is not bytes
            or not 0 < len(result.stdout) <= _COMPOSE_STDOUT_LIMIT
            or type(result.stderr) is not bytes
            or len(result.stderr) > _COMPOSE_STDERR_LIMIT
            or result.stderr != b""
        ):
            return None
        return result.stdout
    except AttributeError:
        return None


def _compose_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous Compose JSON")
        result[key] = value
    return result


def _compose_json_constant(_value: str) -> None:
    raise ValueError("non-finite Compose JSON")


def _compose_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite Compose JSON")
    return number


def _compose_json_depth_within_limit(project: object) -> bool:
    """Bound every decoded container, counting the root container as depth one."""
    pending: list[tuple[object, int]] = [(project, 1)]
    while pending:
        value, depth = pending.pop()
        if not isinstance(value, (dict, list)):
            continue
        if depth > _COMPOSE_JSON_MAX_DEPTH:
            return False
        children = value.values() if isinstance(value, dict) else value
        pending.extend((child, depth + 1) for child in children)
    return True


def decode_compose_config(
    result: PrivateProcessResult,
    *,
    owner: OwnerEvidence,
    deadline: Deadline,
) -> ComposeMetadataResult:
    """Match supplied private config metadata, not runtime inventory."""
    not_ready = ComposeMetadataResult(ComposeMetadataStatus.NOT_READY)
    admitted = _compose_owner(owner)
    raw = _compose_stdout(result)
    if admitted is None or raw is None or not _live(deadline):
        return not_ready
    expected_fingerprint = admitted.compose_resource_fingerprint
    try:
        project = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_compose_json_object,
            parse_constant=_compose_json_constant,
            parse_float=_compose_json_float,
        )
    except (UnicodeError, ValueError, RecursionError):
        return not_ready
    if (
        type(project) is not dict
        or not _live(deadline)
        or not _compose_json_depth_within_limit(project)
        or not _live(deadline)
    ):
        return not_ready
    try:
        evidence = live_stand._compose_resource_evidence_from_project(
            project,
            admitted.project_name,
            dict(admitted.published_ports),
            stack=admitted.stack,
            service_roots=admitted.service_roots,
        )
    except (live_stand.StandError, TypeError, ValueError, RecursionError):
        return not_ready
    if (
        evidence.fingerprint != expected_fingerprint
        or evidence.stack != admitted.stack
        or evidence.service_roots != admitted.service_roots
        or evidence.selected_services != admitted.selected_services
        or not _live(deadline)
    ):
        return not_ready
    return ComposeMetadataResult(ComposeMetadataStatus.MATCHED_METADATA, evidence)


def observe_compose_metadata(
    owner: OwnerEvidence,
    pins: DockerReadPins,
    compose: ComposeConfigPins,
    *,
    deadline: Deadline,
) -> ComposeMetadataResult:
    """Observe supplied Compose metadata once, without runtime admission."""
    admitted = _compose_owner(owner)
    if admitted is None:
        return ComposeMetadataResult(ComposeMetadataStatus.NOT_READY)
    request = prepare_compose_config(admitted, pins, compose, deadline=deadline)
    if request is None:
        return ComposeMetadataResult(ComposeMetadataStatus.NOT_READY)
    result = process.run_private_process(request, deadline=deadline)
    return decode_compose_config(result, owner=admitted, deadline=deadline)
