"""Tests for a same-lease owned Core runtime adapter."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import live_nats_transport as transport
from scripts import live_stand
from scripts.owned_nats_coordinator import (
    ContainerSnapshot,
    OwnerEvidence,
    RuntimeEvidence,
)
from scripts.owned_nats_docker import ComposeConfigPins, DockerReadPins
from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_owner_adapter import (
    OwnerFilePins,
    OwnerReadNotReady,
    SignedOwnerLeasePort,
)
from scripts.owned_nats_runtime_adapter import OwnedCoreRuntimePort, RuntimeReadNotReady

_KEY = bytes(range(32))
_SOURCE = "a" * 40


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _deadline(clock: FakeClock) -> Deadline:
    return Deadline.after(20.0, clock=clock)


def _supports_posix_reader() -> bool:
    try:
        importlib.import_module("fcntl")
    except ImportError:
        return False
    return (
        os.name == "posix"
        and all(
            hasattr(os, name)
            for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC")
        )
        and os.open in getattr(os, "supports_dir_fd", set())
        and os.stat in getattr(os, "supports_dir_fd", set())
        and os.stat in getattr(os, "supports_follow_symlinks", set())
    )


def _lock_is_held(lock_path: Path) -> bool:
    fcntl = importlib.import_module("fcntl")
    descriptor = os.open(lock_path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
    finally:
        os.close(descriptor)


@pytest.fixture
def signed_state(tmp_path: Path):
    root = tmp_path / "ue-live-acceptance" / "runtime-adapter"
    secrets = root / ".secrets"
    secrets.mkdir(parents=True)
    root.chmod(0o700)
    secrets.chmod(0o700)
    repository = tmp_path / "repository"
    ports = {
        name: 20_000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    payload = {
        "version": 11,
        "repository": str(repository),
        "worktree": str(root),
        "project_name": "ue-live-0123456789abcdef",
        "published_ports": dict(live_stand._validate_published_ports(ports)),
        "daemon_fingerprint": "1" * 64,
        "compose_resource_fingerprint": "2" * 64,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": live_stand.LIVE_STACK_CORE,
        "service_roots": list(live_stand.LIVE_CORE_SERVICE_ROOTS),
        "selected_services": list(live_stand.LIVE_CORE_EXPECTED_SERVICES),
        "source_sha": _SOURCE,
    }
    marker_bytes = json.dumps(
        {**payload, "signature": live_stand._owner_signature(payload, _KEY)},
        separators=(",", ":"),
    ).encode("utf-8")
    marker = secrets / live_stand.STAND_FILE.name
    key_file = secrets / "live-stand-owner.key"
    marker.write_bytes(marker_bytes)
    key_file.write_bytes(_KEY)
    marker.chmod(0o600)
    key_file.chmod(0o600)
    lock_path = root.parent / f".{root.name}.lifecycle.lock"
    lock_path.touch(mode=0o600)
    uid = os.getuid() if hasattr(os, "getuid") else 0
    owner_file_pins = OwnerFilePins(
        repository=str(repository),
        state_root=str(root),
        source_sha=_SOURCE,
        owner_uid=uid,
    )
    owner = OwnerEvidence(
        repository=str(repository),
        worktree=str(root),
        project_name=payload["project_name"],
        published_ports=live_stand._validate_published_ports(ports),
        schema_version=11,
        daemon_fingerprint=payload["daemon_fingerprint"],
        compose_resource_fingerprint=payload["compose_resource_fingerprint"],
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha=_SOURCE,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )
    docker_pins = DockerReadPins(
        executable="/usr/bin/docker",
        endpoint="unix:///var/run/docker.sock",
        config_directory="/",
        cwd=str(root),
        environment=(("LANG", "C"),),
        daemon_fingerprint="1" * 64,
    )
    compose_pins = ComposeConfigPins(
        project_directory=str(repository),
        env_file=f"{root}/.env.docker",
        compose_files=(
            f"{repository}/{live_stand.COMPOSE_FILES[0]}",
            f"{repository}/{live_stand.OVERLAY}",
            f"{root}/{live_stand.IN_PLACE_OVERLAY}",
        ),
    )
    adapter_repository = "/opt/ue-runtime-adapter/repository"
    adapter_worktree = "/opt/ue-runtime-adapter/worktree"
    adapter_owner = OwnerEvidence(
        **{
            **owner.__dict__,
            "repository": adapter_repository,
            "worktree": adapter_worktree,
        }
    )
    adapter_docker_pins = DockerReadPins(
        executable="/usr/bin/docker",
        endpoint="unix:///var/run/docker.sock",
        config_directory="/",
        cwd=adapter_worktree,
        environment=(("LANG", "C"),),
        daemon_fingerprint="1" * 64,
    )
    adapter_compose_pins = ComposeConfigPins(
        project_directory=adapter_repository,
        env_file=f"{adapter_worktree}/.env.docker",
        compose_files=(
            f"{adapter_repository}/{live_stand.COMPOSE_FILES[0]}",
            f"{adapter_repository}/{live_stand.OVERLAY}",
            f"{adapter_worktree}/{live_stand.IN_PLACE_OVERLAY}",
        ),
    )
    return SimpleNamespace(
        root=root,
        marker=marker,
        key_file=key_file,
        lock_path=lock_path,
        marker_bytes=marker_bytes,
        owner_file_pins=owner_file_pins,
        owner=owner,
        adapter_owner=adapter_owner,
        docker_pins=docker_pins,
        compose_pins=compose_pins,
        adapter_docker_pins=adapter_docker_pins,
        adapter_compose_pins=adapter_compose_pins,
    )


def _container(container_id: str, service: str, *, running: bool) -> ContainerSnapshot:
    return ContainerSnapshot(
        container_id=container_id,
        service=service,
        identity=(container_id[0] if container_id else "a") * 64,
        running=running,
        status="running" if running else "exited",
        health="healthy" if running else None,
        restart_count=0,
        exit_code=0,
        oom_killed=False,
    )


def _runtime_evidence() -> RuntimeEvidence:
    # The adapter must pass the full reader result to coordinator validation;
    # it must not filter stopped initializers or same-project orphan evidence.
    return RuntimeEvidence(
        daemon_fingerprint="1" * 64,
        resource_fingerprint="2" * 64,
        containers=(
            _container("a" * 64, "backend", running=True),
            _container("b" * 64, "migrations", running=False),
            _container("c" * 64, "orphan-control", running=True),
        ),
    )


def test_posix_signed_owner_lease_spans_real_runtime_handoff(signed_state, monkeypatch):
    port = SignedOwnerLeasePort(
        signed_state.owner_file_pins, sleep=lambda _seconds: None
    )
    runtime_port = OwnedCoreRuntimePort(
        port, signed_state.docker_pins, signed_state.compose_pins
    )
    clock = FakeClock()
    deadline = _deadline(clock)

    if not _supports_posix_reader():
        before = signed_state.marker.read_bytes()
        helper_calls = []
        monkeypatch.setattr(
            "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
            lambda *_args, **_kwargs: helper_calls.append(True) or _runtime_evidence(),
        )
        assert runtime_port.acquire_lock(deadline=deadline) is None
        with pytest.raises(RuntimeReadNotReady):
            runtime_port.observe_runtime(
                signed_state.owner, "1" * 64, deadline=deadline
            )
        assert signed_state.marker.read_bytes() == before
        assert helper_calls == []
        assert port._lease is None
        return

    expected_evidence = _runtime_evidence()
    read_deadlines = []
    real_read = transport.read_signed_owner_v11_under_lease

    def tracked_read(*args, deadline: Deadline, **kwargs):
        read_deadlines.append(deadline)
        return real_read(*args, deadline=deadline, **kwargs)

    monkeypatch.setattr(transport, "read_signed_owner_v11_under_lease", tracked_read)
    lease = runtime_port.acquire_lock(deadline=deadline)
    assert lease is not None
    assert _lock_is_held(signed_state.lock_path)

    calls = []

    def observe(owner, pins, compose, *, deadline: Deadline):
        calls.append((owner, pins, compose, deadline))
        assert port._lease is lease and not lease._released
        assert _lock_is_held(signed_state.lock_path)
        assert owner == signed_state.owner
        assert pins == signed_state.docker_pins
        assert compose == signed_state.compose_pins
        assert deadline is deadline_arg
        return expected_evidence

    deadline_arg = deadline
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        observe,
    )

    evidence = runtime_port.observe_runtime(
        signed_state.owner, "1" * 64, deadline=deadline
    )
    assert evidence is expected_evidence
    assert len(calls) == 1
    assert calls[0] == (
        signed_state.owner,
        signed_state.docker_pins,
        signed_state.compose_pins,
        deadline,
    )
    assert len(read_deadlines) == 2
    assert all(candidate is deadline for candidate in read_deadlines)
    assert port._lease is lease and not lease._released
    assert _lock_is_held(signed_state.lock_path)

    runtime_port.release_lock(lease, deadline=deadline)
    assert port._lease is None and lease._released
    assert not _lock_is_held(signed_state.lock_path)


def _mock_port(monkeypatch, signed_state, owner_results=None):
    lease = transport.LifecycleLockLease()
    owner_port = SignedOwnerLeasePort(
        signed_state.owner_file_pins, sleep=lambda _seconds: None
    )
    reads = []
    results = list(
        owner_results or [signed_state.adapter_owner, signed_state.adapter_owner]
    )

    def acquire(self, *, deadline: Deadline):
        self._lease = lease
        return lease

    def read(self, *, deadline: Deadline):
        reads.append(deadline)
        if self._lease is not lease or lease._released:
            raise OwnerReadNotReady
        if not results:
            raise OwnerReadNotReady
        return results.pop(0)

    def release(self, candidate, *, deadline: Deadline):
        if candidate is not lease or self._lease is not lease or lease._released:
            raise OwnerReadNotReady
        lease._released = True
        self._lease = None
        return None

    monkeypatch.setattr(SignedOwnerLeasePort, "acquire_lock", acquire)
    monkeypatch.setattr(SignedOwnerLeasePort, "read_signed_owner", read)
    monkeypatch.setattr(SignedOwnerLeasePort, "release_lock", release)
    runtime_port = OwnedCoreRuntimePort(
        owner_port,
        signed_state.adapter_docker_pins,
        signed_state.adapter_compose_pins,
    )
    return runtime_port, owner_port, lease, reads


def test_runtime_call_rejects_owner_or_lease_drift_after_observation(
    signed_state, monkeypatch
):
    changed_owner = replace(
        signed_state.adapter_owner, project_name="ue-live-fedcba9876543210"
    )
    runtime_port, owner_port, lease, reads = _mock_port(
        monkeypatch, signed_state, [signed_state.adapter_owner, changed_owner]
    )
    clock = FakeClock()
    deadline = _deadline(clock)
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    helper_calls = []
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        lambda *_args, **_kwargs: helper_calls.append(True) or _runtime_evidence(),
    )

    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert helper_calls == [True]
    assert len(reads) == 2 and all(candidate is deadline for candidate in reads)
    assert owner_port._lease is lease and not lease._released
    runtime_port.release_lock(lease, deadline=deadline)


def test_foreign_released_missing_and_mismatched_leases_never_reach_runtime_helper(
    signed_state, monkeypatch
):
    runtime_port, owner_port, lease, _reads = _mock_port(monkeypatch, signed_state)
    clock = FakeClock()
    deadline = _deadline(clock)
    helper_calls = []
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        lambda *_args, **_kwargs: helper_calls.append(True) or _runtime_evidence(),
    )

    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    owner_port._lease = transport.LifecycleLockLease()
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    owner_port._lease = lease
    lease._released = True
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert helper_calls == []


def test_pin_layout_and_deadline_controls_fail_before_runtime_helper(
    signed_state, monkeypatch
):
    runtime_port, _owner_port, lease, _reads = _mock_port(monkeypatch, signed_state)
    clock = FakeClock()
    deadline = _deadline(clock)
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    helper_calls = []
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        lambda *_args, **_kwargs: helper_calls.append(True) or _runtime_evidence(),
    )

    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "3" * 64, deadline=deadline
        )
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=object()
        )
    expired_clock = FakeClock()
    expired = _deadline(expired_clock)
    assert expired.expires_at is not None
    expired_clock.now = expired.expires_at
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=expired
        )
    object.__setattr__(runtime_port._docker_pins, "cwd", "/opt/foreign-worktree")
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    object.__setattr__(
        runtime_port._docker_pins,
        "cwd",
        signed_state.adapter_owner.worktree,
    )
    object.__setattr__(
        runtime_port._compose_pins, "env_file", "/opt/foreign/.env.docker"
    )
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert helper_calls == []
    runtime_port.release_lock(lease, deadline=deadline)


def test_deadline_expiry_during_observation_discards_full_evidence(
    signed_state, monkeypatch
):
    runtime_port, owner_port, lease, reads = _mock_port(monkeypatch, signed_state)
    clock = FakeClock()
    deadline = _deadline(clock)
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    evidence = _runtime_evidence()

    def observe(*_args, deadline: Deadline):
        clock.now = deadline.expires_at
        return evidence

    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        observe,
    )
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert len(reads) == 1
    assert owner_port._lease is lease and not lease._released
    runtime_port.release_lock(lease, deadline=_deadline(FakeClock()))


def test_lease_replacement_during_helper_discards_runtime_evidence(
    signed_state, monkeypatch
):
    runtime_port, owner_port, lease, reads = _mock_port(monkeypatch, signed_state)
    deadline = _deadline(FakeClock())
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    foreign_lease = transport.LifecycleLockLease()
    helper_calls = []

    def observe(*_args, **_kwargs):
        helper_calls.append(True)
        owner_port._lease = foreign_lease
        return _runtime_evidence()

    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        observe,
    )
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert helper_calls == [True]
    assert len(reads) == 1 and reads[0] is deadline
    assert runtime_port._lease is lease
    assert not lease._released


def test_malformed_owner_port_and_helper_errors_fail_closed(signed_state, monkeypatch):
    malformed_owner_port = object.__new__(SignedOwnerLeasePort)
    runtime_port = OwnedCoreRuntimePort(
        malformed_owner_port,
        signed_state.adapter_docker_pins,
        signed_state.adapter_compose_pins,
    )
    deadline = _deadline(FakeClock())
    helper_calls = []
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        lambda *_args, **_kwargs: helper_calls.append(True) or _runtime_evidence(),
    )
    assert runtime_port.acquire_lock(deadline=deadline) is None
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert helper_calls == []

    runtime_port, _owner_port, lease, _reads = _mock_port(monkeypatch, signed_state)
    assert runtime_port.acquire_lock(deadline=deadline) is lease

    def fail(*_args, **_kwargs):
        raise OSError("private diagnostic")

    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime", fail
    )
    with pytest.raises(RuntimeReadNotReady) as caught:
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert str(caught.value) == ""
    runtime_port.release_lock(lease, deadline=deadline)


def test_helper_pin_mutation_discards_returned_inventory(signed_state, monkeypatch):
    runtime_port, owner_port, lease, reads = _mock_port(monkeypatch, signed_state)
    deadline = _deadline(FakeClock())
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    evidence = _runtime_evidence()

    def mutate_pins(_owner, pins, _compose, *, deadline: Deadline):
        object.__setattr__(pins, "cwd", "/opt/foreign-worktree")
        return evidence

    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        mutate_pins,
    )
    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
    assert len(reads) == 1 and reads[0] is deadline
    assert owner_port._lease is lease and not lease._released
    runtime_port.release_lock(lease, deadline=deadline)


def test_input_pin_objects_are_snapshotted_at_construction(signed_state, monkeypatch):
    runtime_port, _owner_port, lease, _reads = _mock_port(monkeypatch, signed_state)
    deadline = _deadline(FakeClock())
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    object.__setattr__(signed_state.adapter_docker_pins, "cwd", "/opt/mutated-input")
    object.__setattr__(
        signed_state.adapter_compose_pins,
        "env_file",
        "/opt/mutated-input/.env.docker",
    )
    evidence = _runtime_evidence()
    observed = []

    def observe(owner, pins, compose, *, deadline: Deadline):
        observed.append((owner, pins, compose, deadline))
        return evidence

    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        observe,
    )
    assert (
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )
        is evidence
    )
    assert observed == [
        (
            signed_state.adapter_owner,
            DockerReadPins(
                executable="/usr/bin/docker",
                endpoint="unix:///var/run/docker.sock",
                config_directory="/",
                cwd="/opt/ue-runtime-adapter/worktree",
                environment=(("LANG", "C"),),
                daemon_fingerprint="1" * 64,
            ),
            ComposeConfigPins(
                project_directory="/opt/ue-runtime-adapter/repository",
                env_file="/opt/ue-runtime-adapter/worktree/.env.docker",
                compose_files=(
                    f"/opt/ue-runtime-adapter/repository/{live_stand.COMPOSE_FILES[0]}",
                    f"/opt/ue-runtime-adapter/repository/{live_stand.OVERLAY}",
                    f"/opt/ue-runtime-adapter/worktree/{live_stand.IN_PLACE_OVERLAY}",
                ),
            ),
            deadline,
        )
    ]
    runtime_port.release_lock(lease, deadline=deadline)


def test_foreign_requested_owner_is_rejected_before_runtime_helper(
    signed_state, monkeypatch
):
    runtime_port, owner_port, lease, reads = _mock_port(monkeypatch, signed_state)
    clock = FakeClock()
    deadline = _deadline(clock)
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    foreign_owner = replace(
        signed_state.adapter_owner,
        project_name="ue-live-fedcba9876543210",
    )
    helper_calls = []
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        lambda *_args, **_kwargs: helper_calls.append(True) or _runtime_evidence(),
    )

    with pytest.raises(RuntimeReadNotReady):
        runtime_port.observe_runtime(foreign_owner, "1" * 64, deadline=deadline)

    assert helper_calls == []
    assert len(reads) == 1 and reads[0] is deadline
    assert runtime_port._lease is lease
    assert owner_port._lease is lease and not lease._released
    runtime_port.release_lock(lease, deadline=deadline)


def test_late_acquisition_retains_exact_lease_for_finally_cleanup(
    signed_state, monkeypatch
):
    runtime_port, owner_port, lease, _reads = _mock_port(monkeypatch, signed_state)
    clock = FakeClock()
    deadline = _deadline(clock)

    def acquire_late(self, *, deadline: Deadline):
        assert deadline is operation_deadline
        self._lease = lease
        assert deadline.expires_at is not None
        clock.now = deadline.expires_at
        return lease

    operation_deadline = deadline
    monkeypatch.setattr(SignedOwnerLeasePort, "acquire_lock", acquire_late)

    assert runtime_port.acquire_lock(deadline=deadline) is lease
    assert runtime_port._lease is lease
    assert owner_port._lease is lease and not lease._released

    runtime_port.release_lock(lease, deadline=_deadline(FakeClock()))
    assert runtime_port._lease is None
    assert owner_port._lease is None and lease._released


def test_wrong_runtime_evidence_type_fails_closed_and_retains_lease(
    signed_state, monkeypatch
):
    runtime_port, owner_port, lease, reads = _mock_port(monkeypatch, signed_state)
    deadline = _deadline(FakeClock())
    assert runtime_port.acquire_lock(deadline=deadline) is lease
    monkeypatch.setattr(
        "scripts.owned_nats_runtime_adapter.docker.observe_owned_core_runtime",
        lambda *_args, **_kwargs: object(),
    )

    with pytest.raises(RuntimeReadNotReady) as caught:
        runtime_port.observe_runtime(
            signed_state.adapter_owner, "1" * 64, deadline=deadline
        )

    assert str(caught.value) == ""
    assert len(reads) == 2 and all(candidate is deadline for candidate in reads)
    assert runtime_port._lease is lease
    assert owner_port._lease is lease and not lease._released
    runtime_port.release_lock(lease, deadline=deadline)


def test_release_failure_retains_exact_held_lease_for_retry(signed_state, monkeypatch):
    runtime_port, owner_port, lease, _reads = _mock_port(monkeypatch, signed_state)
    deadline = _deadline(FakeClock())
    assert runtime_port.acquire_lock(deadline=deadline) is lease

    def fail_release(self, candidate, *, deadline: Deadline):
        assert candidate is lease and self._lease is lease
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(SignedOwnerLeasePort, "release_lock", fail_release)
    with pytest.raises(RuntimeReadNotReady) as caught:
        runtime_port.release_lock(lease, deadline=deadline)
    assert str(caught.value) == ""
    assert runtime_port._lease is lease
    assert owner_port._lease is lease and not lease._released

    def retry_release(self, candidate, *, deadline: Deadline):
        assert candidate is lease and self._lease is lease
        lease._released = True
        self._lease = None

    monkeypatch.setattr(SignedOwnerLeasePort, "release_lock", retry_release)
    runtime_port.release_lock(lease, deadline=deadline)
    assert runtime_port._lease is None
    assert owner_port._lease is None and lease._released
