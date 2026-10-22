"""RED tests for the run-wide pinned NATS owner lease adapter."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import live_nats_transport as transport
from scripts import live_stand
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_owner_adapter import (
    OwnerFilePins,
    OwnerReadNotReady,
    SignedOwnerLeasePort,
)

_KEY = bytes(range(32))
_SOURCE = "a" * 40


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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _deadline(clock: FakeClock) -> Deadline:
    return Deadline.after(20.0, clock=clock)


def _pin_values(root: Path, repository: Path, owner_uid: int) -> dict[str, object]:
    return {
        "repository": str(repository),
        "state_root": str(root),
        "source_sha": _SOURCE,
        "owner_uid": owner_uid,
    }


@pytest.fixture
def signed_state(tmp_path: Path):
    root = tmp_path / "ue-live-acceptance" / "run-owner-adapter"
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
    pins = OwnerFilePins(**_pin_values(root, repository, uid))
    expected = OwnerEvidence(
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
    return SimpleNamespace(
        root=root,
        secrets=secrets,
        marker=marker,
        key_file=key_file,
        lock_path=lock_path,
        marker_bytes=marker_bytes,
        key_bytes=_KEY,
        pins=pins,
        expected=expected,
    )


def _port(state) -> SignedOwnerLeasePort:
    return SignedOwnerLeasePort(state.pins, sleep=lambda _seconds: None)


def _assert_unsupported_or_preserved(state) -> bool:
    if _supports_posix_reader():
        return False
    port = _port(state)
    deadline = _deadline(FakeClock())
    snapshots = (
        state.marker.read_bytes(),
        state.key_file.read_bytes(),
        state.lock_path.read_bytes(),
    )
    assert port.acquire_lock(deadline=deadline) is None
    with pytest.raises(OwnerReadNotReady):
        port.read_signed_owner(deadline=deadline)
    with pytest.raises(OwnerReadNotReady):
        port.release_lock(object(), deadline=deadline)
    assert _lock_snapshot(state.lock_path) == snapshots[2]
    assert state.marker.read_bytes() == snapshots[0]
    assert state.key_file.read_bytes() == snapshots[1]
    return True


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


def _lock_snapshot(lock_path: Path) -> bytes:
    return lock_path.read_bytes()


def test_posix_signed_file_handoff_holds_one_lease_across_repeated_reads(
    signed_state, monkeypatch, capsys
):
    if not _supports_posix_reader():
        assert _assert_unsupported_or_preserved(signed_state)
        return

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy, Docker, process, and mutation APIs are forbidden")

    for name in (
        "_owner_signing_key",
        "load_stand_owner",
        "stand_lifecycle_lock",
        "docker_daemon_fingerprint",
    ):
        monkeypatch.setattr(live_stand, name, forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("scripts.owned_nats_process.run_private_process", forbidden)
    for name in (
        "write",
        "mkdir",
        "makedirs",
        "unlink",
        "remove",
        "rename",
        "replace",
        "chmod",
        "truncate",
        "ftruncate",
    ):
        monkeypatch.setattr(os, name, forbidden)

    clock = FakeClock()
    deadline = _deadline(clock)
    port = _port(signed_state)
    marker_before = signed_state.marker.read_bytes()
    key_before = signed_state.key_file.read_bytes()
    lock_before = signed_state.lock_path.read_bytes()

    lease = port.acquire_lock(deadline=deadline)
    assert lease is not None
    assert _lock_is_held(signed_state.lock_path)

    assert port.read_signed_owner(deadline=deadline) == signed_state.expected
    assert port.read_signed_owner(deadline=deadline) == signed_state.expected
    assert _lock_is_held(signed_state.lock_path)

    assert port.release_lock(lease, deadline=deadline) is None
    assert not _lock_is_held(signed_state.lock_path)
    assert signed_state.marker.read_bytes() == marker_before
    assert signed_state.key_file.read_bytes() == key_before
    assert signed_state.lock_path.read_bytes() == lock_before
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    for private in (signed_state.marker_bytes.decode(), signed_state.key_bytes.hex()):
        assert private not in repr(port)
        assert private not in captured.out + captured.err


def test_unsupported_platform_fails_closed_without_creating_private_state(tmp_path):
    root = tmp_path / "missing" / "private-state"
    pins = OwnerFilePins(
        repository=str(tmp_path / "repository"),
        state_root=str(root),
        source_sha=_SOURCE,
        owner_uid=0,
    )
    port = SignedOwnerLeasePort(pins, sleep=lambda _seconds: None)
    deadline = _deadline(FakeClock())

    if _supports_posix_reader():
        # Invalid source pins must fail before the reader opens the missing path.
        invalid = OwnerFilePins(
            repository=str(tmp_path / "repository"),
            state_root=str(root),
            source_sha="A" * 40,
            owner_uid=0,
        )
        port = SignedOwnerLeasePort(invalid, sleep=lambda _seconds: None)
    assert port.acquire_lock(deadline=deadline) is None
    with pytest.raises(OwnerReadNotReady):
        port.read_signed_owner(deadline=deadline)
    assert not root.exists()
    assert not root.parent.exists()
    assert not (root.parent / f".{root.name}.lifecycle.lock").exists()


def test_owner_read_requires_the_exact_held_lease(signed_state):
    if not _supports_posix_reader():
        assert _assert_unsupported_or_preserved(signed_state)
        return
    port = _port(signed_state)
    deadline = _deadline(FakeClock())
    with pytest.raises(OwnerReadNotReady):
        port.read_signed_owner(deadline=deadline)

    lease = port.acquire_lock(deadline=deadline)
    assert lease is not None
    with pytest.raises(OwnerReadNotReady):
        port.release_lock(object(), deadline=deadline)
    assert _lock_is_held(signed_state.lock_path)
    assert port.read_signed_owner(deadline=deadline) == signed_state.expected
    port.release_lock(lease, deadline=deadline)


def test_second_acquire_cannot_replace_or_release_the_existing_lease(signed_state):
    if not _supports_posix_reader():
        assert _assert_unsupported_or_preserved(signed_state)
        return
    port = _port(signed_state)
    deadline = _deadline(FakeClock())
    lease = port.acquire_lock(deadline=deadline)
    assert lease is not None

    assert port.acquire_lock(deadline=deadline) is None
    assert _lock_is_held(signed_state.lock_path)
    assert port.read_signed_owner(deadline=deadline) == signed_state.expected
    port.release_lock(lease, deadline=deadline)


def test_invalid_pin_or_expired_deadline_never_acquires_a_lease(tmp_path):
    root = tmp_path / "missing-state"
    invalid = OwnerFilePins(
        repository=str(tmp_path / "repo"),
        state_root=str(root),
        source_sha="A" * 40,
        owner_uid=0,
    )
    port = SignedOwnerLeasePort(invalid, sleep=lambda _seconds: None)
    assert port.acquire_lock(deadline=_deadline(FakeClock())) is None
    assert not root.exists()

    clock = FakeClock()
    deadline = _deadline(clock)
    clock.now = deadline.expires_at
    valid = OwnerFilePins(
        repository=str(tmp_path / "repo"),
        state_root=str(root),
        source_sha=_SOURCE,
        owner_uid=0,
    )
    assert (
        SignedOwnerLeasePort(valid, sleep=lambda _seconds: None).acquire_lock(
            deadline=deadline
        )
        is None
    )
    assert not root.exists()


def test_port_forwards_exact_pins_and_deadline_while_retaining_one_lease(
    signed_state, monkeypatch
):
    clock = FakeClock()
    deadline = _deadline(clock)
    lease = transport.LifecycleLockLease()
    acquire_calls = []
    read_calls = []
    release_calls = []

    def acquire(root, *, deadline: Deadline, sleep):
        acquire_calls.append((root, deadline, sleep))
        return lease

    def read(
        candidate,
        *,
        pinned_repository,
        pinned_state_root,
        pinned_source_sha,
        pinned_owner_uid,
        deadline: Deadline,
    ):
        read_calls.append(
            (
                candidate,
                pinned_repository,
                pinned_state_root,
                pinned_source_sha,
                pinned_owner_uid,
                deadline,
            )
        )
        return transport.OwnerParseResult(
            transport.OwnerParseStatus.SIGNED_METADATA, signed_state.expected
        )

    def release(candidate, *, deadline: Deadline):
        release_calls.append((candidate, deadline))
        candidate._released = True
        return True

    monkeypatch.setattr(transport, "acquire_existing_lifecycle_lock", acquire)
    monkeypatch.setattr(transport, "read_signed_owner_v11_under_lease", read)
    monkeypatch.setattr(transport, "release_lifecycle_lock", release)
    port = _port(signed_state)

    assert port.acquire_lock(deadline=deadline) is lease
    assert port.read_signed_owner(deadline=deadline) == signed_state.expected
    assert port.read_signed_owner(deadline=deadline) == signed_state.expected
    assert acquire_calls == [(signed_state.pins.state_root, deadline, port._sleep)]
    assert read_calls == [
        (
            lease,
            signed_state.pins.repository,
            signed_state.pins.state_root,
            signed_state.pins.source_sha,
            signed_state.pins.owner_uid,
            deadline,
        ),
        (
            lease,
            signed_state.pins.repository,
            signed_state.pins.state_root,
            signed_state.pins.source_sha,
            signed_state.pins.owner_uid,
            deadline,
        ),
    ]
    assert port.release_lock(lease, deadline=deadline) is None
    assert release_calls == [(lease, deadline)]


def test_deadline_expiry_after_signed_read_rejects_owner_but_retains_lease(
    signed_state, monkeypatch
):
    clock = FakeClock()
    deadline = _deadline(clock)
    assert deadline.expires_at is not None
    lease = transport.LifecycleLockLease()
    monkeypatch.setattr(
        transport,
        "acquire_existing_lifecycle_lock",
        lambda *_args, **_kwargs: lease,
    )

    def late_read(*_args, deadline: Deadline, **_kwargs):
        clock.now = deadline.expires_at
        return transport.OwnerParseResult(
            transport.OwnerParseStatus.SIGNED_METADATA, signed_state.expected
        )

    monkeypatch.setattr(transport, "read_signed_owner_v11_under_lease", late_read)
    monkeypatch.setattr(
        transport, "release_lifecycle_lock", lambda *_args, **_kwargs: True
    )
    port = _port(signed_state)
    assert port.acquire_lock(deadline=deadline) is lease

    with pytest.raises(OwnerReadNotReady):
        port.read_signed_owner(deadline=deadline)
    assert port._lease is lease
    assert port.release_lock(lease, deadline=_deadline(FakeClock())) is None


def test_owner_file_rejection_keeps_original_lease_for_explicit_cleanup(signed_state):
    if not _supports_posix_reader():
        assert _assert_unsupported_or_preserved(signed_state)
        return
    signed_state.marker.write_bytes(
        signed_state.marker_bytes.replace(b"1" * 64, b"3" * 64, 1)
    )
    signed_state.marker.chmod(0o600)
    port = _port(signed_state)
    deadline = _deadline(FakeClock())
    lease = port.acquire_lock(deadline=deadline)
    assert lease is not None
    with pytest.raises(OwnerReadNotReady):
        port.read_signed_owner(deadline=deadline)
    assert _lock_is_held(signed_state.lock_path)
    assert port.release_lock(lease, deadline=deadline) is None
    assert not _lock_is_held(signed_state.lock_path)


def test_reader_interrupt_does_not_consume_lease_and_cleanup_failure_is_visible(
    signed_state, monkeypatch
):
    if not _supports_posix_reader():
        assert _assert_unsupported_or_preserved(signed_state)
        return
    port = _port(signed_state)
    deadline = _deadline(FakeClock())
    lease = port.acquire_lock(deadline=deadline)
    assert lease is not None

    error = KeyboardInterrupt("private fixture")

    def interrupt(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(transport, "read_signed_owner_v11_under_lease", interrupt)
    with pytest.raises(KeyboardInterrupt) as caught:
        port.read_signed_owner(deadline=deadline)
    assert caught.value is error
    assert _lock_is_held(signed_state.lock_path)

    monkeypatch.setattr(
        transport,
        "read_signed_owner_v11_under_lease",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        transport, "release_lifecycle_lock", lambda *_args, **_kwargs: False
    )
    with pytest.raises(OwnerReadNotReady):
        port.release_lock(lease, deadline=deadline)
    assert _lock_is_held(signed_state.lock_path)
    monkeypatch.undo()
    assert transport.release_lifecycle_lock(lease, deadline=deadline) is True
