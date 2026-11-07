"""Only bounded metadata from the signed initializer can escape startup failure."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from scripts import live_stand

CID = "a" * 64
ROW = b"[postgres-roles-init] phase=reconcile exit=3 sqlstate=42501\n"


@pytest.mark.parametrize("state", [b"42501", b"42P01", b"UNKNOWN"])
def test_bootstrap_projection_returns_only_closed_metadata(state) -> None:
    row = b"[postgres-roles-init] phase=reconcile exit=3 sqlstate=" + state + b"\n"
    assert live_stand._parse_bootstrap_diagnostic(b"private noise\n" + row, b"") == (
        3,
        state.decode("ascii"),
    )


@pytest.mark.parametrize(
    "data",
    [
        b"",
        ROW[:-1],
        ROW + ROW,
        ROW.replace(b"42501", b"42p01"),
        ROW.replace(b"42501", b"42501 private"),
        ROW.replace(b"exit=3", b"exit=256"),
        ROW.replace(b"exit=3", b"exit=0"),
        ROW.replace(b"exit=3", b"exit=03"),
        ROW.replace(b"reconcile", b"password"),
        b"private=" + ROW,
        ROW.replace(b"\n", b"\r\n"),
        b"\xff\n",
        ROW + b"x" * 4096,
    ],
)
def test_bootstrap_projection_rejects_malformed_ambiguous_or_unbounded_data(
    data,
) -> None:
    with pytest.raises(live_stand.StandError):
        live_stand._parse_bootstrap_diagnostic(data, b"")


def test_bootstrap_projection_rejects_duplicate_across_streams() -> None:
    with pytest.raises(live_stand.StandError):
        live_stand._parse_bootstrap_diagnostic(ROW, ROW)


def _capture_fixture(monkeypatch):
    owner = SimpleNamespace(project_name="ue-live-0123456789abcdef")
    evidence = SimpleNamespace(
        managed_services=("postgres-roles-init",), declared_volume_names=()
    )
    record = {
        "Id": CID,
        "Name": "/owned-init",
        "Image": "sha256:" + "b" * 64,
        "Config": {
            "Image": "pgvector/pgvector:pg17",
            "Labels": {
                "com.docker.compose.project": owner.project_name,
                "com.docker.compose.service": "postgres-roles-init",
                "com.docker.compose.oneoff": "False",
            },
        },
        "Mounts": [],
        "State": {
            "Running": False,
            "Status": "exited",
            "ExitCode": 3,
            "OOMKilled": False,
        },
    }
    calls = []
    context = object()
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(live_stand, "_new_live_docker_read_context", lambda: context)
    monkeypatch.setattr(live_stand, "_assert_live_docker_read_context", lambda *_: None)
    monkeypatch.setattr(
        live_stand, "_assert_core_owner_unchanged", lambda *_, **__: None
    )
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", lambda *_, **__: evidence
    )

    def output(arguments, _error, **kwargs):
        assert kwargs["deadline"] == 110.0
        assert kwargs["docker_context"] is context
        calls.append(tuple(arguments))
        if arguments[0] == "ps":
            assert f"label=com.docker.compose.project={owner.project_name}" in arguments
            assert "label=com.docker.compose.service=postgres-roles-init" in arguments
            return CID + "\n"
        assert arguments[:3] == ["inspect", "--type", "container"]
        assert ".Env" not in arguments[4]
        assert arguments[-1] == CID
        return json.dumps(record)

    def read(command, **kwargs):
        assert command == ["docker", "logs", "--tail", "32", CID]
        assert kwargs["maximum_bytes"] == 4096
        assert kwargs["deadline"] == 110.0
        assert kwargs["command_timeout_seconds"] == 3.0
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, ROW, b"private noise\n")

    monkeypatch.setattr(live_stand, "_docker_output", output)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", read)
    return owner, evidence, record, calls


def test_capture_pins_exact_owned_failed_container_before_and_after_read(
    monkeypatch,
) -> None:
    owner, _, _, calls = _capture_fixture(monkeypatch)
    assert live_stand._capture_owned_bootstrap_diagnostic(owner) == (
        "[postgres-roles-init] phase=reconcile exit=3 sqlstate=42501"
    )
    assert sum(call[0] == "inspect" for call in calls) == 2
    assert sum(call[0] == "ps" for call in calls) == 2


@pytest.mark.parametrize(
    "mutation", ["project", "service", "running", "oom", "exit", "identity"]
)
def test_capture_rejects_changed_or_foreign_container(monkeypatch, mutation) -> None:
    owner, _, record, calls = _capture_fixture(monkeypatch)
    if mutation == "project":
        record["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    elif mutation == "service":
        record["Config"]["Labels"]["com.docker.compose.service"] = "backend"
    elif mutation == "running":
        record["State"]["Running"] = True
    elif mutation == "oom":
        record["State"]["OOMKilled"] = True
    elif mutation == "exit":
        record["State"]["ExitCode"] = 1
    else:
        record["Id"] = "c" * 64
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)
    if mutation != "exit":
        assert not any(call[:2] == ("docker", "logs") for call in calls)


@pytest.mark.parametrize("reason", ["timeout", "overflow", "owner"])
def test_capture_fails_closed_without_emitting_private_error(
    monkeypatch, capsys, reason
) -> None:
    owner, _, _, _ = _capture_fixture(monkeypatch)

    def fail(*_, **__):
        raise live_stand.StandError("private diagnostic data")

    if reason == "owner":
        monkeypatch.setattr(live_stand, "_assert_core_owner_unchanged", fail)
    elif reason == "timeout":
        monkeypatch.setattr(live_stand, "_run_live_bounded_read", fail)
    else:
        monkeypatch.setattr(
            live_stand,
            "_run_live_bounded_read",
            lambda *_, **__: subprocess.CompletedProcess([], 0, ROW + b"x" * 4096, b""),
        )
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)
    assert capsys.readouterr().out == ""


def test_capture_rechecks_identity_after_log_read(monkeypatch) -> None:
    owner, _, record, _ = _capture_fixture(monkeypatch)

    def read(*_, **__):
        record["Image"] = "changed"
        return subprocess.CompletedProcess([], 0, ROW, b"")

    monkeypatch.setattr(live_stand, "_run_live_bounded_read", read)
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)


@pytest.mark.parametrize("diagnostic_failure", [False, True])
def test_start_command_preserves_original_exception_and_suppresses_private_context(
    monkeypatch, capsys, diagnostic_failure
) -> None:
    failure = subprocess.CalledProcessError(1, ["pwsh", "start-docker.ps1"])

    def run(*_, **__):
        raise failure

    def capture(_owner):
        if diagnostic_failure:
            raise RuntimeError("private diagnostic data")
        return ROW.decode("ascii").strip()

    monkeypatch.setattr(live_stand, "_run", run)
    monkeypatch.setattr(live_stand, "_capture_owned_bootstrap_diagnostic", capture)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        live_stand._run_owned_start_command(["pwsh"], object(), {})
    assert caught.value is failure
    assert caught.value.__suppress_context__ is True
    output = capsys.readouterr()
    assert "private" not in output.out + output.err
    assert output.out == ("" if diagnostic_failure else ROW.decode("ascii"))


def test_successful_start_does_not_read_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr(live_stand, "_run", lambda *_, **__: None)

    def forbidden(_owner):
        pytest.fail("successful startup must not inspect failure logs")

    monkeypatch.setattr(live_stand, "_capture_owned_bootstrap_diagnostic", forbidden)
    live_stand._run_owned_start_command(["pwsh"], object(), {})


@pytest.mark.parametrize("selection", ["", CID + "\n" + "b" * 64 + "\n", "invalid\n"])
def test_capture_rejects_ambiguous_container_selection_before_logs(
    monkeypatch, selection
) -> None:
    owner, _, _, calls = _capture_fixture(monkeypatch)
    monkeypatch.setattr(live_stand, "_docker_output", lambda *_, **__: selection)
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)
    assert calls == []


def test_capture_rejects_service_outside_signed_closure(monkeypatch) -> None:
    owner, evidence, _, calls = _capture_fixture(monkeypatch)
    evidence.managed_services = ("backend",)
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)
    assert calls == []


def test_capture_rejects_oneoff_container_before_log_read(monkeypatch) -> None:
    owner, _, record, calls = _capture_fixture(monkeypatch)
    record["Config"]["Labels"]["com.docker.compose.oneoff"] = "True"
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)
    assert not any(call[:2] == ("docker", "logs") for call in calls)


def test_capture_rejects_failed_docker_log_command(monkeypatch) -> None:
    owner, _, _, _ = _capture_fixture(monkeypatch)
    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        lambda *_, **__: subprocess.CompletedProcess([], 1, ROW, b"private failure\n"),
    )
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)


def test_capture_rejects_post_read_owner_change(monkeypatch) -> None:
    owner, _, _, _ = _capture_fixture(monkeypatch)
    checks = 0

    def verify(*_, **__):
        nonlocal checks
        checks += 1
        if checks == 2:
            raise live_stand.StandError("owner changed")

    monkeypatch.setattr(live_stand, "_assert_core_owner_unchanged", verify)
    with pytest.raises(live_stand.StandError):
        live_stand._capture_owned_bootstrap_diagnostic(owner)
    assert checks == 2


def test_start_command_print_failure_does_not_replace_startup_failure(
    monkeypatch,
) -> None:
    failure = subprocess.CalledProcessError(3, ["pwsh"])

    def run(*_, **__):
        raise failure

    def fail_print(*_, **__):
        raise BrokenPipeError("private diagnostic failure")

    monkeypatch.setattr(live_stand, "_run", run)
    monkeypatch.setattr(
        live_stand,
        "_capture_owned_bootstrap_diagnostic",
        lambda _: ROW.decode("ascii").strip(),
    )
    monkeypatch.setattr("builtins.print", fail_print)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        live_stand._run_owned_start_command(["pwsh"], object(), {})
    assert caught.value is failure
    assert caught.value.__suppress_context__ is True
