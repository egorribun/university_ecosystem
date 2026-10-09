"""Regression tests for the live stand's destructive resource boundary."""

from __future__ import annotations

import json
import re
import subprocess
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from scripts import live_stand

_PROJECT_NAME = "ue-live-aaaaaaaaaaaaaaaa"
_DAEMON_FINGERPRINT = "d" * 64
_COMPOSE_SOURCE = """name: ${COMPOSE_PROJECT_NAME:?required}
services:
  backend:
    volumes:
      - app-data:/var/lib/app
    volumes_from: []
volumes:
  app-data:
    name: ${LIVE_TEST_VOLUME:?required}
"""


def _valid_published_ports() -> dict[str, int]:
    return {
        name: 30000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }


def _pre_minio_published_ports() -> dict[str, int]:
    current = _valid_published_ports()
    return {name: current[name] for name in live_stand.PRE_MINIO_PUBLISHED_PORT_NAMES}


def _matches_published_port_environment(
    environment: dict[str, str], ports: dict[str, int]
) -> bool:
    return all(
        environment.get(
            "LIVE_MAILPIT_PORT" if name == "MAILPIT" else f"LIVE_HOST_PORT_{name}"
        )
        == str(port)
        for name, port in ports.items()
    )


def _install_hermetic_stand(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    volume_name: str,
    unused_volume_name: str | None = None,
    network_name: str | None = None,
    network_labels: dict[str, dict[str, str] | None] | None = None,
    container_labels: dict[str, dict[str, str] | None] | None = None,
    container_mounts: dict[str, list[object]] | None = None,
) -> tuple[Path, Path, list[list[str]], dict[str, dict[str, str] | None]]:
    repository = tmp_path / "repository"
    worktree = repository / "live-worktree"
    metadata = tmp_path / "git-metadata"
    worktree.mkdir(parents=True)
    metadata.mkdir()
    compose_source = _COMPOSE_SOURCE
    if unused_volume_name is not None:
        compose_source += f"  unused-data:\n    name: {unused_volume_name}\n"
    if network_name is not None:
        compose_source = compose_source.replace(
            "    volumes_from: []\n",
            "    volumes_from: []\n    networks:\n      - private\n",
        )
        compose_source += (
            "networks:\n  private:\n    name: ${LIVE_TEST_NETWORK:?required}\n"
        )
    (worktree / "docker-compose.full.yml").write_text(compose_source, encoding="utf-8")
    (worktree / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    env_file = worktree / ".env.docker"
    environment_lines = [f"LIVE_TEST_VOLUME={volume_name}"]
    if network_name is not None:
        environment_lines.append(f"LIVE_TEST_NETWORK={network_name}")
    env_file.write_text("\n".join(environment_lines) + "\n", encoding="utf-8")

    compose_calls: list[list[str]] = []
    volume_labels: dict[str, dict[str, str] | None] = {}
    existing_network_labels = network_labels if network_labels is not None else {}
    existing_container_labels = container_labels if container_labels is not None else {}
    existing_container_mounts = container_mounts if container_mounts is not None else {}

    def fake_subprocess_run(
        command: list[str] | tuple[str, ...],
        *,
        cwd: Path | None = None,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        argv = list(command)
        if argv[:4] == ["docker", "volume", "ls", "--format"]:
            assert argv[4] == "{{.Name}}"
            return subprocess.CompletedProcess(
                argv, 0, stdout="\n".join(volume_labels), stderr=""
            )
        if argv[:3] == ["docker", "volume", "inspect"]:
            name = argv[-1]
            assert name in volume_labels
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps(volume_labels[name]), stderr=""
            )
        if argv[:3] == ["docker", "network", "ls"]:
            return subprocess.CompletedProcess(
                argv, 0, stdout="\n".join(existing_network_labels), stderr=""
            )
        if argv[:3] == ["docker", "network", "inspect"]:
            name = argv[-1]
            assert name in existing_network_labels
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(existing_network_labels[name]),
                stderr="",
            )
        if argv[:3] == ["docker", "ps", "--all"]:
            return subprocess.CompletedProcess(
                argv, 0, stdout="\n".join(existing_container_labels), stderr=""
            )
        if argv[:4] == ["docker", "inspect", "--type", "container"]:
            assert argv[4:5] == ["--format"]
            assert argv[5] == live_stand._DOCKER_INSPECT_FORMAT
            records = []
            for container_id in argv[6:]:
                assert container_id in existing_container_labels
                assert not existing_container_mounts.get(container_id, [])
                labels = existing_container_labels[container_id]
                records.append(
                    json.dumps(
                        {
                            "Id": container_id,
                            "ProjectLabel": labels.get("com.docker.compose.project"),
                            "ServiceLabel": labels.get("com.docker.compose.service"),
                            "Mounts": [],
                        }
                    )
                )
            return subprocess.CompletedProcess(
                argv, 0, stdout="\n".join(records), stderr=""
            )
        if argv[:4] == ["docker", "inspect", "--format", "{{json .Mounts}}"]:
            container_id = argv[-1]
            assert container_id in existing_container_labels
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(existing_container_mounts.get(container_id, [])),
                stderr="",
            )
        if argv[:2] == ["docker", "inspect"]:
            container_id = argv[-1]
            assert container_id in existing_container_labels
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(existing_container_labels[container_id]),
                stderr="",
            )
        if argv[:2] != ["docker", "compose"] or "config" not in argv:
            raise AssertionError("unexpected subprocess in hermetic live-stand test")
        compose_calls.append(argv)
        assert cwd is not None
        assert Path(cwd) == worktree
        assert "--env-file" in argv
        assert ".env.docker" in argv
        project_index = argv.index("-p") + 1
        project_name = argv[project_index]
        assert "docker-compose.full.yml" in argv
        assert live_stand.OVERLAY in argv
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["COMPOSE_PROJECT_NAME"] == project_name
        assert (
            environment["LIVE_VAPID_PUBLIC_KEY"]
            == live_stand.COMPOSE_INSPECTION_PLACEHOLDER
        )
        assert (
            environment["LIVE_VAPID_PRIVATE_KEY"]
            == live_stand.COMPOSE_INSPECTION_PLACEHOLDER
        )
        assert _matches_published_port_environment(
            environment, _valid_published_ports()
        ) or _matches_published_port_environment(
            environment, _pre_minio_published_ports()
        )

        compose_text = (worktree / "docker-compose.full.yml").read_text(
            encoding="utf-8"
        )
        env_values = dict(
            line.split("=", 1)
            for line in env_file.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        volume_match = re.search(r"(?m)^\s+name:\s*(.+?)\s*$", compose_text)
        assert volume_match is not None
        expression = volume_match.group(1).strip("\"'")
        if expression.startswith("${LIVE_TEST_VOLUME"):
            resolved_volume_name = env_values["LIVE_TEST_VOLUME"].strip()
        elif "LIVE_VAPID_PRIVATE_KEY" in expression:
            resolved_volume_name = (
                f"{project_name}_app-{live_stand.COMPOSE_INSPECTION_PLACEHOLDER}"
            )
        else:
            resolved_volume_name = expression

        services: dict[str, dict[str, object]] = {
            "backend": {
                "volumes": [
                    {
                        "type": "volume",
                        "source": "app-data",
                        "target": "/var/lib/app",
                        "read_only": False,
                    }
                ],
                "volumes_from": [],
            }
        }
        networks: dict[str, object] = {}
        network_match = re.search(
            r"(?ms)^networks:\s*\n\s{2}(?P<key>[A-Za-z0-9_-]+):\s*\n\s{4}name:\s*\$\{LIVE_TEST_NETWORK",
            compose_text,
        )
        if network_match is not None:
            network_key = network_match.group("key")
            networks[network_key] = {
                "name": env_values["LIVE_TEST_NETWORK"],
                "external": False,
            }
            services["backend"]["networks"] = {network_key: None}
        resolved_volumes = {"app-data": {"name": resolved_volume_name}}
        if unused_volume_name is not None:
            resolved_volumes["unused-data"] = {"name": unused_volume_name}
        rendered = json.dumps(
            {
                "name": project_name,
                "services": services,
                "networks": networks,
                "volumes": resolved_volumes,
            }
        )
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr="")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git_common_directory", lambda: metadata)
    monkeypatch.setattr(live_stand, "_git", lambda *_args: "")
    monkeypatch.setattr(live_stand.secrets, "token_hex", lambda _bytes: "a" * 16)
    monkeypatch.setattr(
        live_stand, "docker_daemon_fingerprint", lambda: _DAEMON_FINGERPRINT
    )
    monkeypatch.setattr(
        live_stand, "load_vapid", lambda _worktree: {"public": "pub", "private": "priv"}
    )
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand.subprocess, "run", fake_subprocess_run)
    return repository, worktree, compose_calls, volume_labels


def _create_complete_hermetic_stand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path, list[list[str]], dict[str, dict[str, str] | None]]:
    repository, worktree, compose_calls, volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    live_stand._bind_stand_owner_compose_resources(worktree, owner)
    return repository, worktree, compose_calls, volume_labels


def _write_v4_owner_marker(worktree: Path, owner: live_stand.StandOwner) -> None:
    assert owner.daemon_fingerprint is not None
    payload = {
        "version": live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
        "repository": owner.repository,
        "worktree": owner.worktree,
        "project_name": owner.project_name,
        "published_ports": _pre_minio_published_ports(),
        "daemon_fingerprint": owner.daemon_fingerprint,
    }
    marker = {
        **payload,
        "signature": live_stand._owner_signature(
            payload, live_stand._owner_signing_key(create=False)
        ),
    }
    (worktree / live_stand.STAND_FILE).write_text(json.dumps(marker), encoding="utf-8")


def _write_v5_owner_marker(
    worktree: Path,
    owner: live_stand.StandOwner,
    *,
    fingerprint: str | None = None,
) -> None:
    assert owner.daemon_fingerprint is not None
    payload = {
        "version": live_stand.RESOURCE_OWNER_SCHEMA_VERSION,
        "repository": owner.repository,
        "worktree": owner.worktree,
        "project_name": owner.project_name,
        "published_ports": _pre_minio_published_ports(),
        "daemon_fingerprint": owner.daemon_fingerprint,
        "compose_resource_fingerprint": (
            owner.compose_resource_fingerprint if fingerprint is None else fingerprint
        ),
    }
    marker = {
        **payload,
        "signature": live_stand._owner_signature(
            payload, live_stand._owner_signing_key(create=False)
        ),
    }
    (worktree / live_stand.STAND_FILE).write_text(json.dumps(marker), encoding="utf-8")


def test_owner_creation_refuses_unscoped_explicit_volume_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch, tmp_path, volume_name="shared-volume"
    )

    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    assert owner.compose_resource_fingerprint is None

    with pytest.raises(live_stand.StandError, match="volume"):
        live_stand._bind_stand_owner_compose_resources(worktree, owner)

    marker = json.loads((worktree / live_stand.STAND_FILE).read_text(encoding="utf-8"))
    assert marker["compose_resource_fingerprint"] is None


def test_resource_identity_cannot_depend_on_vapid_placeholder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    compose_path = worktree / "docker-compose.full.yml"
    compose_path.write_text(
        _COMPOSE_SOURCE.replace(
            "${LIVE_TEST_VOLUME:?required}",
            "${COMPOSE_PROJECT_NAME}_app-${LIVE_VAPID_PRIVATE_KEY:?required}",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        live_stand,
        "load_vapid",
        lambda _worktree: (_ for _ in ()).throw(AssertionError("VAPID was read")),
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )

    with pytest.raises(live_stand.StandError, match=r"cannot determine.*identity"):
        live_stand._bind_stand_owner_compose_resources(worktree, owner)


def test_resource_fingerprint_ignores_non_identity_volume_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    resolved = {
        "name": _PROJECT_NAME,
        "services": {
            "backend": {
                "volumes": [
                    {
                        "type": "volume",
                        "source": "app-data",
                        "target": "/var/lib/app",
                        "read_only": False,
                    }
                ]
            }
        },
        "volumes": {
            "app-data": {
                "name": f"{_PROJECT_NAME}_app-data",
                "driver_opts": {"fixture_option": "first-value"},
            }
        },
    }

    def compose_config(
        command: list[str] | tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert list(command)[:2] == ["docker", "compose"]
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(resolved), stderr=""
        )

    monkeypatch.setattr(live_stand.subprocess, "run", compose_config)
    first = live_stand._compose_resource_fingerprint(
        worktree, _PROJECT_NAME, _valid_published_ports()
    )
    resolved["volumes"]["app-data"]["driver_opts"]["fixture_option"] = "second-value"
    second = live_stand._compose_resource_fingerprint(
        worktree, _PROJECT_NAME, _valid_published_ports()
    )

    assert first == second
    resolved["services"]["backend"]["volumes"][0]["target"] = "/var/lib/other"
    redirected = live_stand._compose_resource_fingerprint(
        worktree, _PROJECT_NAME, _valid_published_ports()
    )
    assert redirected != first


def test_resource_fingerprint_tracks_service_network_attachment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    resolved: dict[str, Any] = {
        "name": _PROJECT_NAME,
        "networks": {
            "internal": {"name": f"{_PROJECT_NAME}_internal"},
            "public": {"name": f"{_PROJECT_NAME}_public"},
        },
        "services": {
            "backend": {
                "networks": {"public": None},
                "volumes": [],
                "volumes_from": [],
            }
        },
        "volumes": {},
    }

    def compose_config(
        command: list[str] | tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert list(command)[:2] == ["docker", "compose"]
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(resolved), stderr=""
        )

    monkeypatch.setattr(live_stand.subprocess, "run", compose_config)
    public = live_stand._compose_resource_fingerprint(
        worktree, _PROJECT_NAME, _valid_published_ports()
    )
    resolved["services"]["backend"]["networks"] = {"internal": None}
    internal = live_stand._compose_resource_fingerprint(
        worktree, _PROJECT_NAME, _valid_published_ports()
    )

    assert public != internal


def test_teardown_refuses_incomplete_reservation_before_config_or_down(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    live_stand.create_stand_owner(worktree, published_ports=_valid_published_ports())
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"incomplete|evidence"):
        live_stand.teardown()

    assert compose_calls == []
    assert lifecycle_calls == []


def test_status_refuses_signed_incomplete_reservation_before_compose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI status must not report an incomplete reservation as a running stand."""
    _repository, worktree, compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    assert live_stand.load_stand_owner(worktree) == owner
    marker = worktree / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    result = live_stand.main(["status"])

    assert result == 2
    assert "startup is incomplete" in capsys.readouterr().err
    assert compose_calls == []
    assert lifecycle_calls == []
    assert marker.read_bytes() == marker_before
    assert not (worktree / live_stand.VAPID_FILE).exists()


def test_teardown_refuses_changed_network_identity_before_compose_down(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=f"{_PROJECT_NAME}_private",
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    live_stand._bind_stand_owner_compose_resources(worktree, owner)
    (worktree / ".env.docker").write_text(
        f"LIVE_TEST_VOLUME={_PROJECT_NAME}_app-data\n"
        f"LIVE_TEST_NETWORK={_PROJECT_NAME}_replacement\n",
        encoding="utf-8",
    )
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"resource|network|ownership"):
        live_stand.teardown()

    assert lifecycle_calls == []


def test_teardown_refuses_network_with_wrong_compose_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    network_name = f"{_PROJECT_NAME}_private"
    network_labels: dict[str, dict[str, str] | None] = {}
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=network_name,
        network_labels=network_labels,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    live_stand._bind_stand_owner_compose_resources(worktree, owner)
    network_labels[network_name] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.network": "different-network",
    }
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"network|ownership"):
        live_stand.teardown()

    assert lifecycle_calls == []


def test_teardown_refuses_project_container_for_unknown_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    container_labels: dict[str, dict[str, str] | None] = {}
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=f"{_PROJECT_NAME}_private",
        container_labels=container_labels,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    live_stand._bind_stand_owner_compose_resources(worktree, owner)
    container_labels["c" * 64] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.service": "unexpected-service",
    }
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"container|ownership"):
        live_stand.teardown()

    assert lifecycle_calls == []


def test_teardown_rejects_previous_resource_marker_until_up_rebinds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    compose_calls_before_teardown = len(compose_calls)
    _write_v5_owner_marker(worktree, owner)
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(
        live_stand.StandError, match=r"legacy|current|evidence|resources"
    ):
        live_stand.teardown()

    assert len(compose_calls) == compose_calls_before_teardown + 1
    assert lifecycle_calls == []


def test_incomplete_previous_resource_marker_cannot_adopt_existing_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    network_name = f"{_PROJECT_NAME}_private"
    network_labels = {
        network_name: {
            "com.docker.compose.project": _PROJECT_NAME,
            "com.docker.compose.network": "private",
        }
    }
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=network_name,
        network_labels=network_labels,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    _write_v5_owner_marker(worktree, owner)
    ports = _valid_published_ports()
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: "a" * 40)
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: ports)
    monkeypatch.setattr(live_stand, "require_free_ports", lambda *_args: None)
    monkeypatch.setattr(live_stand, "ensure_worktree", lambda _sha: worktree)
    monkeypatch.setattr(live_stand, "_assert_worktree_clean", lambda _path: None)
    monkeypatch.setattr(
        live_stand,
        "load_or_create_vapid",
        lambda _path: {"public": "p", "private": "q"},
    )
    monkeypatch.setattr(live_stand, "stand_environment", lambda *_args: {})
    monkeypatch.setattr(live_stand.shutil, "which", lambda _name: "pwsh")
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match="network already exists"):
        live_stand._up_locked("HEAD")

    current = live_stand.load_stand_owner(worktree)
    assert current.schema_version == live_stand.OWNER_SCHEMA_VERSION
    assert current.compose_resource_fingerprint is None
    assert current.resume_compose_resource_fingerprint is None
    assert lifecycle_calls and "-PrepareOnly" in lifecycle_calls[0]
    assert all("-Build" not in command for command in lifecycle_calls)


def test_new_reservation_rejects_preexisting_project_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    network_name = f"{_PROJECT_NAME}_private"
    network_labels = {
        network_name: {
            "com.docker.compose.project": _PROJECT_NAME,
            "com.docker.compose.network": "private",
        }
    }
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=network_name,
        network_labels=network_labels,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )

    with pytest.raises(live_stand.StandError, match="network already exists"):
        live_stand._bind_stand_owner_compose_resources(worktree, owner)

    assert live_stand.load_stand_owner(worktree).compose_resource_fingerprint is None


def test_new_reservation_rejects_preexisting_project_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    container_labels = {
        "d" * 64: {
            "com.docker.compose.project": _PROJECT_NAME,
            "com.docker.compose.service": "backend",
        }
    }
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=f"{_PROJECT_NAME}_private",
        container_labels=container_labels,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )

    with pytest.raises(live_stand.StandError, match="container already exists"):
        live_stand._bind_stand_owner_compose_resources(worktree, owner)

    assert live_stand.load_stand_owner(worktree).compose_resource_fingerprint is None


def test_teardown_accepts_resources_with_exact_compose_ownership_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    network_name = f"{_PROJECT_NAME}_private"
    network_labels: dict[str, dict[str, str] | None] = {}
    container_labels: dict[str, dict[str, str] | None] = {}
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        network_name=network_name,
        network_labels=network_labels,
        container_labels=container_labels,
        container_mounts={"e" * 64: []},
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    live_stand._bind_stand_owner_compose_resources(worktree, owner)
    network_labels[network_name] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.network": "private",
    }
    container_labels["e" * 64] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.service": "backend",
    }
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    live_stand.teardown()

    assert len(lifecycle_calls) == 1
    assert "down" in lifecycle_calls[0]
    assert "--volumes" in lifecycle_calls[0]


def test_teardown_does_not_remove_unprojected_orphan_containers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Orphans are outside the signed Compose resource projection."""
    _repository, _worktree, _compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    live_stand.teardown()

    assert len(lifecycle_calls) == 1
    assert "down" in lifecycle_calls[0]
    assert "--volumes" in lifecycle_calls[0]
    assert "--remove-orphans" not in lifecycle_calls[0]


@pytest.mark.parametrize("redirect_input", ["compose", "env-file"])
def test_teardown_refuses_redirected_volume_before_compose_down(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    redirect_input: str,
) -> None:
    _repository, worktree, compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    owner = live_stand._bind_stand_owner_compose_resources(worktree, owner)
    assert owner.project_name == _PROJECT_NAME

    if redirect_input == "compose":
        compose_file = worktree / "docker-compose.full.yml"
        compose_file.write_text(
            _COMPOSE_SOURCE.replace("${LIVE_TEST_VOLUME:?required}", "shared-volume"),
            encoding="utf-8",
        )
    else:
        (worktree / ".env.docker").write_text(
            "LIVE_TEST_VOLUME=shared-volume\n",  # pragma: allowlist secret
            encoding="utf-8",
        )

    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"(compose|volume|ownership)"):
        live_stand.teardown()

    assert lifecycle_calls == []
    assert compose_calls


def test_bind_refuses_preexisting_project_scoped_volume_before_signing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    volume_labels[f"{_PROJECT_NAME}_app-data"] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.volume": "app-data",
    }
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )

    with pytest.raises(live_stand.StandError, match="already exists"):
        live_stand._bind_stand_owner_compose_resources(worktree, owner)

    assert live_stand.load_stand_owner(worktree).compose_resource_fingerprint is None


def test_resumable_v5_owner_evidence_remains_signed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    assert owner.compose_resource_fingerprint is not None

    incomplete = live_stand.update_stand_owner_ports(
        worktree, owner, dict(owner.published_ports)
    )
    assert incomplete.compose_resource_fingerprint is None
    assert incomplete.resume_compose_resource_fingerprint == (
        owner.compose_resource_fingerprint
    )

    marker_path = worktree / live_stand.STAND_FILE
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["resume_compose_resource_fingerprint"] = "f" * 64
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(live_stand.StandError, match="signature"):
        live_stand.load_stand_owner(worktree)


def test_resume_evidence_refuses_redirected_existing_volume_before_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    original_fingerprint = owner.compose_resource_fingerprint
    assert original_fingerprint is not None

    incomplete = live_stand.update_stand_owner_ports(
        worktree, owner, dict(owner.published_ports)
    )
    redirected_name = f"{_PROJECT_NAME}_replacement"
    volume_labels[redirected_name] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.volume": "app-data",
    }
    (worktree / ".env.docker").write_text(
        f"LIVE_TEST_VOLUME={redirected_name}\n", encoding="utf-8"
    )

    with pytest.raises(live_stand.StandError, match=r"resource identity|fingerprint"):
        live_stand._bind_stand_owner_compose_resources(
            worktree, incomplete, allow_existing_owned_volumes=True
        )

    current = live_stand.load_stand_owner(worktree)
    assert current.compose_resource_fingerprint is None
    assert current.resume_compose_resource_fingerprint == original_fingerprint


def test_old_v5_owner_marker_without_resume_field_remains_readable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    _write_v5_owner_marker(worktree, live_stand.load_stand_owner(worktree))

    loaded = live_stand.load_stand_owner(worktree)
    assert loaded.schema_version == live_stand.RESOURCE_OWNER_SCHEMA_VERSION
    assert dict(loaded.published_ports) == _pre_minio_published_ports()
    assert loaded.compose_resource_fingerprint is not None
    assert loaded.resume_compose_resource_fingerprint is None


def test_bind_refuses_docker_daemon_change_during_resource_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    daemon_fingerprints = iter((_DAEMON_FINGERPRINT, _DAEMON_FINGERPRINT, "e" * 64))
    monkeypatch.setattr(
        live_stand,
        "docker_daemon_fingerprint",
        lambda: next(daemon_fingerprints),
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )

    with pytest.raises(live_stand.StandError, match="different Docker daemon"):
        live_stand._bind_stand_owner_compose_resources(worktree, owner)

    assert len(compose_calls) == 1
    assert live_stand.load_stand_owner(worktree).compose_resource_fingerprint is None


def test_teardown_refuses_unused_declared_volume_with_wrong_compose_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Full-stack down must preflight declared volumes even when unmounted."""
    unused_volume_name = f"{_PROJECT_NAME}_unused-data"
    _repository, worktree, _compose_calls, volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        unused_volume_name=unused_volume_name,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    owner = live_stand._bind_stand_owner_compose_resources(worktree, owner)
    volume_labels[unused_volume_name] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.volume": "different-volume",
    }
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match="not owned"):
        live_stand.teardown()

    assert live_stand.load_stand_owner(worktree) == owner
    assert lifecycle_calls == []


def test_legacy_full_projection_retains_unused_declared_volume_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    unused_volume_name = f"{_PROJECT_NAME}_unused-data"
    _repository, worktree, _compose_calls, _volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
        unused_volume_name=unused_volume_name,
    )
    owner = live_stand.create_stand_owner(
        worktree, published_ports=_valid_published_ports()
    )
    owner = live_stand._bind_stand_owner_compose_resources(worktree, owner)
    _write_v5_owner_marker(worktree, owner)

    legacy_owner = live_stand.load_stand_owner(worktree)
    evidence = live_stand._owner_compose_resource_evidence(worktree, legacy_owner)

    assert legacy_owner.schema_version == live_stand.RESOURCE_OWNER_SCHEMA_VERSION
    assert evidence.declared_volume_names == (
        f"{_PROJECT_NAME}_app-data",
        unused_volume_name,
    )
    assert evidence.managed_volumes == (
        ("app-data", f"{_PROJECT_NAME}_app-data"),
        ("unused-data", unused_volume_name),
    )


def test_stop_refuses_compose_resource_redirect_before_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    (worktree / ".env.docker").write_text(
        "LIVE_TEST_VOLUME=shared-volume\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"resources|volume"):
        live_stand._stop_locked()

    assert compose_calls
    assert lifecycle_calls == []


def test_stop_rechecks_daemon_after_resource_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, _worktree, _compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    daemon_checks = 0
    lifecycle_calls: list[list[str]] = []

    def check_daemon(_owner: live_stand.StandOwner) -> None:
        nonlocal daemon_checks
        daemon_checks += 1
        if daemon_checks == 2:
            raise live_stand.StandError("different Docker daemon detected")

    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", check_daemon)
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match="different Docker daemon"):
        live_stand._stop_locked()

    assert daemon_checks == 2
    assert lifecycle_calls == []


def test_stop_preserves_owned_files_and_volumes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, _compose_calls, volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    volume_name = f"{owner.project_name}_app-data"
    volume_labels[volume_name] = {
        "com.docker.compose.project": owner.project_name,
        "com.docker.compose.volume": "app-data",
    }

    stand_marker = worktree / live_stand.STAND_FILE
    vapid_file = worktree / live_stand.VAPID_FILE
    admin_password_file = worktree / live_stand.ADMIN_PASSWORD_FILE
    preserved_files = {
        worktree / ".env": b"OPERATOR_VALUE=keep\n",
        worktree / ".env.docker": f"LIVE_TEST_VOLUME={volume_name}\n".encode(),
        stand_marker: stand_marker.read_bytes(),
        vapid_file: b'{"public":"synthetic","private":"synthetic"}',
        admin_password_file: b'{"password":"synthetic"}',  # pragma: allowlist secret -- synthetic resource-preservation bytes
    }
    for path, contents in preserved_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    owner_key = live_stand._git_common_directory() / "live-stand-owner.key"
    preserved_key = owner_key.read_bytes()
    preserved_volume_labels = volume_labels.copy()
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    live_stand.stop()

    assert lifecycle_calls == [
        live_stand.compose_command("stop", project_name=owner.project_name)
    ]
    assert all(
        path.read_bytes() == contents for path, contents in preserved_files.items()
    )
    assert owner_key.read_bytes() == preserved_key
    assert volume_labels == preserved_volume_labels


def test_seed_refuses_compose_resource_redirect_before_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    (worktree / ".env.docker").write_text(
        "LIVE_TEST_VOLUME=shared-volume\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    lifecycle_calls: list[list[str]] = []
    monkeypatch.setattr(
        live_stand,
        "stand_environment",
        lambda *_args: {"COMPOSE_PROJECT_NAME": owner.project_name},
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"resources|volume"):
        live_stand._seed_locked("fixture-password", owner=owner)

    assert compose_calls
    assert lifecycle_calls == []


def test_seed_rechecks_daemon_after_resource_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _repository, worktree, compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    daemon_checks = 0
    lifecycle_calls: list[list[str]] = []

    def check_daemon(_owner: live_stand.StandOwner) -> None:
        nonlocal daemon_checks
        daemon_checks += 1
        if daemon_checks == 2:
            raise live_stand.StandError("different Docker daemon detected")

    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", check_daemon)
    monkeypatch.setattr(
        live_stand,
        "stand_environment",
        lambda *_args: {"COMPOSE_PROJECT_NAME": owner.project_name},
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: lifecycle_calls.append(list(command)),
    )

    with pytest.raises(live_stand.StandError, match="different Docker daemon"):
        live_stand._seed_locked("fixture-password", owner=owner)

    assert daemon_checks == 2
    assert compose_calls
    assert lifecycle_calls == []


def test_e2e_rechecks_daemon_after_resource_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository, worktree, _compose_calls, _volume_labels = (
        _create_complete_hermetic_stand(monkeypatch, tmp_path)
    )
    owner = live_stand.load_stand_owner(worktree)
    events: list[str] = []
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    monkeypatch.setattr(
        live_stand,
        "_seed_locked",
        lambda _password, *, owner: events.append("seed"),
    )
    monkeypatch.setattr(
        live_stand,
        "_live_e2e_environment",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        live_stand,
        "_ensure_live_e2e_dependencies",
        lambda _frontend, _environment: events.append("dependencies"),
    )
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda _path, _owner: events.append("resource-preflight"),
    )

    def changed_daemon(_owner: live_stand.StandOwner) -> None:
        events.append("daemon-check")
        raise live_stand.StandError("different Docker daemon detected")

    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", changed_daemon)
    monkeypatch.setattr(
        live_stand,
        "_run_live_playwright",
        lambda **_kwargs: events.append("playwright"),
    )

    with pytest.raises(live_stand.StandError, match="different Docker daemon"):
        live_stand._e2e_locked("fixture-password")

    assert events == ["seed", "dependencies", "resource-preflight", "daemon-check"]


@pytest.mark.parametrize(
    "existing_reservation_schema",
    [
        None,
        live_stand.OWNER_SCHEMA_VERSION,
        live_stand.RESOURCE_OWNER_SCHEMA_VERSION,
        live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
    ],
)
@pytest.mark.parametrize("prepare_fails", [False, True])
@pytest.mark.parametrize("daemon_changes_after_resource_check", [False, True])
def test_up_prepares_environment_before_fingerprinting_and_starting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    existing_reservation_schema: int | None,
    prepare_fails: bool,
    daemon_changes_after_resource_check: bool,
) -> None:
    repository = tmp_path / "repository"
    worktree = repository / "live-worktree"
    metadata = tmp_path / "git-metadata"
    repository.mkdir()
    metadata.mkdir()
    events: list[str] = []
    ports = _valid_published_ports()
    fingerprint = "f" * 64

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git_common_directory", lambda: metadata)
    monkeypatch.setattr(live_stand, "_git", lambda *_args: "")
    monkeypatch.setattr(live_stand.secrets, "token_hex", lambda _bytes: "a" * 16)
    monkeypatch.setattr(live_stand, "_assert_stand_paths_safe", lambda *_args: None)
    monkeypatch.setattr(live_stand, "_assert_worktree_paths_safe", lambda *_args: None)
    monkeypatch.setattr(live_stand, "_assert_no_reparse_ancestors", lambda *_args: None)
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: "a" * 40)
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: ports)
    monkeypatch.setattr(live_stand, "require_free_ports", lambda *_args: None)

    def fake_ensure_worktree(_sha: str) -> Path:
        if not worktree.exists():
            worktree.mkdir()
            (worktree / live_stand.OVERLAY).write_text(
                "services: {}\n", encoding="utf-8"
            )
            (worktree / "docker-compose.full.yml").write_text(
                _COMPOSE_SOURCE, encoding="utf-8"
            )
        return worktree

    monkeypatch.setattr(live_stand, "ensure_worktree", fake_ensure_worktree)
    monkeypatch.setattr(
        live_stand, "docker_daemon_fingerprint", lambda: _DAEMON_FINGERPRINT
    )
    monkeypatch.setattr(
        live_stand,
        "load_or_create_vapid",
        lambda _worktree: {"public": "pub", "private": "priv"},
    )
    monkeypatch.setattr(
        live_stand, "load_vapid", lambda _worktree: {"public": "pub", "private": "priv"}
    )
    monkeypatch.setattr(live_stand.shutil, "which", lambda _name: "pwsh")
    prepare_environment: dict[str, str] | None = None

    def fake_evidence(
        actual_worktree: Path,
        project_name: str,
        published_ports: dict[str, int],
        *,
        legacy_projection: bool = False,
    ) -> live_stand.ComposeResourceEvidence:
        assert actual_worktree == worktree
        assert published_ports == ports
        assert (worktree / ".env.docker").is_file(), (
            "config checked before prepare-only"
        )
        assert project_name == _PROJECT_NAME
        events.append("evidence")
        return live_stand.ComposeResourceEvidence(
            fingerprint=fingerprint,
            managed_volumes=(("app-data", f"{_PROJECT_NAME}_app-data"),),
            declared_volume_names=(f"{_PROJECT_NAME}_app-data",),
            managed_networks=(("default", f"{_PROJECT_NAME}_default"),),
            managed_services=("backend",),
            service_roots=("backend",),
            selected_services=("backend",),
        )

    def fake_volume_ownership(
        project_name: str,
        managed_volumes: tuple[tuple[str, str], ...],
        *,
        declared_volume_names: tuple[str, ...],
        allow_existing_owned: bool,
        managed_networks: tuple[tuple[str, str], ...] = (),
        managed_services: tuple[str, ...] = (),
    ) -> tuple[tuple[str, str], ...]:
        assert project_name == _PROJECT_NAME
        assert managed_volumes == (("app-data", f"{_PROJECT_NAME}_app-data"),)
        assert declared_volume_names == (f"{_PROJECT_NAME}_app-data",)
        assert managed_networks == (("default", f"{_PROJECT_NAME}_default"),)
        assert managed_services == ("backend",)
        assert allow_existing_owned is (
            existing_reservation_schema
            in {
                live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
                live_stand.RESOURCE_OWNER_SCHEMA_VERSION,
            }
        )
        if daemon_changes_after_resource_check and events.count("volume-check") == 1:
            monkeypatch.setattr(
                live_stand, "docker_daemon_fingerprint", lambda: "e" * 64
            )
        events.append("volume-check")
        return ()

    monkeypatch.setattr(live_stand, "_compose_resource_evidence", fake_evidence)
    monkeypatch.setattr(
        live_stand, "_assert_compose_volume_ownership", fake_volume_ownership
    )

    if existing_reservation_schema is not None:
        fake_ensure_worktree("a" * 40)
        created_owner = live_stand.create_stand_owner(worktree, published_ports=ports)
        if existing_reservation_schema == live_stand.PREVIOUS_OWNER_SCHEMA_VERSION:
            _write_v4_owner_marker(worktree, created_owner)
        elif existing_reservation_schema == live_stand.RESOURCE_OWNER_SCHEMA_VERSION:
            _write_v5_owner_marker(worktree, created_owner, fingerprint=fingerprint)
        else:
            assert existing_reservation_schema == live_stand.OWNER_SCHEMA_VERSION
        if existing_reservation_schema in {
            live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
            live_stand.RESOURCE_OWNER_SCHEMA_VERSION,
        }:
            assert (
                dict(live_stand.load_stand_owner(worktree).published_ports)
                == _pre_minio_published_ports()
            )

    def fake_run(
        command: list[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> None:
        nonlocal prepare_environment
        assert cwd == worktree
        assert env is not None
        if "-PrepareOnly" in command:
            events.append("prepare")
            reserved_owner = live_stand.load_stand_owner(worktree)
            assert reserved_owner.compose_resource_fingerprint is None
            assert "-ExtraCompose" in command
            assert command[command.index("-ExtraCompose") + 1] == live_stand.OVERLAY
            assert "-Build" not in command
            assert env["COMPOSE_PROJECT_NAME"] == _PROJECT_NAME
            assert env["LIVE_HOST_PORT_BACKEND"] == str(ports["BACKEND"])
            if prepare_fails:
                raise subprocess.CalledProcessError(1, command)
            prepare_environment = env.copy()
            (worktree / ".env.docker").write_text(
                f"LIVE_TEST_VOLUME={_PROJECT_NAME}_app-data\n", encoding="utf-8"
            )
            return
        if command[-1] == "stop":
            events.append("stop")
            return
        events.append("start")
        assert "-Build" in command
        assert ("-AllowExistingOwnedVolumes" in command) is (
            existing_reservation_schema
            in {
                live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
                live_stand.RESOURCE_OWNER_SCHEMA_VERSION,
            }
        )
        assert env == prepare_environment
        owner = live_stand.load_stand_owner(worktree)
        assert owner.compose_resource_fingerprint == fingerprint

    monkeypatch.setattr(live_stand, "_run", fake_run)

    if prepare_fails:
        with pytest.raises(subprocess.CalledProcessError):
            live_stand._up_locked("HEAD")
        assert (
            live_stand.load_stand_owner(worktree).compose_resource_fingerprint is None
        )
        with pytest.raises(live_stand.StandError, match="incomplete"):
            live_stand.teardown()
        assert events == ["prepare"]
    elif daemon_changes_after_resource_check:
        with pytest.raises(live_stand.StandError, match="different Docker daemon"):
            live_stand._up_locked("HEAD")
        assert (
            live_stand.load_stand_owner(worktree).compose_resource_fingerprint is None
        )
        with pytest.raises(live_stand.StandError, match="incomplete"):
            live_stand.teardown()
        expected_events = ["prepare", "evidence"]
        if existing_reservation_schema == live_stand.RESOURCE_OWNER_SCHEMA_VERSION:
            expected_events.append("evidence")
        expected_events.extend(["volume-check", "evidence", "volume-check"])
        assert events == expected_events
    else:
        live_stand._up_locked("HEAD")
        expected_events = ["prepare", "evidence"]
        if existing_reservation_schema == live_stand.RESOURCE_OWNER_SCHEMA_VERSION:
            expected_events.append("evidence")
        expected_events.append("volume-check")
        if existing_reservation_schema in {
            live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
            live_stand.RESOURCE_OWNER_SCHEMA_VERSION,
        }:
            expected_events.extend(["evidence", "volume-check", "stop"])
        expected_events.extend(["evidence", "volume-check", "start"])
        assert events == expected_events


@pytest.mark.parametrize("failure_stage", ["prepare", "resource-bind"])
def test_existing_v5_stand_can_retry_after_incomplete_startup_with_owned_volumes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_stage: str,
) -> None:
    repository, worktree, _compose_calls, volume_labels = _install_hermetic_stand(
        monkeypatch,
        tmp_path,
        volume_name=f"{_PROJECT_NAME}_app-data",
    )
    ports = _valid_published_ports()
    owner = live_stand.create_stand_owner(worktree, published_ports=ports)
    owner = live_stand._bind_stand_owner_compose_resources(worktree, owner)
    assert owner.compose_resource_fingerprint is not None

    volume_labels[f"{_PROJECT_NAME}_app-data"] = {
        "com.docker.compose.project": _PROJECT_NAME,
        "com.docker.compose.volume": "app-data",
    }
    original_resource_evidence = live_stand._compose_resource_evidence
    evidence_calls = 0

    def fake_resource_evidence(
        actual_worktree: Path,
        project_name: str,
        published_ports: dict[str, int],
        **kwargs: Any,
    ) -> live_stand.ComposeResourceEvidence:
        nonlocal evidence_calls
        evidence_calls += 1
        # Existing-owner preflight is call 1; the first bind after PrepareOnly
        # is call 2. Simulate resolution failure at that precise boundary.
        if failure_stage == "resource-bind" and evidence_calls == 2:
            raise live_stand.StandError("simulated resource registration failure")
        return original_resource_evidence(
            actual_worktree, project_name, published_ports, **kwargs
        )

    monkeypatch.setattr(
        live_stand, "_compose_resource_evidence", fake_resource_evidence
    )
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: "a" * 40)
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: ports)
    monkeypatch.setattr(live_stand, "require_free_ports", lambda *_args: None)
    monkeypatch.setattr(live_stand, "ensure_worktree", lambda _sha: worktree)
    monkeypatch.setattr(live_stand, "_assert_worktree_clean", lambda _worktree: None)
    monkeypatch.setattr(
        live_stand,
        "load_or_create_vapid",
        lambda _worktree: {"public": "pub", "private": "priv"},
    )
    monkeypatch.setattr(live_stand.shutil, "which", lambda _name: "pwsh")

    prepare_attempts = 0
    starts: list[list[str]] = []

    def fake_run(
        command: list[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> None:
        nonlocal prepare_attempts
        assert cwd == worktree
        assert env is not None
        if "-PrepareOnly" in command:
            prepare_attempts += 1
            if failure_stage == "prepare" and prepare_attempts == 1:
                raise subprocess.CalledProcessError(1, command)
            return
        if command[-1] == "stop":
            return
        starts.append(command)

    monkeypatch.setattr(live_stand, "_run", fake_run)

    if failure_stage == "prepare":
        with pytest.raises(subprocess.CalledProcessError):
            live_stand._up_locked("HEAD")
    else:
        with pytest.raises(
            live_stand.StandError, match="simulated resource registration failure"
        ):
            live_stand._up_locked("HEAD")
    incomplete = live_stand.load_stand_owner(worktree)
    assert incomplete.schema_version == live_stand.OWNER_SCHEMA_VERSION
    assert incomplete.compose_resource_fingerprint is None
    assert incomplete.resume_compose_resource_fingerprint is not None

    live_stand._up_locked("HEAD")

    assert prepare_attempts == 2
    assert len(starts) == 1
    assert "-AllowExistingOwnedVolumes" in starts[0]
    completed = live_stand.load_stand_owner(worktree)
    assert completed.compose_resource_fingerprint is not None
    assert completed.resume_compose_resource_fingerprint is None
