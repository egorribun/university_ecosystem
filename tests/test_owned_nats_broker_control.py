from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import runpy
import secrets
import sys
import time
import types
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import live_stand
from scripts.live_nats_transport import LifecycleLockLease
from scripts.owned_nats_coordinator import (
    BrokerErrorEvidence,
    BrokerProbePhase,
    CommandEvidence,
    OwnerEvidence,
    RuntimeEvidence,
)
from scripts.owned_nats_docker import ComposeConfigPins, DockerReadPins
from scripts.owned_nats_outage import ContainerSnapshot, Deadline
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessResult,
    ProcessOutcome,
)
from scripts.owned_nats_runtime_adapter import OwnedCoreRuntimePort

WORK = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "owned_nats_broker_control_private",
    WORK / "scripts" / "owned_nats_broker_control.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("private candidate module is unavailable")
broker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = broker
SPEC.loader.exec_module(broker)
UUID_CHAT = "11111111-1111-4111-8111-111111111111"
SUBJECT = f"chat.{UUID_CHAT}"
PROJECT = "ue-live-0123456789abcdef"
DAEMON = "a" * 64
RESOURCE = "b" * 64
_NATS_USERNAME = secrets.token_urlsafe(12)
_NATS_PASSWORD = secrets.token_urlsafe(24)
_DEFAULT_NATS_URL = f"nats://{_NATS_USERNAME}:{_NATS_PASSWORD}@nats:4222"
_OTHER_NATS_URL = (
    f"nats://{secrets.token_urlsafe(12)}:{secrets.token_urlsafe(24)}@nats:4222"
)
_TLS_NATS_URL = (
    f"tls://{secrets.token_urlsafe(12)}:{secrets.token_urlsafe(24)}@nats:4222"
)


def deadline(now: list[float] | None = None, seconds: float = 30) -> Deadline:
    if now is None:
        now = [100.0]
    return Deadline.after(seconds, clock=lambda: now[0])


def _configured_project(
    *,
    backend_url: str = _DEFAULT_NATS_URL,
    worker_url: str | None = None,
    extra_backend: dict[str, str] | None = None,
    extra_worker: dict[str, str] | None = None,
) -> dict[str, object]:
    backend = {"NATS_URL": backend_url}
    worker = {"NATS_URL": worker_url or backend_url}
    backend.update(extra_backend or {})
    worker.update(extra_worker or {})
    return {
        "services": {
            "backend": {"environment": backend},
            "outbox-worker": {"environment": worker},
        }
    }


def _inspect_record(
    container_id: str,
    service: str,
    *,
    nats_url: str = _DEFAULT_NATS_URL,
) -> dict[str, object]:
    env = [f"NATS_URL={nats_url}"]
    return {
        "Id": container_id,
        "Labels": {
            "com.docker.compose.project": PROJECT,
            "com.docker.compose.service": service,
            "com.docker.compose.oneoff": "False",
        },
        "Env": env,
        "State": {
            "Running": True,
            "Status": "running",
            "Health": {"Status": "healthy"},
        },
    }


def _records() -> tuple[ContainerSnapshot, ...]:
    return tuple(
        ContainerSnapshot(
            container_id=f"{index + 1:064x}",
            service=service,
            identity=hashlib.sha256(service.encode()).hexdigest(),
            running=True,
            status="running",
            health="healthy",
            restart_count=0,
            exit_code=0,
            oom_killed=False,
        )
        for index, service in enumerate(live_stand.LIVE_CORE_EXPECTED_SERVICES)
    )


def _owner() -> OwnerEvidence:
    ports = tuple(
        (name, 20000 + index)
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    )
    return OwnerEvidence(
        repository="/workspace/owned-nats-repo",
        worktree="/fixtures/system-temp/ue-live-acceptance/run-broker-control",
        project_name=PROJECT,
        published_ports=ports,
        schema_version=11,
        daemon_fingerprint=DAEMON,
        compose_resource_fingerprint=RESOURCE,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha="c" * 40,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )


def _pins(owner: OwnerEvidence) -> tuple[DockerReadPins, ComposeConfigPins]:
    docker_pins = DockerReadPins(
        executable="/usr/bin/docker",
        endpoint="unix:///var/run/docker.sock",
        config_directory="/home/runner/.docker",
        cwd=owner.worktree,
        environment=(("LC_ALL", "C"),),
        daemon_fingerprint=DAEMON,
    )
    compose_pins = ComposeConfigPins(
        project_directory=owner.repository,
        env_file=f"{owner.worktree}/.env.docker",
        compose_files=(
            f"{owner.repository}/{live_stand.COMPOSE_FILES[0]}",
            f"{owner.repository}/{live_stand.OVERLAY}",
            f"{owner.worktree}/{live_stand.IN_PLACE_OVERLAY}",
        ),
    )
    return docker_pins, compose_pins


def _port(monkeypatch: pytest.MonkeyPatch):
    owner = _owner()
    pins, compose = _pins(owner)
    lease = LifecycleLockLease()
    owner_port = SimpleNamespace(_lease=lease)
    runtime = object.__new__(OwnedCoreRuntimePort)
    runtime._owner_port = owner_port
    runtime._docker_pins = pins
    runtime._compose_pins = compose
    runtime._lease = lease
    rows = list(_records())
    monkeypatch.setattr(
        OwnedCoreRuntimePort,
        "read_signed_owner",
        lambda self, *, deadline: owner,
    )

    def observe(self, supplied_owner, pinned_daemon, *, deadline):
        assert supplied_owner == owner
        assert pinned_daemon == DAEMON
        return RuntimeEvidence(DAEMON, RESOURCE, tuple(rows))

    monkeypatch.setattr(OwnedCoreRuntimePort, "observe_runtime", observe)
    port = broker.OwnedNatsBrokerControlPort(runtime, pins, compose)
    port.read_signed_owner(deadline=deadline())
    port.observe_runtime(owner, DAEMON, deadline=deadline())
    return port, owner, pins, compose, rows


def test_resolved_backend_and_worker_nats_settings_are_explicit_and_equal() -> None:
    config = broker.extract_effective_nats_settings(_configured_project())

    assert config is not None
    assert config.endpoint_host == "nats"
    assert config.endpoint_port == 4222
    assert config.url == _DEFAULT_NATS_URL
    assert config.token is None
    assert _NATS_PASSWORD not in repr(config)


@pytest.mark.parametrize(
    "project",
    [
        {"services": {"backend": {}, "outbox-worker": {}}},
        _configured_project(worker_url=_OTHER_NATS_URL),
        _configured_project(
            extra_backend={"NATS_AUTH_TOKEN_FILE": "/run/secrets/nats"}
        ),
        _configured_project(extra_worker={"NATS_TLS": "true"}),
        _configured_project(backend_url="nats://nats:4333"),
        _configured_project(backend_url="nats://localhost:4222"),
        _configured_project(backend_url=_TLS_NATS_URL),
        _configured_project(
            extra_backend={"NATS_AUTH_TOKEN": "token"},
            extra_worker={"NATS_AUTH_TOKEN": "token"},
        ),
    ],
)
def test_unpinned_or_ambiguous_nats_settings_fail_closed(project) -> None:
    assert broker.extract_effective_nats_settings(project) is None


def test_direct_token_is_supported_only_without_url_userinfo() -> None:
    auth_value = "fixture-" + "value"
    project = _configured_project(
        backend_url="nats://nats:4222",
        extra_backend={"NATS_AUTH_TOKEN": auth_value},
        extra_worker={"NATS_AUTH_TOKEN": auth_value},
    )

    config = broker.extract_effective_nats_settings(project)

    assert config is not None
    assert config.token == auth_value
    assert auth_value not in repr(config)


def test_runtime_configuration_is_bound_to_exact_ids_services_and_project() -> None:
    ids = {"1" * 64: "backend", "2" * 64: "outbox-worker"}
    rows = [
        _inspect_record(container_id, service) for container_id, service in ids.items()
    ]
    stdout = b"".join(
        json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows
    )
    settings = broker.extract_effective_nats_settings(_configured_project())
    assert settings is not None

    assert broker.runtime_nats_configuration_matches(
        stdout,
        expected_containers=ids,
        project_name=PROJECT,
        expected=settings,
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.update(Id="3" * 64),
        lambda row: row["Labels"].update({"com.docker.compose.oneoff": "True"}),
        lambda row: row["Labels"].update({"com.docker.compose.project": "foreign"}),
        lambda row: row["Labels"].update({"com.docker.compose.service": "nats"}),
        lambda row: row["Env"].append("NATS_AUTH_TOKEN_FILE=/run/secrets/token"),
        lambda row: row["Env"].append("NATS_TLS=true"),
        lambda row: row["Env"].append(f"NATS_URL={_OTHER_NATS_URL}"),
    ],
)
def test_runtime_configuration_rejects_foreign_duplicate_or_changed_rows(
    mutate,
) -> None:
    ids = {"1" * 64: "backend", "2" * 64: "outbox-worker"}
    rows = [
        _inspect_record(container_id, service) for container_id, service in ids.items()
    ]
    mutate(rows[0])
    stdout = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
    settings = broker.extract_effective_nats_settings(_configured_project())
    assert settings is not None

    assert not broker.runtime_nats_configuration_matches(
        stdout,
        expected_containers=ids,
        project_name=PROJECT,
        expected=settings,
    )


def test_runtime_configuration_rejects_duplicate_and_stale_id_sets() -> None:
    ids = {"1" * 64: "backend", "2" * 64: "outbox-worker"}
    rows = [
        _inspect_record(container_id, service) for container_id, service in ids.items()
    ]
    settings = broker.extract_effective_nats_settings(_configured_project())

    assert settings is not None
    duplicate = (
        json.dumps(rows[0]).encode() + b"\n" + json.dumps(rows[0]).encode() + b"\n"
    )
    stale = json.dumps(rows[0]).encode() + b"\n"
    assert not broker.runtime_nats_configuration_matches(
        duplicate, expected_containers=ids, project_name=PROJECT, expected=settings
    )
    assert not broker.runtime_nats_configuration_matches(
        stale, expected_containers=ids, project_name=PROJECT, expected=settings
    )


def test_control_command_contains_only_exact_pinned_container_id() -> None:
    owner = _owner()
    pins, _compose = _pins(owner)
    end = deadline()

    request = broker.prepare_container_control_request(
        pins, ("7" * 64), "stop", deadline=end
    )

    assert request is not None
    assert request.argv[:5] == (
        "/usr/bin/docker",
        "--config",
        "/home/runner/.docker",
        "--host",
        "unix:///var/run/docker.sock",
    )
    assert request.argv[5:] == ("stop", "--timeout", "10", "7" * 64)
    assert request.env == {"LC_ALL": "C"}
    assert "compose" not in request.argv


@pytest.mark.parametrize("action", ["exec", "compose", "restart", "rm", "run", "up"])
def test_control_command_refuses_non_stop_start_actions(action: str) -> None:
    owner = _owner()
    pins, _compose = _pins(owner)

    assert (
        broker.prepare_container_control_request(
            pins, "7" * 64, action, deadline=deadline()
        )
        is None
    )


def test_probe_decoding_accepts_only_private_complete_message_or_exact_missing() -> (
    None
):
    message = {
        "type": "new_message",
        "room": UUID_CHAT,
        "payload": {
            "type": "new_message",
            "chat_id": UUID_CHAT,
            "message": {"content": "private probe body", "id": "2" * 36},
        },
    }
    stdout = (
        json.dumps(
            {
                "kind": "message",
                "closed": True,
                "subject": SUBJECT,
                "sequence": 17,
                "envelope": message,
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    result = PrivateProcessResult(
        ProcessOutcome.EXITED, 0, stdout, b"", LocalCleanup.CONFIRMED
    )

    evidence = broker.decode_broker_probe_result(
        result, expected_subject=SUBJECT, deadline=deadline()
    )

    assert type(evidence).__name__ == "_PrivateBrokerMessageEvidence"
    assert evidence.subject == SUBJECT
    assert evidence.sequence == 17
    assert evidence.envelope == message
    assert "private probe body" not in repr(evidence)
    missing = PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        b'{"kind":"missing","closed":true,"status":404,"error_code":10037}\n',
        b"",
        LocalCleanup.CONFIRMED,
    )
    assert (
        broker.decode_broker_probe_result(
            missing, expected_subject=SUBJECT, deadline=deadline()
        ).status
        == 404
    )


@pytest.mark.parametrize(
    "stdout",
    [
        b'{"kind":"missing","closed":true,"status":404,"error_code":10059}\n',
        b'{"kind":"message","closed":false,"subject":"chat.x","sequence":1,"envelope":{}}\n',
        b'{"kind":"message","closed":true,"subject":"chat.x","subject":"chat.y","sequence":1,"envelope":{}}\n',
        b'{"kind":"message","closed":true,"subject":"chat.x","sequence":1,"envelope":[]}\n',
        b'{"kind":"message","closed":true,"subject":"chat.x","sequence":1,"envelope":{}}\nextra\n',
    ],
)
def test_probe_decoder_rejects_wrong_missing_code_duplicate_keys_and_bad_json(
    stdout,
) -> None:
    result = PrivateProcessResult(
        ProcessOutcome.EXITED, 0, stdout, b"", LocalCleanup.CONFIRMED
    )

    evidence = broker.decode_broker_probe_result(
        result, expected_subject=SUBJECT, deadline=deadline()
    )

    assert evidence.status is None
    assert evidence.error_code is None


def test_probe_decoder_rejects_local_timeout_without_remote_completion_marker() -> None:
    result = PrivateProcessResult(
        ProcessOutcome.TIMED_OUT,
        None,
        b'{"kind":"message"}\n',
        b"",
        LocalCleanup.UNPROVEN,
    )

    evidence = broker.decode_broker_probe_result(
        result, expected_subject=SUBJECT, deadline=deadline()
    )

    assert evidence.status is None
    assert evidence.error_code is None


def test_probe_decoder_classifies_execution_and_decode_failures_separately() -> None:
    from scripts.owned_nats_coordinator import BrokerProbePhase

    timed_out = PrivateProcessResult(
        ProcessOutcome.TIMED_OUT,
        None,
        b'{"kind":"message"}\n',
        b"",
        LocalCleanup.UNPROVEN,
    )
    malformed = PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        b"not-json\n",
        b"",
        LocalCleanup.CONFIRMED,
    )
    remote_failure = PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        b'{"kind":"invalid","closed":true}\n',
        b"",
        LocalCleanup.CONFIRMED,
    )
    unclosed = PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        (
            b'{"kind":"message","closed":false,"subject":"'
            + SUBJECT.encode()
            + b'","sequence":1,"envelope":{}}\n'
        ),
        b"",
        LocalCleanup.CONFIRMED,
    )

    execution_error = broker.decode_broker_probe_result(
        timed_out, expected_subject=SUBJECT, deadline=deadline()
    )
    decode_error = broker.decode_broker_probe_result(
        malformed, expected_subject=SUBJECT, deadline=deadline()
    )
    remote_error = broker.decode_broker_probe_result(
        remote_failure, expected_subject=SUBJECT, deadline=deadline()
    )
    unclosed_error = broker.decode_broker_probe_result(
        unclosed, expected_subject=SUBJECT, deadline=deadline()
    )

    assert type(execution_error) is broker.BrokerErrorEvidence
    assert execution_error.failure_phase is BrokerProbePhase.PRIVATE_EXEC
    assert type(decode_error) is broker.BrokerErrorEvidence
    assert decode_error.failure_phase is BrokerProbePhase.DECODE
    assert remote_error.failure_phase is BrokerProbePhase.PRIVATE_EXEC
    assert unclosed_error.failure_phase is BrokerProbePhase.PRIVATE_EXEC
    assert repr(execution_error) == "BrokerErrorEvidence(status=None, error_code=None)"


@pytest.mark.parametrize(
    ("stdout", "expected_phase"),
    [
        (b'{"kind":"invalid"}\n', BrokerProbePhase.DECODE),
        (b'{"kind":"invalid","closed":true,"extra":0}\n', BrokerProbePhase.DECODE),
        (b'{"kind":"invalid","closed":"true"}\n', BrokerProbePhase.DECODE),
        (b'{"kind":"invalid","closed":true}\n', BrokerProbePhase.PRIVATE_EXEC),
    ],
    ids=[
        "missing-close-marker",
        "unexpected-key",
        "non-boolean-close-marker",
        "exact-remote-marker",
    ],
)
def test_probe_decoder_requires_exact_invalid_marker(
    stdout: bytes, expected_phase: BrokerProbePhase
) -> None:
    result = PrivateProcessResult(
        ProcessOutcome.EXITED, 0, stdout, b"", LocalCleanup.CONFIRMED
    )

    evidence = broker.decode_broker_probe_result(
        result, expected_subject=SUBJECT, deadline=deadline()
    )

    assert type(evidence) is BrokerErrorEvidence
    assert evidence.failure_phase is expected_phase
    assert evidence.status is None
    assert evidence.error_code is None


def _fake_nats_modules(monkeypatch, client_type, api_error_type) -> None:
    nats_package = types.ModuleType("nats")
    nats_package.__path__ = []
    aio_package = types.ModuleType("nats.aio")
    aio_package.__path__ = []
    client_package = types.ModuleType("nats.aio.client")
    client_package.Client = client_type
    js_package = types.ModuleType("nats.js")
    js_package.__path__ = []
    errors_package = types.ModuleType("nats.js.errors")
    errors_package.APIError = api_error_type
    monkeypatch.setitem(sys.modules, "nats", nats_package)
    monkeypatch.setitem(sys.modules, "nats.aio", aio_package)
    monkeypatch.setitem(sys.modules, "nats.aio.client", client_package)
    monkeypatch.setitem(sys.modules, "nats.js", js_package)
    monkeypatch.setitem(sys.modules, "nats.js.errors", errors_package)


def _run_probe(
    monkeypatch, capsys, tmp_path, client_type, api_error_type, *, budget=0.2
):
    _fake_nats_modules(monkeypatch, client_type, api_error_type)
    monkeypatch.setenv("NATS_URL", _DEFAULT_NATS_URL)
    monkeypatch.delenv("NATS_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("NATS_AUTH_TOKEN_FILE", raising=False)
    script = broker.build_broker_probe_script(SUBJECT, budget_seconds=budget)
    assert script is not None
    probe_path = tmp_path / "owned_nats_probe.py"
    probe_path.write_bytes(script)
    runpy.run_path(str(probe_path))
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_probe_script_reads_existing_message_and_closes_before_emitting(
    monkeypatch, capsys, tmp_path
) -> None:
    observed = []
    envelope = {"type": "new_message", "room": UUID_CHAT, "payload": {}}

    class FakeJetStream:
        async def get_last_msg(self, stream, *, subject, direct):
            observed.append(("get", stream, subject, direct))
            return SimpleNamespace(
                subject=subject, seq=19, data=json.dumps(envelope).encode()
            )

    class FakeClient:
        async def connect(self, servers, **kwargs):
            observed.append(("connect", tuple(servers), kwargs.get("allow_reconnect")))

        def jetstream(self):
            return FakeJetStream()

        async def close(self):
            observed.append(("close",))

    class FakeAPIError(Exception):
        pass

    data = _run_probe(monkeypatch, capsys, tmp_path, FakeClient, FakeAPIError)

    assert data == {
        "kind": "message",
        "closed": True,
        "subject": SUBJECT,
        "sequence": 19,
        "envelope": envelope,
    }
    assert observed[0][0] == "connect"
    assert observed[0][2] is False
    assert observed[1] == ("get", "CHAT_EVENTS", SUBJECT, False)
    assert observed[-1] == ("close",)


@pytest.mark.parametrize("stall", ["connect", "get", "close"])
def test_probe_script_deadline_covers_connect_get_and_close(
    monkeypatch, capsys, tmp_path, stall
) -> None:
    observed = []

    class FakeJetStream:
        async def get_last_msg(self, stream, *, subject, direct):
            observed.append("get")
            if stall == "get":
                await asyncio.Event().wait()
            raise AssertionError("unreachable")

    class FakeClient:
        async def connect(self, servers, **kwargs):
            observed.append("connect")
            if stall == "connect":
                await asyncio.Event().wait()

        def jetstream(self):
            return FakeJetStream()

        async def close(self):
            observed.append("close")
            if stall == "close":
                await asyncio.Event().wait()

    class FakeAPIError(Exception):
        pass

    before = time.monotonic()
    data = _run_probe(
        monkeypatch, capsys, tmp_path, FakeClient, FakeAPIError, budget=0.12
    )
    elapsed = time.monotonic() - before

    assert elapsed < 0.7
    assert data.get("kind") == "invalid"
    if stall == "connect":
        assert observed == ["connect", "close"]
    elif stall == "get":
        assert observed == ["connect", "get", "close"]
    else:
        assert observed == ["connect", "get", "close"]


def test_probe_script_marks_only_exact_missing_message_as_pollable(
    monkeypatch, capsys, tmp_path
) -> None:
    class FakeAPIError(Exception):
        def __init__(self, code, err_code):
            self.code = code
            self.err_code = err_code

    for code, err_code, kind in (
        (404, 10037, "missing"),
        (404, 10059, "invalid"),
        (401, 10037, "invalid"),
    ):

        class FakeJetStream:
            async def get_last_msg(
                self, stream, *, subject, direct, code=code, err_code=err_code
            ):
                raise FakeAPIError(code, err_code)

        class FakeClient:
            async def connect(self, servers, **kwargs):
                return None

            def jetstream(self):
                return FakeJetStream()

            async def close(self):
                return None

        result = _run_probe(monkeypatch, capsys, tmp_path, FakeClient, FakeAPIError)
        assert result["kind"] == kind
        if kind == "missing":
            assert result["status"] == 404 and result["error_code"] == 10037


def test_control_port_rejects_non_target_and_inspects_stopped_target_without_health_admission(
    monkeypatch,
) -> None:
    port, _owner_value, _pins_value, _compose, rows = _port(monkeypatch)
    nats = next(row for row in rows if row.service == "nats")
    other = replace(nats, container_id="f" * 64)

    assert port.inspect_container("f" * 64, DAEMON, deadline=deadline()) is None
    rows[rows.index(nats)] = replace(nats, running=False, status="exited", health=None)

    observed = port.inspect_container(nats.container_id, DAEMON, deadline=deadline())

    assert (
        observed == rows[rows.index(next(row for row in rows if row.service == "nats"))]
    )
    assert observed.running is False
    assert other.container_id != observed.container_id


def test_stop_and_start_use_original_id_and_require_remote_state_transition(
    monkeypatch,
) -> None:
    port, _owner_value, _pins_value, _compose, rows = _port(monkeypatch)
    nats = next(row for row in rows if row.service == "nats")
    calls = []

    def run(request, *, deadline):
        calls.append(request.argv)
        current = next(row for row in rows if row.service == "nats")
        if "stop" in request.argv:
            rows[rows.index(current)] = replace(
                current, running=False, status="exited", health=None
            )
        elif "start" in request.argv:
            rows[rows.index(current)] = replace(
                current, running=True, status="running", health="starting"
            )
        return PrivateProcessResult(
            ProcessOutcome.EXITED, 0, b"nats\n", b"", LocalCleanup.CONFIRMED
        )

    monkeypatch.setattr(broker.process, "run_private_process", run)
    stopped = port.stop_container(nats.container_id, DAEMON, deadline=deadline())
    started = port.start_container(nats.container_id, DAEMON, deadline=deadline())

    assert stopped == CommandEvidence(0, False)
    assert started == CommandEvidence(0, False)
    assert calls[0][-4:] == ("stop", "--timeout", "10", nats.container_id)
    assert calls[1][-2:] == ("start", nats.container_id)
    assert all("compose" not in call for call in calls)
    assert next(row for row in rows if row.service == "nats").health == "starting"


def test_control_port_never_calls_transport_after_precommand_drift_or_expiry(
    monkeypatch,
) -> None:
    port, _owner_value, _pins_value, _compose, rows = _port(monkeypatch)
    nats = next(row for row in rows if row.service == "nats")
    calls = []
    monkeypatch.setattr(
        broker.process,
        "run_private_process",
        lambda request, *, deadline: calls.append(request.argv),
    )
    other = next(row for row in rows if row.service == "backend")
    rows[rows.index(other)] = replace(other, restart_count=1)

    result = port.stop_container(nats.container_id, DAEMON, deadline=deadline())

    assert result.returncode != 0
    assert calls == []
    now = [0.0]
    expired = deadline(now, 1)
    now[0] = 2.0
    result = port.stop_container(nats.container_id, DAEMON, deadline=expired)
    assert result.timed_out is True
    assert calls == []


def test_runtime_inspection_uses_only_exact_captured_ids_and_filters_nats_service_env() -> (
    None
):
    owner = _owner()
    pins, _compose = _pins(owner)
    ids = {"1" * 64: "backend", "2" * 64: "outbox-worker", "3" * 64: "nats"}

    request = broker.prepare_runtime_nats_inspect_request(
        pins, ids, deadline=deadline()
    )

    assert request is not None
    assert request.argv[-3:] == tuple(ids)
    assert "inspect" in request.argv
    format_string = request.argv[request.argv.index("--format") + 1]
    assert "com.docker.compose.service" in format_string
    assert "outbox-worker" in format_string
    assert 'split . "_"' in format_string
    assert "json .Config.Env" not in format_string
    assert "else}}[]{{end}}" in format_string


def test_runtime_inspection_binds_restored_nats_id_and_health() -> None:
    ids = {"1" * 64: "backend", "2" * 64: "outbox-worker", "3" * 64: "nats"}
    rows = [
        _inspect_record(container_id, service)
        for container_id, service in ids.items()
        if service != "nats"
    ]
    rows.append(
        {
            "Id": "3" * 64,
            "Labels": {
                "com.docker.compose.project": PROJECT,
                "com.docker.compose.service": "nats",
                "com.docker.compose.oneoff": "False",
            },
            "Env": [],
            "State": {
                "Running": True,
                "Status": "running",
                "Health": {"Status": "healthy"},
            },
        }
    )
    stdout = b"".join(
        json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows
    )
    settings = broker.extract_effective_nats_settings(_configured_project())
    assert settings is not None

    assert broker.runtime_nats_configuration_matches(
        stdout, expected_containers=ids, project_name=PROJECT, expected=settings
    )
    rows[-1]["Labels"]["com.docker.compose.oneoff"] = "True"
    changed = b"".join(
        json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows
    )
    assert not broker.runtime_nats_configuration_matches(
        changed, expected_containers=ids, project_name=PROJECT, expected=settings
    )


def test_stop_requires_observed_remote_stopped_state_after_local_success(
    monkeypatch,
) -> None:
    port, _owner_value, _pins_value, _compose, rows = _port(monkeypatch)
    nats = next(row for row in rows if row.service == "nats")
    calls = []

    def success_without_remote_transition(request, *, deadline):
        calls.append(request.argv)
        return PrivateProcessResult(
            ProcessOutcome.EXITED, 0, b"nats\n", b"", LocalCleanup.CONFIRMED
        )

    monkeypatch.setattr(
        broker.process, "run_private_process", success_without_remote_transition
    )

    result = port.stop_container(nats.container_id, DAEMON, deadline=deadline())

    assert result == CommandEvidence(1, False)
    assert len(calls) == 1
    assert calls[0][-1] == nats.container_id


def test_lease_loss_blocks_control_without_a_docker_process(monkeypatch) -> None:
    port, _owner_value, _pins_value, _compose, rows = _port(monkeypatch)
    nats = next(row for row in rows if row.service == "nats")
    port._runtime._lease._released = True
    calls = []
    monkeypatch.setattr(
        broker.process,
        "run_private_process",
        lambda request, *, deadline: calls.append(request.argv),
    )

    result = port.stop_container(nats.container_id, DAEMON, deadline=deadline())

    assert result == CommandEvidence(None, False)
    assert calls == []
    assert repr(port) == "<OwnedNatsBrokerControlPort>"
