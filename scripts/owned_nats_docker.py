"""Bounded metadata and owner-scoped inventory reads for Docker observation.

Preparation and decoding perform no transport I/O; the collector composes the
metadata and inventory reads under one deadline. No coordinator or CLI caller
is connected.
Matching supplied daemon metadata does not prove configuration provenance,
daemon authenticity or complete container inventory.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from scripts import live_stand
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import (
    OwnerEvidence,
    RuntimeEvidence,
    RuntimeObservationPhase,
    RuntimeObservationRecorder,
)
from scripts.owned_nats_outage import ContainerSnapshot, Deadline, DeadlineVerdict
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
_RUNTIME_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_RUNTIME_CONTAINER_ID_LIMIT = 10_000
_RUNTIME_CONTAINER_ID_STDOUT_LIMIT = _RUNTIME_CONTAINER_ID_LIMIT * 66
_RUNTIME_INSPECT_BATCH_SIZE = 64
_RUNTIME_INSPECT_STDOUT_LIMIT = 1_048_576
_RUNTIME_INSPECT_STDERR_LIMIT = 16_384
_CONTEXT_STDOUT_LIMIT = 256
_CONTEXT_STDERR_LIMIT = 1_024
_DEFAULT_DOCKER_ENDPOINT = "unix:///var/run/docker.sock"
_DEFAULT_DOCKER_CONTEXT_FORMAT = "{{json .Endpoints.docker.Host}}"
_RUNTIME_INSPECT_FORMAT = (
    '{"Id":{{json .Id}},'
    '"Name":{{json .Name}},'
    '"Image":{{json .Image}},'
    '"Config":{"Image":{{json .Config.Image}},'
    '"Labels":{{json .Config.Labels}}},'
    '"Mounts":[{{range $i, $m := .Mounts}}{{if $i}},{{end}}'
    '{"Type":{{json (index $m "Type")}},'
    '"Name":{{json (index $m "Name")}},'
    '"Source":{{json (index $m "Source")}},'
    '"Destination":{{json (index $m "Destination")}},'
    '"Driver":{{json (index $m "Driver")}},'
    '"Mode":{{json (index $m "Mode")}},'
    '"RW":{{json (index $m "RW")}},'
    '"Propagation":{{json (index $m "Propagation")}}'
    "}{{end}}],"
    '"State":{"Running":{{json .State.Running}},'
    '"Status":{{json .State.Status}},'
    '"Health":{{with index .State "Health"}}'
    '{"Status":{{json (index . "Status")}}}'
    "{{else}}null{{end}},"
    '"ExitCode":{{json .State.ExitCode}},'
    '"OOMKilled":{{json .State.OOMKilled}}},'
    '"RestartCount":{{json .RestartCount}}}'
)


@dataclass(frozen=True, slots=True)
class DockerReadPins:
    executable: str = field(repr=False)
    endpoint: str = field(repr=False)
    config_directory: str = field(repr=False)
    cwd: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    daemon_fingerprint: str = field(repr=False)
    _executable_identity: tuple[int, int, int, int] | None = field(
        default=None, repr=False
    )
    _factory_seal: object | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _DockerPinFactorySeal:
    executable: str = field(repr=False)
    endpoint: str = field(repr=False)
    config_directory: str = field(repr=False)
    cwd: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    daemon_fingerprint: str = field(repr=False)
    executable_identity: tuple[int, int, int, int] = field(repr=False)


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


def _valid_executable_identity(value: object) -> bool:
    return (
        type(value) is tuple
        and len(value) == 4
        and all(type(item) is int and item >= 0 for item in value)
    )


def _factory_provenance_valid(pins: object) -> bool:
    if type(pins) is not DockerReadPins:
        return False
    try:
        identity = pins._executable_identity
        seal = pins._factory_seal
        if identity is None and seal is None:
            return True
        if type(seal) is not _DockerPinFactorySeal:
            return False
        pin_strings = (
            pins.executable,
            pins.endpoint,
            pins.config_directory,
            pins.cwd,
            pins.daemon_fingerprint,
        )
        seal_strings = (
            seal.executable,
            seal.endpoint,
            seal.config_directory,
            seal.cwd,
            seal.daemon_fingerprint,
        )
        if (
            any(type(value) is not str for value in (*pin_strings, *seal_strings))
            or not _valid_executable_identity(identity)
            or not _valid_executable_identity(seal.executable_identity)
            or _environment(pins.environment) is None
            or _environment(seal.environment) is None
        ):
            return False
        return (
            seal.executable == pins.executable
            and seal.endpoint == pins.endpoint
            and seal.config_directory == pins.config_directory
            and seal.cwd == pins.cwd
            and seal.environment == pins.environment
            and seal.daemon_fingerprint == pins.daemon_fingerprint
            and seal.executable_identity == identity
        )
    except AttributeError:
        return False


def _factory_executable_matches(pins: DockerReadPins) -> bool:
    if not _factory_provenance_valid(pins):
        return False
    if pins._factory_seal is None:
        return True
    try:
        actual = live_stand._live_docker_executable_identity(pins.executable)
    except (AttributeError, OSError, RuntimeError, live_stand.StandError):
        return False
    return actual == pins._executable_identity


def _not_ready_process_result(
    cleanup: LocalCleanup = LocalCleanup.NOT_STARTED,
) -> PrivateProcessResult:
    return PrivateProcessResult(ProcessOutcome.NOT_READY, None, b"", b"", cleanup)


def _run_pinned_docker_process(
    pins: DockerReadPins,
    request: PrivateProcessRequest,
    *,
    deadline: Deadline,
) -> PrivateProcessResult:
    if (
        type(pins) is not DockerReadPins
        or type(request) is not PrivateProcessRequest
        or not _factory_provenance_valid(pins)
        or not _live(deadline)
    ):
        return _not_ready_process_result()
    try:
        snapshot = replace(pins)
        if (
            not _absolute_path(snapshot.executable, allow_root=False)
            or not _absolute_path(snapshot.config_directory, allow_root=True)
            or not _absolute_path(snapshot.cwd, allow_root=True)
            or not _local_endpoint(snapshot.endpoint)
            or request.argv[:5]
            != (
                snapshot.executable,
                "--config",
                snapshot.config_directory,
                "--host",
                snapshot.endpoint,
            )
            or request.cwd != snapshot.cwd
            or not _factory_executable_matches(snapshot)
            or not _live(deadline)
        ):
            return _not_ready_process_result()
    except (AttributeError, TypeError, ValueError):
        return _not_ready_process_result()

    result = process.run_private_process(request, deadline=deadline)
    if type(result) is not PrivateProcessResult:
        return _not_ready_process_result(LocalCleanup.UNPROVEN)
    if not _live(deadline) or not _factory_executable_matches(snapshot):
        cleanup = (
            result.local_cleanup
            if type(result.local_cleanup) is LocalCleanup
            else LocalCleanup.UNPROVEN
        )
        return _not_ready_process_result(cleanup)
    return result


def _linux_core_supported() -> bool:
    return (
        sys.platform == "linux"
        and os.name == "posix"
        and "WSL_DISTRO_NAME" not in os.environ
        and "WSL_INTEROP" not in os.environ
    )


def _context_snapshot(
    owner: OwnerEvidence, context: object
) -> tuple[live_stand._LiveDockerReadContext, str, str] | None:
    if type(context) is not live_stand._LiveDockerReadContext:
        return None
    try:
        snapshot = replace(context)
        if (
            type(snapshot.executable) is not str
            or not _absolute_path(snapshot.executable, allow_root=False)
            or not _valid_executable_identity(snapshot.executable_identity)
            or type(snapshot.cwd) is not str
            or snapshot.cwd not in (owner.repository, owner.worktree)
            or not _absolute_path(snapshot.cwd, allow_root=False)
            or type(snapshot.environment) is not tuple
            or len(snapshot.environment) > 512
        ):
            return None
        environment: dict[str, str] = {}
        size = 0
        for pair in snapshot.environment:
            if type(pair) is not tuple or len(pair) != 2:
                return None
            name, value = pair
            if (
                type(name) is not str
                or not name
                or "=" in name
                or "\x00" in name
                or type(value) is not str
                or "\x00" in value
                or name in environment
            ):
                return None
            size += len(name) + len(value)
            if size > 65_536 or name.upper().startswith("DOCKER_"):
                return None
            environment[name] = value
        home = environment.get("HOME")
        if type(home) is not str or not _absolute_path(home, allow_root=False):
            return None
        config_directory = f"{home}/.docker"
        if not _absolute_path(config_directory, allow_root=False):
            return None
        live_stand._assert_live_docker_read_context(snapshot)
    except (
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        live_stand.StandError,
    ):
        return None
    return replace(snapshot, cwd=owner.worktree), home, config_directory


def _context_process_result(
    context: live_stand._LiveDockerReadContext,
    config_directory: str,
    environment: dict[str, str],
    arguments: tuple[str, ...],
    *,
    deadline: Deadline,
) -> bytes | None:
    if not _live(deadline):
        return None
    try:
        request = PrivateProcessRequest(
            argv=(context.executable, "--config", config_directory, *arguments),
            cwd=context.cwd,
            env=environment,
            stdin=b"",
            stdout_limit=_CONTEXT_STDOUT_LIMIT,
            stderr_limit=_CONTEXT_STDERR_LIMIT,
            input_limit=0,
        )
        live_stand._assert_live_docker_read_context(context)
        if not _live(deadline):
            return None
        result = process.run_private_process(request, deadline=deadline)
        live_stand._assert_live_docker_read_context(context)
    except (
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        live_stand.StandError,
    ):
        return None
    if (
        type(result) is not PrivateProcessResult
        or result.outcome is not ProcessOutcome.EXITED
        or type(result.returncode) is not int
        or result.returncode != 0
        or result.local_cleanup is not LocalCleanup.CONFIRMED
        or type(result.stdout) is not bytes
        or not 0 < len(result.stdout) <= _CONTEXT_STDOUT_LIMIT
        or type(result.stderr) is not bytes
        or len(result.stderr) > _CONTEXT_STDERR_LIMIT
        or result.stderr != b""
        or not _live(deadline)
    ):
        return None
    return result.stdout


def prepare_daemon_read(
    pins: DockerReadPins, *, deadline: Deadline
) -> PrivateProcessRequest | None:
    """Prepare one explicit local request without inspecting paths or executing."""
    if (
        type(pins) is not DockerReadPins
        or not _factory_provenance_valid(pins)
        or not _live(deadline)
    ):
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
    result = _run_pinned_docker_process(pins, request, deadline=deadline)
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


def resolve_core_docker_pins(
    owner: OwnerEvidence, *, deadline: Deadline
) -> tuple[DockerReadPins, ComposeConfigPins] | None:
    """Resolve fixed Linux Core pins from signed evidence under its held lease.

    Call only after the coordinator has acquired its lifecycle lease and read the
    signed owner. This resolver does not acquire a lock or authenticate owner data.
    """
    admitted = _compose_owner(owner)
    if admitted is None or not _linux_core_supported() or not _live(deadline):
        return None
    try:
        context = live_stand._new_live_docker_read_context()
    except (
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        live_stand.StandError,
    ):
        return None
    context_values = _context_snapshot(admitted, context)
    if context_values is None:
        return None
    context, home, config_directory = context_values
    compose = ComposeConfigPins(
        project_directory=admitted.repository,
        env_file=f"{admitted.worktree}/.env.docker",
        compose_files=(
            f"{admitted.repository}/{live_stand.COMPOSE_FILES[0]}",
            f"{admitted.repository}/{live_stand.OVERLAY}",
            f"{admitted.worktree}/{live_stand.IN_PLACE_OVERLAY}",
        ),
    )
    if not _compose_layout(admitted, compose) or not _live(deadline):
        return None

    context_environment = {"HOME": home, "LANG": "C", "LC_ALL": "C"}
    current_context = _context_process_result(
        context,
        config_directory,
        context_environment,
        ("context", "show"),
        deadline=deadline,
    )
    if current_context != b"default\n" or not _live(deadline):
        return None
    current_endpoint = _context_process_result(
        context,
        config_directory,
        context_environment,
        (
            "context",
            "inspect",
            "default",
            "--format",
            _DEFAULT_DOCKER_CONTEXT_FORMAT,
        ),
        deadline=deadline,
    )
    if current_endpoint != b'"unix:///var/run/docker.sock"\n' or not _live(deadline):
        return None

    environment = (("LANG", "C"), ("LC_ALL", "C"))
    seal = _DockerPinFactorySeal(
        executable=context.executable,
        endpoint=_DEFAULT_DOCKER_ENDPOINT,
        config_directory=config_directory,
        cwd=admitted.worktree,
        environment=environment,
        daemon_fingerprint=admitted.daemon_fingerprint,
        executable_identity=context.executable_identity,
    )
    pins = DockerReadPins(
        executable=context.executable,
        endpoint=_DEFAULT_DOCKER_ENDPOINT,
        config_directory=config_directory,
        cwd=admitted.worktree,
        environment=environment,
        daemon_fingerprint=admitted.daemon_fingerprint,
        _executable_identity=context.executable_identity,
        _factory_seal=seal,
    )
    daemon = observe_daemon_metadata(pins, deadline=deadline)
    if (
        type(daemon) is not DaemonMetadataResult
        or daemon.status is not DaemonMetadataStatus.MATCHED_METADATA
        or daemon.fingerprint != admitted.daemon_fingerprint
        or not _factory_executable_matches(pins)
        or not _live(deadline)
    ):
        return None
    return pins, compose


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
    diagnostic: RuntimeObservationRecorder | None = None,
) -> ComposeMetadataResult:
    """Observe supplied Compose metadata once, without runtime admission."""
    if diagnostic is not None:
        diagnostic.reset()
        diagnostic.record(RuntimeObservationPhase.COMPOSE_PREPARE)
    admitted = _compose_owner(owner)
    if admitted is None:
        return ComposeMetadataResult(ComposeMetadataStatus.NOT_READY)
    request = prepare_compose_config(admitted, pins, compose, deadline=deadline)
    if request is None:
        return ComposeMetadataResult(ComposeMetadataStatus.NOT_READY)
    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.COMPOSE_PROCESS)
    result = _run_pinned_docker_process(pins, request, deadline=deadline)
    process_ok = diagnostic is None or _compose_stdout(result) is not None
    if diagnostic is not None and process_ok:
        diagnostic.record(RuntimeObservationPhase.COMPOSE_DECODE)
    decoded = decode_compose_config(result, owner=admitted, deadline=deadline)
    if (
        diagnostic is not None
        and process_ok
        and type(decoded) is ComposeMetadataResult
        and decoded.status is ComposeMetadataStatus.MATCHED_METADATA
        and type(decoded.evidence) is live_stand.ComposeResourceEvidence
    ):
        diagnostic.reset()
    return decoded


def _runtime_metadata_pair(value: object) -> CoordinatorMetadataPair | None:
    if type(value) is not CoordinatorMetadataPair:
        return None
    try:
        owner = _compose_owner(value.owner)
        daemon_fingerprint = value.daemon_fingerprint
        resource_fingerprint = value.resource_fingerprint
        service_roots = value.service_roots
        selected_services = value.selected_services
    except AttributeError:
        return None
    if (
        owner is None
        or daemon_fingerprint != owner.daemon_fingerprint
        or resource_fingerprint != owner.compose_resource_fingerprint
        or service_roots != owner.service_roots
        or selected_services != owner.selected_services
    ):
        return None
    return CoordinatorMetadataPair(
        owner=owner,
        daemon_fingerprint=daemon_fingerprint,
        resource_fingerprint=resource_fingerprint,
        service_roots=service_roots,
        selected_services=selected_services,
    )


def _runtime_pins(
    metadata: CoordinatorMetadataPair,
    pins: object,
    *,
    deadline: Deadline,
) -> tuple[DockerReadPins, PrivateProcessRequest] | None:
    if type(pins) is not DockerReadPins:
        return None
    try:
        snapshot = replace(pins)
        request = prepare_daemon_read(snapshot, deadline=deadline)
        if (
            request is None
            or snapshot.cwd != metadata.owner.worktree
            or snapshot.daemon_fingerprint != metadata.daemon_fingerprint
        ):
            return None
    except AttributeError:
        return None
    return snapshot, request


def prepare_container_id_read(
    metadata: CoordinatorMetadataPair,
    pins: DockerReadPins,
    *,
    deadline: Deadline,
) -> PrivateProcessRequest | None:
    """Prepare a project-wide Docker list, including stopped/orphan containers."""
    admitted = _runtime_metadata_pair(metadata)
    if admitted is None:
        return None
    pinned = _runtime_pins(admitted, pins, deadline=deadline)
    if pinned is None:
        return None
    _snapshot, daemon_request = pinned
    argv = (
        *daemon_request.argv[:5],
        "ps",
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        f"label=com.docker.compose.project={admitted.owner.project_name}",
    )
    request = PrivateProcessRequest(
        argv=argv,
        cwd=daemon_request.cwd,
        env=dict(daemon_request.env),
        stdin=b"",
        stdout_limit=_RUNTIME_CONTAINER_ID_STDOUT_LIMIT,
        stderr_limit=_RUNTIME_INSPECT_STDERR_LIMIT,
        input_limit=0,
    )
    return request if _live(deadline) else None


def _container_ids(values: object) -> tuple[str, ...] | None:
    if (
        type(values) is not tuple
        or len(values) > _RUNTIME_CONTAINER_ID_LIMIT
        or any(
            type(value) is not str or _RUNTIME_CONTAINER_ID.fullmatch(value) is None
            for value in values
        )
        or len(set(values)) != len(values)
    ):
        return None
    return values


def _bounded_process_result(
    result: object, *, stdout_limit: int, stderr_limit: int
) -> PrivateProcessResult | None:
    if type(result) is not PrivateProcessResult:
        return None
    try:
        if (
            result.outcome is not ProcessOutcome.EXITED
            or type(result.returncode) is not int
            or result.returncode != 0
            or result.local_cleanup is not LocalCleanup.CONFIRMED
            or type(result.stdout) is not bytes
            or len(result.stdout) > stdout_limit
            or type(result.stderr) is not bytes
            or len(result.stderr) > stderr_limit
            or result.stderr != b""
        ):
            return None
    except AttributeError:
        return None
    return result


def decode_container_id_read(
    result: PrivateProcessResult,
    metadata: CoordinatorMetadataPair,
    *,
    deadline: Deadline,
) -> tuple[str, ...] | None:
    """Decode only a bounded complete set of canonical IDs for the pinned project."""
    admitted = _runtime_metadata_pair(metadata)
    supplied = _bounded_process_result(
        result,
        stdout_limit=_RUNTIME_CONTAINER_ID_STDOUT_LIMIT,
        stderr_limit=_RUNTIME_INSPECT_STDERR_LIMIT,
    )
    if admitted is None or supplied is None or not _live(deadline):
        return None
    try:
        raw = supplied.stdout.decode("ascii")
        raw = raw.replace("\r\n", "\n")
        if raw.endswith("\n"):
            raw = raw[:-1]
        if "\r" in raw:
            return None
        values = () if raw == "" else tuple(raw.split("\n"))
    except UnicodeError:
        return None
    ids = _container_ids(values)
    if ids is None or not _live(deadline):
        return None
    return ids


def prepare_container_inspect_reads(
    metadata: CoordinatorMetadataPair,
    pins: DockerReadPins,
    container_ids: tuple[str, ...],
    *,
    deadline: Deadline,
) -> tuple[PrivateProcessRequest, ...] | None:
    """Prepare bounded inspect batches containing only previously captured IDs."""
    admitted = _runtime_metadata_pair(metadata)
    ids = _container_ids(container_ids)
    if admitted is None or ids is None:
        return None
    pinned = _runtime_pins(admitted, pins, deadline=deadline)
    if pinned is None:
        return None
    _snapshot, daemon_request = pinned
    requests = tuple(
        PrivateProcessRequest(
            argv=(
                *daemon_request.argv[:5],
                "inspect",
                "--type",
                "container",
                "--format",
                _RUNTIME_INSPECT_FORMAT,
                *ids[start : start + _RUNTIME_INSPECT_BATCH_SIZE],
            ),
            cwd=daemon_request.cwd,
            env=dict(daemon_request.env),
            stdin=b"",
            stdout_limit=_RUNTIME_INSPECT_STDOUT_LIMIT,
            stderr_limit=_RUNTIME_INSPECT_STDERR_LIMIT,
            input_limit=0,
        )
        for start in range(0, len(ids), _RUNTIME_INSPECT_BATCH_SIZE)
    )
    return requests if _live(deadline) else None


def _runtime_compose_evidence(
    metadata: CoordinatorMetadataPair, evidence: object
) -> ComposeResourceEvidence | None:
    if type(evidence) is not live_stand.ComposeResourceEvidence:
        return None
    try:
        snapshot = replace(evidence)
        if (
            type(snapshot.fingerprint) is not str
            or snapshot.fingerprint != metadata.resource_fingerprint
            or snapshot.stack != metadata.owner.stack
            or snapshot.service_roots != metadata.service_roots
            or snapshot.selected_services != metadata.selected_services
            or snapshot.managed_services != metadata.selected_services
            or type(snapshot.declared_volume_names) is not tuple
            or any(type(name) is not str for name in snapshot.declared_volume_names)
        ):
            return None
    except AttributeError:
        return None
    return snapshot


def _runtime_stand_owner(owner: OwnerEvidence) -> live_stand.StandOwner:
    return live_stand.StandOwner(
        repository=owner.repository,
        worktree=owner.worktree,
        project_name=owner.project_name,
        published_ports=owner.published_ports,
        schema_version=owner.schema_version,
        daemon_fingerprint=owner.daemon_fingerprint,
        compose_resource_fingerprint=owner.compose_resource_fingerprint,
        resume_compose_resource_fingerprint=owner.resume_compose_resource_fingerprint,
        resume_compose_resource_schema_version=(
            owner.resume_compose_resource_schema_version
        ),
        source_sha=owner.source_sha,
        stack=owner.stack,
        service_roots=owner.service_roots,
        selected_services=owner.selected_services,
    )


def _pinned_daemon_matches(
    metadata: CoordinatorMetadataPair,
    pins: DockerReadPins,
    *,
    deadline: Deadline,
) -> bool:
    observed = observe_daemon_metadata(pins, deadline=deadline)
    return (
        type(observed) is DaemonMetadataResult
        and observed.status is DaemonMetadataStatus.MATCHED_METADATA
        and observed.fingerprint == metadata.daemon_fingerprint
        and _live(deadline)
    )


def _runtime_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    return _compose_json_object(pairs)


def _runtime_json_constant(_value: str) -> None:
    raise ValueError("non-finite runtime inspect JSON")


def _runtime_mounts(value: object) -> bool:
    if type(value) is not list:
        return False
    fields = {
        "Type",
        "Name",
        "Source",
        "Destination",
        "Driver",
        "Mode",
        "RW",
        "Propagation",
    }
    for mount in value:
        if type(mount) is not dict or set(mount) != fields:
            return False
        if type(mount["Type"]) is not str or mount["Type"] not in {
            "volume",
            "bind",
            "tmpfs",
        }:
            return False
        if (
            any(
                item is not None and type(item) is not str
                for item in (
                    mount["Name"],
                    mount["Source"],
                    mount["Destination"],
                    mount["Driver"],
                    mount["Mode"],
                    mount["Propagation"],
                )
            )
            or type(mount["RW"]) is not bool
        ):
            return False
    return True


def _runtime_snapshot(
    metadata: CoordinatorMetadataPair,
    evidence: ComposeResourceEvidence,
    expected_id: str,
    value: object,
) -> ContainerSnapshot | None:
    if type(value) is not dict or set(value) != {
        "Id",
        "Name",
        "Image",
        "Config",
        "Mounts",
        "State",
        "RestartCount",
    }:
        return None
    try:
        container_id = value["Id"]
        name = value["Name"]
        image = value["Image"]
        config = value["Config"]
        mounts = value["Mounts"]
        state = value["State"]
        restart_count = value["RestartCount"]
        if (
            type(container_id) is not str
            or _RUNTIME_CONTAINER_ID.fullmatch(container_id) is None
            or container_id != expected_id
            or type(name) is not str
            or type(image) is not str
            or type(config) is not dict
            or set(config) != {"Image", "Labels"}
            or type(config["Image"]) is not str
            or type(config["Labels"]) is not dict
            or any(
                type(key) is not str or type(label) is not str
                for key, label in config["Labels"].items()
            )
            or config["Labels"].get("com.docker.compose.oneoff") != "False"
            or not _runtime_mounts(mounts)
            or type(state) is not dict
            or set(state) != {"Running", "Status", "Health", "ExitCode", "OOMKilled"}
            or type(state["Running"]) is not bool
            or (state["Status"] is not None and type(state["Status"]) is not str)
            or (
                state["Health"] is not None
                and (
                    type(state["Health"]) is not dict
                    or set(state["Health"]) != {"Status"}
                    or type(state["Health"]["Status"]) is not str
                )
            )
            or type(state["ExitCode"]) is not int
            or type(state["OOMKilled"]) is not bool
            or type(restart_count) is not int
        ):
            return None
    except (KeyError, TypeError):
        return None

    owner = metadata.owner
    record = {
        "Id": container_id,
        "Name": name,
        "Image": image,
        "Config": {"Image": config["Image"], "Labels": config["Labels"]},
        "Mounts": mounts,
        "State": {
            "Running": state["Running"],
            "Status": state["Status"],
            "Health": state["Health"],
        },
    }
    try:
        projected = live_stand._core_container_record_from_inspect(
            container_id,
            _runtime_stand_owner(owner),
            evidence,
            record,
        )
    except (live_stand.StandError, TypeError, ValueError, RecursionError):
        return None
    return ContainerSnapshot(
        container_id=container_id,
        service=projected.service,
        identity=projected.identity,
        running=projected.running,
        status=projected.status,
        health=projected.health,
        restart_count=restart_count,
        exit_code=state["ExitCode"],
        oom_killed=state["OOMKilled"],
    )


def decode_container_inspect_reads(
    metadata: CoordinatorMetadataPair,
    compose_evidence: ComposeResourceEvidence,
    container_ids: tuple[str, ...],
    results: tuple[PrivateProcessResult, ...],
    *,
    deadline: Deadline,
) -> tuple[ContainerSnapshot, ...] | None:
    """Bind every projected inspect response to exactly one captured container ID."""
    admitted = _runtime_metadata_pair(metadata)
    evidence = (
        _runtime_compose_evidence(admitted, compose_evidence)
        if admitted is not None
        else None
    )
    ids = _container_ids(container_ids)
    if (
        admitted is None
        or evidence is None
        or ids is None
        or type(results) is not tuple
        or not _live(deadline)
    ):
        return None
    batches = tuple(
        ids[start : start + _RUNTIME_INSPECT_BATCH_SIZE]
        for start in range(0, len(ids), _RUNTIME_INSPECT_BATCH_SIZE)
    )
    if len(results) != len(batches):
        return None
    snapshots: list[ContainerSnapshot] = []
    seen: set[str] = set()
    try:
        for expected_batch, supplied in zip(batches, results, strict=True):
            result = _bounded_process_result(
                supplied,
                stdout_limit=_RUNTIME_INSPECT_STDOUT_LIMIT,
                stderr_limit=_RUNTIME_INSPECT_STDERR_LIMIT,
            )
            if result is None:
                return None
            output = result.stdout.decode("utf-8")
            lines = output.splitlines()
            if len(lines) != len(expected_batch) or any(not line for line in lines):
                return None
            parsed: dict[str, ContainerSnapshot] = {}
            for line in lines:
                raw_record = json.loads(
                    line,
                    object_pairs_hook=_runtime_json_object,
                    parse_float=_compose_json_float,
                    parse_constant=_runtime_json_constant,
                )
                if type(raw_record) is not dict or not _compose_json_depth_within_limit(
                    raw_record
                ):
                    return None
                identity = raw_record.get("Id")
                if (
                    type(identity) is not str
                    or identity not in expected_batch
                    or identity in parsed
                ):
                    return None
                snapshot = _runtime_snapshot(admitted, evidence, identity, raw_record)
                if snapshot is None:
                    return None
                parsed[identity] = snapshot
            if set(parsed) != set(expected_batch):
                return None
            for container_id in expected_batch:
                if container_id in seen:
                    return None
                seen.add(container_id)
                snapshots.append(parsed[container_id])
            if not _live(deadline):
                return None
    except (UnicodeError, ValueError, RecursionError):
        return None
    if seen != set(ids) or not _live(deadline):
        return None
    return tuple(snapshots)


def observe_owned_core_runtime(
    owner: OwnerEvidence,
    pins: DockerReadPins,
    compose: ComposeConfigPins,
    *,
    deadline: Deadline,
    diagnostic: RuntimeObservationRecorder | None = None,
) -> RuntimeEvidence | None:
    """Collect private read-only owner-scoped inventory evidence under one deadline.

    Caller-supplied signed-owner/key provenance and the authority of the local
    Docker executable, config and socket remain external preconditions. The
    result is evidence for the existing coordinator validator, not an outage
    admission or a substitute for its inventory verdict.
    """
    if diagnostic is not None:
        diagnostic.reset()
        diagnostic.record(RuntimeObservationPhase.OWNER_PINS)
    admitted_owner = _compose_owner(owner)
    if admitted_owner is None or type(pins) is not DockerReadPins:
        return None
    try:
        admitted_pins = replace(pins)
        admitted_compose = replace(compose)
    except TypeError:
        return None
    if (
        admitted_pins.cwd != admitted_owner.worktree
        or admitted_pins.daemon_fingerprint != admitted_owner.daemon_fingerprint
        or not _live(deadline)
    ):
        return None

    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.DAEMON)
    daemon = observe_daemon_metadata(admitted_pins, deadline=deadline)
    if (
        type(daemon) is not DaemonMetadataResult
        or daemon.status is not DaemonMetadataStatus.MATCHED_METADATA
        or daemon.fingerprint != admitted_owner.daemon_fingerprint
        or not _live(deadline)
    ):
        return None
    if diagnostic is None:
        compose_result = observe_compose_metadata(
            admitted_owner,
            admitted_pins,
            admitted_compose,
            deadline=deadline,
        )
    else:
        diagnostic.record(RuntimeObservationPhase.COMPOSE_PREPARE)
        compose_result = observe_compose_metadata(
            admitted_owner,
            admitted_pins,
            admitted_compose,
            deadline=deadline,
            diagnostic=diagnostic,
        )
    if type(compose_result) is not ComposeMetadataResult:
        return None
    if diagnostic is not None and diagnostic.phase is None:
        diagnostic.record(RuntimeObservationPhase.COMPOSE_BINDING)
    metadata = _runtime_metadata_pair(
        compose_coordinator_metadata(admitted_owner, daemon, compose_result)
    )
    evidence = (
        _runtime_compose_evidence(metadata, compose_result.evidence)
        if metadata is not None
        else None
    )
    if metadata is None or evidence is None or not _live(deadline):
        return None

    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.CONTAINER_IDS_PREPARE)
    id_request = prepare_container_id_read(metadata, admitted_pins, deadline=deadline)
    if id_request is None:
        return None
    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.DAEMON)
    if not _pinned_daemon_matches(metadata, admitted_pins, deadline=deadline):
        return None
    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.CONTAINER_IDS_PROCESS)
    id_result = _run_pinned_docker_process(admitted_pins, id_request, deadline=deadline)
    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.DAEMON)
    if not _pinned_daemon_matches(metadata, admitted_pins, deadline=deadline):
        return None
    if diagnostic is not None:
        process_ok = (
            _bounded_process_result(
                id_result,
                stdout_limit=_RUNTIME_CONTAINER_ID_STDOUT_LIMIT,
                stderr_limit=_RUNTIME_INSPECT_STDERR_LIMIT,
            )
            is not None
        )
        diagnostic.record(
            RuntimeObservationPhase.CONTAINER_IDS_DECODE
            if process_ok
            else RuntimeObservationPhase.CONTAINER_IDS_PROCESS
        )
    container_ids = decode_container_id_read(id_result, metadata, deadline=deadline)
    if container_ids is None:
        return None

    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.INSPECT_PREPARE)
    inspect_requests = prepare_container_inspect_reads(
        metadata,
        admitted_pins,
        container_ids,
        deadline=deadline,
    )
    if inspect_requests is None:
        return None
    inspect_results: list[PrivateProcessResult] = []
    for request in inspect_requests:
        if diagnostic is not None:
            diagnostic.record(RuntimeObservationPhase.DAEMON)
        if not _pinned_daemon_matches(metadata, admitted_pins, deadline=deadline):
            return None
        if diagnostic is not None:
            diagnostic.record(RuntimeObservationPhase.INSPECT_PROCESS)
        result = _run_pinned_docker_process(admitted_pins, request, deadline=deadline)
        if diagnostic is not None:
            diagnostic.record(RuntimeObservationPhase.DAEMON)
        if not _pinned_daemon_matches(metadata, admitted_pins, deadline=deadline):
            return None
        inspect_results.append(result)

    if diagnostic is not None:
        process_ok = all(
            _bounded_process_result(
                result,
                stdout_limit=_RUNTIME_INSPECT_STDOUT_LIMIT,
                stderr_limit=_RUNTIME_INSPECT_STDERR_LIMIT,
            )
            is not None
            for result in inspect_results
        )
        diagnostic.record(
            RuntimeObservationPhase.INSPECT_DECODE
            if process_ok
            else RuntimeObservationPhase.INSPECT_PROCESS
        )
    containers = decode_container_inspect_reads(
        metadata,
        evidence,
        container_ids,
        tuple(inspect_results),
        deadline=deadline,
    )
    if containers is None:
        return None
    if diagnostic is not None:
        diagnostic.record(RuntimeObservationPhase.RUNTIME_BINDING)
    if not _live(deadline):
        return None
    runtime_evidence = RuntimeEvidence(
        daemon_fingerprint=metadata.daemon_fingerprint,
        resource_fingerprint=metadata.resource_fingerprint,
        containers=containers,
    )
    if diagnostic is not None:
        diagnostic.reset()
    return runtime_evidence
