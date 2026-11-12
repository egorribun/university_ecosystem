"""AUD-164: the coordinator that runs the fixed client-IP probe on an owned stand.

Docker is replaced by a fake over synthetic inspect records; a hosted run on a real
stand is separate evidence.
"""

from __future__ import annotations

import copy
import json
import runpy
import sys
from typing import Any

import pytest

from scripts import live_stand, owned_client_ip_cli
from scripts.owned_client_ip_cli import ClientIpNotAccepted
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)
from tests.test_owned_client_ip_acceptance_v2 import _frame
from tests.test_owned_client_ip_runtime_topology import _inspect_fixture


def _process_result(stdout: bytes) -> PrivateProcessResult:
    return PrivateProcessResult(
        ProcessOutcome.EXITED, 0, stdout, b"", LocalCleanup.CONFIRMED
    )


class FakeDocker:
    """Answer the coordinator's calls from one synthetic stand snapshot."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.probe_id: str = snapshot["expected_probe_id"]
        self.calls: list[tuple[str, ...]] = []
        self.programs: list[bytes] = []
        frame = _frame()
        frame["source_sha"] = snapshot["owner"].source_sha
        frame["run_id"] = snapshot["run_id"]
        self.result = _process_result(json.dumps(frame).encode() + b"\n")
        self.removed = False
        self.survive_removal = False
        self.fail_removal = False
        self.drift_after_probe = False

    def read(self, arguments: Any) -> str:
        arguments = tuple(arguments)
        self.calls.append(arguments)
        if arguments[0] == "create":
            return self.probe_id + "\n"
        if arguments[0] == "rm":
            if self.fail_removal:
                raise live_stand.StandError("rm failed")
            self.removed = True
            return ""
        if arguments[0] == "ps":
            return self.probe_id if self.survive_removal else ""
        return ""

    def inspect(self, arguments: Any) -> dict[str, Any]:
        kind, _verb, identity = tuple(arguments)
        if kind == "network":
            return copy.deepcopy(self.snapshot["networks"][identity])
        if kind == "image":
            return copy.deepcopy(self.snapshot["image"])
        if identity == self.probe_id:
            return copy.deepcopy(self.snapshot["probe"])
        record = next(
            item
            for item in self.snapshot["containers"].values()
            if item["Id"] == identity
        )
        record = copy.deepcopy(record)
        if self.programs and self.drift_after_probe:
            record["RestartCount"] = 1
        return record

    def attach(self, container_id: str, program: bytes) -> PrivateProcessResult:
        assert container_id == self.probe_id
        self.programs.append(program)
        return self.result


@pytest.fixture
def stand(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    snapshot, _marker = _inspect_fixture()
    for service, record in snapshot["containers"].items():
        record["Config"].setdefault("Labels", {})
        record["Config"]["Labels"]["com.docker.compose.service"] = service
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: snapshot["owner"])
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda _owner: None)
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda _path, _owner: snapshot["evidence"],
    )
    monkeypatch.setattr(
        live_stand,
        "_project_container_ids",
        lambda _project: tuple(
            record["Id"] for record in snapshot["containers"].values()
        ),
    )
    monkeypatch.setattr(
        owned_client_ip_cli.secrets, "token_hex", lambda _n: snapshot["run_id"]
    )
    return FakeDocker(snapshot)


def test_a_passing_run_reports_verdicts_and_removes_the_probe(
    stand: FakeDocker,
) -> None:
    result = owned_client_ip_cli.run_locked(stand)

    assert result.verdict.backend is True
    assert result.verdict.ws_hub is True
    assert result.verdict.gateway is True
    assert result.verdict.deployment == "not_assessed"
    assert stand.removed is True
    assert [call[0] for call in stand.calls] == [
        "create",
        "network",
        "start",
        "rm",
        "ps",
    ]
    assert stand.calls[-1][-1] == f"id={stand.probe_id}"


def test_probe_is_created_without_mounts_from_the_backend_image(
    stand: FakeDocker,
) -> None:
    owned_client_ip_cli.run_locked(stand)

    create = stand.calls[0]
    backend_image = stand.snapshot["containers"]["backend"]["Image"]
    assert create[create.index("--entrypoint") + 1 :] == ("python", backend_image, "-")
    for flag, value in (
        ("--user", "10001:10001"),
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges:true"),
        ("--pids-limit", "64"),
        ("--memory", "256m"),
        ("--memory-swap", "256m"),
        ("--cpus", "1"),
        ("--restart", "no"),
    ):
        assert create[create.index(flag) + 1] == value
    assert "--read-only" in create
    assert "--no-healthcheck" in create
    assert not {"--volume", "-v", "--mount", "--publish", "-p", "--privileged"} & set(
        create
    )


def test_the_program_is_the_probe_source_with_the_derived_input(
    stand: FakeDocker,
) -> None:
    owned_client_ip_cli.run_locked(stand)

    program = stand.programs[0].decode()
    assert program.startswith(owned_client_ip_cli._PROBE_SOURCE.read_text("utf-8"))
    compile(program, "<probe>", "exec")
    literal = program.split("\n_OWNED_INPUT = ", 1)[1].split("\n", 1)[0]
    derived = json.loads(json.loads(literal))
    assert derived["run_id"] == stand.snapshot["run_id"]
    assert derived["source_sha"] == stand.snapshot["owner"].source_sha


def test_summary_states_statuses_without_addresses_or_identities(
    stand: FakeDocker,
) -> None:
    lines = owned_client_ip_cli.summary_lines(owned_client_ip_cli.run_locked(stand))

    text = "\n".join(lines)
    assert (
        "owned client-IP case=login allowed=60 allowed_status=422 blocked=429 "
        "other_client=422 spoofed=429,429,429 direct_untrusted=429 "
        "backend_direct_untrusted=429 elapsed_ms=1"
    ) in lines
    assert "backend_direct_untrusted=n/a" in text
    assert (
        "owned client-IP verdict backend=true ws_hub=true gateway=true "
        "deployment=not_assessed"
    ) in lines
    assert "172." not in text
    assert stand.snapshot["run_id"] not in text
    assert stand.probe_id not in text


def _expect_phase(stand: FakeDocker, phase: str) -> None:
    with pytest.raises(ClientIpNotAccepted) as caught:
        owned_client_ip_cli.run_locked(stand)
    assert caught.value.phase == phase


def test_a_missing_network_binding_stops_before_any_container_exists(
    stand: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = stand.snapshot["evidence"]
    kept = tuple(b for b in evidence.network_bindings if b[0] != "frontend_net")
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda _path, _owner: type(evidence)(
            **{**evidence.__dict__, "network_bindings": kept}
        ),
    )

    _expect_phase(stand, "networks")
    assert stand.calls == []


def test_a_missing_service_stops_before_any_container_exists(
    stand: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = tuple(
        record["Id"]
        for name, record in stand.snapshot["containers"].items()
        if name != "gateway"
    )
    monkeypatch.setattr(live_stand, "_project_container_ids", lambda _project: ids)

    _expect_phase(stand, "containers")
    assert stand.calls == []


def test_a_duplicated_service_stops_before_any_container_exists(
    stand: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = tuple(r["Id"] for r in stand.snapshot["containers"].values())
    monkeypatch.setattr(
        live_stand, "_project_container_ids", lambda _project: (*ids, ids[0])
    )

    _expect_phase(stand, "containers")
    assert stand.calls == []


def test_an_unrelated_project_container_is_ignored(
    stand: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = {"Id": "f" * 64, "Config": {"Labels": {"com.docker.compose.service": "x"}}}
    stand.snapshot["containers_extra"] = other
    ids = tuple(r["Id"] for r in stand.snapshot["containers"].values())
    monkeypatch.setattr(
        live_stand, "_project_container_ids", lambda _project: (*ids, other["Id"])
    )
    original = stand.inspect
    monkeypatch.setattr(
        stand,
        "inspect",
        lambda arguments: other
        if tuple(arguments)[-1] == other["Id"]
        else original(arguments),
    )

    assert owned_client_ip_cli.run_locked(stand).verdict.backend is True


def test_a_backend_without_an_image_stops_before_any_container_exists(
    stand: FakeDocker,
) -> None:
    stand.snapshot["containers"]["backend"]["Image"] = None

    _expect_phase(stand, "containers")
    assert stand.calls == []


def test_an_inconsistent_probe_record_is_refused_and_removed(
    stand: FakeDocker,
) -> None:
    stand.snapshot["probe"]["HostConfig"]["Privileged"] = True

    with pytest.raises(ClientIpNotAccepted) as caught:
        owned_client_ip_cli.run_locked(stand)

    assert caught.value.phase == "topology"
    assert caught.value.step == "probe"
    assert stand.programs == []
    assert stand.removed is True


def test_an_unreadable_frame_is_refused_and_the_probe_removed(
    stand: FakeDocker,
) -> None:
    stand.result = _process_result(b"not a frame\n")

    _expect_phase(stand, "probe")
    assert stand.removed is True


def test_a_probe_that_outlives_its_budget_is_refused(stand: FakeDocker) -> None:
    ticks = iter((0.0, 121.0))

    with pytest.raises(ClientIpNotAccepted) as caught:
        owned_client_ip_cli.run_locked(stand, clock=lambda: next(ticks))

    assert caught.value.phase == "probe"
    assert stand.removed is True


def test_a_stack_that_changed_during_the_probe_is_refused(stand: FakeDocker) -> None:
    stand.drift_after_probe = True

    _expect_phase(stand, "topology_changed")
    assert stand.removed is True


def test_health_log_changes_are_not_topology_drift() -> None:
    record = {"Id": "a", "State": {"Running": True, "Status": "running"}}
    moved = {
        **record,
        "State": {**record["State"], "Health": {"Log": ["newer"]}},
    }

    assert owned_client_ip_cli._stable_container(
        record
    ) == owned_client_ip_cli._stable_container(moved)


def test_the_exited_probe_is_not_part_of_the_network_witness() -> None:
    record = {"Name": "n", "Containers": {"probe": {}, "kept": {"x": 1}}}

    assert owned_client_ip_cli._stable_network(record, "probe") == {
        "Name": "n",
        "Containers": {"kept": {"x": 1}},
    }


def test_a_surviving_probe_fails_an_otherwise_passing_run(stand: FakeDocker) -> None:
    stand.survive_removal = True

    _expect_phase(stand, "cleanup")


def test_a_failed_removal_fails_an_otherwise_passing_run(stand: FakeDocker) -> None:
    stand.fail_removal = True

    _expect_phase(stand, "cleanup")


def test_a_failed_removal_does_not_hide_the_original_phase(stand: FakeDocker) -> None:
    stand.fail_removal = True
    stand.result = _process_result(b"not a frame\n")

    _expect_phase(stand, "probe")


def _main(monkeypatch: pytest.MonkeyPatch, outcome: object) -> int:
    class _Lock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_exc: object) -> None:
            return None

    def run(_docker: object) -> object:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", _Lock)
    monkeypatch.setattr(owned_client_ip_cli, "run_locked", run)
    return owned_client_ip_cli.main(["--state-dir", "owned-state"])


def test_main_passes_only_when_backend_and_hub_both_pass(
    stand: FakeDocker,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = owned_client_ip_cli.run_locked(stand)

    assert _main(monkeypatch, result) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "owned client-IP outcome=passed"

    failed = owned_client_ip_cli.ClientIpResult(
        result.observed,
        type(result.verdict)(backend=True, ws_hub=False),
    )
    assert _main(monkeypatch, failed) == 1
    assert capsys.readouterr().out.splitlines()[-1] == (
        "owned client-IP outcome=failed phase=verdict"
    )

    gateway_failed = owned_client_ip_cli.ClientIpResult(
        result.observed,
        type(result.verdict)(backend=True, ws_hub=True, gateway=False),
    )
    assert _main(monkeypatch, gateway_failed) == 1
    assert capsys.readouterr().out.splitlines()[-1] == (
        "owned client-IP outcome=failed phase=verdict"
    )


def test_main_names_only_the_failed_phase(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, ClientIpNotAccepted("probe")) == 1
    assert capsys.readouterr().out == "owned client-IP outcome=failed phase=probe\n"


def test_main_names_the_fixed_topology_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, ClientIpNotAccepted("topology", "trust")) == 1
    assert capsys.readouterr().out == (
        "owned client-IP outcome=failed phase=topology step=trust\n"
    )


def test_main_does_not_print_stand_error_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, live_stand.StandError("private detail")) == 1
    assert capsys.readouterr().out == "owned client-IP outcome=failed phase=stand\n"


def test_main_runs_under_in_place_state_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        live_stand,
        "_configure_state_mode",
        lambda args: seen.append((args.in_place, args.state_dir, args.command)),
    )
    monkeypatch.setattr(
        live_stand,
        "stand_lifecycle_lock",
        lambda: (_ for _ in ()).throw(live_stand.StandError("stop")),
    )

    assert owned_client_ip_cli.main(["--state-dir", "owned-state"]) == 1
    assert seen == [(True, "owned-state", "client-ip")]


def test_module_entrypoint_exits_with_the_acceptance_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_args: object) -> None:
        raise live_stand.StandError("stop")

    monkeypatch.setattr(live_stand, "_configure_state_mode", refuse)
    monkeypatch.setattr(
        sys, "argv", ["owned_client_ip_cli", "--state-dir", "owned-state"]
    )
    monkeypatch.delitem(sys.modules, "scripts.owned_client_ip_cli", raising=False)

    with pytest.raises(SystemExit) as caught:
        runpy.run_module("scripts.owned_client_ip_cli", run_name="__main__")

    assert caught.value.code == 1


def test_live_docker_delegates_reads_to_the_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_stand, "_docker_output", lambda arguments, _message: "|".join(arguments)
    )
    monkeypatch.setattr(
        live_stand,
        "_docker_inspect_object",
        lambda arguments, _message: {"arguments": list(arguments)},
    )
    docker = owned_client_ip_cli._LiveDocker()

    assert docker.read(["ps", "--all"]) == "ps|--all"
    assert docker.inspect(["network", "inspect", "n"]) == {
        "arguments": ["network", "inspect", "n"]
    }


def test_live_docker_attach_sends_the_program_without_inherited_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[PrivateProcessRequest] = []

    def run(request: PrivateProcessRequest, *, deadline: object) -> str:
        assert deadline is not None
        captured.append(request)
        return "result"

    monkeypatch.setattr(owned_client_ip_cli, "run_private_process", run)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("UE_PRIVATE_VALUE", "private")

    assert owned_client_ip_cli._LiveDocker().attach("abc", b"program") == "result"
    request = captured[0]
    assert request.argv == ("docker", "attach", "--sig-proxy=false", "abc")
    assert request.stdin == b"program"
    assert "UE_PRIVATE_VALUE" not in request.env
    assert request.env["PATH"] == "/usr/bin"
    assert request.input_limit >= len(owned_client_ip_cli._PROBE_SOURCE.read_bytes())
