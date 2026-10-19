"""Existing-file descriptor boundary, not runtime or post-read path admission."""

from __future__ import annotations

import builtins
import errno
import io
import json
import os
import stat
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import live_nats_transport as transport
from scripts import live_stand
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline

_KEY = bytes(range(32))  # Synthetic test fixture only.
_MARKER = "live-stand.json"
_KEY_FILE = "live-stand-owner.key"
_POSIX_DESCRIPTOR_API = (
    os.name == "posix"
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NONBLOCK")
    and hasattr(os, "O_CLOEXEC")
    and os.open in getattr(os, "supports_dir_fd", set())
    and hasattr(os, "mkfifo")
)
requires_posix_reader = pytest.mark.skipif(
    not _POSIX_DESCRIPTOR_API,
    reason="requires POSIX dir_fd, nofollow and nonblocking-open support",
)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def forbid_legacy_owner_or_runtime_helpers(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("owner-file reader must not call legacy/runtime helpers")

    for name in (
        "_owner_signing_key",
        "load_stand_owner",
        "stand_lifecycle_lock",
        "docker_daemon_fingerprint",
    ):
        monkeypatch.setattr(live_stand, name, forbidden)


@pytest.fixture
def owner_files(tmp_path):
    state_root = tmp_path / "ue-live-acceptance" / "run-reader"
    secrets = state_root / ".secrets"
    secrets.mkdir(parents=True)
    marker = secrets / _MARKER
    key_file = secrets / _KEY_FILE
    pins = {
        "pinned_repository": str(tmp_path / "repository"),
        "pinned_state_root": str(state_root),
        "pinned_source_sha": "a" * 40,
    }
    ports = {
        name: 20_000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    payload = {
        "version": 11,
        "repository": pins["pinned_repository"],
        "worktree": pins["pinned_state_root"],
        "project_name": "ue-live-0123456789abcdef",
        "published_ports": dict(live_stand._validate_published_ports(ports)),
        "daemon_fingerprint": "1" * 64,
        "compose_resource_fingerprint": "2" * 64,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": live_stand.LIVE_STACK_CORE,
        "service_roots": list(live_stand.LIVE_CORE_SERVICE_ROOTS),
        "selected_services": list(live_stand.LIVE_CORE_EXPECTED_SERVICES),
        "source_sha": pins["pinned_source_sha"],
    }
    signed = {**payload, "signature": live_stand._owner_signature(payload, _KEY)}
    marker_bytes = json.dumps(signed, indent=2).encode("utf-8")
    marker.write_bytes(marker_bytes)
    key_file.write_bytes(_KEY)
    key_file.chmod(0o600)
    return SimpleNamespace(
        pins=pins,
        state_root=state_root,
        secrets=secrets,
        marker=marker,
        key_file=key_file,
        marker_bytes=marker_bytes,
        key_bytes=_KEY,
    )


def _read(files, deadline):
    return transport.read_signed_owner_v11_from_state(**files.pins, deadline=deadline)


def _not_ready(result):
    assert result.status is transport.OwnerParseStatus.NOT_READY
    assert result.owner is None


def _deadline(clock=None):
    clock = clock or FakeClock()
    return clock, Deadline.after(10.0, clock=clock)


def _snapshot(path):
    info = path.lstat()
    return (
        path.read_bytes(),
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _observe_reader_call(
    monkeypatch,
    files,
    deadline,
    *,
    clock=None,
    after_read=None,
    fifo_leaf=None,
    observations=None,
    event_hook=None,
):
    ops = {
        "opens": [],
        "opened_fds": [],
        "closed_fds": [],
        "fd_names": {},
        "reads": [],
        "leaf_fstats": [],
        "write_attempts": [],
        "blocking_fifo_attempts": [],
        "opens_after_expiry": [],
        "reads_after_expiry": [],
        "high_level_io": [],
        "stats_after_expiry": [],
    }
    ops["close_attempts"] = []
    if observations is not None:
        observations.update(ops)
        ops = observations

    def event(stage, name, fd=None):
        if event_hook is not None:
            event_hook(stage, name, fd)

    real_open, real_close, real_read = os.open, os.close, os.read
    real_fstat, real_stat = os.fstat, os.stat
    write_mask = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def forbidden_file_api(*_args, **_kwargs):
        ops["high_level_io"].append(True)
        raise AssertionError("reader must use descriptor-relative I/O")

    def expired():
        return (
            clock is not None
            and deadline.expires_at is not None
            and clock.now >= deadline.expires_at
        )

    def open_spy(path, flags, mode=0o777, *, dir_fd=None):
        raw_path = os.fsdecode(path)
        name = "/" if raw_path == "/" else os.path.basename(raw_path)
        record = {
            "path": raw_path,
            "name": name,
            "flags": flags,
            "dir_fd": dir_fd,
            "fd": None,
        }
        ops["opens"].append(record)
        if expired():
            ops["opens_after_expiry"].append(name)
        if flags & write_mask:
            ops["write_attempts"].append(name)
            raise OSError(errno.EPERM, "test forbids file mutation")
        if name == fifo_leaf and not flags & getattr(os, "O_NONBLOCK", 0):
            ops["blocking_fifo_attempts"].append(name)
            raise OSError(errno.EPERM, "test prevents blocking FIFO open")
        event("before_open", name)
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        record["fd"] = fd
        ops["opened_fds"].append(fd)
        ops["fd_names"][fd] = name
        return fd

    def close_spy(fd):
        name = ops["fd_names"].get(fd, "")
        ops["close_attempts"].append(fd)
        event("before_close", name, fd)
        real_close(fd)
        ops["closed_fds"].append(fd)
        event("after_close", name, fd)

    def read_spy(fd, size):
        name = ops["fd_names"].get(fd, "")
        if expired():
            ops["reads_after_expiry"].append(name)
        event("before_read", name, fd)
        data = real_read(fd, size)
        ops["reads"].append((name, size, len(data)))
        if after_read is not None:
            after_read(name, data)
        return data

    def fstat_spy(fd):
        if expired():
            ops["stats_after_expiry"].append(True)
        info = real_fstat(fd)
        name = ops["fd_names"].get(fd, "")
        if name in {_MARKER, _KEY_FILE}:
            ops["leaf_fstats"].append((name, stat.S_ISREG(info.st_mode)))
        return info

    def stat_spy(path, *args, **kwargs):
        if expired():
            ops["stats_after_expiry"].append(True)
        info = real_stat(path, *args, **kwargs)
        event("after_stat", os.path.basename(os.fsdecode(path)))
        return info

    wrappers = (
        (real_open, open_spy),
        (real_close, close_spy),
        (real_read, read_spy),
        (real_fstat, fstat_spy),
        (real_stat, stat_spy),
    )
    with monkeypatch.context() as guard:
        for module, attr in (
            (builtins, "open"),
            (io, "open"),
            (Path, "open"),
            (Path, "read_bytes"),
            (Path, "write_bytes"),
            (Path, "resolve"),
        ):
            guard.setattr(module, attr, forbidden_file_api)
        for attr, wrapper in (
            ("open", open_spy),
            ("close", close_spy),
            ("read", read_spy),
            ("fstat", fstat_spy),
            ("stat", stat_spy),
        ):
            guard.setattr(os, attr, wrapper)
        for support in ("supports_dir_fd", "supports_fd", "supports_follow_symlinks"):
            if hasattr(os, support):
                members = set(getattr(os, support))
                for original, wrapper in wrappers:
                    if original in members:
                        members.add(wrapper)
                guard.setattr(os, support, members)
        result = _read(files, deadline)

    assert ops["high_level_io"] == []
    return result, ops


def _assert_fds_closed(ops):
    assert Counter(ops["opened_fds"]) == Counter(ops["closed_fds"])


def _assert_initial_component_walk(ops, state_root):
    expected_dirs = ["/", *Path(state_root).parts[1:], ".secrets"]
    directory_calls = ops["opens"][: len(expected_dirs)]
    assert [call["name"] for call in directory_calls] == expected_dirs
    for index, call in enumerate(directory_calls):
        expected_dir_fd = None if index == 0 else directory_calls[index - 1]["fd"]
        assert call["path"] == expected_dirs[index]
        assert call["dir_fd"] == expected_dir_fd
        assert call["flags"] & os.O_DIRECTORY
        assert call["flags"] & os.O_NOFOLLOW
        assert call["flags"] & os.O_CLOEXEC
    secrets_fd = directory_calls[-1]["fd"]
    leaves = ops["opens"][len(expected_dirs) :]
    assert {call["name"] for call in leaves} == {_MARKER, _KEY_FILE}
    assert len(leaves) == 2
    for call in leaves:
        assert call["path"] == call["name"]
        assert call["dir_fd"] == secrets_fd
        assert call["flags"] & os.O_NOFOLLOW
        assert call["flags"] & os.O_CLOEXEC
        assert call["flags"] & os.O_NONBLOCK


@requires_posix_reader
@pytest.mark.parametrize("pad_to_limit", [False, True], ids=["ordinary", "exact-cap"])
def test_existing_signed_files_return_signed_metadata_without_mutation(
    monkeypatch, capsys, owner_files, pad_to_limit
):
    files = owner_files
    if pad_to_limit:
        files.marker.write_bytes(
            files.marker_bytes
            + b" " * (transport.MAX_OWNER_MARKER_BYTES - len(files.marker_bytes))
        )
    before = (_snapshot(files.marker), _snapshot(files.key_file))
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    assert result.status is transport.OwnerParseStatus.SIGNED_METADATA
    assert isinstance(result.owner, OwnerEvidence)
    assert result.owner.repository == files.pins["pinned_repository"]
    assert result.owner.worktree == files.pins["pinned_state_root"]
    assert result.owner.schema_version == 11
    assert result.owner.project_name == "ue-live-0123456789abcdef"
    assert result.owner.stack == live_stand.LIVE_STACK_CORE
    assert result.owner.source_sha == files.pins["pinned_source_sha"]
    assert (_snapshot(files.marker), _snapshot(files.key_file)) == before
    assert ops["write_attempts"] == []
    for leaf in (_MARKER, _KEY_FILE):
        assert any(name == leaf and regular for name, regular in ops["leaf_fstats"])
    assert all(regular for _name, regular in ops["leaf_fstats"])
    _assert_initial_component_walk(ops, files.state_root)
    _assert_fds_closed(ops)
    shown = repr(result)
    assert files.pins["pinned_state_root"] not in shown
    assert files.key_bytes.hex() not in shown
    assert json.loads(files.marker_bytes)["signature"] not in shown
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@requires_posix_reader
@pytest.mark.parametrize("leaf", ["marker", "key"])
def test_missing_leaf_is_not_created(monkeypatch, owner_files, leaf):
    files = owner_files
    missing = files.marker if leaf == "marker" else files.key_file
    missing.unlink()
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    assert not missing.exists()
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
@pytest.mark.parametrize(
    "key",
    [b"k" * 31, b"k" * 32, b"k" * 33, b"k" * 65_537],
    ids=["short", "wrong-key", "one-byte-over", "large-key"],
)
def test_invalid_existing_key_is_rejected_without_replacement(
    monkeypatch, owner_files, key
):
    files = owner_files
    files.key_file.write_bytes(key)
    before = _snapshot(files.key_file)
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    assert _snapshot(files.key_file) == before
    key_reads = [
        (requested, actual)
        for name, requested, actual in ops["reads"]
        if name == _KEY_FILE
    ]
    assert all(requested <= 33 for requested, _actual in key_reads)
    assert sum(actual for _requested, actual in key_reads) <= 33
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
@pytest.mark.parametrize("leaf", ["marker", "key"])
def test_symlink_to_valid_leaf_is_rejected(monkeypatch, owner_files, leaf):
    files = owner_files
    link = files.marker if leaf == "marker" else files.key_file
    original = link.read_bytes()
    target = files.secrets / ("target-" + link.name)
    link.unlink()
    target.write_bytes(original)
    link.symlink_to(target.name)
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    assert link.is_symlink()
    assert target.read_bytes() == original
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
@pytest.mark.parametrize("where", ["state-root", "ancestor", "secrets"])
def test_initial_directory_walk_rejects_symlink_component(
    monkeypatch, owner_files, where
):
    files = owner_files
    if where == "state-root":
        link = files.state_root
        target = link.parent / "real-state-root"
        target_secrets = target / ".secrets"
    elif where == "ancestor":
        link = files.state_root.parent
        target = link.parent / "real-state-ancestor"
        target_secrets = target / files.state_root.name / ".secrets"
    else:
        link = files.secrets
        target = link.parent / "real-secrets"
        target_secrets = target
    marker_bytes = files.marker.read_bytes()
    key_bytes = files.key_file.read_bytes()
    link.rename(target)
    link.symlink_to(target, target_is_directory=True)
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    assert (target_secrets / _MARKER).read_bytes() == marker_bytes
    assert (target_secrets / _KEY_FILE).read_bytes() == key_bytes
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
@pytest.mark.parametrize("leaf", ["marker", "key"])
def test_fifo_is_rejected_without_blocking_open(monkeypatch, owner_files, leaf):
    files = owner_files
    fifo = files.marker if leaf == "marker" else files.key_file
    fifo.unlink()
    os.mkfifo(fifo, 0o600)
    fifo_name = _MARKER if leaf == "marker" else _KEY_FILE
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(
        monkeypatch, files, deadline, clock=clock, fifo_leaf=fifo_name
    )

    _not_ready(result)
    assert stat.S_ISFIFO(fifo.lstat().st_mode)
    assert ops["blocking_fifo_attempts"] == []
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
def test_oversized_marker_is_rejected_with_bounded_reads(monkeypatch, owner_files):
    files = owner_files
    files.marker.write_bytes(b" " * (transport.MAX_OWNER_MARKER_BYTES + 1))
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    marker_reads = [
        (requested, actual)
        for name, requested, actual in ops["reads"]
        if name == _MARKER
    ]
    cap = transport.MAX_OWNER_MARKER_BYTES + 1
    assert all(requested <= cap for requested, _actual in marker_reads)
    assert sum(actual for _requested, actual in marker_reads) <= cap
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
def test_dotdot_state_pin_is_rejected_before_open(monkeypatch, owner_files):
    files = owner_files
    files.pins["pinned_state_root"] += "/../run-reader"
    clock, deadline = _deadline()

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    assert ops["opens"] == []
    assert ops["reads"] == []


@requires_posix_reader
def test_expired_deadline_starts_no_filesystem_operation(monkeypatch, owner_files):
    files = owner_files
    clock = FakeClock()
    deadline = Deadline.after(1.0, clock=clock)
    clock.now = deadline.expires_at

    result, ops = _observe_reader_call(monkeypatch, files, deadline, clock=clock)

    _not_ready(result)
    assert ops["opens"] == []
    assert ops["reads"] == []
    assert ops["opened_fds"] == ops["closed_fds"] == []


@requires_posix_reader
def test_expiry_after_read_stops_work_and_still_closes_all_fds(
    monkeypatch, owner_files
):
    files = owner_files
    clock = FakeClock()
    deadline = Deadline.after(1.0, clock=clock)
    expired = False

    def expire_after_read(_name, data):
        nonlocal expired
        if data and not expired:
            expired = True
            clock.now = deadline.expires_at

    result, ops = _observe_reader_call(
        monkeypatch, files, deadline, clock=clock, after_read=expire_after_read
    )

    _not_ready(result)
    assert expired
    assert ops["opens_after_expiry"] == []
    assert ops["reads_after_expiry"] == []
    assert ops["stats_after_expiry"] == []
    _assert_fds_closed(ops)


@pytest.mark.parametrize(
    "missing", ["dir_fd", "O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC"]
)
def test_missing_required_open_capability_fails_closed_without_io(
    monkeypatch, owner_files, missing
):
    original_open = os.open
    calls = []

    def counted_open(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("unsupported API must be rejected before open")

    supported = set(getattr(os, "supports_dir_fd", set()))
    if original_open in supported:
        supported.add(counted_open)
    if missing == "dir_fd":
        supported.discard(counted_open)
    _clock, deadline = _deadline()

    with monkeypatch.context() as guard:
        guard.setattr(os, "open", counted_open)
        guard.setattr(os, "supports_dir_fd", supported, raising=False)
        if missing != "dir_fd":
            guard.setattr(os, missing, 0, raising=False)
        result = _read(owner_files, deadline)

    _not_ready(result)
    assert calls == []


@requires_posix_reader
@pytest.mark.parametrize("leaf", ["marker", "key"])
@pytest.mark.parametrize("mutation", ["replace", "metadata"])
def test_leaf_change_after_both_reads_prevents_parser_admission(
    monkeypatch, owner_files, leaf, mutation
):
    files = owner_files
    target = files.marker if leaf == "marker" else files.key_file
    replacement = files.secrets / "prepared-replacement"
    replacement.write_bytes(target.read_bytes())
    before = target.stat()
    real_replace, real_utime = os.replace, os.utime
    changed = []
    parser_calls = []

    def forbidden_parser(*_args, **_kwargs):
        parser_calls.append(True)
        raise AssertionError("changed leaf must be rejected before parsing")

    def mutate_after_key_eof(name, data):
        if name != _KEY_FILE or data or changed:
            return
        if mutation == "replace":
            real_replace(replacement, target)
        else:
            real_utime(
                target,
                ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
            )
        changed.append(True)

    monkeypatch.setattr(transport, "parse_signed_owner_v11", forbidden_parser)
    clock, deadline = _deadline()
    result, ops = _observe_reader_call(
        monkeypatch, files, deadline, clock=clock, after_read=mutate_after_key_eof
    )

    assert changed == [True]
    _not_ready(result)
    assert parser_calls == []
    assert any(name == _MARKER and size == 0 for name, _count, size in ops["reads"])
    assert any(name == _KEY_FILE and size == 0 for name, _count, size in ops["reads"])
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
@pytest.mark.parametrize("interrupt_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("stage", ["before_open", "before_read", "after_close"])
def test_interrupt_propagates_after_attempting_all_descriptor_cleanup(
    monkeypatch, owner_files, interrupt_type, stage
):
    _clock, deadline = _deadline()
    observations = {}
    interruption = interrupt_type("synthetic reader interruption")
    triggered = []

    def inject(event, name, _fd):
        if event == stage and name == _KEY_FILE and not triggered:
            triggered.append(event)
            raise interruption

    with pytest.raises(interrupt_type) as caught:
        _observe_reader_call(
            monkeypatch,
            owner_files,
            deadline,
            observations=observations,
            event_hook=inject,
        )

    assert caught.value is interruption
    assert triggered == [stage]
    assert observations["opened_fds"]
    assert observations["close_attempts"] == list(reversed(observations["opened_fds"]))
    _assert_fds_closed(observations)


@requires_posix_reader
def test_operation_interrupt_is_preserved_over_cleanup_interrupt(
    monkeypatch, owner_files
):
    _clock, deadline = _deadline()
    observations = {}
    operation_interrupt = KeyboardInterrupt("synthetic read interruption")
    cleanup_interrupt = SystemExit("synthetic cleanup interruption")
    triggered = []

    def inject(event, name, _fd):
        if name != _KEY_FILE:
            return
        if event == "before_read":
            triggered.append("read")
            raise operation_interrupt
        if event == "after_close":
            triggered.append("close")
            raise cleanup_interrupt

    with pytest.raises(KeyboardInterrupt) as caught:
        _observe_reader_call(
            monkeypatch,
            owner_files,
            deadline,
            observations=observations,
            event_hook=inject,
        )

    assert caught.value is operation_interrupt
    assert triggered == ["read", "close"]
    assert observations["close_attempts"] == list(reversed(observations["opened_fds"]))
    _assert_fds_closed(observations)


@requires_posix_reader
def test_first_cleanup_interrupt_is_preserved_and_later_closes_continue(
    monkeypatch, owner_files
):
    _clock, deadline = _deadline()
    observations = {}
    first = KeyboardInterrupt("synthetic first cleanup interruption")
    second = SystemExit("synthetic later cleanup interruption")
    triggered = []

    def inject(event, name, _fd):
        if event != "after_close":
            return
        if name == _KEY_FILE:
            triggered.append(name)
            raise first
        if name == _MARKER:
            triggered.append(name)
            raise second

    with pytest.raises(KeyboardInterrupt) as caught:
        _observe_reader_call(
            monkeypatch,
            owner_files,
            deadline,
            observations=observations,
            event_hook=inject,
        )

    assert caught.value is first
    assert triggered == [_KEY_FILE, _MARKER]
    assert observations["close_attempts"] == list(reversed(observations["opened_fds"]))
    _assert_fds_closed(observations)


@requires_posix_reader
@pytest.mark.parametrize("error_number", [errno.EINTR, errno.EIO])
@pytest.mark.parametrize("released", [False, True], ids=["unreleased", "released"])
def test_ambiguous_close_error_is_not_retried_and_fails_closed(
    monkeypatch, owner_files, error_number, released
):
    _clock, deadline = _deadline()
    observations = {}
    real_close = os.close
    stage = "after_close" if released else "before_close"
    triggered = []
    cleanup_needed = set()

    def inject(event, name, fd):
        if event == stage and name == _KEY_FILE and not triggered:
            triggered.append(fd)
            if not released:
                cleanup_needed.add(fd)
            raise OSError(error_number, "synthetic ambiguous close")

    try:
        result, ops = _observe_reader_call(
            monkeypatch,
            owner_files,
            deadline,
            observations=observations,
            event_hook=inject,
        )

        _not_ready(result)
        assert len(triggered) == 1
        assert ops["close_attempts"] == list(reversed(ops["opened_fds"]))
        assert Counter(ops["close_attempts"]) == Counter(ops["opened_fds"])
        if released:
            _assert_fds_closed(ops)
        else:
            assert Counter(ops["closed_fds"]) == (
                Counter(ops["opened_fds"]) - Counter(triggered)
            )
    finally:
        # Fixture cleanup only: the injected branch never performed real close.
        for fd in cleanup_needed:
            if fd not in observations.get("closed_fds", []):
                real_close(fd)


@requires_posix_reader
@pytest.mark.parametrize("where", ["state-root", "ancestor", "secrets"])
@pytest.mark.parametrize(
    "replacement", ["missing", "symlink"], ids=["renamed-away", "symlink-back"]
)
def test_post_read_directory_rename_is_rejected_before_parser(
    monkeypatch, owner_files, where, replacement
):
    files = owner_files
    _clock, deadline = _deadline()
    if where == "state-root":
        original = files.state_root
    elif where == "ancestor":
        original = files.state_root.parent
    else:
        original = files.secrets
    moved = original.with_name(original.name + "-moved")
    changed = []

    def forbidden_parser(*_args, **_kwargs):
        raise AssertionError("changed ancestor must be rejected before parsing")

    def rename_after_both_reads(name, data):
        if name == _KEY_FILE and data == b"" and not changed:
            original.rename(moved)
            if replacement == "symlink":
                original.symlink_to(moved, target_is_directory=True)
            changed.append(True)

    monkeypatch.setattr(transport, "parse_signed_owner_v11", forbidden_parser)
    result, ops = _observe_reader_call(
        monkeypatch,
        files,
        deadline,
        after_read=rename_after_both_reads,
    )

    assert changed == [True]
    _not_ready(result)
    assert any(name == _MARKER and size == 0 for name, _count, size in ops["reads"])
    assert any(name == _KEY_FILE and size == 0 for name, _count, size in ops["reads"])
    assert ops["write_attempts"] == []
    _assert_fds_closed(ops)


@requires_posix_reader
def test_expiry_during_ancestor_revalidation_stops_work_and_closes_fds(
    monkeypatch, owner_files
):
    clock, deadline = _deadline()
    state_checks = []
    parser_calls = []

    def forbidden_parser(*_args, **_kwargs):
        parser_calls.append(True)
        raise AssertionError("expired revalidation must not reach parser")

    monkeypatch.setattr(transport, "parse_signed_owner_v11", forbidden_parser)

    def expire_after_recheck(event, name, _fd):
        if event == "after_stat" and name == owner_files.state_root.name:
            state_checks.append(name)
            if len(state_checks) == 2:
                clock.now = deadline.expires_at

    result, ops = _observe_reader_call(
        monkeypatch,
        owner_files,
        deadline,
        clock=clock,
        event_hook=expire_after_recheck,
    )

    assert len(state_checks) == 2
    assert parser_calls == []
    assert any(name == _MARKER and size == 0 for name, _count, size in ops["reads"])
    assert any(name == _KEY_FILE and size == 0 for name, _count, size in ops["reads"])
    _not_ready(result)
    assert ops["opens_after_expiry"] == []
    assert ops["reads_after_expiry"] == []
    assert ops["stats_after_expiry"] == []
    _assert_fds_closed(ops)
