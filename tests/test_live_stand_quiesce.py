from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from scripts import live_stand

DATA_STORES = frozenset({"postgres", "minio"})
SOURCE_SHA = "a" * 40
OWNER_FINGERPRINT = "b" * 64


@pytest.fixture
def quiesce_stand(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    state_root = tmp_path / "owned-run"
    state_root.mkdir()
    (state_root / live_stand.IN_PLACE_OVERLAY).write_text(
        "services: {}\n", encoding="utf-8"
    )
    (state_root / ".secrets").mkdir()

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", SOURCE_SHA)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)
    monkeypatch.setattr(
        live_stand,
        "_ensure_private_state_directory",
        lambda path, **_kwargs: Path(path).mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(
        live_stand, "_assert_private_state_directory", lambda _path: None
    )

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return SOURCE_SHA
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        if args and args[0] == "ls-files":
            return ""
        raise AssertionError(f"unexpected git query: {args!r}")

    monkeypatch.setattr(live_stand, "_git", fake_git)
    ports = {
        name: 20000 + index
        for index, (name, _service, _container_port) in enumerate(
            live_stand.LIVE_PORT_SPECS
        )
    }
    owner = live_stand.create_stand_owner(
        state_root,
        published_ports=ports,
        stack=live_stand.LIVE_STACK_CORE,
    )
    owner = live_stand._write_stand_owner_update(
        state_root,
        replace(
            owner,
            compose_resource_fingerprint=OWNER_FINGERPRINT,
            service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
            selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
        ),
    )
    evidence = live_stand.ComposeResourceEvidence(
        fingerprint=OWNER_FINGERPRINT,
        managed_volumes=(),
        declared_volume_names=(),
        managed_networks=(),
        managed_services=owner.selected_services,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=owner.service_roots,
        selected_services=owner.selected_services,
    )
    evidence_calls: list[tuple[Path, live_stand.StandOwner]] = []

    def verify_resources(
        worktree: Path,
        candidate: live_stand.StandOwner,
        **_kwargs: Any,
    ) -> live_stand.ComposeResourceEvidence:
        evidence_calls.append((worktree, candidate))
        if candidate != owner:
            raise live_stand.StandError("live stand ownership metadata changed")
        return evidence

    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", verify_resources
    )

    state_by_service = {
        service: {
            "running": True,
            "status": "running",
            "health": "healthy" if service in DATA_STORES else None,
        }
        for service in owner.selected_services
    }
    ids_by_service = {
        service: f"{index + 1:064x}"
        for index, service in enumerate(owner.selected_services)
    }
    records: dict[str, dict[str, Any]] = {}

    def make_record(service: str, container_id: str) -> dict[str, Any]:
        service_state = state_by_service[service]
        return {
            "Id": container_id,
            "Name": f"/{owner.project_name}-{service}-1",
            "Image": "c" * 64,
            "Config": {
                "Image": f"example/{service}:test",
                "Labels": {
                    "com.docker.compose.project": owner.project_name,
                    "com.docker.compose.service": service,
                },
            },
            "Mounts": [],
            "State": {
                "Running": service_state["running"],
                "Status": service_state["status"],
                "Health": (
                    {"Status": service_state["health"]}
                    if service in DATA_STORES
                    else None
                ),
            },
        }

    for service, container_id in ids_by_service.items():
        records[container_id] = make_record(service, container_id)

    inventory = {
        "worktree": state_root,
        "owner": owner,
        "evidence": evidence,
        "evidence_calls": evidence_calls,
        "state_by_service": state_by_service,
        "ids_by_service": ids_by_service,
        "records": records,
        "make_record": make_record,
    }

    monkeypatch.setattr(
        live_stand,
        "_project_container_ids",
        lambda _project_name: tuple(inventory["records"]),
    )
    monkeypatch.setattr(
        live_stand,
        "_docker_inspect_object",
        lambda arguments, _message: inventory["records"][arguments[-1]],
    )
    return inventory


def test_quiesce_stops_only_owned_core_services_and_preserves_schema_11_owner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiesce_stand: dict[str, Any],
) -> None:
    owner = quiesce_stand["owner"]
    marker = quiesce_stand["worktree"] / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    already_exited = next(
        service for service in owner.selected_services if service not in DATA_STORES
    )
    quiesce_stand["state_by_service"][already_exited].update(
        running=False, status="exited"
    )
    container_id = quiesce_stand["ids_by_service"][already_exited]
    quiesce_stand["records"][container_id] = quiesce_stand["make_record"](
        already_exited, container_id
    )
    stop_services = tuple(
        service for service in owner.selected_services if service not in DATA_STORES
    )
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def stop_owned(command: list[str], **kwargs: Any) -> None:
        calls.append((command, kwargs))
        assert command == live_stand.compose_command(
            "stop", *stop_services, project_name=owner.project_name
        )
        assert kwargs["cwd"] == quiesce_stand["worktree"]
        for service in stop_services:
            state = quiesce_stand["state_by_service"][service]
            state["running"] = False
            state["status"] = "exited"
            container_id = quiesce_stand["ids_by_service"][service]
            quiesce_stand["records"][container_id] = quiesce_stand["make_record"](
                service, container_id
            )

    monkeypatch.setattr(live_stand, "_run", stop_owned)

    live_stand.quiesce()

    assert len(calls) == 1
    assert len(quiesce_stand["evidence_calls"]) >= 2
    assert marker.read_bytes() == marker_before
    for service in owner.selected_services:
        state = quiesce_stand["state_by_service"][service]
        if service in DATA_STORES:
            assert state["running"] is True
            assert state["health"] == "healthy"
        else:
            assert state["running"] is False
            assert state["status"] == "exited"
    output = capsys.readouterr().out
    assert "quiesced" in output.lower()
    assert "external writers are not verified" in output.lower()
    assert owner.schema_version == live_stand.IN_PLACE_OWNER_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("service", "running", "health"),
    [("postgres", False, "healthy"), ("minio", True, "unhealthy")],
)
def test_quiesce_requires_both_data_stores_healthy_before_stopping(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiesce_stand: dict[str, Any],
    service: str,
    running: bool,
    health: str,
) -> None:
    quiesce_stand["state_by_service"][service]["running"] = running
    quiesce_stand["state_by_service"][service]["health"] = health
    container_id = quiesce_stand["ids_by_service"][service]
    quiesce_stand["records"][container_id] = quiesce_stand["make_record"](
        service, container_id
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_kwargs: calls.append(command)
    )
    marker = quiesce_stand["worktree"] / live_stand.STAND_FILE
    marker_before = marker.read_bytes()

    with pytest.raises(
        live_stand.StandError, match="data stores must be running and healthy"
    ):
        live_stand.quiesce()

    assert calls == []
    assert marker.read_bytes() == marker_before
    assert "quiesced" not in capsys.readouterr().out.lower()


@pytest.mark.parametrize("inventory_change", ["missing", "duplicate", "foreign"])
def test_quiesce_fails_closed_on_incomplete_or_foreign_container_inventory(
    monkeypatch: pytest.MonkeyPatch,
    quiesce_stand: dict[str, Any],
    inventory_change: str,
) -> None:
    ids = list(quiesce_stand["records"])
    if inventory_change == "missing":
        quiesce_stand["records"].pop(ids[-1])
    elif inventory_change == "duplicate":
        service = quiesce_stand["owner"].selected_services[0]
        duplicate_id = "e" * 64
        quiesce_stand["records"][duplicate_id] = quiesce_stand["make_record"](
            service, duplicate_id
        )
    else:
        service = quiesce_stand["owner"].selected_services[0]
        container_id = quiesce_stand["ids_by_service"][service]
        quiesce_stand["records"][container_id]["Config"]["Labels"][
            "com.docker.compose.service"
        ] = "foreign-service"

    calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_kwargs: calls.append(command)
    )

    with pytest.raises(live_stand.StandError):
        live_stand.quiesce()

    assert calls == []


def test_quiesce_requires_both_datastore_services_in_signed_projection(
    monkeypatch: pytest.MonkeyPatch,
    quiesce_stand: dict[str, Any],
) -> None:
    owner = quiesce_stand["owner"]
    evidence = quiesce_stand["evidence"]
    selected = tuple(
        service for service in owner.selected_services if service != "minio"
    )
    incomplete_owner = replace(owner, selected_services=selected)
    incomplete_evidence = replace(
        evidence,
        selected_services=selected,
        managed_services=selected,
    )
    inventory_calls: list[str] = []
    monkeypatch.setattr(
        live_stand,
        "_project_container_ids",
        lambda project: inventory_calls.append(project) or (),
    )

    with pytest.raises(live_stand.StandError, match="projection is incomplete"):
        live_stand._core_quiesce_container_inventory(
            incomplete_owner, incomplete_evidence
        )

    assert inventory_calls == []


def test_quiesce_rejects_source_drift_before_inspecting_or_stopping(
    monkeypatch: pytest.MonkeyPatch,
    quiesce_stand: dict[str, Any],
) -> None:
    original_git = live_stand._git
    calls: list[list[str]] = []

    def modified_source(*args: str) -> str:
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return " M scripts/live_stand.py"
        return original_git(*args)

    monkeypatch.setattr(live_stand, "_git", modified_source)
    monkeypatch.setattr(
        live_stand,
        "_project_container_ids",
        lambda _project: pytest.fail("source drift must fail before Docker inventory"),
    )
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_kwargs: calls.append(command)
    )

    with pytest.raises(live_stand.StandError, match="source checkout has modified"):
        live_stand.quiesce()

    assert calls == []


def test_quiesce_rejects_container_identity_change_after_stop_without_success_claim(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiesce_stand: dict[str, Any],
) -> None:
    owner = quiesce_stand["owner"]
    calls: list[list[str]] = []

    def replace_container(command: list[str], **_kwargs: Any) -> None:
        calls.append(command)
        for service in owner.selected_services:
            if service in DATA_STORES:
                continue
            state = quiesce_stand["state_by_service"][service]
            state["running"] = False
            state["status"] = "exited"
        service = owner.selected_services[0]
        old_id = quiesce_stand["ids_by_service"][service]
        new_id = "e" * 64
        quiesce_stand["records"].pop(old_id)
        quiesce_stand["ids_by_service"][service] = new_id
        quiesce_stand["records"][new_id] = quiesce_stand["make_record"](service, new_id)

    monkeypatch.setattr(live_stand, "_run", replace_container)

    with pytest.raises(live_stand.StandError, match="container inventory changed"):
        live_stand.quiesce()

    assert len(calls) == 1
    assert "quiesced" not in capsys.readouterr().out.lower()


def test_quiesce_control_failure_does_not_claim_success_or_change_owner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiesce_stand: dict[str, Any],
) -> None:
    marker = quiesce_stand["worktree"] / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, command)
        ),
    )

    with pytest.raises(
        live_stand.StandError, match="failed to stop owned Core services"
    ):
        live_stand.quiesce()

    assert marker.read_bytes() == marker_before
    assert "quiesced" not in capsys.readouterr().out.lower()


@pytest.mark.parametrize(
    ("changed_service", "running", "status", "health"),
    [
        ("postgres", False, "exited", "healthy"),
        ("minio", True, "running", "unhealthy"),
        ("backend", True, "running", None),
    ],
)
def test_quiesce_fails_without_success_if_post_stop_state_is_not_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiesce_stand: dict[str, Any],
    changed_service: str,
    running: bool,
    status: str,
    health: str | None,
) -> None:
    owner = quiesce_stand["owner"]
    stop_services = tuple(
        service for service in owner.selected_services if service not in DATA_STORES
    )

    def leave_one_service_unsafe(command: list[str], **_kwargs: Any) -> None:
        assert command == live_stand.compose_command(
            "stop", *stop_services, project_name=owner.project_name
        )
        for service in stop_services:
            state = quiesce_stand["state_by_service"][service]
            state.update(running=False, status="exited")
        state = quiesce_stand["state_by_service"][changed_service]
        state.update(running=running, status=status, health=health)
        container_id = quiesce_stand["ids_by_service"][changed_service]
        quiesce_stand["records"][container_id] = quiesce_stand["make_record"](
            changed_service, container_id
        )

    monkeypatch.setattr(live_stand, "_run", leave_one_service_unsafe)

    with pytest.raises(live_stand.StandError):
        live_stand.quiesce()

    assert "quiesced" not in capsys.readouterr().out.lower()


def test_quiesce_rejects_a_full_stack_before_container_or_compose_control(
    monkeypatch: pytest.MonkeyPatch,
    quiesce_stand: dict[str, Any],
) -> None:
    owner = quiesce_stand["owner"]
    full_owner = replace(
        owner,
        stack=live_stand.LIVE_STACK_FULL,
        service_roots=(),
        selected_services=(),
    )
    full_owner = live_stand._write_stand_owner_update(
        quiesce_stand["worktree"], full_owner
    )
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: full_owner)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_project_container_ids",
        lambda _project: pytest.fail(
            "non-Core owner must fail before Docker inventory"
        ),
    )
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_kwargs: calls.append(command)
    )

    with pytest.raises(live_stand.StandError, match="only for Core stands"):
        live_stand.quiesce()

    assert calls == []


def test_quiesce_requires_in_place_mode_before_lifecycle_or_owner_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    for function_name in (
        "stand_lifecycle_lock",
        "_require_worktree",
        "load_stand_owner",
        "_project_container_ids",
        "_run",
    ):
        monkeypatch.setattr(
            live_stand,
            function_name,
            lambda *args, _name=function_name, **kwargs: pytest.fail(
                f"{_name} must not run for a non-in-place quiesce request"
            ),
        )

    with pytest.raises(
        live_stand.StandError, match="quiesce requires an in-place Core stand"
    ):
        live_stand.quiesce()


def test_quiesce_revalidates_compose_projection_before_stop(
    monkeypatch: pytest.MonkeyPatch,
    quiesce_stand: dict[str, Any],
) -> None:
    original_verifier = live_stand._verify_stand_owner_compose_resources
    calls = 0

    def drift_on_final_check(
        worktree: Path, owner: live_stand.StandOwner, **kwargs: Any
    ) -> live_stand.ComposeResourceEvidence:
        nonlocal calls
        calls += 1
        evidence = original_verifier(worktree, owner, **kwargs)
        if calls >= 2:
            return replace(evidence, fingerprint="f" * 64)
        return evidence

    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", drift_on_final_check
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_kwargs: commands.append(command)
    )

    with pytest.raises(live_stand.StandError, match="Compose resources changed"):
        live_stand.quiesce()

    assert calls >= 2
    assert commands == []


@pytest.mark.parametrize("drift", ["container identity", "store health"])
def test_quiesce_rechecks_inventory_and_health_immediately_before_stop(
    monkeypatch: pytest.MonkeyPatch,
    quiesce_stand: dict[str, Any],
    drift: str,
) -> None:
    owner = quiesce_stand["owner"]
    original_verifier = live_stand._verify_stand_owner_compose_resources
    verifier_calls = 0

    def drift_during_projection_check(
        worktree: Path, candidate: live_stand.StandOwner, **kwargs: Any
    ) -> live_stand.ComposeResourceEvidence:
        nonlocal verifier_calls
        verifier_calls += 1
        evidence = original_verifier(worktree, candidate, **kwargs)
        if verifier_calls == 2:
            if drift == "container identity":
                service = next(
                    item for item in owner.selected_services if item not in DATA_STORES
                )
                old_id = quiesce_stand["ids_by_service"][service]
                new_id = "e" * 64
                quiesce_stand["records"].pop(old_id)
                quiesce_stand["ids_by_service"][service] = new_id
                quiesce_stand["records"][new_id] = quiesce_stand["make_record"](
                    service, new_id
                )
            else:
                service = "minio"
                quiesce_stand["state_by_service"][service]["health"] = "unhealthy"
                container_id = quiesce_stand["ids_by_service"][service]
                quiesce_stand["records"][container_id] = quiesce_stand["make_record"](
                    service, container_id
                )
        return evidence

    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        drift_during_projection_check,
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_kwargs: commands.append(command)
    )

    expected_error = (
        "container inventory changed"
        if drift == "container identity"
        else "data stores must be running and healthy"
    )
    with pytest.raises(live_stand.StandError, match=expected_error):
        live_stand.quiesce()

    assert verifier_calls == 2
    assert commands == []


def test_quiesce_command_is_registered_for_owned_state_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    monkeypatch.setattr(live_stand, "quiesce", lambda: calls.append(True))

    assert (
        live_stand.main(["quiesce", "--in-place", "--state-dir", "C:/private/run"]) == 0
    )
    assert calls == [True]
