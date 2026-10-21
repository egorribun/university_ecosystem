"""Tests for source-bound default Docker context pin resolution."""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import live_stand
from scripts import owned_nats_docker as docker
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)

_EXECUTABLE = "/usr/bin/docker"
_EXECUTABLE_IDENTITY = (11, 22, 33, 44)
_WORKTREE = "/opt/university/worktree"
_REPOSITORY = "/opt/university/repository"
_HOME = "/home/runner"
_CONFIG = f"{_HOME}/.docker"
_ENDPOINT = "unix:///var/run/docker.sock"
_DAEMON_ID = "docker-daemon-test-id"
_DAEMON_FINGERPRINT = hashlib.sha256(_DAEMON_ID.encode("utf-8")).hexdigest()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _owner(*, daemon_fingerprint: str = _DAEMON_FINGERPRINT) -> OwnerEvidence:
    ports = {
        name: 20_000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    return OwnerEvidence(
        repository=_REPOSITORY,
        worktree=_WORKTREE,
        project_name="ue-live-0123456789abcdef",
        published_ports=live_stand._validate_published_ports(ports),
        schema_version=11,
        daemon_fingerprint=daemon_fingerprint,
        compose_resource_fingerprint="2" * 64,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha="a" * 40,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )


def _context(**environment: str) -> Any:
    pairs = {
        "HOME": _HOME,
        "LANG": "en_US.UTF-8",
        "PATH": "/usr/bin",
        **environment,
    }
    return live_stand._LiveDockerReadContext(
        executable=_EXECUTABLE,
        executable_identity=_EXECUTABLE_IDENTITY,
        cwd=_WORKTREE,
        environment=tuple(sorted(pairs.items())),
    )


def _result(
    stdout: bytes, *, stderr: bytes = b"", returncode: int = 0
) -> PrivateProcessResult:
    return PrivateProcessResult(
        ProcessOutcome.EXITED,
        returncode,
        stdout,
        stderr,
        LocalCleanup.CONFIRMED,
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Any:
    clock = FakeClock()
    deadline = Deadline.after(20.0, clock=clock)
    calls: list[tuple[object, object]] = []
    responses = [
        _result(b"default\n"),
        _result(b'"unix:///var/run/docker.sock"\n'),
        _result(f"{_DAEMON_ID}\n".encode()),
    ]

    def run(request: object, *, deadline: object) -> PrivateProcessResult:
        calls.append((request, deadline))
        if not responses:
            raise AssertionError("unexpected private process call")
        return responses.pop(0)

    harness = SimpleNamespace(
        calls=calls,
        clock=clock,
        deadline=deadline,
        responses=responses,
        run=run,
        context=_context(),
    )
    monkeypatch.setattr(docker, "_linux_core_supported", lambda: True, raising=False)
    monkeypatch.setattr(
        live_stand,
        "_live_docker_executable_identity",
        lambda _path: _EXECUTABLE_IDENTITY,
    )
    monkeypatch.setattr(
        live_stand,
        "_new_live_docker_read_context",
        lambda: harness.context,
        raising=False,
    )
    monkeypatch.setattr(docker.process, "run_private_process", run)
    return harness


def test_resolver_reads_default_context_then_owner_pinned_daemon(harness: Any) -> None:
    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is not None
    pins, compose = resolved
    assert pins.executable == _EXECUTABLE
    assert pins.endpoint == _ENDPOINT
    assert pins.config_directory == _CONFIG
    assert pins.cwd == _WORKTREE
    assert pins.daemon_fingerprint == _DAEMON_FINGERPRINT
    assert pins._executable_identity == _EXECUTABLE_IDENTITY
    assert pins._factory_seal is not None
    assert compose.project_directory == _REPOSITORY
    assert compose.env_file == f"{_WORKTREE}/.env.docker"
    assert compose.compose_files == (
        f"{_REPOSITORY}/{live_stand.COMPOSE_FILES[0]}",
        f"{_REPOSITORY}/{live_stand.OVERLAY}",
        f"{_WORKTREE}/{live_stand.IN_PLACE_OVERLAY}",
    )
    assert len(harness.calls) == 3
    assert all(call_deadline is harness.deadline for _, call_deadline in harness.calls)
    show, inspect, info = (request for request, _ in harness.calls)
    assert show.argv == (_EXECUTABLE, "--config", _CONFIG, "context", "show")
    assert inspect.argv == (
        _EXECUTABLE,
        "--config",
        _CONFIG,
        "context",
        "inspect",
        "default",
        "--format",
        "{{json .Endpoints.docker.Host}}",
    )
    assert info.argv == (
        _EXECUTABLE,
        "--config",
        _CONFIG,
        "--host",
        _ENDPOINT,
        "info",
        "--format",
        "{{.ID}}",
    )
    assert show.env == {"HOME": _HOME, "LANG": "C", "LC_ALL": "C"}
    assert inspect.env == show.env
    assert info.env == {"LANG": "C", "LC_ALL": "C"}
    assert all(request.stdout_limit <= 256 for request in (show, inspect, info))
    assert all(request.stderr_limit <= 1024 for request in (show, inspect, info))
    assert _HOME not in repr(pins)
    assert _DAEMON_ID not in repr(pins)


@pytest.mark.parametrize(
    "override",
    (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "DOCKER_TLS_CERTDIR",
        "DOCKER_API_VERSION",
    ),
)
def test_resolver_rejects_docker_environment_overrides_before_execution(
    harness: Any, override: str
) -> None:
    harness.context = _context(**{override: "sensitive-override"})

    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is None
    assert harness.calls == []
    assert "sensitive-override" not in repr(resolved)


def test_resolver_rejects_unsupported_runner_before_context_discovery(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def unexpected_context() -> Any:
        nonlocal calls
        calls += 1
        return harness.context

    monkeypatch.setattr(docker, "_linux_core_supported", lambda: False)
    monkeypatch.setattr(live_stand, "_new_live_docker_read_context", unexpected_context)

    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is None
    assert calls == 0
    assert harness.calls == []


def test_resolver_rejects_missing_home_or_unrelated_worktree(harness: Any) -> None:
    harness.context = live_stand._LiveDockerReadContext(
        executable=_EXECUTABLE,
        executable_identity=_EXECUTABLE_IDENTITY,
        cwd=_WORKTREE,
        environment=(("LANG", "C"),),
    )
    assert docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline) is None

    harness.context = replace(_context(), cwd="/opt/other/worktree")
    assert docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline) is None
    assert harness.calls == []


@pytest.mark.parametrize(
    ("context_name", "endpoint", "expected_calls"),
    (
        (b"custom\n", b'"unix:///var/run/docker.sock"\n', 1),
        (b"default\n", b'"tcp://127.0.0.1:2375"\n', 2),
        (b"default\n", b'"unix:///tmp/foreign.sock"\n', 2),
        (b"default\n", b'"unix:///var/run/docker.sock"\nextra', 2),
    ),
)
def test_resolver_requires_exact_default_name_and_local_endpoint(
    harness: Any,
    monkeypatch: pytest.MonkeyPatch,
    context_name: bytes,
    endpoint: bytes,
    expected_calls: int,
) -> None:
    outputs = [_result(context_name), _result(endpoint)]
    requests: list[object] = []

    def run(request: object, *, deadline: object) -> PrivateProcessResult:
        assert deadline is harness.deadline
        requests.append(request)
        return outputs.pop(0)

    monkeypatch.setattr(docker.process, "run_private_process", run)

    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is None
    assert len(requests) == expected_calls
    assert len(outputs) == 2 - expected_calls


def test_resolver_rejects_process_error_and_nonempty_stderr(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def failed(_request: object, *, deadline: object) -> PrivateProcessResult:
        nonlocal calls
        calls += 1
        assert deadline is harness.deadline
        return _result(b"default\n", stderr=b"private-error-detail")

    monkeypatch.setattr(docker.process, "run_private_process", failed)

    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is None
    assert calls == 1
    assert "private-error-detail" not in repr(resolved)


def test_resolver_stops_when_deadline_expires_between_context_reads(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def expire_after_show(request: object, *, deadline: object) -> PrivateProcessResult:
        assert deadline is harness.deadline
        calls.append(request)
        harness.clock.now = 21.0
        return _result(b"default\n")

    monkeypatch.setattr(docker.process, "run_private_process", expire_after_show)

    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is None
    assert len(calls) == 1


def test_resolver_stops_on_executable_identity_drift_after_context_read(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    identities = iter(
        (
            _EXECUTABLE_IDENTITY,
            _EXECUTABLE_IDENTITY,
            (11, 22, 34, 44),
        )
    )
    monkeypatch.setattr(
        live_stand,
        "_live_docker_executable_identity",
        lambda _path: next(identities),
    )

    resolved = docker.resolve_core_docker_pins(_owner(), deadline=harness.deadline)

    assert resolved is None
    assert len(harness.calls) == 1


def test_owner_daemon_fingerprint_must_match_actual_info_read(harness: Any) -> None:
    owner = _owner(daemon_fingerprint="3" * 64)

    resolved = docker.resolve_core_docker_pins(owner, deadline=harness.deadline)

    assert resolved is None
    assert len(harness.calls) == 3


def test_factory_identity_is_rechecked_around_later_docker_processes(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pins, _compose = docker.resolve_core_docker_pins(
        _owner(), deadline=harness.deadline
    )
    harness.calls.clear()
    harness.responses[:] = [_result(f"{_DAEMON_ID}\n".encode())]
    identities = iter((_EXECUTABLE_IDENTITY, (11, 22, 35, 44)))
    monkeypatch.setattr(
        live_stand,
        "_live_docker_executable_identity",
        lambda _path: next(identities),
    )

    observed = docker.observe_daemon_metadata(pins, deadline=harness.deadline)

    assert observed.status is docker.DaemonMetadataStatus.NOT_READY
    assert len(harness.calls) == 1


def test_caller_forged_optional_identity_is_not_factory_provenance(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pins, _compose = docker.resolve_core_docker_pins(
        _owner(), deadline=harness.deadline
    )
    forged = replace(
        pins,
        _executable_identity=_EXECUTABLE_IDENTITY,
        _factory_seal=None,
    )
    harness.calls.clear()
    calls = 0

    def unexpected(_request: object, *, deadline: object) -> PrivateProcessResult:
        nonlocal calls
        calls += 1
        return _result(f"{_DAEMON_ID}\n".encode())

    monkeypatch.setattr(docker.process, "run_private_process", unexpected)

    observed = docker.observe_daemon_metadata(forged, deadline=harness.deadline)

    assert observed.status is docker.DaemonMetadataStatus.NOT_READY
    assert calls == 0
    assert harness.calls == []


@pytest.mark.parametrize(
    "changes",
    (
        {"executable": "/usr/local/bin/docker"},
        {"endpoint": "unix:///tmp/other.sock"},
        {"config_directory": "/home/other/.docker"},
        {"cwd": "/opt/other/worktree"},
        {"daemon_fingerprint": "3" * 64},
        {"environment": (("LANG", "C.UTF-8"),)},
    ),
)
def test_factory_binding_rejects_caller_changed_pins_before_execution(
    harness: Any,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
) -> None:
    pins, _compose = docker.resolve_core_docker_pins(
        _owner(), deadline=harness.deadline
    )
    harness.calls.clear()
    harness.responses[:] = [_result(f"{_DAEMON_ID}\n".encode())]
    changed = replace(pins, **changes)
    calls = 0

    def unexpected(_request: object, *, deadline: object) -> PrivateProcessResult:
        nonlocal calls
        calls += 1
        return _result(f"{_DAEMON_ID}\n".encode())

    monkeypatch.setattr(docker.process, "run_private_process", unexpected)

    observed = docker.observe_daemon_metadata(changed, deadline=harness.deadline)

    assert observed.status is docker.DaemonMetadataStatus.NOT_READY
    assert calls == 0
    assert harness.calls == []


def test_legacy_pins_without_factory_identity_keep_existing_observation_scope(
    harness: Any,
) -> None:
    harness.responses[:] = [_result(f"{_DAEMON_ID}\n".encode())]
    pins = docker.DockerReadPins(
        executable=_EXECUTABLE,
        endpoint=_ENDPOINT,
        config_directory=_CONFIG,
        cwd=_WORKTREE,
        environment=(("LANG", "C"),),
        daemon_fingerprint=_DAEMON_FINGERPRINT,
    )

    observed = docker.observe_daemon_metadata(pins, deadline=harness.deadline)

    assert observed.status is docker.DaemonMetadataStatus.MATCHED_METADATA
    assert len(harness.calls) == 1


def test_runtime_inspect_template_indexes_optional_docker_map_fields() -> None:
    template = docker._RUNTIME_INSPECT_FORMAT

    assert '{{with index .State "Health"}}' in template
    assert '{{json (index . "Status")}}' in template
    assert ".State.Health" not in template
    assert '"OOMKilled":{{json .State.OOMKilled}}},' in template
    assert '"RestartCount":{{json .RestartCount}}}' in template
    for field in (
        "Type",
        "Name",
        "Source",
        "Destination",
        "Driver",
        "Mode",
        "RW",
        "Propagation",
    ):
        assert f'{{{{json (index $m "{field}")}}}}' in template
        assert f"$m.{field}" not in template


@pytest.mark.skipif(
    sys.platform != "linux"
    or os.name != "posix"
    or "WSL_DISTRO_NAME" in os.environ
    or "WSL_INTEROP" in os.environ,
    reason="Core Docker pin resolution requires native Linux",
)
@pytest.mark.parametrize("launch_root", ("repository", "state", "unrelated"))
def test_real_context_factory_binds_owned_state_from_signed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launch_root: str
) -> None:
    roots = {name: tmp_path / name for name in ("repository", "state", "unrelated")}
    for root in roots.values():
        root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    executable = binary_directory / "docker"
    executable.write_text("fixture is never executed", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(binary_directory))
    for name in tuple(os.environ):
        if name.upper().startswith("DOCKER_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(roots[launch_root])
    original_cwd = Path.cwd()
    owner = replace(
        _owner(),
        repository=str(roots["repository"].resolve()),
        worktree=str(roots["state"].resolve()),
    )
    clock = FakeClock()
    operation_deadline = Deadline.after(20.0, clock=clock)
    responses = [
        _result(b"default\n"),
        _result(b'"unix:///var/run/docker.sock"\n'),
        _result(f"{_DAEMON_ID}\n".encode()),
    ]
    calls: list[PrivateProcessRequest] = []

    def run(
        request: PrivateProcessRequest, *, deadline: Deadline
    ) -> PrivateProcessResult:
        assert deadline is operation_deadline
        calls.append(request)
        assert responses, "unexpected private process call"
        return responses.pop(0)

    monkeypatch.setattr(docker.process, "run_private_process", run)
    captured = live_stand._new_live_docker_read_context()
    assert captured.cwd == str(original_cwd)
    assert captured.executable == str(executable.resolve())

    resolved = docker.resolve_core_docker_pins(owner, deadline=operation_deadline)

    assert Path.cwd() == original_cwd
    if launch_root == "unrelated":
        assert resolved is None
        assert calls == []
        assert len(responses) == 3
        return
    assert resolved is not None
    pins, compose = resolved
    assert pins.cwd == owner.worktree
    assert pins.executable == str(executable.resolve())
    assert docker._factory_provenance_valid(pins)
    assert compose.project_directory == owner.repository
    assert compose.env_file == f"{owner.worktree}/.env.docker"
    assert compose.compose_files == (
        f"{owner.repository}/{live_stand.COMPOSE_FILES[0]}",
        f"{owner.repository}/{live_stand.OVERLAY}",
        f"{owner.worktree}/{live_stand.IN_PLACE_OVERLAY}",
    )
    assert len(calls) == 3
    assert responses == []
    assert all(request.cwd == owner.worktree for request in calls)
    assert calls[0].argv[-2:] == ("context", "show")
    assert calls[1].argv[-4:] == (
        "inspect",
        "default",
        "--format",
        "{{json .Endpoints.docker.Host}}",
    )
    assert calls[2].argv[-3:] == ("info", "--format", "{{.ID}}")
    assert calls[0].env == {"HOME": str(home), "LANG": "C", "LC_ALL": "C"}
    assert calls[1].env == calls[0].env
    assert calls[2].env == {"LANG": "C", "LC_ALL": "C"}
