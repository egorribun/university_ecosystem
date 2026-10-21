from __future__ import annotations

import json
import secrets
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import owned_nats_broker_control as broker
from scripts import owned_nats_docker as docker
from scripts import owned_nats_http_adapter as http
from scripts import owned_nats_process as process
from scripts import owned_nats_sql_adapter as sql
from scripts import owned_nats_transport_port as transport_port
from scripts.owned_nats_coordinator import OwnerEvidence, RuntimeEvidence
from scripts.owned_nats_outage import (
    ContainerSnapshot,
    Deadline,
    WorkerPolicy,
)
from scripts.owned_nats_owner_adapter import OwnerFilePins, SignedOwnerLeasePort
from scripts.owned_nats_runtime_adapter import OwnedCoreRuntimePort

_NOW = 0.0
_OWNER = OwnerEvidence(
    repository=r"C:\private\repo",
    worktree=r"C:\private\repo",
    project_name="private-live-project",
    published_ports=(("backend", 12345),),
    schema_version=11,
    daemon_fingerprint="a" * 64,
    compose_resource_fingerprint="b" * 64,
    resume_compose_resource_fingerprint=None,
    resume_compose_resource_schema_version=None,
    source_sha="c" * 40,
    stack="core",
    service_roots=("backend", "frontend"),
    selected_services=("outbox-worker", "nats", "postgres", "backend"),
)
_WORKER = ContainerSnapshot(
    container_id="d" * 64,
    service="outbox-worker",
    identity="e" * 64,
    running=True,
    status="running",
    health=None,
    restart_count=0,
    exit_code=0,
    oom_killed=False,
)


def _deadline() -> Deadline:
    return Deadline.after(20.0, clock=lambda: _NOW)


def _port() -> transport_port.OwnedNatsTransportPort:
    owner_pins = OwnerFilePins(
        repository=r"C:\private\repo",
        state_root=r"C:\private\repo",
        source_sha="c" * 40,
        owner_uid=1000,
    )
    docker_pins = docker.DockerReadPins(
        executable=r"C:\private\docker.exe",
        endpoint="npipe:////./pipe/private-docker",
        config_directory=r"C:\private\docker-config",
        cwd=r"C:\private\repo",
        environment=(("PATH", r"C:\private\bin"),),
        daemon_fingerprint="a" * 64,
    )
    compose_pins = docker.ComposeConfigPins(
        project_directory=r"C:\private\repo",
        env_file=r"C:\private\repo\.env.private",
        compose_files=(
            r"C:\private\repo\docker-compose.full.yml",
            r"C:\private\repo\docker-compose.live.yml",
        ),
    )
    return transport_port.OwnedNatsTransportPort(
        owner_pins,
        docker_pins,
        compose_pins,
        sleep=lambda _seconds: None,
    )


def _successful_process(stdout: bytes) -> process.PrivateProcessResult:
    return process.PrivateProcessResult(
        outcome=process.ProcessOutcome.EXITED,
        returncode=0,
        stdout=stdout,
        stderr=b"",
        local_cleanup=process.LocalCleanup.CONFIRMED,
    )


def _inspect_lines(
    *,
    env: tuple[str, ...] = (),
    project: str = _OWNER.project_name,
    service: str = "outbox-worker",
    oneoff: str = "False",
    running: bool = True,
    status: str = "running",
    command_matches: bool = True,
    entrypoint_matches: bool = True,
) -> bytes:
    header = {
        "id": _WORKER.container_id,
        "project": project,
        "service": service,
        "oneoff": oneoff,
        "running": running,
        "status": status,
        "command_matches": command_matches,
        "entrypoint_matches": entrypoint_matches,
    }
    rows = [json.dumps(header, separators=(",", ":"))]
    rows.extend(json.dumps(value, separators=(",", ":")) for value in env)
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_composite_wires_one_owner_lease_runtime_and_all_adapters() -> None:
    port = _port()

    assert type(port._owner_port) is SignedOwnerLeasePort
    assert type(port._runtime) is OwnedCoreRuntimePort
    assert port._runtime._owner_port is port._owner_port
    assert port._sql._owner_port is port._owner_port
    assert port._http._owner_port is port._owner_port
    assert port._broker._runtime is port._runtime
    assert port._sql._docker_pins == port._broker._pins == port._runtime._docker_pins
    assert (
        port._sql._compose_pins == port._broker._compose == port._runtime._compose_pins
    )
    assert repr(port) == "<OwnedNatsTransportPort>"


def test_coordinator_callbacks_delegate_once_with_same_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    deadline = _deadline()
    owner = _OWNER
    worker = _WORKER
    postgres = replace(worker, service="postgres", container_id="f" * 64)
    sentinel = object()
    calls: list[tuple[str, tuple[object, ...], object]] = []

    def make(name: str, result: object) -> object:
        def operation(self: object, *args: object, deadline: object) -> object:
            calls.append((name, args, deadline))
            return result

        return operation

    delegation = (
        (broker.OwnedNatsBrokerControlPort, "acquire_lock", sentinel),
        (broker.OwnedNatsBrokerControlPort, "release_lock", None),
        (broker.OwnedNatsBrokerControlPort, "read_signed_owner", owner),
        (
            broker.OwnedNatsBrokerControlPort,
            "observe_runtime",
            RuntimeEvidence("a" * 64, "b" * 64, (worker,)),
        ),
        (broker.OwnedNatsBrokerControlPort, "inspect_container", worker),
        (sql.OwnedNatsSqlAdapter, "read_admission", sentinel),
        (sql.OwnedNatsSqlAdapter, "read_dm", sentinel),
        (sql.OwnedNatsSqlAdapter, "pending_count", 0),
        (sql.OwnedNatsSqlAdapter, "read_correlation", sentinel),
        (sql.OwnedNatsSqlAdapter, "outbox_state", sentinel),
        (http.OwnedNatsHttpPort, "login_admin", sentinel),
        (http.OwnedNatsHttpPort, "create_dm_once", sentinel),
        (http.OwnedNatsHttpPort, "send_message_once", sentinel),
        (broker.OwnedNatsBrokerControlPort, "stop_container", sentinel),
        (broker.OwnedNatsBrokerControlPort, "start_container", sentinel),
        (broker.OwnedNatsBrokerControlPort, "broker_last_message", sentinel),
    )
    for adapter, method, result in delegation:
        monkeypatch.setattr(adapter, method, make(method, result))

    cases = (
        ("acquire_lock", (), sentinel),
        ("release_lock", (sentinel,), None),
        ("read_signed_owner", (), owner),
        (
            "observe_runtime",
            (owner, "a" * 64),
            RuntimeEvidence("a" * 64, "b" * 64, (worker,)),
        ),
        ("inspect_container", (worker.container_id, "a" * 64), worker),
        ("read_admission", (owner, postgres), sentinel),
        ("read_dm", (owner, postgres, "chat-id"), sentinel),
        ("pending_count", (owner, postgres), 0),
        ("read_correlation", (owner, postgres, "message-id"), sentinel),
        ("outbox_state", (owner, postgres, "event-id"), sentinel),
        ("login_admin", (owner, "admin-id"), sentinel),
        ("create_dm_once", ("peer-id",), sentinel),
        ("send_message_once", ("chat-id", "private message"), sentinel),
        ("stop_container", (worker.container_id, "a" * 64), sentinel),
        ("start_container", (worker.container_id, "a" * 64), sentinel),
        ("broker_last_message", (owner, worker, "messages.created"), sentinel),
    )
    for method, args, result in cases:
        assert getattr(port, method)(*args, deadline=deadline) == result

    assert [name for name, _, _ in calls] == [method for method, _, _ in cases]
    assert all(seen_deadline is deadline for _, _, seen_deadline in calls)
    assert [args for _, args, _ in calls] == [args for _, args, _ in cases]


def test_write_failure_is_closed_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    attempts = 0

    def ambiguous(*_args: object, **_kwargs: object) -> object:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("private credential-shaped value")

    monkeypatch.setattr(http.OwnedNatsHttpPort, "send_message_once", ambiguous)
    with pytest.raises(transport_port.TransportPortNotReady) as raised:
        port.send_message_once("chat-id", "private content", deadline=_deadline())

    assert attempts == 1
    assert str(raised.value) == "NATS transport is not ready"
    assert "private credential-shaped value" not in repr(raised.value)


def test_close_attempts_http_and_broker_with_same_deadline_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    deadline = _deadline()
    seen: list[tuple[str, object]] = []

    def close_http(self: object, *, deadline: object) -> None:
        seen.append(("http", deadline))
        raise RuntimeError("private http detail")

    def close_broker(self: object, *, deadline: object) -> None:
        seen.append(("broker", deadline))

    monkeypatch.setattr(http.OwnedNatsHttpPort, "close_clients", close_http)
    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort, "close_clients", close_broker
    )

    with pytest.raises(transport_port.TransportPortNotReady):
        port.close_clients(deadline=deadline)

    assert seen == [("http", deadline), ("broker", deadline)]


def test_policy_decoder_accepts_only_exact_inspected_worker_metadata() -> None:
    decoded = transport_port._decode_worker_policy_inspect(
        _inspect_lines(
            env=(
                "OUTBOX_POLL_INTERVAL_SECONDS=2.5",
                "outbox_batch_size=4",
                "OUTBOX_MAX_RETRIES=5",
            )
        ),
        owner=_OWNER,
        worker=_WORKER,
    )

    assert decoded == WorkerPolicy(2.5, 4, 5)


@pytest.mark.parametrize(
    "mutations",
    (
        {"project": "foreign-project"},
        {"service": "backend"},
        {"oneoff": "True"},
        {"oneoff": "malformed"},
        {"running": False, "status": "exited"},
        {"status": "restarting"},
        {"command_matches": False},
        {"entrypoint_matches": False},
    ),
)
def test_policy_decoder_rejects_unbound_or_nonrunning_worker(
    mutations: dict[str, object],
) -> None:
    decoded = transport_port._decode_worker_policy_inspect(
        _inspect_lines(**mutations), owner=_OWNER, worker=_WORKER
    )

    assert decoded is None


@pytest.mark.parametrize(
    "env",
    (
        ("OUTBOX_POLL_INTERVAL_SECONDS=2", "outbox_poll_interval_seconds=3"),
        ("OUTBOX_POLL_INTERVAL_SECONDS=nan",),
        ("OUTBOX_BATCH_SIZE=1",),
        ("OUTBOX_MAX_RETRIES=4",),
        ("OUTBOX_POLL_INTERVAL_SECONDS=",),
        ("ENV_FILE_PATH=/private/config.env",),
    ),
)
def test_policy_decoder_rejects_duplicate_invalid_and_alternate_file_settings(
    env: tuple[str, ...],
) -> None:
    decoded = transport_port._decode_worker_policy_inspect(
        _inspect_lines(env=env), owner=_OWNER, worker=_WORKER
    )

    assert decoded is None


def test_missing_policy_environment_uses_source_bound_settings_defaults() -> None:
    decoded = transport_port._decode_worker_policy_inspect(
        _inspect_lines(), owner=_OWNER, worker=_WORKER
    )

    assert decoded == WorkerPolicy(5.0, 20, 5)


def test_policy_inspection_uses_only_pinned_daemon_captured_worker_and_closed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    deadline = _deadline()
    baseline = RuntimeEvidence("a" * 64, "b" * 64, (_WORKER,))
    port._broker._owner = _OWNER
    port._broker._baseline = baseline
    port._broker._by_service = {"outbox-worker": _WORKER}
    port._broker._by_id = {_WORKER.container_id: _WORKER}
    deadlines: list[object] = []

    def read_owner(self: object, *, deadline: Deadline) -> OwnerEvidence:
        deadlines.append(deadline)
        return _OWNER

    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "_active", lambda *_: True)
    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort, "read_signed_owner", read_owner
    )

    def observe(
        pins: docker.DockerReadPins, *, deadline: Deadline
    ) -> docker.DaemonMetadataResult:
        deadlines.append(deadline)
        return docker.DaemonMetadataResult(
            docker.DaemonMetadataStatus.MATCHED_METADATA, "a" * 64
        )

    monkeypatch.setattr(
        docker,
        "observe_daemon_metadata",
        observe,
    )
    seen: list[process.PrivateProcessRequest] = []

    def prepare(
        pins: docker.DockerReadPins, *, deadline: Deadline
    ) -> process.PrivateProcessRequest:
        deadlines.append(deadline)
        return process.PrivateProcessRequest(
            argv=(
                pins.executable,
                "--config",
                pins.config_directory,
                "--host",
                pins.endpoint,
                "info",
            ),
            cwd=pins.cwd,
            env=dict(pins.environment),
            stdin=b"",
            stdout_limit=256,
            stderr_limit=1024,
            input_limit=0,
        )

    def run(
        request: process.PrivateProcessRequest, *, deadline: Deadline
    ) -> process.PrivateProcessResult:
        deadlines.append(deadline)
        seen.append(request)
        return _successful_process(_inspect_lines())

    monkeypatch.setattr(docker, "prepare_daemon_read", prepare)
    monkeypatch.setattr(process, "run_private_process", run)

    result = port.read_policy(_OWNER, _WORKER, deadline=deadline)

    assert result == WorkerPolicy(5.0, 20, 5)
    assert len(seen) == 1
    assert seen[0].argv[:5] == (
        r"C:\private\docker.exe",
        "--config",
        r"C:\private\docker-config",
        "--host",
        "npipe:////./pipe/private-docker",
    )
    assert seen[0].argv[-1] == _WORKER.container_id
    assert seen[0].stdout_limit <= 8192
    assert seen[0].stderr_limit <= 1024
    assert seen[0].stdin == b""
    assert "DATABASE_URL" not in seen[0].argv[-2]
    assert "private" not in repr(result)
    assert len(deadlines) == 6
    assert all(seen_deadline is deadline for seen_deadline in deadlines)


@pytest.mark.parametrize("drift", ("owner", "daemon"))
def test_policy_rejects_owner_or_daemon_drift_after_inspect(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    port = _port()
    deadline = _deadline()
    port._broker._owner = _OWNER
    port._broker._baseline = RuntimeEvidence("a" * 64, "b" * 64, (_WORKER,))
    port._broker._by_service = {"outbox-worker": _WORKER}
    port._broker._by_id = {_WORKER.container_id: _WORKER}
    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "_active", lambda *_: True)
    owner_calls = 0

    def read_owner(self: object, *, deadline: Deadline) -> OwnerEvidence:
        nonlocal owner_calls
        owner_calls += 1
        if drift == "owner" and owner_calls == 2:
            return replace(_OWNER, source_sha="f" * 40)
        return _OWNER

    daemon_calls = 0

    def observe(
        pins: docker.DockerReadPins, *, deadline: Deadline
    ) -> docker.DaemonMetadataResult:
        nonlocal daemon_calls
        daemon_calls += 1
        if drift == "daemon" and daemon_calls == 2:
            return docker.DaemonMetadataResult(
                docker.DaemonMetadataStatus.MATCHED_METADATA, "f" * 64
            )
        return docker.DaemonMetadataResult(
            docker.DaemonMetadataStatus.MATCHED_METADATA, "a" * 64
        )

    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort, "read_signed_owner", read_owner
    )
    monkeypatch.setattr(docker, "observe_daemon_metadata", observe)
    monkeypatch.setattr(
        docker,
        "prepare_daemon_read",
        lambda pins, *, deadline: process.PrivateProcessRequest(
            argv=(
                pins.executable,
                "--config",
                pins.config_directory,
                "--host",
                pins.endpoint,
                "info",
            ),
            cwd=pins.cwd,
            env=dict(pins.environment),
            stdin=b"",
        ),
    )
    inspected = 0

    def run(
        request: process.PrivateProcessRequest, *, deadline: Deadline
    ) -> process.PrivateProcessResult:
        nonlocal inspected
        inspected += 1
        return _successful_process(_inspect_lines())

    monkeypatch.setattr(process, "run_private_process", run)

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_policy(_OWNER, _WORKER, deadline=deadline)

    assert inspected == 1
    assert owner_calls == 2
    assert daemon_calls == 2


def test_policy_stops_followup_checks_when_inspect_exhausts_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    now = {"value": 0.0}
    deadline = Deadline.after(20.0, clock=lambda: now["value"])
    port._broker._owner = _OWNER
    port._broker._baseline = RuntimeEvidence("a" * 64, "b" * 64, (_WORKER,))
    port._broker._by_service = {"outbox-worker": _WORKER}
    port._broker._by_id = {_WORKER.container_id: _WORKER}
    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "_active", lambda *_: True)
    owner_calls = 0
    daemon_calls = 0

    def read_owner(self: object, *, deadline: Deadline) -> OwnerEvidence:
        nonlocal owner_calls
        owner_calls += 1
        return _OWNER

    def observe(
        pins: docker.DockerReadPins, *, deadline: Deadline
    ) -> docker.DaemonMetadataResult:
        nonlocal daemon_calls
        daemon_calls += 1
        return docker.DaemonMetadataResult(
            docker.DaemonMetadataStatus.MATCHED_METADATA, "a" * 64
        )

    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort, "read_signed_owner", read_owner
    )
    monkeypatch.setattr(docker, "observe_daemon_metadata", observe)
    monkeypatch.setattr(
        docker,
        "prepare_daemon_read",
        lambda pins, *, deadline: process.PrivateProcessRequest(
            argv=(
                pins.executable,
                "--config",
                pins.config_directory,
                "--host",
                pins.endpoint,
                "info",
            ),
            cwd=pins.cwd,
            env=dict(pins.environment),
            stdin=b"",
        ),
    )

    def run(
        request: process.PrivateProcessRequest, *, deadline: Deadline
    ) -> process.PrivateProcessResult:
        now["value"] = 21.0
        return _successful_process(_inspect_lines())

    monkeypatch.setattr(process, "run_private_process", run)

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_policy(_OWNER, _WORKER, deadline=deadline)

    assert owner_calls == 1
    assert daemon_calls == 1


def test_policy_does_not_read_owner_after_post_inspect_daemon_check_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    now = {"value": 0.0}
    deadline = Deadline.after(20.0, clock=lambda: now["value"])
    port._broker._owner = _OWNER
    port._broker._baseline = RuntimeEvidence("a" * 64, "b" * 64, (_WORKER,))
    port._broker._by_service = {"outbox-worker": _WORKER}
    port._broker._by_id = {_WORKER.container_id: _WORKER}
    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "_active", lambda *_: True)
    owner_calls = 0
    daemon_calls = 0

    def read_owner(self: object, *, deadline: Deadline) -> OwnerEvidence:
        nonlocal owner_calls
        owner_calls += 1
        return _OWNER

    def observe(
        pins: docker.DockerReadPins, *, deadline: Deadline
    ) -> docker.DaemonMetadataResult:
        nonlocal daemon_calls
        daemon_calls += 1
        if daemon_calls == 2:
            now["value"] = 21.0
            return docker.DaemonMetadataResult(docker.DaemonMetadataStatus.NOT_READY)
        return docker.DaemonMetadataResult(
            docker.DaemonMetadataStatus.MATCHED_METADATA, "a" * 64
        )

    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort, "read_signed_owner", read_owner
    )
    monkeypatch.setattr(docker, "observe_daemon_metadata", observe)
    monkeypatch.setattr(
        docker,
        "prepare_daemon_read",
        lambda pins, *, deadline: process.PrivateProcessRequest(
            argv=(
                pins.executable,
                "--config",
                pins.config_directory,
                "--host",
                pins.endpoint,
                "info",
            ),
            cwd=pins.cwd,
            env=dict(pins.environment),
            stdin=b"",
        ),
    )
    monkeypatch.setattr(
        process,
        "run_private_process",
        lambda request, *, deadline: _successful_process(_inspect_lines()),
    )

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_policy(_OWNER, _WORKER, deadline=deadline)

    assert daemon_calls == 2
    assert owner_calls == 1


def test_policy_rejects_caller_worker_before_inspect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    port._broker._owner = _OWNER
    port._broker._baseline = RuntimeEvidence("a" * 64, "b" * 64, (_WORKER,))
    port._broker._by_service = {"outbox-worker": _WORKER}
    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "_active", lambda *_: True)
    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort,
        "read_signed_owner",
        lambda *_args, **_kwargs: _OWNER,
    )
    called = False

    def should_not_run(
        *_args: object, **_kwargs: object
    ) -> process.PrivateProcessResult:
        nonlocal called
        called = True
        return _successful_process(b"{}\n")

    monkeypatch.setattr(process, "run_private_process", should_not_run)
    foreign_worker = replace(_WORKER, container_id="1" * 64)

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_policy(_OWNER, foreign_worker, deadline=_deadline())

    assert not called


def test_policy_output_and_errors_do_not_include_unrelated_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _port()
    port._broker._owner = _OWNER
    port._broker._baseline = RuntimeEvidence("a" * 64, "b" * 64, (_WORKER,))
    port._broker._by_service = {"outbox-worker": _WORKER}
    port._broker._by_id = {_WORKER.container_id: _WORKER}
    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "_active", lambda *_: True)
    monkeypatch.setattr(
        broker.OwnedNatsBrokerControlPort,
        "read_signed_owner",
        lambda *_args, **_kwargs: _OWNER,
    )
    monkeypatch.setattr(
        docker,
        "observe_daemon_metadata",
        lambda *_args, **_kwargs: docker.DaemonMetadataResult(
            docker.DaemonMetadataStatus.MATCHED_METADATA, "a" * 64
        ),
    )
    monkeypatch.setattr(
        docker,
        "prepare_daemon_read",
        lambda *_args, **_kwargs: process.PrivateProcessRequest(
            argv=("docker", "--config", "pin", "--host", "endpoint", "info"),
            cwd="C:\\private\\repo",
            env={},
            stdin=b"",
        ),
    )
    secret = secrets.token_urlsafe(24)
    monkeypatch.setattr(
        process,
        "run_private_process",
        lambda *_args, **_kwargs: _successful_process(
            _inspect_lines(env=(f"OUTBOX_BATCH_SIZE={secret}",))
        ),
    )

    with pytest.raises(transport_port.TransportPortNotReady) as raised:
        port.read_policy(_OWNER, _WORKER, deadline=_deadline())

    assert secret not in str(raised.value)
    assert secret not in repr(raised.value)
    assert secret not in repr(port)


def test_policy_template_projects_only_public_worker_fields() -> None:
    template = transport_port._POLICY_INSPECT_FORMAT

    assert "DATABASE_URL" not in template
    assert "NATS_URL" not in template
    assert 'split . "="' in template
    assert "outbox_poll_interval_seconds" in template
    assert "outbox_batch_size" in template
    assert "outbox_max_retries" in template
    assert ".Config.Env" in template
    assert "{{println}}{{range .Config.Env}}" in template
    assert "{{println (json .)}}" in template


def test_policy_static_defaults_remain_bound_to_effective_worker_sources() -> None:
    repo = Path(__file__).parents[1]
    notifications = (repo / "app/core/config/notifications.py").read_text(
        encoding="utf-8"
    )
    infrastructure = (repo / "app/core/di/infrastructure.py").read_text(
        encoding="utf-8"
    )
    worker = (repo / "app/workers/outbox.py").read_text(encoding="utf-8")
    full = (repo / "docker-compose.full.yml").read_text(encoding="utf-8")
    live = (repo / "docker-compose.live.yml").read_text(encoding="utf-8")
    dockerfile = (repo / "backend.Dockerfile").read_text(encoding="utf-8")
    config_base = (repo / "app/core/config/base.py").read_text(encoding="utf-8")

    assert "outbox_poll_interval_seconds: float = 5.0" in notifications
    assert "outbox_batch_size: int = 20" in notifications
    assert "outbox_max_retries: int = 5" in notifications
    assert "poll_interval=settings.outbox_poll_interval_seconds" in infrastructure
    assert "batch_size=settings.outbox_batch_size" in infrastructure
    assert "max_retries=settings.outbox_max_retries" in infrastructure
    assert "settings.outbox_poll_interval_seconds" in worker
    assert "settings.outbox_batch_size" in worker
    assert "settings.outbox_max_retries" in worker
    assert "command: python -m app.workers.outbox" in full
    assert "outbox-worker:\n    environment: *live-delivery" in live
    assert "COPY --chown=app:app app ./app" in dockerfile
    assert "COPY --chown=app:app .env" not in dockerfile
    assert "ENV_FILE_PATH" in config_base
    assert "case_sensitive=False" in config_base


def test_transport_forwards_only_exact_runtime_diagnostic(monkeypatch):
    from scripts.owned_nats_coordinator import RuntimeObservationPhase

    port = _port()
    for supplied, expected in (
        (RuntimeObservationPhase.DAEMON, RuntimeObservationPhase.DAEMON),
        ("daemon", None),
        (None, None),
    ):
        monkeypatch.setattr(
            OwnedCoreRuntimePort,
            "runtime_diagnostic",
            property(lambda _self, value=supplied: value),
            raising=False,
        )
        assert port.runtime_diagnostic is expected
