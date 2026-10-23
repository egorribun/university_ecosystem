from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest

from scripts import live_stand
from scripts import owned_nats_outage_cli as cli
from scripts.owned_nats_coordinator import OutageOutcome, OutageResult, OutageStage
from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_owner_adapter import OwnerFilePins
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessResult,
    ProcessOutcome,
)
from tests.helpers.owned_nats_coordinator import FakePorts


def repository_with_source(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    source_path = scripts / "owned_nats_outage_cli.py"
    source_path.write_text("private test source", encoding="utf-8")
    return repository, source_path


def pins(tmp_path: Path) -> OwnerFilePins:
    return OwnerFilePins(
        repository=str(tmp_path / "repository"),
        state_root=str(tmp_path / "state-run"),
        source_sha="a" * 40,
        owner_uid=1000,
    )


def test_facade_construction_is_pure_and_lock_precedes_owner_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    underlying = FakePorts()
    safe_pins = pins(tmp_path)
    monkeypatch.setattr(
        cli,
        "_prepare_owner_file_pins",
        lambda state_dir, *, in_place, deadline: events.append("preflight")
        or safe_pins,
    )

    def make_transport(owner_pins: OwnerFilePins, *, sleep: object) -> FakePorts:
        assert owner_pins is safe_pins
        events.append("construct")
        return underlying

    monkeypatch.setattr(cli, "_make_transport", make_transport)
    monkeypatch.setattr(cli, "_transport_type", lambda: FakePorts)
    port = cli._LazyOwnedNatsPorts(
        tmp_path / "state-run", in_place=True, sleep=lambda _: None
    )
    assert events == []
    assert underlying.calls == []

    deadline = Deadline.after(10, clock=underlying.clock)
    with pytest.raises(cli._FacadeNotReady):
        port.read_signed_owner(deadline=deadline)
    assert underlying.calls == []
    lease = port.acquire_lock(deadline=deadline)
    assert lease is underlying.lease
    assert events == ["preflight", "construct"]
    assert [call.name for call in underlying.calls] == ["acquire_lock"]

    owner = port.read_signed_owner(deadline=deadline)
    assert owner is underlying.owner
    assert [call.name for call in underlying.calls] == [
        "acquire_lock",
        "read_signed_owner",
    ]
    assert (
        port.release_lock(lease, deadline=Deadline.after(10, clock=underlying.clock))
        is None
    )
    assert [call.name for call in underlying.calls][-1] == "release_lock"


def test_git_state_preflight_uses_one_deadline_and_rejects_dirty_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = FakePorts().clock
    deadline = Deadline.after(10, clock=clock)
    repository, source_path = repository_with_source(tmp_path)
    state_root = tmp_path
    git = tmp_path / "git"
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(cli.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(cli, "_repository_root", lambda _deadline: repository)
    monkeypatch.setattr(cli, "_facade_source_path", lambda _deadline: source_path)
    monkeypatch.setattr(cli, "_validated_state_root", lambda raw, deadline: state_root)
    monkeypatch.setattr(cli, "_git_executable", lambda: git)
    monkeypatch.setattr(cli, "_GIT_PATH", git)
    monkeypatch.setattr(cli, "_git_executable_identity", lambda path: (1, 2, 3, 4, 5))
    assert cli._deadline_live(deadline)
    assert cli.os.name == "posix"
    assert state_root.resolve(strict=True) == state_root
    assert repository.is_dir()
    assert cli._git_executable_identity(git) == (1, 2, 3, 4, 5)
    outputs = [
        os_fsencode(repository) + b"\n",
        b"a" * 40 + b"\n",
        b" M scripts/unsafe.py\n",
    ]
    seen: list[tuple[object, object]] = []

    def run(request: object, *, deadline: Deadline) -> PrivateProcessResult:
        seen.append((request, deadline))
        return PrivateProcessResult(
            ProcessOutcome.EXITED,
            0,
            outputs.pop(0),
            b"",
            LocalCleanup.CONFIRMED,
        )

    monkeypatch.setattr(cli.process, "run_private_process", run)
    result = cli._prepare_owner_file_pins("/", in_place=True, deadline=deadline)

    assert result is None
    assert len(seen) == 3
    assert all(supplied_deadline is deadline for _, supplied_deadline in seen)
    requests = [request for request, _ in seen]
    assert all(request.argv[0] == str(git) for request in requests)
    assert all(request.cwd == str(repository) for request in requests)
    assert all(request.stdin == b"" for request in requests)
    assert all(
        request.stdout_limit <= 4096 and request.stderr_limit <= 1024
        for request in requests
    )
    assert all(
        not any(key.casefold().endswith("token") for key in request.env)
        for request in requests
    )
    assert requests[0].argv[-1] == "--show-toplevel"
    assert requests[1].argv[-1] == "HEAD^{commit}"
    assert requests[2].argv[-1] == "--ignore-submodules=none"


def test_preflight_returns_only_clean_source_and_current_uid_pins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = FakePorts().clock
    deadline = Deadline.after(10, clock=clock)
    repository, source_path = repository_with_source(tmp_path)
    state_root = tmp_path
    git = tmp_path / "git"
    state_args: list[str] = []
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(cli.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(cli, "_repository_root", lambda _deadline: repository)
    monkeypatch.setattr(cli, "_facade_source_path", lambda _deadline: source_path)
    monkeypatch.setattr(
        cli,
        "_validated_state_root",
        lambda raw, deadline: state_args.append(raw) or state_root,
    )
    monkeypatch.setattr(cli, "_git_executable", lambda: git)
    monkeypatch.setattr(cli, "_GIT_PATH", git)
    monkeypatch.setattr(cli, "_git_executable_identity", lambda path: (1, 2, 3, 4, 5))
    outputs = [
        os_fsencode(repository) + b"\n",
        b"b" * 40 + b"\n",
        b"",
    ]
    seen: list[tuple[object, Deadline]] = []

    def run(request: object, *, deadline: Deadline) -> PrivateProcessResult:
        seen.append((request, deadline))
        return PrivateProcessResult(
            ProcessOutcome.EXITED,
            0,
            outputs.pop(0),
            b"",
            LocalCleanup.CONFIRMED,
        )

    monkeypatch.setattr(cli.process, "run_private_process", run)
    result = cli._prepare_owner_file_pins("/", in_place=True, deadline=deadline)

    assert type(result) is OwnerFilePins
    assert result.repository == str(repository)
    assert result.state_root == str(state_root)
    assert result.source_sha == "b" * 40
    assert result.owner_uid == 1000
    assert state_args == ["/"]
    assert len(seen) == 3
    assert all(seen_deadline is deadline for _, seen_deadline in seen)
    requests = [request for request, _ in seen]
    assert requests[0].argv[-2:] == ("rev-parse", "--show-toplevel")
    assert requests[1].argv[-4:] == (
        "rev-parse",
        "--verify",
        "--end-of-options",
        "HEAD^{commit}",
    )
    assert requests[2].argv[-4:] == (
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    assert set(requests[0].env) == {
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_OPTIONAL_LOCKS",
        "GIT_TERMINAL_PROMPT",
        "LC_ALL",
        "LANG",
        "PATH",
    }
    assert all(request.stdin == b"" for request in requests)
    assert all(request.stdout_limit == 4096 for request in requests)
    assert all(request.stderr_limit == 1024 for request in requests)


def os_fsencode(path: Path) -> bytes:
    return str(path).encode("utf-8")


def test_expired_git_preflight_never_constructs_transport_or_reads_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    underlying = FakePorts()
    clock = underlying.clock
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(cli.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000, raising=False)
    repository, source_path = repository_with_source(tmp_path)
    monkeypatch.setattr(cli, "_repository_root", lambda _deadline: repository)
    monkeypatch.setattr(cli, "_facade_source_path", lambda _deadline: source_path)
    monkeypatch.setattr(cli, "_validated_state_root", lambda raw, deadline: tmp_path)
    monkeypatch.setattr(cli, "_git_executable", lambda: tmp_path / "git")
    monkeypatch.setattr(cli, "_GIT_PATH", tmp_path / "git")
    monkeypatch.setattr(cli, "_git_executable_identity", lambda path: (1, 2, 3, 4, 5))
    constructed: list[OwnerFilePins] = []

    def make_transport(owner_pins: OwnerFilePins, *, sleep: object) -> FakePorts:
        constructed.append(owner_pins)
        return underlying

    monkeypatch.setattr(cli, "_make_transport", make_transport)
    monkeypatch.setattr(cli, "_transport_type", lambda: FakePorts)
    monkeypatch.setattr(cli.time, "monotonic", clock)
    monkeypatch.setattr(cli.time, "sleep", underlying.sleep)

    git_calls: list[Deadline] = []

    def expire_on_git(request: object, *, deadline: Deadline) -> PrivateProcessResult:
        git_calls.append(deadline)
        clock.now = 11
        return PrivateProcessResult(
            ProcessOutcome.EXITED,
            0,
            os_fsencode(tmp_path / "repository") + b"\n",
            b"",
            LocalCleanup.CONFIRMED,
        )

    monkeypatch.setattr(cli.process, "run_private_process", expire_on_git)
    result = cli.run_owned_nats_outage("/", in_place=True)

    assert result == cli.OutageResult(OutageOutcome.FAILED, OutageStage.PREFLIGHT)
    assert len(git_calls) == 1
    assert constructed == []
    assert underlying.calls == []


@pytest.mark.parametrize(
    ("failed_operation", "expected_stage"),
    [
        ("send_message_once", OutageStage.SEND),
        ("close_clients", OutageStage.CLEANUP),
        ("release_lock", OutageStage.CLEANUP),
    ],
)
def test_coordinator_runs_once_and_owns_cleanup_and_restoration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failed_operation: str,
    expected_stage: OutageStage,
) -> None:
    underlying = FakePorts()
    underlying.script[failed_operation] = [RuntimeError("private transport detail")]
    safe_pins = pins(tmp_path)
    events: list[str] = []
    monkeypatch.setattr(cli.time, "monotonic", underlying.clock)
    monkeypatch.setattr(cli.time, "sleep", underlying.sleep)
    monkeypatch.setattr(
        cli,
        "_prepare_owner_file_pins",
        lambda state_dir, *, in_place, deadline: safe_pins,
    )

    class CompositeProbe:
        def __getattr__(self, name: str) -> object:
            return getattr(underlying, name)

        def close_clients(self, *, deadline: Deadline) -> None:
            events.extend(("http-close", "broker-close"))
            underlying.close_clients(deadline=deadline)

    composite = CompositeProbe()
    constructions: list[OwnerFilePins] = []

    def make_transport(owner_pins: OwnerFilePins, *, sleep: object) -> CompositeProbe:
        constructions.append(owner_pins)
        return composite

    monkeypatch.setattr(cli, "_make_transport", make_transport)
    monkeypatch.setattr(cli, "_transport_type", lambda: CompositeProbe)
    original = cli.coordinator.run_owned_outage
    coordinator_calls: list[object] = []

    def counted(*args: object, **kwargs: object) -> object:
        coordinator_calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(cli.coordinator, "run_owned_outage", counted)
    result = cli.run_owned_nats_outage("/", in_place=True)

    names = [call.name for call in underlying.calls]
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is expected_stage
    assert len(coordinator_calls) == 1
    assert constructions == [safe_pins]
    assert names.count("acquire_lock") == names.count("release_lock") == 1
    assert names.count("close_clients") == 1
    assert names.index("acquire_lock") < names.index("read_signed_owner")
    assert names.index("send_message_once") < names.index("start_container")
    assert (
        names.index("start_container")
        < names.index("close_clients")
        < names.index("release_lock")
    )
    assert events == ["http-close", "broker-close"]
    assert underlying.contract_errors == []
    assert "private transport detail" not in repr(result)


def test_invalid_mode_is_closed_without_preflight_or_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli,
        "_prepare_owner_file_pins",
        lambda *args, **kwargs: calls.append("preflight") or pins(tmp_path),
    )
    monkeypatch.setattr(
        cli,
        "_make_transport",
        lambda *args, **kwargs: calls.append("transport") or FakePorts(),
    )
    result = cli.run_owned_nats_outage("/private/nonexistent/path", in_place=1)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is OutageStage.PREFLIGHT
    assert calls == []
    assert "/private/nonexistent/path" not in repr(result)


@pytest.mark.parametrize("outcome", list(OutageOutcome))
@pytest.mark.parametrize("stage", list(OutageStage))
def test_main_reports_only_finite_outage_result_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outcome: OutageOutcome,
    stage: OutageStage,
) -> None:
    calls: list[tuple[object, object]] = []
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda args: None)

    def run(state_dir: object, *, in_place: object) -> OutageResult:
        calls.append((state_dir, in_place))
        return OutageResult(outcome, stage)

    monkeypatch.setattr(cli, "run_owned_nats_outage", run)
    accepted = outcome is OutageOutcome.ACCEPTED and stage is OutageStage.COMPLETE
    result = live_stand.main(
        ["nats-outage", "--in-place", "--state-dir", "/private/state"]
    )
    assert result == (0 if accepted else 2)
    captured = capsys.readouterr()
    expected = (
        ""
        if accepted
        else "live_stand: owned NATS acceptance failed "
        f"outcome={outcome.value} stage={stage.value}\n"
    )
    assert captured.out == ""
    assert captured.err == expected
    assert calls == [("/private/state", True)]


@pytest.mark.parametrize("boundary", ["state", "runner"])
def test_main_outage_exception_diagnostics_never_format_private_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    boundary: str,
) -> None:
    calls: list[str] = []

    class PrivateFailure(RuntimeError):
        def __str__(self) -> str:
            pytest.fail("private exception must never be formatted")

        def __repr__(self) -> str:
            pytest.fail("private exception must never be represented")

    def configure(args: object) -> None:
        calls.append("state")
        if boundary == "state":
            raise PrivateFailure("private detail\n::error::injected")

    def run(state_dir: object, *, in_place: object) -> OutageResult:
        calls.append("runner")
        raise PrivateFailure("private detail\n::error::injected")

    monkeypatch.setattr(live_stand, "_configure_state_mode", configure)
    monkeypatch.setattr(cli, "run_owned_nats_outage", run)
    assert (
        live_stand.main(["nats-outage", "--in-place", "--state-dir", "/private/state"])
        == 2
    )
    captured = capsys.readouterr()
    reason = "state_configuration" if boundary == "state" else "runner_exception"
    assert captured.out == ""
    assert captured.err == f"live_stand: owned NATS acceptance failed reason={reason}\n"
    assert calls == (["state"] if boundary == "state" else ["state", "runner"])


class _PrivateOutageValue:
    def __str__(self) -> str:
        raise AssertionError("private result must never be formatted")

    def __repr__(self) -> str:
        raise AssertionError("private result must never be represented")


@pytest.mark.parametrize(
    "bad_result",
    [
        None,
        "private detail\n::error::injected",
        OutageResult(cast(OutageOutcome, "accepted"), OutageStage.COMPLETE),
        OutageResult(OutageOutcome.ACCEPTED, cast(OutageStage, "complete")),
        OutageResult(cast(OutageOutcome, "private detail"), OutageStage.PREFLIGHT),
        OutageResult(
            OutageOutcome.FAILED, cast(OutageStage, "private\n::error::injected")
        ),
        _PrivateOutageValue(),
        OutageResult(cast(OutageOutcome, _PrivateOutageValue()), OutageStage.PREFLIGHT),
        OutageResult(OutageOutcome.FAILED, cast(OutageStage, _PrivateOutageValue())),
    ],
    ids=[
        "missing",
        "private-string",
        "string-outcome",
        "string-stage",
        "private-outcome",
        "private-stage",
        "hostile-result",
        "hostile-outcome",
        "hostile-stage",
    ],
)
def test_main_outage_rejects_untyped_result_without_emitting_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_result: object,
) -> None:
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda args: None)
    monkeypatch.setattr(
        cli, "run_owned_nats_outage", lambda *args, **kwargs: bad_result
    )
    assert (
        live_stand.main(["nats-outage", "--in-place", "--state-dir", "/private/state"])
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "live_stand: owned NATS acceptance failed reason=invalid_result\n"
    )


_PREFLIGHT_CHECKPOINT_OPERATIONS = (
    "acquire_lock",
    "read_signed_owner",
    "observe_runtime",
    "read_policy",
    "read_admission",
    "login_admin",
    "create_dm_once",
    "read_dm",
    "pending_count",
)


def _require_checkpoint_contract() -> type[StrEnum]:
    checkpoint_type = getattr(cli.coordinator, "OutageCheckpoint", None)
    assert checkpoint_type is not None, "missing finite OutageCheckpoint diagnostic"
    assert isinstance(checkpoint_type, type) and issubclass(checkpoint_type, StrEnum)
    result = OutageResult(OutageOutcome.FAILED, OutageStage.PREFLIGHT)
    assert hasattr(result, "checkpoint"), "missing optional result checkpoint"
    assert result.checkpoint is None
    expected = {
        *_PREFLIGHT_CHECKPOINT_OPERATIONS,
        "coordinator_exception",
        "broker_probe",
        "broker_receipt",
    }
    assert {entry.value for entry in checkpoint_type} == expected
    assert replace(result, checkpoint=checkpoint_type("acquire_lock")) == result
    return checkpoint_type


def _install_checkpoint_fake_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> FakePorts:
    underlying = FakePorts()
    safe_pins = pins(tmp_path)
    monkeypatch.setattr(cli.time, "monotonic", underlying.clock)
    monkeypatch.setattr(cli.time, "sleep", underlying.sleep)
    monkeypatch.setattr(
        cli,
        "_prepare_owner_file_pins",
        lambda state_dir, *, in_place, deadline: safe_pins,
    )
    monkeypatch.setattr(cli, "_make_transport", lambda owner_pins, *, sleep: underlying)
    monkeypatch.setattr(cli, "_transport_type", lambda: FakePorts)
    return underlying


def _rejected_preflight_evidence(underlying: FakePorts, operation: str) -> object:
    if operation == "acquire_lock":
        return None
    original = underlying._default(operation)
    if operation == "read_signed_owner":
        return replace(original, stack="full")
    if operation == "observe_runtime":
        return replace(original, daemon_fingerprint="0" * 64)
    if operation == "read_policy":
        return replace(original, poll_interval_seconds=-1)
    if operation == "read_admission":
        return replace(original, users=())
    if operation == "login_admin":
        return replace(original, status_code=401)
    if operation == "create_dm_once":
        return replace(original, status_code=500)
    if operation == "read_dm":
        return replace(original, chat=None)
    assert operation == "pending_count"
    return 1


@pytest.mark.parametrize("operation", _PREFLIGHT_CHECKPOINT_OPERATIONS)
@pytest.mark.parametrize("failure_kind", ["exception", "rejected-evidence"])
def test_preflight_checkpoint_identifies_real_facade_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    failure_kind: str,
) -> None:
    checkpoint_type = _require_checkpoint_contract()
    underlying = _install_checkpoint_fake_ports(monkeypatch, tmp_path)

    class PrivateFailure(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("private exception must not be inspected")

        def __repr__(self) -> str:
            raise AssertionError("private exception must not be inspected")

    value = (
        PrivateFailure("private\n::error::injected")
        if failure_kind == "exception"
        else _rejected_preflight_evidence(underlying, operation)
    )
    underlying.script[operation] = [value]
    result = cli.run_owned_nats_outage("/", in_place=True)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is OutageStage.PREFLIGHT
    assert result.checkpoint is checkpoint_type(operation)
    names = [call.name for call in underlying.calls]
    assert names.count(operation) == 1
    failed_index = _PREFLIGHT_CHECKPOINT_OPERATIONS.index(operation)
    assert not set(names) & set(_PREFLIGHT_CHECKPOINT_OPERATIONS[failed_index + 1 :])
    assert [name for name in names if name in _PREFLIGHT_CHECKPOINT_OPERATIONS] == list(
        _PREFLIGHT_CHECKPOINT_OPERATIONS[: failed_index + 1]
    )
    assert "stop_container" not in names
    assert "start_container" not in names
    assert names.count("close_clients") == 1
    assert names.count("release_lock") == (0 if operation == "acquire_lock" else 1)
    assert underlying.contract_errors == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    ("operation", "stage"),
    [
        ("send_message_once", OutageStage.SEND),
        ("close_clients", OutageStage.CLEANUP),
        ("release_lock", OutageStage.CLEANUP),
    ],
)
def test_preflight_checkpoint_does_not_override_later_failure_or_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    stage: OutageStage,
) -> None:
    _require_checkpoint_contract()
    underlying = _install_checkpoint_fake_ports(monkeypatch, tmp_path)
    underlying.script[operation] = [RuntimeError("private transport detail")]
    result = cli.run_owned_nats_outage("/", in_place=True)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is stage
    assert result.checkpoint is None
    names = [call.name for call in underlying.calls]
    for name in (
        "acquire_lock",
        "stop_container",
        "send_message_once",
        "start_container",
        "close_clients",
        "release_lock",
    ):
        assert names.count(name) == 1
    assert names.index("stop_container") < names.index("send_message_once")
    assert names.index("send_message_once") < names.index("start_container")
    assert names.index("start_container") < names.index("close_clients")
    assert names.index("close_clients") < names.index("release_lock")
    assert underlying.restore_started is True
    assert underlying.stopped is False
    assert underlying.contract_errors == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("cleanup", ["close_clients", "release_lock"])
def test_preflight_checkpoint_is_cleared_when_cleanup_supersedes_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cleanup: str
) -> None:
    _require_checkpoint_contract()
    underlying = _install_checkpoint_fake_ports(monkeypatch, tmp_path)
    underlying.script["read_policy"] = [RuntimeError("private preflight detail")]
    underlying.script[cleanup] = [RuntimeError("private cleanup detail")]
    result = cli.run_owned_nats_outage("/", in_place=True)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is OutageStage.CLEANUP
    assert result.checkpoint is None
    names = [call.name for call in underlying.calls]
    assert "stop_container" not in names
    assert "start_container" not in names
    assert names.count("close_clients") == names.count("release_lock") == 1
    assert underlying.contract_errors == []


def test_successful_facade_clears_preflight_checkpoint_and_stays_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _require_checkpoint_contract()
    underlying = _install_checkpoint_fake_ports(monkeypatch, tmp_path)
    result = cli.run_owned_nats_outage("/", in_place=True)
    assert result.outcome is OutageOutcome.ACCEPTED
    assert result.stage is OutageStage.COMPLETE
    assert result.checkpoint is None
    names = [call.name for call in underlying.calls]
    assert names.count("stop_container") == names.count("start_container") == 1
    assert names.count("close_clients") == names.count("release_lock") == 1
    assert underlying.contract_errors == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_facade_unexpected_coordinator_exception_has_distinct_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint_type = _require_checkpoint_contract()
    calls: list[str] = []

    class PrivateFailure(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("private exception must not be inspected")

        def __repr__(self) -> str:
            raise AssertionError("private exception must not be inspected")

    def fail(ports: object, *, clock: object, sleep: object) -> OutageResult:
        calls.append("coordinator")
        raise PrivateFailure("private\n::error::injected")

    monkeypatch.setattr(cli.coordinator, "run_owned_outage", fail)
    result = cli.run_owned_nats_outage("/private/state", in_place=True)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is OutageStage.PREFLIGHT
    assert result.checkpoint is checkpoint_type("coordinator_exception")
    assert calls == ["coordinator"]
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    "checkpoint_value",
    (*_PREFLIGHT_CHECKPOINT_OPERATIONS, "coordinator_exception"),
)
def test_main_renders_only_typed_preflight_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    checkpoint_value: str,
) -> None:
    checkpoint_type = _require_checkpoint_contract()
    result = replace(
        OutageResult(OutageOutcome.FAILED, OutageStage.PREFLIGHT),
        checkpoint=checkpoint_type(checkpoint_value),
    )
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda args: None)
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *args, **kwargs: result)
    assert (
        live_stand.main(["nats-outage", "--in-place", "--state-dir", "/private/state"])
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed outcome=failed stage=preflight "
        f"checkpoint={checkpoint_value}\n"
    )


def test_main_renders_broker_receipt_checkpoint_without_private_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.owned_nats_coordinator import (
        BrokerMessageEvidence,
        OutageCheckpoint,
    )

    underlying = _install_checkpoint_fake_ports(monkeypatch, tmp_path)
    private_marker = "private-broker-envelope-must-not-leak"
    underlying.broker = BrokerMessageEvidence(
        subject="chat.invalid",
        sequence=1,
        envelope={"private": private_marker},
    )
    result = cli.run_owned_nats_outage("/", in_place=True)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is OutageStage.BROKER
    assert result.checkpoint is OutageCheckpoint.BROKER_RECEIPT

    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *_a, **_k: result)
    assert (
        live_stand.main(["nats-outage", "--in-place", "--state-dir", "/private/state"])
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed outcome=failed stage=broker "
        "checkpoint=broker_receipt\n"
    )
    assert private_marker not in captured.out + captured.err


@pytest.mark.parametrize("accepted", [False, True])
def test_main_default_checkpoint_preserves_legacy_result_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    accepted: bool,
) -> None:
    _require_checkpoint_contract()
    result = (
        OutageResult(OutageOutcome.ACCEPTED, OutageStage.COMPLETE)
        if accepted
        else OutageResult(OutageOutcome.FAILED, OutageStage.PREFLIGHT)
    )
    assert result.checkpoint is None
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda args: None)
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *args, **kwargs: result)
    exit_code = live_stand.main(
        ["nats-outage", "--in-place", "--state-dir", "/private/state"]
    )
    assert exit_code == (0 if accepted else 2)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        ""
        if accepted
        else "live_stand: owned NATS acceptance failed outcome=failed stage=preflight\n"
    )


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize(
    "bad_kind", ["matching-string", "private-string", "integer", "boolean", "hostile"]
)
def test_main_rejects_malformed_checkpoint_before_success_or_formatting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    accepted: bool,
    bad_kind: str,
) -> None:
    _require_checkpoint_contract()

    class PrivateValue:
        def __str__(self) -> str:
            raise AssertionError("private checkpoint must not be inspected")

        def __repr__(self) -> str:
            raise AssertionError("private checkpoint must not be inspected")

        def __bool__(self) -> bool:
            raise AssertionError("private checkpoint must not be inspected")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("private checkpoint must not be inspected")

    bad_values: dict[str, object] = {
        "matching-string": "acquire_lock",
        "private-string": "private\n::error::injected",
        "integer": 1,
        "boolean": True,
        "hostile": PrivateValue(),
    }
    result = (
        OutageResult(OutageOutcome.ACCEPTED, OutageStage.COMPLETE)
        if accepted
        else OutageResult(OutageOutcome.FAILED, OutageStage.PREFLIGHT)
    )
    object.__setattr__(result, "checkpoint", bad_values[bad_kind])
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda args: None)
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *args, **kwargs: result)
    assert (
        live_stand.main(["nats-outage", "--in-place", "--state-dir", "/private/state"])
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed reason=invalid_result\n"
    )


def test_outage_facade_attaches_diagnostic_only_to_runtime_preflight(monkeypatch):
    from types import SimpleNamespace

    from scripts.owned_nats_coordinator import (
        OutageCheckpoint,
        RuntimeObservationPhase,
    )

    phase = RuntimeObservationPhase.CONTAINER_IDS_PROCESS
    facade = SimpleNamespace(runtime_diagnostic=phase)
    monkeypatch.setattr(cli, "_LazyOwnedNatsPorts", lambda *_args, **_kwargs: facade)
    matching = OutageResult(
        OutageOutcome.FAILED,
        OutageStage.PREFLIGHT,
        OutageCheckpoint.OBSERVE_RUNTIME,
    )
    monkeypatch.setattr(
        cli.coordinator, "run_owned_outage", lambda *_args, **_kwargs: matching
    )
    result = cli.run_owned_nats_outage("/private/state", in_place=True)
    assert result.runtime_diagnostic is phase
    assert phase.value not in repr(result)

    unrelated = replace(matching, checkpoint=OutageCheckpoint.READ_POLICY)
    monkeypatch.setattr(
        cli.coordinator, "run_owned_outage", lambda *_args, **_kwargs: unrelated
    )
    result = cli.run_owned_nats_outage("/private/state", in_place=True)
    assert result.runtime_diagnostic is None


def test_main_formats_only_exact_runtime_diagnostic(monkeypatch, capsys):
    from scripts.owned_nats_coordinator import (
        OutageCheckpoint,
        RuntimeObservationPhase,
    )

    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    result = OutageResult(
        OutageOutcome.FAILED,
        OutageStage.PREFLIGHT,
        OutageCheckpoint.OBSERVE_RUNTIME,
        runtime_diagnostic=RuntimeObservationPhase.CONTAINER_IDS_DECODE,
    )
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *_args, **_kwargs: result)
    arguments = ["nats-outage", "--in-place", "--state-dir", "/private/state"]
    assert live_stand.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed outcome=failed stage=preflight "
        "checkpoint=observe_runtime runtime_diagnostic=container_ids_decode\n"
    )

    legacy = replace(result, runtime_diagnostic=None)
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *_args, **_kwargs: legacy)
    assert live_stand.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed outcome=failed stage=preflight "
        "checkpoint=observe_runtime\n"
    )

    class OtherPhase(StrEnum):
        CONTAINER_IDS_DECODE = "container_ids_decode"

    for invalid in (
        "container_ids_decode",
        OtherPhase.CONTAINER_IDS_DECODE,
        3,
        True,
        _PrivateOutageValue(),
    ):
        malformed = replace(result, runtime_diagnostic=invalid)
        monkeypatch.setattr(
            cli, "run_owned_nats_outage", lambda *_a, _r=malformed, **_k: _r
        )
        assert live_stand.main(arguments) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == (
            "live_stand: owned NATS acceptance failed reason=invalid_result\n"
        )


@pytest.mark.parametrize(
    ("outcome", "stage", "checkpoint"),
    [
        ("failed", "preflight", "read_policy"),
        ("accepted", "complete", None),
    ],
)
def test_main_refuses_runtime_diagnostic_outside_matching_failure(
    monkeypatch, capsys, outcome, stage, checkpoint
):
    from scripts.owned_nats_coordinator import (
        OutageCheckpoint,
        RuntimeObservationPhase,
    )

    result = OutageResult(
        OutageOutcome(outcome),
        OutageStage(stage),
        OutageCheckpoint(checkpoint) if checkpoint else None,
        runtime_diagnostic=RuntimeObservationPhase.DAEMON,
    )
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *_args, **_kwargs: result)
    arguments = ["nats-outage", "--in-place", "--state-dir", "/private/state"]
    assert live_stand.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed reason=invalid_result\n"
    )


def test_main_rejects_accepted_result_with_stale_checkpoint(monkeypatch, capsys):
    from scripts.owned_nats_coordinator import OutageCheckpoint

    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    result = OutageResult(
        OutageOutcome.ACCEPTED,
        OutageStage.COMPLETE,
        OutageCheckpoint.BROKER_PROBE,
    )
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *_a, **_k: result)

    assert (
        live_stand.main(["nats-outage", "--in-place", "--state-dir", "/private/state"])
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed reason=invalid_result\n"
    )


def test_main_formats_only_exact_broker_probe_diagnostic(monkeypatch, capsys):
    from scripts.owned_nats_coordinator import (
        BrokerProbePhase,
        OutageCheckpoint,
    )

    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    result = OutageResult(
        OutageOutcome.FAILED,
        OutageStage.BROKER,
        OutageCheckpoint.BROKER_PROBE,
        broker_diagnostic=BrokerProbePhase.DECODE,
    )
    monkeypatch.setattr(cli, "run_owned_nats_outage", lambda *_args, **_kwargs: result)
    arguments = ["nats-outage", "--in-place", "--state-dir", "/private/state"]

    assert live_stand.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "live_stand: owned NATS acceptance failed outcome=failed stage=broker "
        "checkpoint=broker_probe broker_diagnostic=decode\n"
    )

    class OtherPhase(StrEnum):
        DECODE = "decode"

    for invalid in ("decode", OtherPhase.DECODE, 3, True, _PrivateOutageValue()):
        malformed = replace(result, broker_diagnostic=invalid)
        monkeypatch.setattr(
            cli, "run_owned_nats_outage", lambda *_a, _r=malformed, **_k: _r
        )
        assert live_stand.main(arguments) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == (
            "live_stand: owned NATS acceptance failed reason=invalid_result\n"
        )


def test_main_rejects_broker_diagnostic_outside_matching_failure(monkeypatch, capsys):
    from scripts.owned_nats_coordinator import (
        BrokerProbePhase,
        OutageCheckpoint,
    )

    results = (
        OutageResult(
            OutageOutcome.ACCEPTED,
            OutageStage.COMPLETE,
            broker_diagnostic=BrokerProbePhase.PRECHECK,
        ),
        OutageResult(
            OutageOutcome.FAILED,
            OutageStage.BROKER,
            OutageCheckpoint.BROKER_RECEIPT,
            broker_diagnostic=BrokerProbePhase.POSTCHECK,
        ),
    )
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    arguments = ["nats-outage", "--in-place", "--state-dir", "/private/state"]
    for result in results:
        monkeypatch.setattr(
            cli, "run_owned_nats_outage", lambda *_a, _r=result, **_k: _r
        )
        assert live_stand.main(arguments) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == (
            "live_stand: owned NATS acceptance failed reason=invalid_result\n"
        )


def test_broker_diagnostic_field_is_private_and_not_semantic():
    from dataclasses import fields

    from scripts.owned_nats_coordinator import (
        BrokerProbePhase,
        OutageCheckpoint,
    )

    result = OutageResult(
        OutageOutcome.FAILED,
        OutageStage.BROKER,
        OutageCheckpoint.BROKER_PROBE,
    )
    schema = {item.name: item for item in fields(result)}
    assert set(schema) == {
        "outcome",
        "stage",
        "checkpoint",
        "runtime_diagnostic",
        "broker_diagnostic",
    }
    assert result.broker_diagnostic is None
    assert schema["broker_diagnostic"].compare is False
    assert schema["broker_diagnostic"].repr is False
    annotated = replace(result, broker_diagnostic=BrokerProbePhase.DECODE)
    assert annotated == result
    assert repr(annotated) == repr(result)


def test_real_lazy_facade_forwards_finite_runtime_failure(
    monkeypatch, tmp_path, capsys
):
    from scripts.owned_nats_coordinator import (
        OutageCheckpoint,
        RuntimeObservationPhase,
    )

    underlying = _install_checkpoint_fake_ports(monkeypatch, tmp_path)
    underlying.runtime_diagnostic = RuntimeObservationPhase.COMPOSE_DECODE
    underlying.script["observe_runtime"] = [None]
    result = cli.run_owned_nats_outage("/", in_place=True)
    assert result.outcome is OutageOutcome.FAILED
    assert result.stage is OutageStage.PREFLIGHT
    assert result.checkpoint is OutageCheckpoint.OBSERVE_RUNTIME
    assert result.runtime_diagnostic is RuntimeObservationPhase.COMPOSE_DECODE
    assert underlying.contract_errors == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_runtime_diagnostic_field_is_private_and_not_semantic():
    from dataclasses import fields

    from scripts.owned_nats_coordinator import (
        OutageCheckpoint,
        RuntimeObservationPhase,
    )

    result = OutageResult(
        OutageOutcome.FAILED,
        OutageStage.PREFLIGHT,
        OutageCheckpoint.OBSERVE_RUNTIME,
    )
    schema = {item.name: item for item in fields(result)}
    assert set(schema) == {
        "outcome",
        "stage",
        "checkpoint",
        "runtime_diagnostic",
        "broker_diagnostic",
    }
    assert result.runtime_diagnostic is None
    assert schema["runtime_diagnostic"].compare is False
    assert schema["runtime_diagnostic"].repr is False
    annotated = replace(result, runtime_diagnostic=RuntimeObservationPhase.DAEMON)
    assert annotated == result
    assert repr(annotated) == repr(result)
