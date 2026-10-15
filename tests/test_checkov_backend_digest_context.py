"""Focused Checkov image-digest context and OCI resolver contracts."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
sys.path.insert(0, str(ROOT / "scripts" / "quality"))
from resolve_oci_platform_digest import (
    InvalidImageArchive,
    main,
    render_checkov_values,
    resolve_linux_amd64_manifest_digest,
)

OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
OCI_CONFIG = "application/vnd.oci.image.config.v1+json"


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _descriptor(media_type: str, raw: bytes) -> dict[str, Any]:
    return {"mediaType": media_type, "digest": _digest(raw), "size": len(raw)}


def _oci_archive(
    path: Path,
    *,
    index_count: int = 1,
    os_name: str = "linux",
    architecture: str = "amd64",
    config_os: str = "linux",
    corrupt_manifest: bool = False,
    duplicate_index: bool = False,
) -> str:
    config_raw = json.dumps(
        {"architecture": "amd64", "os": config_os}, separators=(",", ":")
    ).encode()
    manifest = {
        "schemaVersion": 2,
        "mediaType": OCI_MANIFEST,
        "config": _descriptor(OCI_CONFIG, config_raw),
        "layers": [],
    }
    manifest_raw = json.dumps(manifest, separators=(",", ":")).encode()
    manifest_digest = _digest(manifest_raw)
    stored_manifest = manifest_raw + (b" " if corrupt_manifest else b"")
    descriptor = {
        **_descriptor(OCI_MANIFEST, manifest_raw),
        "platform": {"os": os_name, "architecture": architecture},
    }
    index = {
        "schemaVersion": 2,
        "mediaType": OCI_INDEX,
        "manifests": [descriptor] * index_count,
    }
    entries = {
        "oci-layout": json.dumps({"imageLayoutVersion": "1.0.0"}).encode(),
        "index.json": json.dumps(index, separators=(",", ":")).encode(),
        f"blobs/sha256/{hashlib.sha256(config_raw).hexdigest()}": config_raw,
        f"blobs/sha256/{hashlib.sha256(manifest_raw).hexdigest()}": stored_manifest,
    }
    with tarfile.open(path, mode="w") as archive:
        for name, raw in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(raw))
        if duplicate_index:
            member = tarfile.TarInfo("index.json")
            raw = entries["index.json"]
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    return manifest_digest


def test_resolver_returns_only_a_content_verified_linux_amd64_manifest(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "valid.oci.tar"
    expected = _oci_archive(archive)

    assert resolve_linux_amd64_manifest_digest(archive) == expected
    assert render_checkov_values(expected) == (
        f'global:\n  backendImageDigest: "{expected}"\n'
    )


@pytest.mark.parametrize(
    "archive_options",
    [
        {"index_count": 2},
        {"os_name": "windows"},
        {"architecture": "arm64"},
        {"config_os": "windows"},
        {"corrupt_manifest": True},
        {"duplicate_index": True},
    ],
)
def test_resolver_rejects_ambiguous_or_unverified_oci_layouts(
    tmp_path: Path, archive_options: dict[str, Any]
) -> None:
    archive = tmp_path / "invalid.oci.tar"
    _oci_archive(archive, **archive_options)

    with pytest.raises(InvalidImageArchive):
        resolve_linux_amd64_manifest_digest(archive)


def test_resolver_cli_fails_without_emitting_values_for_bad_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = tmp_path / "invalid.oci.tar"
    _oci_archive(archive, index_count=2)

    assert main([str(archive)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: backend OCI archive")


def test_checkov_workflow_uses_local_oci_context_for_the_full_scan() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "checkov.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["checkov"]
    steps = job["steps"]
    setup = next(
        step
        for step in steps
        if step.get("name") == "Set up Buildx for local OCI exports"
    )
    build = next(
        step
        for step in steps
        if step.get("name")
        == "Build the five chart image manifests as unpublished OCI archives"
    )
    resolve = next(
        step
        for step in steps
        if step.get("name") == "Resolve each local OCI platform manifest"
    )
    scan = next(step for step in steps if step.get("id") == "checkov_all")
    cleanup = next(
        step
        for step in steps
        if step.get("name") == "Remove local OCI and Helm scan inputs"
    )

    assert (
        setup["uses"]
        == "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069"
    )
    for component, dockerfile in (
        ("backend", "backend.Dockerfile"),
        ("frontend", "frontend.Dockerfile"),
        ("gateway", "services/gateway/Dockerfile"),
        ("ws-hub", "services/ws-hub/Dockerfile"),
        ("file-processor", "services/file-processor/Dockerfile"),
    ):
        assert f"build_local_oci {component} {dockerfile}" in build["run"]
    assert 'oci_dir="$RUNNER_TEMP/checkov-oci"' in build["run"]
    assert 'archive="$oci_dir/$image_name.oci.tar"' in build["run"]
    assert "--platform linux/amd64" in build["run"]
    assert "--provenance=false" in build["run"]
    assert "--sbom=false" in build["run"]
    assert '--output "type=oci,dest=$archive"' in build["run"]
    assert "docker push" not in build["run"]
    assert "python3 scripts/quality/resolve_oci_platform_digest.py" in resolve["run"]
    assert '"$oci_dir/$image_name.oci.tar"' in resolve["run"]
    assert 'cp -- "$oci_dir/backend.values.yaml"' in resolve["run"]
    assert '"$GITHUB_WORKSPACE/.checkov-backend-values.yaml"' in resolve["run"]
    assert scan["with"]["directory"] == "."
    assert scan["with"]["framework"] == "all"
    assert scan["with"]["var_file"] == ".checkov-backend-values.yaml"
    assert scan["with"]["output_format"] == "sarif"
    assert scan["with"]["output_file_path"] == "results.sarif,"
    assert job["timeout-minutes"] == 60
    assert cleanup["if"] == "always()"
    assert '"$GITHUB_WORKSPACE/.checkov-backend-values.yaml"' in cleanup["run"]
    assert '"$RUNNER_TEMP/checkov-oci"' in cleanup["run"]


def test_global_backend_digest_is_optional_and_schema_bounded() -> None:
    parent = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    revocation = json.loads(
        (ROOT / "charts" / "revocation-store" / "values.schema.json").read_text(
            encoding="utf-8"
        )
    )
    with tarfile.open(CHART / "charts" / "redis-0.1.0.tgz", mode="r:gz") as archive:
        child = json.loads(
            archive.extractfile("redis/values.schema.json").read().decode("utf-8")
        )
        child_helper = (
            archive.extractfile("redis/templates/_helpers.tpl").read().decode("utf-8")
        )

    schemas = (
        parent["properties"]["global"],
        parent["properties"]["nats"]["properties"]["global"],
        child["properties"]["global"],
        revocation["properties"]["global"],
    )
    for schema in schemas:
        prop = schema["properties"]["backendImageDigest"]
        assert prop == {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
        assert "backendImageDigest" not in schema.get("required", [])
    assert 'eq $image.repository "university-backend"' in child_helper
    assert "$global.backendImageDigest" in child_helper


def _rendered_backend_and_init_images(*extra: str) -> tuple[int, str, str]:
    from tests.test_helm_staging_contract import _existing_secret_command

    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("development", *extra),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return result.returncode, result.stderr, ""
    resources = [item for item in yaml.safe_load_all(result.stdout) if item]
    backend = next(
        container["image"]
        for item in resources
        if item.get("kind") == "Deployment"
        for container in item["spec"]["template"]["spec"]["containers"]
        if container.get("name") == "backend"
    )
    init = next(
        container["image"]
        for item in resources
        if item.get("kind") == "StatefulSet"
        for container in item["spec"]["template"]["spec"].get("initContainers", [])
        if container.get("name") == "redis-exporter-password-file"
    )
    return result.returncode, backend, init


_BACKEND_IMAGE_CLEAR = (
    "--set-string",
    "backend.image.repository=university-backend",
    "--set-string",
    "backend.image.digest=",
    "--set-string",
    "backend.image.tag=",
    "--set-string",
    "redis.metrics.passwordFileInitImage.repository=university-backend",
    "--set-string",
    "redis.metrics.passwordFileInitImage.digest=",
    "--set-string",
    "redis.metrics.passwordFileInitImage.tag=",
)


def test_rendered_backend_and_child_keep_default_and_global_tag_precedence() -> None:
    code, backend, init = _rendered_backend_and_init_images(
        *_BACKEND_IMAGE_CLEAR, "--set-string", "global.imageTag="
    )
    assert code == 0, backend
    assert backend == init == "university-backend:1.0.0"

    code, backend, init = _rendered_backend_and_init_images(
        *_BACKEND_IMAGE_CLEAR, "--set-string", "global.imageTag=contract-sha"
    )
    assert code == 0, backend
    assert backend == init == "university-backend:contract-sha"


def test_rendered_global_digest_fallback_and_component_digest_precedence() -> None:
    global_digest = _digest(b"synthetic global image manifest")
    component_digest = _digest(b"synthetic component image manifest")
    code, backend, init = _rendered_backend_and_init_images(
        *_BACKEND_IMAGE_CLEAR,
        "--set-string",
        "global.imageRegistry=registry.example.invalid",
        "--set-string",
        f"global.backendImageDigest={global_digest}",
    )
    expected_global = f"registry.example.invalid/university-backend@{global_digest}"
    assert code == 0, backend
    assert backend == init == expected_global

    code, backend, init = _rendered_backend_and_init_images(
        *_BACKEND_IMAGE_CLEAR,
        "--set-string",
        f"global.backendImageDigest={global_digest}",
        "--set-string",
        f"backend.image.digest={component_digest}",
        "--set-string",
        f"redis.metrics.passwordFileInitImage.digest={component_digest}",
    )
    expected_component = f"university-backend@{component_digest}"
    assert code == 0, backend
    assert backend == init == expected_component


def test_global_digest_does_not_rewrite_qualified_repositories_or_hide_mismatch() -> (
    None
):
    global_digest = _digest(b"synthetic global image manifest")
    qualified = (
        "--set-string",
        "backend.image.repository=ghcr.io/acme/university-backend",
        "--set-string",
        "backend.image.digest=",
        "--set-string",
        "backend.image.tag=",
        "--set-string",
        "redis.metrics.passwordFileInitImage.repository=ghcr.io/acme/university-backend",
        "--set-string",
        "redis.metrics.passwordFileInitImage.digest=",
        "--set-string",
        "redis.metrics.passwordFileInitImage.tag=",
        "--set-string",
        f"global.backendImageDigest={global_digest}",
        "--set-string",
        "global.imageTag=contract-sha",
    )
    code, backend, init = _rendered_backend_and_init_images(*qualified)
    assert code == 0, backend
    assert backend == init == "ghcr.io/acme/university-backend:contract-sha"

    mismatched = (
        *_BACKEND_IMAGE_CLEAR,
        "--set-string",
        f"global.backendImageDigest={global_digest}",
        "--set-string",
        f"redis.metrics.passwordFileInitImage.digest={_digest(b'mismatched component')}",
    )
    code, stderr, _ = _rendered_backend_and_init_images(*mismatched)
    assert code != 0
    assert (
        "redis.metrics.passwordFileInitImage must resolve exactly to backend.image"
        in stderr
    )
