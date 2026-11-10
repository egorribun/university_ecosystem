"""Offline exact-event proof and bounded owner-scoped read contracts."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scripts import owned_nats_attempt_evidence as evidence
from scripts.owned_nats_coordinator import RuntimeEvidence
from scripts.owned_nats_process import PrivateProcessRequest, ProcessOutcome
from tests.test_owned_nats_transport_port import (
    _OWNER,
    _WORKER,
    _deadline,
    _port,
    _successful_process,
)

EVENT = "00000000-0000-7000-8000-000000000001"
OTHER = "00000000-0000-7000-8000-000000000002"


def record(**changes):
    row = dict(
        message="outbox_event_deferred",
        logger="app.workers.outbox",
        stored_event_id=EVENT,
    )
    row.update(changes)
    return json.dumps(row).encode() + b"\n"


def test_exact_event_can_be_repeated_without_ambiguity():
    assert evidence.project_deferred_event(record() * 2, b"", EVENT) == EVENT


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        record(stored_event_id=OTHER),
        record(logger="foreign"),
        record(message="other"),
        record(payload="private"),
        record()[:-1],
        record() * 65,
        b"{bad}\n",
        b'{"message":"outbox_event_deferred","message":"other"}\n',
        b"\xff\n",
        b"[" * 34 + b"\n",
    ],
)
def test_missing_unmatched_or_unbounded_proof_is_not_accepted(raw):
    assert evidence.project_deferred_event(raw, b"", EVENT) is None


def setup_collector(monkeypatch):
    port = _port()
    nats = replace(
        _WORKER,
        service="nats",
        container_id="b" * 64,
        running=False,
        status="exited",
        health=None,
    )
    runtime = RuntimeEvidence(
        _OWNER.daemon_fingerprint, _OWNER.compose_resource_fingerprint, (_WORKER, nats)
    )
    monkeypatch.setattr(
        evidence.docker, "observe_owned_core_runtime", lambda *a, **kw: runtime
    )
    monkeypatch.setattr(
        evidence.docker,
        "prepare_daemon_read",
        lambda *a, **kw: PrivateProcessRequest(
            argv=("docker", "--config", "private", "--host", "private"),
            cwd="private",
            env={},
        ),
    )
    reads = []

    def read(pins, request, *, deadline):
        reads.append(request)
        return _successful_process(record())

    monkeypatch.setattr(evidence.docker, "_run_pinned_docker_process", read)
    return port, runtime, reads


def test_bounded_collector_reads_exact_worker_while_nats_stopped(monkeypatch):
    port, _, reads = setup_collector(monkeypatch)
    assert (
        evidence.capture_deferred_event(
            _OWNER, port._docker_pins, port._compose_pins, EVENT, deadline=_deadline()
        )
        == EVENT
    )
    assert reads[0].argv[-4:] == ("logs", "--tail", "64", _WORKER.container_id)
    assert reads[0].stdout_limit == reads[0].stderr_limit == 65536


@pytest.mark.parametrize(
    "mode",
    [
        "worker_changed",
        "broker_running",
        "daemon_changed",
        "timed_out",
        "unprepared",
        "expired",
    ],
)
def test_collector_rejects_identity_or_liveness_loss(monkeypatch, mode):
    port, runtime, _ = setup_collector(monkeypatch)
    if mode == "worker_changed":
        after = replace(
            runtime,
            containers=(replace(_WORKER, identity="f" * 64), runtime.containers[1]),
        )
    elif mode == "broker_running":
        after = replace(
            runtime,
            containers=(
                _WORKER,
                replace(runtime.containers[1], running=True, status="running"),
            ),
        )
    elif mode == "daemon_changed":
        after = replace(runtime, daemon_fingerprint="foreign")
    else:
        after = runtime
    snapshots = iter((runtime, after))
    monkeypatch.setattr(
        evidence.docker, "observe_owned_core_runtime", lambda *a, **kw: next(snapshots)
    )
    if mode == "timed_out":
        monkeypatch.setattr(
            evidence.docker,
            "_run_pinned_docker_process",
            lambda *a, **kw: replace(
                _successful_process(record()), outcome=ProcessOutcome.TIMED_OUT
            ),
        )
    if mode == "unprepared":
        monkeypatch.setattr(
            evidence.docker, "prepare_daemon_read", lambda *a, **kw: None
        )
    if mode == "expired":
        monkeypatch.setattr(evidence.docker, "_live", lambda *a: False)
    assert (
        evidence.capture_deferred_event(
            _OWNER, port._docker_pins, port._compose_pins, EVENT, deadline=_deadline()
        )
        is None
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"plain unrelated text\n" + record(),
        b"[]\n" + record(),
        record(stored_event_id=OTHER) + record(),
    ],
)
def test_bounded_unrelated_logs_do_not_hide_exact_marker(raw):
    assert evidence.project_deferred_event(raw, b"", EVENT) == EVENT


@pytest.mark.parametrize(
    "raw",
    [
        record(stored_event_id=None),
        record(stored_event_id=""),
        b"\x00\n",
        b"\xef\xbb\xbf{}\n",
        b'{"x":NaN}\n',
        b"x" * 65537 + b"\n",
    ],
)
def test_malformed_marker_or_stream_fails_closed(raw):
    assert evidence.project_deferred_event(raw, b"", EVENT) is None


@pytest.mark.parametrize(
    "mode", ["accepted", "missing", "before_owner", "after_owner", "exception"]
)
def test_transport_authenticates_owner_on_both_sides(monkeypatch, mode):
    from scripts import owned_nats_transport_port as transport
    from scripts.owned_nats_owner_adapter import SignedOwnerLeasePort

    port = _port()
    owners = iter(
        (
            None if mode == "before_owner" else _OWNER,
            None if mode == "after_owner" else _OWNER,
        )
    )
    monkeypatch.setattr(
        SignedOwnerLeasePort, "read_signed_owner", lambda *a, **kw: next(owners)
    )
    calls = []

    def capture(owner, pins, compose, event, *, deadline):
        calls.append(event)
        if mode == "exception":
            raise RuntimeError("private")
        return None if mode == "missing" else EVENT

    monkeypatch.setattr(transport, "capture_deferred_event", capture)
    if mode in {"accepted", "missing"}:
        assert port.deferred_event(_OWNER, EVENT, deadline=_deadline()) == (
            EVENT if mode == "accepted" else None
        )
    else:
        with pytest.raises(transport.TransportPortNotReady):
            port.deferred_event(_OWNER, EVENT, deadline=_deadline())
    if mode == "before_owner":
        assert not calls


@pytest.mark.parametrize(
    "mode",
    [
        "missing_runtime",
        "missing_worker",
        "duplicate_worker",
        "missing_broker",
        "duplicate_broker",
        "resource_changed",
        "worker_stopped",
        "worker_bad_status",
        "worker_oom",
        "broker_bad_status",
        "broker_oom",
    ],
)
def test_collector_requires_owned_live_worker_and_stopped_broker_before_read(
    monkeypatch, mode
):
    port, runtime, reads = setup_collector(monkeypatch)
    worker, broker = runtime.containers
    if mode == "missing_runtime":
        runtime = None
    elif mode == "missing_worker":
        runtime = replace(runtime, containers=(broker,))
    elif mode == "duplicate_worker":
        runtime = replace(runtime, containers=(worker, worker, broker))
    elif mode == "missing_broker":
        runtime = replace(runtime, containers=(worker,))
    elif mode == "duplicate_broker":
        runtime = replace(runtime, containers=(worker, broker, broker))
    elif mode == "resource_changed":
        runtime = replace(runtime, resource_fingerprint="foreign")
    else:
        changes = {
            "worker_stopped": (replace(worker, running=False), broker),
            "worker_bad_status": (replace(worker, status="restarting"), broker),
            "worker_oom": (replace(worker, oom_killed=True), broker),
            "broker_bad_status": (worker, replace(broker, status="paused")),
            "broker_oom": (worker, replace(broker, oom_killed=True)),
        }
        runtime = replace(runtime, containers=changes[mode])
    monkeypatch.setattr(
        evidence.docker, "observe_owned_core_runtime", lambda *a, **kw: runtime
    )
    assert (
        evidence.capture_deferred_event(
            _OWNER, port._docker_pins, port._compose_pins, EVENT, deadline=_deadline()
        )
        is None
    )
    assert reads == []


@pytest.mark.parametrize("mode", ["missing", "bad_code", "failed_code", "cleanup"])
def test_collector_rejects_unconfirmed_log_read(monkeypatch, mode):
    from scripts.owned_nats_process import LocalCleanup

    port, _, _ = setup_collector(monkeypatch)
    result = _successful_process(record())
    result = {
        "missing": None,
        "bad_code": replace(result, returncode=True),
        "failed_code": replace(result, returncode=1),
        "cleanup": replace(result, local_cleanup=LocalCleanup.NOT_STARTED),
    }[mode]
    monkeypatch.setattr(
        evidence.docker, "_run_pinned_docker_process", lambda *a, **kw: result
    )
    assert (
        evidence.capture_deferred_event(
            _OWNER, port._docker_pins, port._compose_pins, EVENT, deadline=_deadline()
        )
        is None
    )


@pytest.mark.parametrize(
    "stdout,stderr,event",
    [
        (record(), b"", "invalid"),
        ("not-bytes", b"", EVENT),
        (record(), "not-bytes", EVENT),
        (b"", record(), EVENT),
    ],
)
def test_projection_validates_stream_types_and_supports_stderr(stdout, stderr, event):
    result = evidence.project_deferred_event(stdout, stderr, event)
    assert result == (EVENT if type(stderr) is bytes and stderr == record() else None)


def test_collector_rejects_invalid_event_without_runtime_read(monkeypatch):
    port, _, reads = setup_collector(monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("invalid event must not trigger a runtime read")

    monkeypatch.setattr(evidence.docker, "observe_owned_core_runtime", forbidden)
    assert (
        evidence.capture_deferred_event(
            _OWNER,
            port._docker_pins,
            port._compose_pins,
            "invalid",
            deadline=_deadline(),
        )
        is None
    )
    assert reads == []
