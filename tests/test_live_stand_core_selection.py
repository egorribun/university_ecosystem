from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from scripts import live_stand

EXPECTED_CORE_ROOTS = (
    "caddy",
    "mailpit",
    "notifications-worker",
    "outbox-worker",
    "spicedb",
)
EXPECTED_CORE_SERVICES = (
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub",
)


@pytest.fixture
def core_compose_project() -> dict[str, Any]:
    dependencies = {
        "backend": (
            "flagd",
            "flagd-healthprobe",
            "minio-init",
            "migrations",
            "postgres-databases-init",
            "spicedb",
            "tempo-healthprobe",
        ),
        "caddy": ("backend", "frontend", "gateway", "imgproxy", "ws-hub"),
        "flagd": (),
        "flagd-healthprobe": (),
        "frontend": (),
        "gateway": ("redis", "revocation-redis"),
        "imgproxy": (),
        "mailpit": (),
        "migrations": ("postgres",),
        "minio": (),
        "minio-init": ("minio",),
        "nats": (),
        "notifications-worker": ("backend", "nats", "postgres"),
        "outbox-worker": ("backend", "nats", "postgres", "redis"),
        "postgres": (),
        "postgres-databases-init": ("postgres",),
        "redis": (),
        "revocation-redis": (),
        "spicedb": ("postgres", "spicedb-migrate"),
        "spicedb-migrate": (),
        "tempo": (),
        "tempo-healthprobe": ("tempo",),
        "ws-hub": (),
        # An unrelated project service must not be selected merely because it
        # exists in the resolved Compose model.
        "unrelated-admin-tool": (),
    }
    return {
        "services": {
            name: {
                "depends_on": {
                    dependency: {"condition": "service_healthy"}
                    for dependency in required
                }
            }
            for name, required in dependencies.items()
        }
    }


def test_full_selection_is_sorted_and_includes_every_resolved_service(
    core_compose_project: dict[str, Any],
) -> None:
    roots, selected = live_stand.resolve_live_service_selection(
        core_compose_project, live_stand.LIVE_STACK_FULL
    )

    expected = tuple(sorted(core_compose_project["services"]))
    assert roots == expected
    assert selected == expected


def test_core_selection_is_exact_sorted_dependency_closure_without_unrelated_service(
    core_compose_project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = deepcopy(core_compose_project)

    def no_process_or_lifecycle_call(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("service selection must not query or mutate live resources")

    monkeypatch.setattr(live_stand.subprocess, "run", no_process_or_lifecycle_call)
    roots, selected = live_stand.resolve_live_service_selection(
        core_compose_project, live_stand.LIVE_STACK_CORE
    )

    assert roots == EXPECTED_CORE_ROOTS
    assert selected == EXPECTED_CORE_SERVICES
    assert "unrelated-admin-tool" not in selected
    assert core_compose_project == before


def test_core_selection_rejects_unknown_stack(
    core_compose_project: dict[str, Any],
) -> None:
    with pytest.raises(live_stand.StandError, match="unsupported live stand stack"):
        live_stand.resolve_live_service_selection(core_compose_project, "core-plus")


def test_core_selection_rejects_missing_reviewed_root(
    core_compose_project: dict[str, Any],
) -> None:
    del core_compose_project["services"]["spicedb"]

    with pytest.raises(live_stand.StandError, match="service roots are missing"):
        live_stand.resolve_live_service_selection(
            core_compose_project, live_stand.LIVE_STACK_CORE
        )


def test_core_selection_rejects_missing_dependency(
    core_compose_project: dict[str, Any],
) -> None:
    core_compose_project["services"]["outbox-worker"]["depends_on"][
        "missing-database"
    ] = {"condition": "service_healthy"}

    with pytest.raises(live_stand.StandError, match="unknown service"):
        live_stand.resolve_live_service_selection(
            core_compose_project, live_stand.LIVE_STACK_CORE
        )


def test_core_selection_rejects_drift_to_an_additional_service(
    core_compose_project: dict[str, Any],
) -> None:
    core_compose_project["services"]["outbox-worker"]["depends_on"][
        "unrelated-admin-tool"
    ] = {"condition": "service_started"}

    with pytest.raises(live_stand.StandError, match="closure differs"):
        live_stand.resolve_live_service_selection(
            core_compose_project, live_stand.LIVE_STACK_CORE
        )


def test_core_selection_is_stable_across_compose_mapping_order(
    core_compose_project: dict[str, Any],
) -> None:
    services = core_compose_project["services"]
    first = live_stand.resolve_live_service_selection(
        core_compose_project, live_stand.LIVE_STACK_CORE
    )

    core_compose_project["services"] = dict(reversed(list(services.items())))
    second = live_stand.resolve_live_service_selection(
        core_compose_project, live_stand.LIVE_STACK_CORE
    )

    assert first == second == (EXPECTED_CORE_ROOTS, EXPECTED_CORE_SERVICES)


@pytest.fixture
def signed_core_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, live_stand.StandOwner]:
    repository = tmp_path / "repository"
    git_directory = repository / ".git"
    git_directory.mkdir(parents=True)
    worktree = tmp_path / live_stand.WORKTREE_NAME
    worktree.mkdir()
    (worktree / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "a" * 64)
    active_services_seen: list[tuple[str, ...] | None] = []

    def choose_published_ports(
        *, active_services: tuple[str, ...] | None = None
    ) -> dict[str, int]:
        active_services_seen.append(active_services)
        return {
            name: 20000 + index
            for index, (name, _service, _container_port) in enumerate(
                live_stand.LIVE_PORT_SPECS
            )
        }

    monkeypatch.setattr(live_stand, "choose_published_ports", choose_published_ports)

    owner = live_stand.create_stand_owner(worktree, stack=live_stand.LIVE_STACK_CORE)
    assert active_services_seen == [EXPECTED_CORE_SERVICES]
    assert len(owner.published_ports) == len(live_stand.LIVE_PORT_SPECS)
    owner = live_stand._write_stand_owner_update(
        worktree,
        replace(
            owner,
            compose_resource_fingerprint="b" * 64,
            selected_services=EXPECTED_CORE_SERVICES,
        ),
    )
    return worktree, owner


def _tree_state_snapshot(root: Path) -> tuple[tuple[str, tuple[object, ...]], ...]:
    entries: list[tuple[str, tuple[object, ...]]] = []
    root_info = root.lstat()
    entries.append(
        (
            ".",
            (
                "directory",
                root_info.st_dev,
                root_info.st_ino,
                root_info.st_mtime_ns,
                root_info.st_ctime_ns,
            ),
        )
    )
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        identity = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
        if stat.S_ISLNK(info.st_mode):
            detail: tuple[object, ...] = ("symlink", *identity, os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            detail = ("directory", *identity)
        elif stat.S_ISREG(info.st_mode):
            detail = (
                "file",
                *identity,
                info.st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        else:
            detail = ("special", *identity, info.st_mode, info.st_size)
        entries.append((relative, detail))
    return tuple(entries)


@pytest.mark.parametrize("operation", ["status", "stop"])
def test_lifecycle_rejects_signed_owner_with_stale_selection_before_compose_call(
    monkeypatch: pytest.MonkeyPatch,
    signed_core_owner: tuple[Path, live_stand.StandOwner],
    operation: str,
) -> None:
    worktree, owner = signed_core_owner
    marker = worktree / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    full_services = tuple(sorted((*EXPECTED_CORE_SERVICES, "unrelated-admin-tool")))
    mismatched_evidence = live_stand.ComposeResourceEvidence(
        fingerprint=owner.compose_resource_fingerprint or "",
        managed_volumes=(),
        stack=live_stand.LIVE_STACK_FULL,
        service_roots=full_services,
        selected_services=full_services,
    )
    monkeypatch.setattr(
        live_stand,
        "_owner_compose_resource_evidence",
        lambda _worktree, _owner: mismatched_evidence,
    )
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda _owner: None)
    compose_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda *args, **kwargs: compose_calls.append((args, kwargs)),
    )

    with pytest.raises(
        live_stand.StandError,
        match="resolved Compose selection differs from signed live stand ownership",
    ):
        getattr(live_stand, operation)()

    assert compose_calls == []
    assert marker.read_bytes() == marker_before


def test_core_status_is_read_only_and_queries_only_signed_services(
    monkeypatch: pytest.MonkeyPatch,
    signed_core_owner: tuple[Path, live_stand.StandOwner],
) -> None:
    worktree, owner = signed_core_owner
    evidence = live_stand.ComposeResourceEvidence(
        fingerprint=owner.compose_resource_fingerprint or "",
        managed_volumes=(),
        declared_volume_names=(),
        managed_networks=(),
        managed_services=EXPECTED_CORE_SERVICES,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=EXPECTED_CORE_ROOTS,
        selected_services=EXPECTED_CORE_SERVICES,
    )
    monkeypatch.setattr(
        live_stand,
        "_owner_compose_resource_evidence",
        lambda _worktree, _owner: evidence,
    )

    calls: list[tuple[list[str], dict[str, Any]]] = []
    compose_ps = live_stand.compose_command(
        "ps", *EXPECTED_CORE_SERVICES, project_name=owner.project_name
    )
    container_inventory = [
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--filter",
        f"label=com.docker.compose.project={owner.project_name}",
    ]

    def read_only_ps(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        if command == container_inventory:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        assert command == compose_ps
        assert kwargs["cwd"] == worktree
        return subprocess.CompletedProcess(
            command, 0, stdout="core services", stderr=""
        )

    monkeypatch.setattr(live_stand.subprocess, "run", read_only_ps)
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda *_args, **_kwargs: pytest.fail(
            "status must not invoke lifecycle commands"
        ),
    )

    def reject_write(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("status must not create or update stand state")

    for name in (
        "_ensure_private_state_directory",
        "_write_in_place_compose_override",
        "load_or_create_vapid",
        "load_or_create_stand_admin_password",
        "update_stand_owner_ports",
        "_write_stand_owner_update",
        "_bind_stand_owner_compose_resources",
        "_invalidate_stand_owner_compose_resources",
    ):
        monkeypatch.setattr(live_stand, name, reject_write)

    owner_signing_key = live_stand._owner_signing_key

    def read_existing_owner_key(*, create: bool) -> bytes:
        assert create is False
        return owner_signing_key(create=False)

    monkeypatch.setattr(live_stand, "_owner_signing_key", read_existing_owner_key)

    before = _tree_state_snapshot(worktree.parent)
    live_stand.status()
    after = _tree_state_snapshot(worktree.parent)

    assert before == after
    assert [command for command, _kwargs in calls] == [container_inventory, compose_ps]


@pytest.mark.parametrize(
    ("replacement_mode", "expected_error"),
    [
        ("new-id", "live Core project gained an unverified container"),
        (
            "changed-label",
            "live Core container is not owned by the signed service closure",
        ),
    ],
)
def test_core_teardown_never_removes_a_replacement_container(
    monkeypatch: pytest.MonkeyPatch,
    signed_core_owner: tuple[Path, live_stand.StandOwner],
    replacement_mode: str,
    expected_error: str,
) -> None:
    _worktree, owner = signed_core_owner
    evidence = live_stand.ComposeResourceEvidence(
        fingerprint=owner.compose_resource_fingerprint or "",
        managed_volumes=(),
        managed_services=EXPECTED_CORE_SERVICES,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=EXPECTED_CORE_ROOTS,
        selected_services=EXPECTED_CORE_SERVICES,
    )
    monkeypatch.setattr(
        live_stand,
        "_owner_compose_resource_evidence",
        lambda _worktree, _owner: evidence,
    )
    monkeypatch.setattr(
        live_stand, "_assert_compose_volume_ownership", lambda *_args, **_kwargs: ()
    )

    original_id = "a" * 64
    replacement_id = "b" * 64
    inventory_reads = 0

    def project_ids(_project_name: str) -> tuple[str, ...]:
        nonlocal inventory_reads
        inventory_reads += 1
        if replacement_mode == "new-id" and inventory_reads >= 2:
            return (replacement_id,)
        return (original_id,)

    monkeypatch.setattr(live_stand, "_project_container_ids", project_ids)

    inspect_reads = 0

    def inspect_object(arguments: list[str], _error_message: str) -> dict[str, Any]:
        nonlocal inspect_reads
        assert arguments == ["inspect", original_id]
        inspect_reads += 1
        service = (
            "unrelated-admin-tool"
            if replacement_mode == "changed-label" and inspect_reads >= 2
            else EXPECTED_CORE_SERVICES[0]
        )
        return {
            "Id": original_id,
            "Name": "/core-backend",
            "Image": "sha256:" + "1" * 64,
            "Config": {
                "Image": "backend:test",
                "Labels": {
                    "com.docker.compose.project": owner.project_name,
                    "com.docker.compose.service": service,
                },
            },
            "Mounts": [],
            "State": {"Running": False},
        }

    monkeypatch.setattr(live_stand, "_docker_inspect_object", inspect_object)
    docker_actions: list[list[str]] = []

    def docker_output(arguments: list[str], _error_message: str) -> str:
        docker_actions.append(arguments)
        return ""

    monkeypatch.setattr(live_stand, "_docker_output", docker_output)

    with pytest.raises(live_stand.StandError, match=expected_error):
        live_stand.teardown()

    assert docker_actions == []
    assert inspect_reads == (1 if replacement_mode == "new-id" else 2)


def test_core_teardown_preserves_network_referenced_by_stopped_foreign_container(
    monkeypatch: pytest.MonkeyPatch,
    signed_core_owner: tuple[Path, live_stand.StandOwner],
) -> None:
    _worktree, owner = signed_core_owner
    network_id = "c" * 64
    foreign_container_id = "d" * 64
    network_name = f"{owner.project_name}_default"
    evidence = live_stand.ComposeResourceEvidence(
        fingerprint=owner.compose_resource_fingerprint or "",
        managed_volumes=(),
        managed_networks=(("default", network_name),),
        managed_services=EXPECTED_CORE_SERVICES,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=EXPECTED_CORE_ROOTS,
        selected_services=EXPECTED_CORE_SERVICES,
    )
    monkeypatch.setattr(
        live_stand,
        "_owner_compose_resource_evidence",
        lambda _worktree, _owner: evidence,
    )
    monkeypatch.setattr(
        live_stand, "_assert_compose_volume_ownership", lambda *_args, **_kwargs: ()
    )
    monkeypatch.setattr(live_stand, "_project_container_ids", lambda _project: ())

    docker_calls: list[list[str]] = []

    def docker_output(arguments: list[str], _error_message: str) -> str:
        docker_calls.append(arguments)
        if arguments[:2] == ["network", "ls"]:
            return network_id
        if arguments == ["ps", "--all", "--quiet", "--no-trunc"]:
            return foreign_container_id
        return ""

    def inspect_object(arguments: list[str], _error_message: str) -> dict[str, Any]:
        if arguments == ["network", "inspect", network_id]:
            return {
                "Id": network_id,
                "Name": network_name,
                "Labels": {
                    "com.docker.compose.project": owner.project_name,
                    "com.docker.compose.network": "default",
                },
                "Containers": {},
            }
        if arguments == ["inspect", foreign_container_id]:
            return {
                "Id": foreign_container_id,
                "State": {"Running": False},
                "NetworkSettings": {"Networks": {"default": {"NetworkID": network_id}}},
            }
        pytest.fail("unexpected Docker inspect during Core teardown")

    monkeypatch.setattr(live_stand, "_docker_output", docker_output)
    monkeypatch.setattr(live_stand, "_docker_inspect_object", inspect_object)

    with pytest.raises(
        live_stand.StandError,
        match="live Core network is referenced by a container",
    ):
        live_stand.teardown()

    assert not any(
        call[:2] in (["network", "rm"], ["volume", "rm"]) for call in docker_calls
    )
    assert ["ps", "--all", "--quiet", "--no-trunc"] in docker_calls


def test_core_teardown_removes_exact_owned_resources_and_preserves_local_state(
    monkeypatch: pytest.MonkeyPatch,
    signed_core_owner: tuple[Path, live_stand.StandOwner],
) -> None:
    worktree, owner = signed_core_owner
    retained_files = {
        ".env": b"DEMO_SENTINEL=preserve\n",
        ".env.docker": b"LIVE_TEST_VOLUME=owned-data\n",
        "backups/core-teardown-sentinel.dump": b"synthetic-backup-bytes",
    }
    for relative_path, content in retained_files.items():
        path = worktree / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    container_id = "e" * 64
    network_id = "f" * 64
    volume_name = f"{owner.project_name}_app-data"
    network_name = f"{owner.project_name}_default"
    evidence = live_stand.ComposeResourceEvidence(
        fingerprint=owner.compose_resource_fingerprint or "",
        managed_volumes=(("app-data", volume_name),),
        declared_volume_names=(volume_name,),
        managed_networks=(("default", network_name),),
        managed_services=EXPECTED_CORE_SERVICES,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=EXPECTED_CORE_ROOTS,
        selected_services=EXPECTED_CORE_SERVICES,
    )
    monkeypatch.setattr(
        live_stand,
        "_owner_compose_resource_evidence",
        lambda _worktree, _owner: evidence,
    )
    monkeypatch.setattr(
        live_stand, "_assert_compose_volume_ownership", lambda *_args, **_kwargs: ()
    )

    project_inventory_reads = 0

    def project_ids(_project_name: str) -> tuple[str, ...]:
        nonlocal project_inventory_reads
        project_inventory_reads += 1
        return (container_id,) if project_inventory_reads < 4 else ()

    monkeypatch.setattr(live_stand, "_project_container_ids", project_ids)

    container_inspections = 0

    def inspect_object(arguments: list[str], _error_message: str) -> dict[str, Any]:
        nonlocal container_inspections
        if arguments == ["inspect", container_id]:
            container_inspections += 1
            return {
                "Id": container_id,
                "Name": "/core-backend",
                "Image": "sha256:" + "1" * 64,
                "Config": {
                    "Image": "backend:test",
                    "Labels": {
                        "com.docker.compose.project": owner.project_name,
                        "com.docker.compose.service": "backend",
                    },
                },
                "Mounts": [
                    {
                        "Type": "volume",
                        "Name": volume_name,
                        "Source": "/var/lib/docker/volumes/app-data",
                        "Destination": "/data",
                        "Driver": "local",
                        "Mode": "z",
                        "RW": True,
                        "Propagation": "",
                    }
                ],
                "State": {"Running": container_inspections < 3},
            }
        if arguments == ["network", "inspect", network_id]:
            return {
                "Id": network_id,
                "Name": network_name,
                "Labels": {
                    "com.docker.compose.project": owner.project_name,
                    "com.docker.compose.network": "default",
                },
                "Containers": {},
            }
        if arguments == ["volume", "inspect", volume_name]:
            return {
                "Name": volume_name,
                "Labels": {
                    "com.docker.compose.project": owner.project_name,
                    "com.docker.compose.volume": "app-data",
                },
            }
        pytest.fail("unexpected Docker inspect during successful Core teardown")

    monkeypatch.setattr(live_stand, "_docker_inspect_object", inspect_object)

    docker_calls: list[list[str]] = []
    network_inventory_reads = 0
    volume_inventory_reads = 0

    def docker_output(arguments: list[str], _error_message: str) -> str:
        nonlocal network_inventory_reads, volume_inventory_reads
        docker_calls.append(arguments)
        if arguments[:2] == ["network", "ls"]:
            network_inventory_reads += 1
            return network_id if network_inventory_reads == 1 else ""
        if arguments[:2] == ["volume", "ls"]:
            volume_inventory_reads += 1
            return volume_name if volume_inventory_reads == 1 else ""
        if arguments[:3] == ["ps", "--all", "--quiet"]:
            return ""
        if arguments[0] in {"stop", "rm", "network", "volume"}:
            return ""
        pytest.fail("unexpected Docker command during successful Core teardown")

    monkeypatch.setattr(live_stand, "_docker_output", docker_output)
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda *_args, **_kwargs: pytest.fail(
            "Core teardown must not use service-name Compose removal"
        ),
    )

    before = _tree_state_snapshot(worktree)
    marker_before = (worktree / live_stand.STAND_FILE).read_bytes()
    live_stand.teardown()
    after = _tree_state_snapshot(worktree)

    mutations = [
        call
        for call in docker_calls
        if call[0] in {"stop", "rm"}
        or call[:2] in (["network", "rm"], ["volume", "rm"])
    ]
    assert mutations == [
        ["stop", "--time", "10", container_id],
        ["rm", container_id],
        ["network", "rm", network_id],
        ["volume", "rm", volume_name],
    ]
    assert all("--volumes" not in call for call in docker_calls)
    assert before == after
    assert (worktree / live_stand.STAND_FILE).read_bytes() == marker_before
    assert {
        relative_path: (worktree / relative_path).read_bytes()
        for relative_path in retained_files
    } == retained_files
    assert container_inspections == 3
