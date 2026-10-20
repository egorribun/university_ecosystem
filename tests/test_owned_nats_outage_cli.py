from __future__ import annotations

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
