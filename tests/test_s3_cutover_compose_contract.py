"""SeaweedFS is the only S3 storage in every runnable Compose file (ADR-042).

MinIO stopped publishing its images, so no root Compose file may reference
them. The ``minio`` service name stays: backend, Caddy and file-processor
reach storage at ``minio:9000``. The storage volume is project-scoped, and the
legacy MinIO volumes are never declared, so
Compose can neither mount nor delete them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE_FILES = ("docker-compose.yml", "docker-compose.full.yml")
SEAWEEDFS_IMAGE = re.compile(
    r"^ghcr\.io/chrislusf/seaweedfs:4\.47@sha256:[0-9a-f]{64}$"
)
STORAGE_VOLUME = "university_ecosystem_seaweedfs_data"
LEGACY_VOLUME_KEYS = {"minio_data", "minio-data"}
_REQUIRED_VARIABLE = re.compile(r"\$\{([A-Z0-9_]+):\?")


def _compose(relative_path: str) -> dict[str, Any]:
    # Compose merge tags are meaningful to Docker Compose, not to PyYAML.
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    return yaml.safe_load(source.replace("!override", "").replace("!reset", ""))


def _root_compose_files() -> list[Path]:
    files = sorted(ROOT.glob("docker-compose*.yml"))
    return [path for path in files if path.name != "docker-compose.override.yml"]


def test_no_root_compose_file_references_a_minio_image() -> None:
    offenders = []
    for path in _root_compose_files():
        for service_name, service in (
            yaml.safe_load(
                path.read_text(encoding="utf-8")
                .replace("!override", "")
                .replace("!reset", "")
            ).get("services")
            or {}
        ).items():
            image = str((service or {}).get("image", ""))
            if "minio/minio" in image or "minio/mc" in image:
                offenders.append(f"{path.name}:{service_name}:{image}")
        if "quay.io/minio" in path.read_text(encoding="utf-8"):
            offenders.append(f"{path.name}: quay.io/minio")
    assert offenders == []


def test_the_opt_in_cutover_overlay_is_gone() -> None:
    assert not (ROOT / "docker-compose.seaweedfs-cutover.yml").exists()


def test_every_seaweedfs_reference_uses_one_pinned_digest() -> None:
    images = {
        image
        for path in _root_compose_files()
        for image in re.findall(
            r"ghcr\.io/chrislusf/seaweedfs:[^\s\"']+", path.read_text(encoding="utf-8")
        )
    }
    assert len(images) == 1, images
    assert SEAWEEDFS_IMAGE.match(images.pop())


@pytest.mark.parametrize("relative_path", BASE_FILES)
def test_base_storage_runs_seaweedfs_under_the_minio_service_name(
    relative_path: str,
) -> None:
    compose = _compose(relative_path)
    storage = compose["services"]["minio"]

    assert SEAWEEDFS_IMAGE.match(storage["image"])
    assert storage["command"] == ["mini", "-dir=/data", "-s3.port=9000"]
    environment = storage["environment"]
    assert set(environment) == {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_BUCKET",
    }
    assert environment["AWS_ACCESS_KEY_ID"].startswith("${MINIO_ROOT_USER")
    assert environment["AWS_SECRET_ACCESS_KEY"].startswith("${MINIO_ROOT_PASSWORD:?")
    assert environment["S3_BUCKET"] == "uploads"
    assert storage["volumes"] == ["seaweedfs_data:/data"]
    # SeaweedFS mini has no console; the S3 API stays on Compose networks.
    assert "ports" not in storage
    assert storage.get("expose", []) == ["9000"]
    assert storage["healthcheck"]["test"] == [
        "CMD",
        "wget",
        "-qO-",
        "http://localhost:9000/status",
    ]
    memory = storage["deploy"]["resources"]["limits"]["memory"]
    assert memory.endswith("M") and int(memory[:-1]) >= 256


@pytest.mark.parametrize("relative_path", BASE_FILES)
def test_base_storage_volume_is_project_scoped_and_drops_legacy_volumes(
    relative_path: str,
) -> None:
    volumes = _compose(relative_path)["volumes"]

    assert volumes["seaweedfs_data"] is None
    assert _compose(relative_path)["name"] == "university_ecosystem"
    assert LEGACY_VOLUME_KEYS.isdisjoint(volumes)
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    assert "minio_data:" not in source
    assert "minio-data:" not in source


@pytest.mark.parametrize("relative_path", BASE_FILES)
def test_storage_init_waits_for_the_s3_api_without_mc(relative_path: str) -> None:
    services = _compose(relative_path)["services"]
    init = services["minio-init"]

    assert init["image"] == services["minio"]["image"]
    assert init["entrypoint"] == ["/bin/sh", "-ec"]
    assert init["command"] == ["wget -qO- http://minio:9000/status >/dev/null"]
    assert init["depends_on"]["minio"]["condition"] == "service_healthy"
    assert "environment" not in init
    assert init["tmpfs"] == ["/data"]
    assert init["read_only"] is True
    assert init["cap_drop"] == ["ALL"]
    assert init["security_opt"] == ["no-new-privileges:true"]
    assert init["restart"] == "no"


def test_storage_overlays_use_expected_loopback_publications() -> None:
    observability = _compose("docker-compose.observability.yml")["services"]
    assert "minio" not in observability
    infra_ports = _compose("docker-compose.infra.yml")["services"]["minio"]["ports"]
    assert infra_ports == ["127.0.0.1:9000:9000"]
    live = _compose("docker-compose.live.yml")["services"]
    assert live["minio"]["ports"] == [
        "127.0.0.1:${LIVE_HOST_PORT_MINIO:?set by scripts/live_stand.py}:9000"
    ]
    assert "minio-init" not in live


def test_prometheus_has_no_minio_metrics_job() -> None:
    config = yaml.safe_load(
        (ROOT / "infrastructure/observability/prometheus.yml").read_text(
            encoding="utf-8"
        )
    )
    jobs = {job["job_name"] for job in config["scrape_configs"]}
    assert "minio" not in jobs
    assert "/minio/v2/metrics" not in json.dumps(config)


def _docker_compose() -> str:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip(  # QUALITY-123 @egorribun — Docker capability varies by runner
            "Docker CLI is not installed"
        )
    probe = subprocess.run(  # noqa: S603 - fixed local CLI
        [docker, "compose", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip(  # QUALITY-123 @egorribun — Compose plugin capability varies by runner
            "Docker Compose plugin is not available"
        )
    return docker


def _rendered(tmp_path: Path, project: str | None, *files: str) -> dict[str, Any]:
    """Render the real model with placeholder secrets in an isolated copy."""

    docker = _docker_compose()
    for path in _root_compose_files():
        shutil.copyfile(path, tmp_path / path.name)
    for env_file in (".env.docker", ".env.docker.workers"):
        (tmp_path / env_file).write_text("", encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COMPOSE_")
    }
    for path in _root_compose_files():
        for name in _REQUIRED_VARIABLE.findall(path.read_text(encoding="utf-8")):
            env[name] = "placeholder-value"
    live_port_names = sorted(
        {
            name
            for path in _root_compose_files()
            for name in re.findall(
                r"\$\{(LIVE_HOST_PORT_[A-Z_]+|LIVE_MAILPIT_PORT):\?",
                path.read_text(encoding="utf-8"),
            )
        }
    )
    for index, name in enumerate(live_port_names):
        env[name] = str(24000 + index)
    command = [docker, "compose"]
    if project is not None:
        command += ["-p", project]
    for name in files:
        command += ["-f", name]
    result = subprocess.run(  # noqa: S603 - fixed local CLI and repository files
        [*command, "config", "--format", "json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "files",
    [
        ("docker-compose.yml",),
        ("docker-compose.yml", "docker-compose.observability.yml"),
        ("docker-compose.yml", "docker-compose.infra.yml"),
        ("docker-compose.full.yml",),
    ],
)
def test_rendered_stacks_mount_the_named_seaweedfs_volume(
    tmp_path: Path, files: tuple[str, ...]
) -> None:
    model = _rendered(tmp_path, "university_ecosystem", *files)

    storage = model["services"]["minio"]
    assert SEAWEEDFS_IMAGE.match(storage["image"])
    assert [mount["source"] for mount in storage["volumes"]] == ["seaweedfs_data"]
    assert model["volumes"]["seaweedfs_data"]["name"] == STORAGE_VOLUME
    assert LEGACY_VOLUME_KEYS.isdisjoint(model["volumes"])
    assert not any(
        "minio/" in str(service.get("image", ""))
        for service in model["services"].values()
    )


def test_live_stand_storage_volume_is_project_scoped(tmp_path: Path) -> None:
    # Each Compose project owns its storage volume without a global name.
    project_name = "ue-live-0123456789abcdef"
    plain = _rendered(tmp_path, project_name, "docker-compose.full.yml")
    live = _rendered(
        tmp_path, project_name, "docker-compose.full.yml", "docker-compose.live.yml"
    )

    expected_volume = f"{project_name}_seaweedfs_data"
    assert plain["volumes"]["seaweedfs_data"]["name"] == expected_volume
    assert live["volumes"]["seaweedfs_data"]["name"] == expected_volume
    assert live["services"]["minio"]["image"] == plain["services"]["minio"]["image"]


def test_default_and_custom_project_storage_names_are_exact(tmp_path: Path) -> None:
    default = _rendered(tmp_path, None, "docker-compose.full.yml")
    custom = _rendered(tmp_path, "review", "docker-compose.full.yml")

    assert default["name"] == "university_ecosystem"
    assert default["volumes"]["seaweedfs_data"]["name"] == STORAGE_VOLUME
    assert custom["name"] == "review"
    assert custom["volumes"]["seaweedfs_data"]["name"] == "review_seaweedfs_data"
