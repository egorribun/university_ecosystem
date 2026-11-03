"""Bounded, private, exact-request projection from one verified backend container."""

from __future__ import annotations

import json
from uuid import UUID

from scripts import owned_nats_docker as docker
from scripts.owned_nats_coordinator import (
    BackendFailureCategory,
    BackendFailureDiagnostic,
    BackendFailureKind,
    OwnerEvidence,
    RuntimeEvidence,
    valid_backend_diagnostic,
)
from scripts.owned_nats_outage import ContainerSnapshot, Deadline
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)

_MAX_BYTES = 65536
_MAX_JSON_DEPTH = 32
_EVENT = "request_failure_diagnostic"
_RECORD_KEYS = frozenset(
    {
        "message",
        "logger",
        "diagnostic_request_id",
        "diagnostic_category",
        "diagnostic_kind",
        "diagnostic_sqlstate",
    }
)


def _request_id(value: object) -> bool:
    if type(value) is not str or len(value) != 36:
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate diagnostic key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid diagnostic constant")


def _json_depth_within_limit(raw: bytes) -> bool:
    """Bound decoder work independently of interpreter recursion settings.

    Brackets inside strings are data, including after escaped backslashes or
    quotes. The JSON decoder remains responsible for validating JSON syntax.
    """
    depth = 0
    quoted = False
    escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                quoted = False
        elif byte == ord('"'):
            quoted = True
        elif byte in b"{[":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                return False
        elif byte in b"}]":
            depth -= 1
    return True


def project_backend_failure(
    stdout: bytes, stderr: bytes, request_id: str
) -> BackendFailureDiagnostic | None:
    """Never format raw records; ambiguous, partial or unmatched evidence is unknown."""
    if (
        not _request_id(request_id)
        or type(stdout) is not bytes
        or type(stderr) is not bytes
        or len(stdout) + len(stderr) > _MAX_BYTES
        or any(stream and not stream.endswith(b"\n") for stream in (stdout, stderr))
    ):
        return None
    if len(stdout.splitlines()) + len(stderr.splitlines()) > 64:
        return None
    matches: list[BackendFailureDiagnostic] = []
    for stream in (stdout, stderr):
        for line in stream.splitlines():
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                return None
            # The producer emits UTF-8 without BOM. Decode explicitly: passing
            # bytes to json.loads also admits UTF-16/32 outside this byte guard.
            if "\x00" in text or text.lstrip().startswith("\ufeff"):
                return None
            if line.lstrip().startswith((b"{", b"[")) and not _json_depth_within_limit(
                line
            ):
                return None
            try:
                row = json.loads(
                    text,
                    object_pairs_hook=_unique_pairs,
                    parse_constant=_reject_constant,
                )
            except (ValueError, RecursionError):
                if line.lstrip().startswith(b"{"):
                    return None
                continue
            if type(row) is not dict or row.get("message") != _EVENT:
                continue
            if row.get("logger") != "app.core.request_failure_diagnostic":
                continue
            if row.get("diagnostic_request_id") != request_id:
                continue
            if row.keys() != _RECORD_KEYS:
                return None
            category = row.get("diagnostic_category")
            kind = row.get("diagnostic_kind")
            sqlstate = row.get("diagnostic_sqlstate")
            if any(type(value) is not str for value in (category, kind, sqlstate)):
                return None
            try:
                projected = BackendFailureDiagnostic(
                    BackendFailureCategory(category), BackendFailureKind(kind), sqlstate
                )
            except ValueError:
                return None
            if not valid_backend_diagnostic(projected):
                return None
            matches.append(projected)
    return matches[0] if len(matches) == 1 else None


def _backend(snapshot: object, owner: OwnerEvidence) -> ContainerSnapshot | None:
    if (
        type(snapshot) is not RuntimeEvidence
        or snapshot.daemon_fingerprint != owner.daemon_fingerprint
        or snapshot.resource_fingerprint != owner.compose_resource_fingerprint
    ):
        return None
    records = [row for row in snapshot.containers if row.service == "backend"]
    if len(records) != 1:
        return None
    backend = records[0]
    if not backend.running or backend.status != "running" or backend.oom_killed:
        return None
    return backend


def capture_backend_failure(
    owner: OwnerEvidence,
    pins: docker.DockerReadPins,
    compose: docker.ComposeConfigPins,
    request_id: str,
    *,
    deadline: Deadline,
) -> BackendFailureDiagnostic | None:
    """Use existing pinned executable/daemon and signed closure validation twice."""
    if not _request_id(request_id) or not docker._live(deadline):
        return None
    before = docker.observe_owned_core_runtime(owner, pins, compose, deadline=deadline)
    backend = _backend(before, owner)
    if backend is None:
        return None
    prepared = docker.prepare_daemon_read(pins, deadline=deadline)
    if prepared is None:
        return None
    request = PrivateProcessRequest(
        argv=(*prepared.argv[:5], "logs", "--tail", "64", backend.container_id),
        cwd=prepared.cwd,
        env=dict(prepared.env),
        stdin=b"",
        stdout_limit=_MAX_BYTES,
        stderr_limit=_MAX_BYTES,
        input_limit=0,
    )
    result = docker._run_pinned_docker_process(pins, request, deadline=deadline)
    if (
        type(result) is not PrivateProcessResult
        or result.outcome is not ProcessOutcome.EXITED
        or type(result.returncode) is not int
        or result.returncode != 0
        or result.local_cleanup is not LocalCleanup.CONFIRMED
    ):
        return None
    after = docker.observe_owned_core_runtime(owner, pins, compose, deadline=deadline)
    if _backend(after, owner) != backend or not docker._live(deadline):
        return None
    return project_backend_failure(result.stdout, result.stderr, request_id)
