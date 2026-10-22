from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from typing import Any

import pytest

from scripts import live_nats_transport as lifecycle
from scripts import live_stand
from scripts import owned_nats_broker_control as broker
from scripts import owned_nats_docker as docker
from scripts import owned_nats_http_adapter as http
from scripts import owned_nats_sql_adapter as sql
from scripts import owned_nats_transport_port as transport_port
from scripts.owned_nats_coordinator import (
    OutageOutcome,
    OwnerEvidence,
    run_owned_outage,
)
from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_owner_adapter import OwnerFilePins, SignedOwnerLeasePort

_NOW = 0.0
_REPOSITORY = "/opt/university/repository"
_WORKTREE = "/opt/university/worktree"
_DAEMON_FINGERPRINT = hashlib.sha256(b"docker-daemon-test-id").hexdigest()
_EXECUTABLE_IDENTITY = (11, 22, 33, 44)


def _owner() -> OwnerEvidence:
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
        daemon_fingerprint=_DAEMON_FINGERPRINT,
        compose_resource_fingerprint="2" * 64,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha="a" * 40,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )


def _pins(
    owner: OwnerEvidence,
) -> tuple[docker.DockerReadPins, docker.ComposeConfigPins]:
    environment = (("LANG", "C"), ("LC_ALL", "C"))
    seal = docker._DockerPinFactorySeal(
        executable="/usr/bin/docker",
        endpoint="unix:///var/run/docker.sock",
        config_directory="/home/runner/.docker",
        cwd=owner.worktree,
        environment=environment,
        daemon_fingerprint=owner.daemon_fingerprint,
        executable_identity=_EXECUTABLE_IDENTITY,
    )
    pinned = docker.DockerReadPins(
        executable=seal.executable,
        endpoint=seal.endpoint,
        config_directory=seal.config_directory,
        cwd=seal.cwd,
        environment=seal.environment,
        daemon_fingerprint=seal.daemon_fingerprint,
        _executable_identity=_EXECUTABLE_IDENTITY,
        _factory_seal=seal,
    )
    compose = docker.ComposeConfigPins(
        project_directory=owner.repository,
        env_file=f"{owner.worktree}/.env.docker",
        compose_files=(
            f"{owner.repository}/{live_stand.COMPOSE_FILES[0]}",
            f"{owner.repository}/{live_stand.OVERLAY}",
            f"{owner.worktree}/{live_stand.IN_PLACE_OVERLAY}",
        ),
    )
    return pinned, compose


def _owner_file_pins() -> OwnerFilePins:
    return OwnerFilePins(
        repository=r"C:\private\repository",
        state_root=r"C:\private\repository",
        source_sha="a" * 40,
        owner_uid=1000,
    )


def _deadline() -> Deadline:
    return Deadline.after(30.0, clock=lambda: _NOW)


def _lease(monkeypatch: pytest.MonkeyPatch) -> Any:
    lease = lifecycle.LifecycleLockLease()

    def acquire(self: SignedOwnerLeasePort, *, deadline: Deadline) -> object:
        assert type(deadline) is Deadline
        self._lease = lease
        return lease

    monkeypatch.setattr(SignedOwnerLeasePort, "acquire_lock", acquire)
    return lease


_TEST_DEADLINE = Deadline.after(30.0, clock=lambda: _NOW)


def _install_owner_reads(
    monkeypatch: pytest.MonkeyPatch,
    owners: list[OwnerEvidence],
    calls: list[Deadline],
) -> None:
    def read(self: SignedOwnerLeasePort, *, deadline: Deadline) -> OwnerEvidence:
        calls.append(deadline)
        if not owners:
            raise AssertionError("unexpected owner reread")
        return owners.pop(0)

    monkeypatch.setattr(SignedOwnerLeasePort, "read_signed_owner", read)


def _install_release(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[object, object]]
) -> None:
    def release(lease: object, *, deadline: object) -> bool:
        calls.append((lease, deadline))
        assert type(lease) is lifecycle.LifecycleLockLease
        lease._released = True
        return True

    monkeypatch.setattr(lifecycle, "release_lifecycle_lock", release)


def test_lazy_path_resolves_only_after_lease_and_retains_owner_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _owner()
    deadline = _TEST_DEADLINE
    resolver_calls: list[tuple[OwnerEvidence, Deadline]] = []
    constructors: list[str] = []
    owner_reads: list[Deadline] = []
    release_calls: list[tuple[object, object]] = []
    expected_pins = _pins(owner)

    def resolve(seen_owner: OwnerEvidence, *, deadline: Deadline) -> object:
        resolver_calls.append((seen_owner, deadline))
        return expected_pins

    monkeypatch.setattr(docker, "resolve_core_docker_pins", resolve)
    original_sql = transport_port.OwnedNatsSqlAdapter
    original_http = http.OwnedNatsHttpPort
    original_broker = broker.OwnedNatsBrokerControlPort
    original_sql_init = original_sql.__init__
    original_http_init = original_http.__init__
    original_broker_init = original_broker.__init__

    def sql_init(self: object, *args: object) -> None:
        constructors.append("sql")
        original_sql_init(self, *args)

    def http_init(self: object, *args: object) -> None:
        constructors.append("http")
        original_http_init(self, *args)

    def broker_init(self: object, *args: object) -> None:
        constructors.append("broker")
        original_broker_init(self, *args)

    monkeypatch.setattr(transport_port, "OwnedNatsSqlAdapter", original_sql)
    monkeypatch.setattr(original_sql, "__init__", sql_init)
    monkeypatch.setattr(original_http, "__init__", http_init)
    monkeypatch.setattr(original_broker, "__init__", broker_init)

    port = transport_port.OwnedNatsTransportPort.for_owned_core(
        _owner_file_pins(), sleep=lambda _seconds: None
    )
    assert resolver_calls == []
    assert constructors == []
    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_signed_owner(deadline=deadline)
    assert resolver_calls == []

    lease = _lease(monkeypatch)
    _install_owner_reads(monkeypatch, [owner, owner, owner], owner_reads)
    _install_release(monkeypatch, release_calls)
    assert port.acquire_lock(deadline=deadline) is lease
    assert resolver_calls == []
    assert constructors == []

    assert port.read_signed_owner(deadline=deadline) == owner

    assert len(resolver_calls) == 1
    assert resolver_calls[0][0] is owner
    assert resolver_calls[0][1] is deadline
    assert owner_reads == [deadline, deadline, deadline]
    assert constructors == ["sql", "http", "broker"]
    assert port._docker_pins == expected_pins[0]
    assert port._compose_pins == expected_pins[1]
    assert docker._factory_provenance_valid(port._docker_pins)

    cleanup_deadline = Deadline.after(10.0, clock=lambda: _NOW)
    port.release_lock(lease, deadline=cleanup_deadline)
    assert release_calls == [(lease, cleanup_deadline)]
    assert lease._released is True


def test_lazy_factory_owner_drift_stops_before_adapter_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _owner()
    changed = replace(owner, compose_resource_fingerprint="3" * 64)
    resolver_calls: list[tuple[OwnerEvidence, Deadline]] = []
    constructors: list[str] = []
    owner_reads: list[Deadline] = []
    expected_pins = _pins(owner)

    def resolve(seen_owner: OwnerEvidence, *, deadline: Deadline) -> object:
        resolver_calls.append((seen_owner, deadline))
        return expected_pins

    monkeypatch.setattr(docker, "resolve_core_docker_pins", resolve)
    monkeypatch.setattr(
        transport_port.OwnedNatsSqlAdapter,
        "__init__",
        lambda *_args, **_kwargs: constructors.append("sql"),
    )
    port = transport_port.OwnedNatsTransportPort.for_owned_core(
        _owner_file_pins(), sleep=lambda _seconds: None
    )
    lease = _lease(monkeypatch)
    _install_owner_reads(monkeypatch, [owner, changed], owner_reads)
    assert port.acquire_lock(deadline=_TEST_DEADLINE) is lease

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_signed_owner(deadline=_TEST_DEADLINE)

    assert len(resolver_calls) == 1
    assert owner_reads == [_TEST_DEADLINE, _TEST_DEADLINE]
    assert constructors == []
    assert port._sql is None
    assert port._http is None
    assert port._broker is None


def test_lazy_second_owner_drift_blocks_all_later_transport_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _owner()
    changed = replace(owner, compose_resource_fingerprint="4" * 64)
    expected_pins = _pins(owner)
    owner_reads: list[Deadline] = []
    downstream: list[str] = []
    release_calls: list[tuple[object, object]] = []

    monkeypatch.setattr(
        docker,
        "resolve_core_docker_pins",
        lambda _owner, *, deadline: expected_pins,
    )
    port = transport_port.OwnedNatsTransportPort.for_owned_core(
        _owner_file_pins(), sleep=lambda _seconds: None
    )
    lease = _lease(monkeypatch)
    _install_owner_reads(monkeypatch, [owner, owner, changed], owner_reads)
    _install_release(monkeypatch, release_calls)
    assert port.acquire_lock(deadline=_TEST_DEADLINE) is lease

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_signed_owner(deadline=_TEST_DEADLINE)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        downstream.append("called")
        raise AssertionError("downstream action after bootstrap drift")

    monkeypatch.setattr(sql.OwnedNatsSqlAdapter, "pending_count", forbidden)
    with pytest.raises(transport_port.TransportPortNotReady):
        port.pending_count(owner, object(), deadline=_TEST_DEADLINE)

    assert owner_reads == [_TEST_DEADLINE, _TEST_DEADLINE, _TEST_DEADLINE]
    assert downstream == []
    assert port._bootstrap_failed is True
    cleanup_deadline = Deadline.after(10.0, clock=lambda: _NOW)
    port.release_lock(lease, deadline=cleanup_deadline)
    assert release_calls == [(lease, cleanup_deadline)]


def test_lazy_failed_adapter_construction_is_closed_and_original_lease_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _owner()
    expected_pins = _pins(owner)
    owner_reads: list[Deadline] = []
    release_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(
        docker,
        "resolve_core_docker_pins",
        lambda _owner, *, deadline: expected_pins,
    )
    port = transport_port.OwnedNatsTransportPort.for_owned_core(
        _owner_file_pins(), sleep=lambda _seconds: None
    )
    lease = _lease(monkeypatch)
    _install_owner_reads(monkeypatch, [owner, owner], owner_reads)
    _install_release(monkeypatch, release_calls)

    def fail_broker_init(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("private construction failure")

    monkeypatch.setattr(broker.OwnedNatsBrokerControlPort, "__init__", fail_broker_init)
    result = run_owned_outage(port, clock=lambda: _NOW, sleep=lambda _seconds: None)

    assert port._sql is not None
    assert port._http is not None
    assert port._broker is None
    assert port._bootstrap_failed is True
    assert result.outcome is OutageOutcome.FAILED
    assert port._http._closed is True
    assert release_calls and release_calls[0][0] is lease
    assert type(release_calls[0][1]) is Deadline
    assert release_calls[0][1] is not _TEST_DEADLINE
    assert lease._released is True


def test_lazy_public_factory_does_not_accept_caller_pin_resolver() -> None:
    signature = inspect.signature(transport_port.OwnedNatsTransportPort.for_owned_core)
    assert "resolver" not in signature.parameters
    with pytest.raises(TypeError):
        transport_port.OwnedNatsTransportPort.for_owned_core(
            _owner_file_pins(),
            sleep=lambda _seconds: None,
            resolver=lambda *_args, **_kwargs: _pins(_owner()),
        )


def test_adapter_constructor_expiry_stops_before_next_adapter_or_owner_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _owner()
    now = [0.0]
    deadline = Deadline.after(5.0, clock=lambda: now[0])
    expected_pins = _pins(owner)
    constructors: list[str] = []
    owner_reads: list[Deadline] = []
    release_calls: list[tuple[object, object]] = []

    monkeypatch.setattr(
        docker,
        "resolve_core_docker_pins",
        lambda _owner, *, deadline: expected_pins,
    )

    def expire_after_sql(self: object, *_args: object) -> None:
        constructors.append("sql")
        now[0] = 5.0

    monkeypatch.setattr(
        transport_port.OwnedNatsSqlAdapter, "__init__", expire_after_sql
    )
    monkeypatch.setattr(
        http.OwnedNatsHttpPort,
        "__init__",
        lambda *_args, **_kwargs: constructors.append("http"),
    )
    port = transport_port.OwnedNatsTransportPort.for_owned_core(
        _owner_file_pins(), sleep=lambda _seconds: None
    )
    lease = _lease(monkeypatch)
    _install_owner_reads(monkeypatch, [owner, owner], owner_reads)
    _install_release(monkeypatch, release_calls)
    assert port.acquire_lock(deadline=deadline) is lease

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_signed_owner(deadline=deadline)

    assert constructors == ["sql"]
    assert owner_reads == [deadline, deadline]
    assert port._http is None
    assert port._broker is None
    assert port._bootstrap_failed is True
    cleanup_deadline = Deadline.after(10.0, clock=lambda: 5.0)
    port.release_lock(lease, deadline=cleanup_deadline)
    assert release_calls == [(lease, cleanup_deadline)]
    assert lease._released is True


def test_lazy_factory_expiry_stops_without_reread_or_adapter_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _owner()
    now = [0.0]
    deadline = Deadline.after(5.0, clock=lambda: now[0])
    owner_reads: list[Deadline] = []
    constructors: list[str] = []
    release_calls: list[tuple[object, object]] = []
    expected_pins = _pins(owner)

    def resolve(_owner: OwnerEvidence, *, deadline: Deadline) -> object:
        assert deadline is deadline_under_test
        now[0] = 5.0
        return expected_pins

    deadline_under_test = deadline
    monkeypatch.setattr(docker, "resolve_core_docker_pins", resolve)
    monkeypatch.setattr(
        transport_port.OwnedNatsSqlAdapter,
        "__init__",
        lambda *_args, **_kwargs: constructors.append("sql"),
    )
    port = transport_port.OwnedNatsTransportPort.for_owned_core(
        _owner_file_pins(), sleep=lambda _seconds: None
    )
    lease = _lease(monkeypatch)
    _install_owner_reads(monkeypatch, [owner], owner_reads)
    _install_release(monkeypatch, release_calls)
    assert port.acquire_lock(deadline=deadline) is lease

    with pytest.raises(transport_port.TransportPortNotReady):
        port.read_signed_owner(deadline=deadline)

    assert owner_reads == [deadline]
    assert constructors == []
    assert port._sql is None
    cleanup_deadline = Deadline.after(10.0, clock=lambda: 5.0)
    port.release_lock(lease, deadline=cleanup_deadline)
    assert release_calls == [(lease, cleanup_deadline)]
