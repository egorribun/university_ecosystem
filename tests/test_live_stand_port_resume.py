"""Offline contracts for restarting an owned, populated in-place Core stand."""

from __future__ import annotations

import json
import queue
import sqlite3
import subprocess
import sys
import threading
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from scripts import live_stand
from tests.test_live_stand_quiesce import SOURCE_SHA, quiesce_stand

__all__ = ["quiesce_stand"]

_VERIFY_RESOURCES = live_stand._verify_stand_owner_compose_resources
_PORT_IS_FREE = live_stand.port_is_free


@pytest.fixture
def restart_stand(
    monkeypatch: pytest.MonkeyPatch, quiesce_stand: dict[str, Any]
) -> dict[str, Any]:
    """Keep signed markers and lifecycle logic real; simulate Docker and storage."""
    stand = quiesce_stand
    owner = stand["owner"]
    previous_ports = dict(owner.published_ports)
    fresh_ports = {
        name: 31000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    stand["previous_ports"] = previous_ports
    stand["fresh_ports"] = fresh_ports
    stand["busy"] = set()
    stand["events"] = []
    stand["after_stop"] = lambda: None
    stand["after_prepare"] = lambda: None
    stand["allocations"] = []
    base_url = live_stand._stand_base_url(previous_ports)
    data_root = stand["worktree"] / "simulated-data"
    data_root.mkdir()
    stand["database"] = data_root / "demo.sqlite"
    stand["objects"] = data_root / "objects"
    stand["objects"].mkdir()
    with sqlite3.connect(stand["database"]) as database:
        database.execute("CREATE TABLE content (kind TEXT, url TEXT)")
        database.executemany(
            "INSERT INTO content VALUES (?, ?)",
            [
                ("attachment", f"{base_url}/storage/attachment"),
                ("story", f"{base_url}/storage/story"),
            ],
        )
    (stand["objects"] / "attachment").write_bytes(b"existing attachment")
    (stand["objects"] / "story").write_bytes(b"existing story")

    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: SOURCE_SHA)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", _VERIFY_RESOURCES
    )
    monkeypatch.setattr(
        live_stand,
        "_owner_compose_resource_evidence",
        lambda *_args, **_kwargs: stand["evidence"],
    )
    monkeypatch.setattr(
        live_stand, "_assert_compose_volume_ownership", lambda *_args, **_kwargs: ()
    )

    def choose_ports(**_kwargs: Any) -> dict[str, int]:
        stand["allocations"].append(True)
        return fresh_ports.copy()

    def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
        assert host == live_stand.PORT_BIND_HOST
        if port in stand["busy"]:
            return False
        return not any(
            port == previous_ports[name]
            and stand["state_by_service"][service]["running"]
            for name, service, _target in live_stand.LIVE_PORT_SPECS
            if service in stand["state_by_service"]
        )

    def control_environment(_project: str, ports: dict[str, int]) -> dict[str, str]:
        return {"LIVE_BASE_URL": live_stand._stand_base_url(ports)}

    def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        assert cwd == stand["worktree"]
        if "stop" in command:
            current = live_stand.load_stand_owner(cwd)
            assert current.compose_resource_fingerprint is not None
            stand["events"].append(("stop", current, env["LIVE_BASE_URL"]))
            for service in command[command.index("stop") + 1 :]:
                state = stand["state_by_service"][service]
                state.update(running=False, status="exited")
                container_id = stand["ids_by_service"][service]
                stand["records"][container_id] = stand["make_record"](
                    service, container_id
                )
            stand["after_stop"]()
        elif "-PrepareOnly" in command:
            stand["events"].append(("prepare", live_stand.load_stand_owner(cwd)))
            stand["after_prepare"]()
        elif "-Build" in command:
            current = live_stand.load_stand_owner(cwd)
            assert current.compose_resource_fingerprint is not None
            stand["events"].append(("build", current, env["LIVE_BASE_URL"]))
        else:
            pytest.fail("unexpected process in simulated lifecycle")

    monkeypatch.setattr(live_stand, "choose_published_ports", choose_ports)
    monkeypatch.setattr(live_stand, "port_is_free", port_is_free)
    monkeypatch.setattr(live_stand, "compose_control_environment", control_environment)
    monkeypatch.setattr(live_stand, "load_or_create_vapid", lambda _root: {})
    monkeypatch.setattr(
        live_stand,
        "stand_environment",
        lambda _keys, project, ports: control_environment(project, ports),
    )
    monkeypatch.setattr(
        live_stand, "_write_in_place_compose_override", lambda _root: None
    )
    monkeypatch.setattr(live_stand.shutil, "which", lambda _name: "pwsh")
    monkeypatch.setattr(live_stand, "_run", run)
    monkeypatch.setattr(
        live_stand, "_configure_live_trusted_proxy_peers", lambda *_args: 0
    )
    return stand


@pytest.mark.parametrize("pause", ["stop", "quiesce"])
def test_populated_core_resume_preserves_signed_urls(
    restart_stand: dict[str, Any], pause: str
) -> None:
    stand = restart_stand
    marker = stand["worktree"] / live_stand.STAND_FILE
    before_marker = marker.read_bytes()
    with sqlite3.connect(stand["database"]) as database:
        before_database = database.execute("SELECT kind, url FROM content").fetchall()
    before_objects = {
        path.name: path.read_bytes() for path in stand["objects"].iterdir()
    }

    getattr(live_stand, pause)()
    assert marker.read_bytes() == before_marker
    if pause == "quiesce":
        assert all(
            stand["state_by_service"][name]["running"] for name in ("postgres", "minio")
        )

    live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    updated = live_stand.load_stand_owner(stand["worktree"])
    assert dict(updated.published_ports) == stand["previous_ports"]
    with sqlite3.connect(stand["database"]) as database:
        restored_database = database.execute("SELECT kind, url FROM content").fetchall()
    assert restored_database == before_database
    assert {path.name: path.read_bytes() for path in stand["objects"].iterdir()} == (
        before_objects
    )
    assert all(
        url.startswith(live_stand._stand_base_url(dict(updated.published_ports)))
        for _kind, url in restored_database
    )
    assert not stand["allocations"]


def test_current_signed_resume_evidence_preserves_map_without_incomplete_stop(
    restart_stand: dict[str, Any],
) -> None:
    stand = restart_stand
    owner = stand["owner"]
    live_stand.stop()
    incomplete = live_stand._invalidate_stand_owner_compose_resources(
        stand["worktree"], owner
    )
    assert (
        incomplete.resume_compose_resource_fingerprint
        == owner.compose_resource_fingerprint
    )
    assert (
        incomplete.resume_compose_resource_schema_version
        == live_stand.IN_PLACE_OWNER_SCHEMA_VERSION
    )
    stand["events"].clear()

    live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    updated = live_stand.load_stand_owner(stand["worktree"])
    assert dict(updated.published_ports) == stand["previous_ports"]
    assert not stand["allocations"]
    assert [event[0] for event in stand["events"]] == ["prepare", "build"]


@pytest.mark.parametrize("timing", ["before_stop", "after_stop"])
def test_busy_signed_port_rejects_before_rewriting_complete_owner(
    restart_stand: dict[str, Any], timing: str
) -> None:
    stand = restart_stand
    marker = stand["worktree"] / live_stand.STAND_FILE
    before = marker.read_bytes()
    occupied = stand["previous_ports"]["CADDY_HTTP"]
    if timing == "before_stop":
        stand["busy"].add(occupied)
    else:
        stand["after_stop"] = lambda: stand["busy"].add(occupied)

    with pytest.raises(live_stand.StandError, match=r"ports .*in use"):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert marker.read_bytes() == before
    assert [event[0] for event in stand["events"]] == ["stop"]
    assert not stand["allocations"]


def test_foreign_process_port_prevents_restart_without_rebinding_marker(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    stand = restart_stand
    child = subprocess.Popen(  # noqa: S603 - fixed interpreter and loopback-only listener
        [
            sys.executable,
            "-u",
            "-c",
            "import socket,sys; s=socket.socket(); s.bind(('127.0.0.1',0)); "
            "s.listen(); print(s.getsockname()[1],flush=True); sys.stdin.readline()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None and child.stdin is not None
    replies: queue.Queue[str] = queue.Queue(maxsize=1)
    threading.Thread(
        target=lambda: replies.put(child.stdout.readline()), daemon=True
    ).start()
    try:
        port = int(replies.get(timeout=10).strip())
        for name, value in stand["previous_ports"].items():
            if name != "CADDY_HTTP" and value == port:
                used = {*stand["previous_ports"].values(), port}
                stand["previous_ports"][name] = next(
                    candidate
                    for candidate in range(20000, 45001)
                    if candidate not in used
                )
        stand["previous_ports"]["CADDY_HTTP"] = port
        owner = replace(
            stand["owner"], published_ports=tuple(stand["previous_ports"].items())
        )
        live_stand._write_stand_owner_update(stand["worktree"], owner)
        marker = stand["worktree"] / live_stand.STAND_FILE
        before = marker.read_bytes()
        monkeypatch.setattr(
            live_stand,
            "port_is_free",
            lambda candidate, host=live_stand.PORT_BIND_HOST: (
                _PORT_IS_FREE(candidate, host=host) if candidate == port else True
            ),
        )

        with pytest.raises(live_stand.StandError, match=r"ports .*in use"):
            live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

        assert marker.read_bytes() == before
        assert [event[0] for event in stand["events"]] == ["stop"]
        assert child.poll() is None
    finally:
        if child.poll() is None:
            try:
                child.stdin.write("\n")
                child.stdin.flush()
                child.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                child.kill()
                child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
        assert child.stderr is not None
        child.stderr.close()


@pytest.mark.parametrize("timing", ["before_prepare", "during_prepare", "during_bind"])
def test_incomplete_resume_rejects_busy_port_without_stopping(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch, timing: str
) -> None:
    stand = restart_stand
    live_stand.stop()
    live_stand._invalidate_stand_owner_compose_resources(
        stand["worktree"], stand["owner"]
    )
    stand["events"].clear()
    marker = stand["worktree"] / live_stand.STAND_FILE
    before = marker.read_bytes()
    occupied = stand["previous_ports"]["CADDY_HTTP"]
    if timing == "before_prepare":
        stand["busy"].add(occupied)
    elif timing == "during_prepare":
        stand["after_prepare"] = lambda: stand["busy"].add(occupied)
    else:

        def evidence(*_args: Any, **_kwargs: Any) -> live_stand.ComposeResourceEvidence:
            stand["busy"].add(occupied)
            return stand["evidence"]

        monkeypatch.setattr(live_stand, "_owner_compose_resource_evidence", evidence)

    with pytest.raises(live_stand.StandError, match=r"ports .*in use"):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    events = [event[0] for event in stand["events"]]
    assert "stop" not in events and "build" not in events
    assert not stand["allocations"]
    owner = live_stand.load_stand_owner(stand["worktree"])
    assert dict(owner.published_ports) == stand["previous_ports"]
    if timing != "during_bind":
        assert marker.read_bytes() == before
    else:
        assert owner.compose_resource_fingerprint is not None


@pytest.mark.parametrize(
    "failure", ["signature", "source", "daemon", "resource", "volume"]
)
def test_complete_owner_validation_fails_before_stop(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    stand = restart_stand
    marker = stand["worktree"] / live_stand.STAND_FILE
    if failure == "signature":
        payload = json.loads(marker.read_text(encoding="utf-8"))
        payload["signature"] = "0" * 64
        marker.write_text(json.dumps(payload), encoding="utf-8")
    elif failure == "source":
        live_stand._write_stand_owner_update(
            stand["worktree"], replace(stand["owner"], source_sha="b" * 40)
        )
    elif failure == "daemon":
        monkeypatch.setattr(
            live_stand, "docker_daemon_fingerprint", lambda **_k: "e" * 64
        )
    elif failure == "resource":
        stand["evidence"] = replace(stand["evidence"], fingerprint="e" * 64)
    else:

        def reject(*_args: Any, **_kwargs: Any) -> None:
            raise live_stand.StandError("foreign volume")

        monkeypatch.setattr(live_stand, "_assert_compose_volume_ownership", reject)
    before = marker.read_bytes()

    with pytest.raises(live_stand.StandError):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert marker.read_bytes() == before
    assert not stand["events"]
    assert not stand["allocations"]


@pytest.mark.parametrize("failure", ["source", "daemon", "resource"])
def test_owner_drift_during_stop_rejects_before_marker_update(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    stand = restart_stand
    marker = stand["worktree"] / live_stand.STAND_FILE
    before = marker.read_bytes()
    if failure == "source":

        def drift() -> None:
            monkeypatch.setattr(
                live_stand,
                "_git",
                lambda *args: "" if args[0] == "status" else "b" * 40,
            )
    elif failure == "daemon":

        def drift() -> None:
            monkeypatch.setattr(
                live_stand, "docker_daemon_fingerprint", lambda **_k: "e" * 64
            )
    else:

        def drift() -> None:
            stand["evidence"] = replace(stand["evidence"], fingerprint="e" * 64)

    stand["after_stop"] = drift
    with pytest.raises(live_stand.StandError):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert marker.read_bytes() == before
    assert [event[0] for event in stand["events"]] == ["stop"]


@pytest.mark.parametrize("failure", ["fingerprint", "projection_drift"])
def test_incomplete_resume_rejects_unverified_resource_evidence(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    stand = restart_stand
    live_stand.stop()
    live_stand._invalidate_stand_owner_compose_resources(
        stand["worktree"], stand["owner"]
    )
    stand["events"].clear()
    marker = stand["worktree"] / live_stand.STAND_FILE
    before = marker.read_bytes()
    calls: list[bool] = []

    def evidence(*_args: Any, **_kwargs: Any) -> live_stand.ComposeResourceEvidence:
        calls.append(True)
        if failure == "fingerprint" or len(calls) == 1:
            return replace(stand["evidence"], fingerprint="e" * 64)
        return stand["evidence"]

    monkeypatch.setattr(live_stand, "_owner_compose_resource_evidence", evidence)
    with pytest.raises(live_stand.StandError, match="differs from signed resume"):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert marker.read_bytes() == before
    assert [event[0] for event in stand["events"]] == ["prepare"]
    assert not stand["allocations"]


@pytest.mark.parametrize("evidence", ["none", "previous_schema"])
def test_incomplete_owner_without_current_resume_evidence_keeps_fresh_allocation(
    restart_stand: dict[str, Any], evidence: str
) -> None:
    stand = restart_stand
    owner = stand["owner"]
    incomplete = replace(
        owner,
        compose_resource_fingerprint=None,
        resume_compose_resource_fingerprint=(
            owner.compose_resource_fingerprint
            if evidence == "previous_schema"
            else None
        ),
        resume_compose_resource_schema_version=(
            live_stand.OWNER_SCHEMA_VERSION if evidence == "previous_schema" else None
        ),
        selected_services=(),
    )
    live_stand._write_stand_owner_update(stand["worktree"], incomplete)

    live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    updated = live_stand.load_stand_owner(stand["worktree"])
    assert dict(updated.published_ports) == stand["fresh_ports"]
    assert len(stand["allocations"]) == 1
    assert [event[0] for event in stand["events"]] == ["prepare", "build"]


@pytest.mark.parametrize("version", [7, 9])
def test_legacy_in_place_owner_is_not_treated_as_current_core(
    restart_stand: dict[str, Any], version: int
) -> None:
    stand = restart_stand
    marker = stand["worktree"] / live_stand.STAND_FILE
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload.pop("signature")
    payload["version"] = version
    payload["published_ports"].pop("MINIO")
    if version == 7:
        for name in (
            "resume_compose_resource_schema_version",
            "stack",
            "service_roots",
            "selected_services",
        ):
            payload.pop(name)
    else:
        payload["compose_resource_fingerprint"] = None
        payload["selected_services"] = []
    payload["signature"] = live_stand._owner_signature(
        payload, live_stand._owner_signing_key(create=False)
    )
    marker.write_text(json.dumps(payload), encoding="utf-8")
    before = marker.read_bytes()

    with pytest.raises(live_stand.StandError):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert marker.read_bytes() == before
    assert not stand["events"]
    assert not stand["allocations"]


def test_full_in_place_stand_keeps_its_existing_port_allocation_behavior(
    restart_stand: dict[str, Any],
) -> None:
    stand = restart_stand
    owner = replace(
        stand["owner"],
        stack=live_stand.LIVE_STACK_FULL,
        service_roots=("backend",),
        selected_services=("backend",),
    )
    stand["evidence"] = replace(
        stand["evidence"],
        stack=owner.stack,
        service_roots=owner.service_roots,
        selected_services=owner.selected_services,
        managed_services=owner.selected_services,
    )
    live_stand._write_stand_owner_update(stand["worktree"], owner)

    live_stand.up("HEAD", stack=live_stand.LIVE_STACK_FULL)

    updated = live_stand.load_stand_owner(stand["worktree"])
    assert dict(updated.published_ports) == stand["fresh_ports"]
    assert len(stand["allocations"]) == 1


@pytest.mark.parametrize(
    ("phase", "load_number"),
    [("before_stop", 3), ("before_prepare", 2), ("after_prepare", 4)],
)
def test_owner_swap_is_rejected_before_control_or_rebinding(
    restart_stand: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    load_number: int,
) -> None:
    stand = restart_stand
    if phase != "before_stop":
        live_stand.stop()
        live_stand._invalidate_stand_owner_compose_resources(
            stand["worktree"], stand["owner"]
        )
        stand["events"].clear()
    marker = stand["worktree"] / live_stand.STAND_FILE
    before = marker.read_bytes()
    original_load = live_stand.load_stand_owner
    loads: list[bool] = []

    def swapped(root: Path) -> live_stand.StandOwner:
        owner = original_load(root)
        loads.append(True)
        if len(loads) == load_number:
            return replace(owner, project_name="ue-live-1111111111111111")
        return owner

    monkeypatch.setattr(live_stand, "load_stand_owner", swapped)
    with pytest.raises(live_stand.StandError, match="ownership changed"):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert marker.read_bytes() == before
    assert [event[0] for event in stand["events"]] == (
        ["prepare"] if phase == "after_prepare" else []
    )


@pytest.mark.parametrize("phase", ["after_prepare", "after_binding"])
def test_incomplete_resume_rejects_source_drift_before_build(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    stand = restart_stand
    live_stand.stop()
    live_stand._invalidate_stand_owner_compose_resources(
        stand["worktree"], stand["owner"]
    )
    stand["events"].clear()
    marker = stand["worktree"] / live_stand.STAND_FILE
    before = marker.read_bytes()

    def drift() -> None:
        monkeypatch.setattr(
            live_stand, "_git", lambda *args: "" if args[0] == "status" else "b" * 40
        )

    if phase == "after_prepare":
        stand["after_prepare"] = drift
    else:
        calls: list[bool] = []

        def evidence(*_args: Any, **_kwargs: Any) -> live_stand.ComposeResourceEvidence:
            calls.append(True)
            if len(calls) == 3:
                drift()
            return stand["evidence"]

        monkeypatch.setattr(live_stand, "_owner_compose_resource_evidence", evidence)

    with pytest.raises(live_stand.StandError, match="source checkout changed"):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert [event[0] for event in stand["events"]] == ["prepare"]
    after = live_stand.load_stand_owner(stand["worktree"])
    assert dict(after.published_ports) == stand["previous_ports"]
    assert after.compose_resource_fingerprint is None
    if phase == "after_prepare":
        assert marker.read_bytes() == before


@pytest.mark.parametrize("failure", ["port", "source"])
def test_complete_restart_rechecks_port_and_source_after_preparation(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    stand = restart_stand

    def drift() -> None:
        if failure == "port":
            stand["busy"].add(stand["previous_ports"]["CADDY_HTTP"])
        else:
            monkeypatch.setattr(
                live_stand,
                "_git",
                lambda *args: "" if args[0] == "status" else "b" * 40,
            )

    stand["after_prepare"] = drift
    with pytest.raises(live_stand.StandError):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    owner = live_stand.load_stand_owner(stand["worktree"])
    assert dict(owner.published_ports) == stand["previous_ports"]
    assert [event[0] for event in stand["events"]] == ["stop", "prepare"]
    assert (owner.compose_resource_fingerprint is None) == (failure == "source")


def test_complete_restart_does_not_replace_an_owner_removed_after_preflight(
    restart_stand: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    stand = restart_stand
    marker = stand["worktree"] / live_stand.STAND_FILE
    original_check = live_stand.require_free_ports
    removed: list[bool] = []

    def remove_after_check(*args: Any, **kwargs: Any) -> None:
        original_check(*args, **kwargs)
        if not removed:
            marker.unlink()
            removed.append(True)

    monkeypatch.setattr(live_stand, "require_free_ports", remove_after_check)
    with pytest.raises(live_stand.StandError, match="ownership metadata disappeared"):
        live_stand.up("HEAD", stack=live_stand.LIVE_STACK_CORE)

    assert not marker.exists()
    assert [event[0] for event in stand["events"]] == ["stop"]
    assert not stand["allocations"]
