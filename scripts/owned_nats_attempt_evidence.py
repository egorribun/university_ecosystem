"""Private exact-event deferral proof from the authenticated outbox worker."""

from __future__ import annotations

import json

from scripts import owned_nats_docker as docker
from scripts.owned_nats_coordinator import OwnerEvidence, RuntimeEvidence
from scripts.owned_nats_failure_diagnostic import (
    _json_depth_within_limit,
    _reject_constant,
    _unique_pairs,
)
from scripts.owned_nats_outage import ContainerSnapshot, Deadline, _is_canonical_uuid
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)

_MAX_BYTES = 65536
_RECORD_KEYS = frozenset({"message", "logger", "stored_event_id"})


def project_deferred_event(stdout: bytes, stderr: bytes, event_id: str) -> str | None:
    """Project only a canonical exact row ID; never return raw log content."""
    if (
        not _is_canonical_uuid(event_id)
        or type(stdout) is not bytes
        or type(stderr) is not bytes
        or len(stdout) + len(stderr) > _MAX_BYTES
        or any(stream and not stream.endswith(b"\n") for stream in (stdout, stderr))
        or len(stdout.splitlines()) + len(stderr.splitlines()) > 64
    ):
        return None
    found = False
    for stream in (stdout, stderr):
        for line in stream.splitlines():
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                return None
            if (
                "\x00" in text
                or text.lstrip().startswith("\ufeff")
                or not _json_depth_within_limit(line)
            ):
                return None
            try:
                row = json.loads(
                    text,
                    object_pairs_hook=_unique_pairs,
                    parse_constant=_reject_constant,
                )
            except (ValueError, RecursionError):
                if line.lstrip().startswith((b"{", b"[")):
                    return None
                continue
            if (
                type(row) is not dict
                or row.get("message") != "outbox_event_deferred"
                or row.get("logger") != "app.workers.outbox"
            ):
                continue
            if row.keys() != _RECORD_KEYS or not _is_canonical_uuid(
                row.get("stored_event_id")
            ):
                return None
            found |= row["stored_event_id"] == event_id
    return event_id if found else None


def _outage_pair(
    snapshot: object, owner: OwnerEvidence
) -> tuple[ContainerSnapshot, ContainerSnapshot] | None:
    if (
        type(snapshot) is not RuntimeEvidence
        or snapshot.daemon_fingerprint != owner.daemon_fingerprint
        or snapshot.resource_fingerprint != owner.compose_resource_fingerprint
    ):
        return None
    workers = [row for row in snapshot.containers if row.service == "outbox-worker"]
    brokers = [row for row in snapshot.containers if row.service == "nats"]
    if len(workers) != 1 or len(brokers) != 1:
        return None
    worker, broker = workers[0], brokers[0]
    if (
        worker.running is not True
        or worker.status != "running"
        or worker.oom_killed
        or broker.running is not False
        or broker.status != "exited"
        or broker.oom_killed
    ):
        return None
    return worker, broker


def capture_deferred_event(
    owner: OwnerEvidence,
    pins: docker.DockerReadPins,
    compose: docker.ComposeConfigPins,
    event_id: str,
    *,
    deadline: Deadline,
) -> str | None:
    """Bound a single read by signed owner closure, daemon and stopped broker.

    The coordinator creates the correlated event only after stopping NATS, so
    a marker for that exact row cannot predate this outage. Repeated markers are
    legitimate retries. Missing/rotated logs never prove an attempt.
    """
    if not _is_canonical_uuid(event_id) or not docker._live(deadline):
        return None
    before = docker.observe_owned_core_runtime(owner, pins, compose, deadline=deadline)
    pair = _outage_pair(before, owner)
    if pair is None:
        return None
    prepared = docker.prepare_daemon_read(pins, deadline=deadline)
    if prepared is None:
        return None
    request = PrivateProcessRequest(
        argv=(*prepared.argv[:5], "logs", "--tail", "64", pair[0].container_id),
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
    if _outage_pair(after, owner) != pair or not docker._live(deadline):
        return None
    return project_deferred_event(result.stdout, result.stderr, event_id)
