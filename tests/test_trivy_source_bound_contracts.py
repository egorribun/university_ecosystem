"""Contracts for source-bound Trivy Helm profile generation."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "quality"))
sys.path.insert(0, str(ROOT / "tests"))

import resolve_oci_platform_digest
from create_checkov_oci_image_evidence import REVISION_LABEL, SOURCE_LABEL
from prepare_trivy_backend_values import InvalidTrivyImageEvidence, prepare_profiles
from test_checkov_backend_digest_context import _oci_archive

REPOSITORY = "example/university"
SOURCE_SHA = hashlib.sha256(b"source-bound Trivy profile fixture").hexdigest()[:40]
SOURCE_LABEL_VALUE = f"https://github.com/{REPOSITORY}"
IMAGE_REPOSITORY = f"ghcr.io/{REPOSITORY}/backend"
PROFILE_KEYS = {
    "evidence",
    "revocation_values",
    "revocation_config",
    "university_values",
    "university_config",
    "redis_compat_values",
    "redis_compat_config",
}
PROFILE_INPUTS = {
    "revocation": (
        "security/trivy-revocation-config.yaml",
        "security/trivy-revocation-values.yaml",
    ),
    "university": (
        "security/trivy-university-chart-config.yaml",
        "security/trivy-university-values.yaml",
    ),
    "redis-compat": (
        "security/trivy-redis-compat-config.yaml",
        "security/trivy-redis-compat-values.yaml",
    ),
}


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _descriptor(media_type: str, raw: bytes) -> dict[str, Any]:
    return {
        "mediaType": media_type,
        "digest": f"sha256:{_digest(raw)}",
        "size": len(raw),
    }


def _read_tar_entries(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, mode="r:*") as archive:
        entries: dict[str, bytes] = {}
        for member in archive:
            stream = archive.extractfile(member)
            if stream is None:
                raise AssertionError("OCI fixture entries must be regular files")
            entries[member.name] = stream.read()
    return entries


def _write_tar_entries(path: Path, entries: dict[str, bytes]) -> None:
    temporary = path.with_suffix(".rewritten.oci.tar")
    with tarfile.open(temporary, mode="w") as archive:
        for name, raw in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(raw))
    temporary.replace(path)


def _archive_with_labels(
    path: Path,
    *,
    source: str | None = SOURCE_LABEL_VALUE,
    revision: str | None = SOURCE_SHA,
    platform_os: str = "linux",
    architecture: str = "amd64",
    config_os: str = "linux",
) -> None:
    _oci_archive(
        path,
        os_name=platform_os,
        architecture=architecture,
        config_os=config_os,
    )
    entries = _read_tar_entries(path)
    index = json.loads(entries["index.json"])
    manifest_descriptor = index["manifests"][0]
    manifest_name = f"blobs/sha256/{manifest_descriptor['digest'].split(':', 1)[1]}"
    manifest = json.loads(entries[manifest_name])
    config_descriptor = manifest["config"]
    config_name = f"blobs/sha256/{config_descriptor['digest'].split(':', 1)[1]}"
    config = json.loads(entries.pop(config_name))
    labels: dict[str, str] = {}
    if source is not None:
        labels[SOURCE_LABEL] = source
    if revision is not None:
        labels[REVISION_LABEL] = revision
    config["config"] = {"Labels": labels}
    config_raw = json.dumps(config, separators=(",", ":")).encode("utf-8")
    manifest["config"] = _descriptor(
        resolve_oci_platform_digest.OCI_CONFIG_MEDIA_TYPE, config_raw
    )
    entries[f"blobs/sha256/{_digest(config_raw)}"] = config_raw
    manifest_raw = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    entries.pop(manifest_name)
    manifest_descriptor.update(
        _descriptor(resolve_oci_platform_digest.OCI_MANIFEST_MEDIA_TYPE, manifest_raw)
    )
    entries[f"blobs/sha256/{_digest(manifest_raw)}"] = manifest_raw
    entries["index.json"] = json.dumps(index, separators=(",", ":")).encode("utf-8")
    _write_tar_entries(path, entries)


def _tamper_config_digest(path: Path) -> None:
    entries = _read_tar_entries(path)
    index = json.loads(entries["index.json"])
    manifest_descriptor = index["manifests"][0]
    manifest_name = f"blobs/sha256/{manifest_descriptor['digest'].split(':', 1)[1]}"
    manifest = json.loads(entries.pop(manifest_name))
    claimed_digest = _digest(b"expected config bytes")
    actual_bytes = b"present config bytes with a different digest"
    manifest["config"]["digest"] = f"sha256:{claimed_digest}"
    manifest["config"]["size"] = len(actual_bytes)
    entries[f"blobs/sha256/{claimed_digest}"] = actual_bytes
    manifest_raw = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_descriptor.update(
        _descriptor(resolve_oci_platform_digest.OCI_MANIFEST_MEDIA_TYPE, manifest_raw)
    )
    entries[f"blobs/sha256/{_digest(manifest_raw)}"] = manifest_raw
    entries["index.json"] = json.dumps(index, separators=(",", ":")).encode("utf-8")
    _write_tar_entries(path, entries)


def _remove_config_digest(path: Path) -> None:
    entries = _read_tar_entries(path)
    index = json.loads(entries["index.json"])
    manifest_descriptor = index["manifests"][0]
    manifest_name = f"blobs/sha256/{manifest_descriptor['digest'].split(':', 1)[1]}"
    manifest = json.loads(entries.pop(manifest_name))
    manifest["config"].pop("digest")
    manifest_raw = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_descriptor.update(
        _descriptor(resolve_oci_platform_digest.OCI_MANIFEST_MEDIA_TYPE, manifest_raw)
    )
    entries[f"blobs/sha256/{_digest(manifest_raw)}"] = manifest_raw
    entries["index.json"] = json.dumps(index, separators=(",", ":")).encode("utf-8")
    _write_tar_entries(path, entries)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _profile_repository(root: Path) -> Path:
    for config_relative, values_relative in PROFILE_INPUTS.values():
        config_path = root / config_relative
        values_path = root / values_relative
        config_path.parent.mkdir(parents=True, exist_ok=True)
        values_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "misconfiguration": {
                        "scanners": ["helm"],
                        "helm": {"values": [values_relative]},
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        values_path.write_text("{}\n", encoding="utf-8")
    return root


def test_prepare_profiles_binds_only_chart_values_to_verified_backend(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "backend.oci.tar"
    _archive_with_labels(archive)
    output_dir = tmp_path / "trivy-inputs"

    profiles = prepare_profiles(
        archive,
        REPOSITORY,
        SOURCE_SHA,
        output_dir,
        repository_root=_profile_repository(tmp_path / "repository"),
    )

    assert set(profiles) == PROFILE_KEYS
    assert profiles["evidence"] == output_dir / "backend-evidence.json"
    assert profiles["revocation_values"].name == "revocation-values.json"
    assert profiles["university_values"].name == "university-values.json"
    assert profiles["redis_compat_values"].name == "redis-compat-values.json"
    assert profiles["revocation_config"].name == "trivy-revocation-config.json"
    assert profiles["university_config"].name == "trivy-university-config.json"
    assert profiles["redis_compat_config"].name == "trivy-redis-compat-config.json"

    evidence = _load_json(profiles["evidence"])
    manifest_digest = evidence["manifest_digest"]
    assert evidence["repository"] == REPOSITORY
    assert evidence["source_sha"] == SOURCE_SHA
    assert (
        evidence["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    assert evidence["source_label"] == SOURCE_LABEL_VALUE
    assert evidence["revision_label"] == SOURCE_SHA
    assert (
        manifest_digest
        == resolve_oci_platform_digest.resolve_linux_amd64_manifest_digest(archive)
    )

    revocation = _load_json(profiles["revocation_values"])
    university = _load_json(profiles["university_values"])
    redis_compat = _load_json(profiles["redis_compat_values"])

    expected_image = {"repository": IMAGE_REPOSITORY, "digest": manifest_digest}
    assert set(revocation) == {"global", "redis"}
    assert revocation["global"] == {
        "backendImageRepository": IMAGE_REPOSITORY,
        "backendImageDigest": manifest_digest,
    }
    assert revocation["redis"]["metrics"]["passwordFileInitImage"] == {
        "repository": IMAGE_REPOSITORY,
        "tag": "",
        "digest": manifest_digest,
        "pullPolicy": "Always",
    }

    assert set(university) == {"global", "backend", "outboxWorker", "redis"}
    assert university["global"] == {"backendImageDigest": manifest_digest}
    assert university["backend"]["image"] == expected_image
    assert university["outboxWorker"]["image"] == expected_image
    assert university["redis"]["metrics"]["passwordFileInitImage"] == expected_image

    assert set(redis_compat) == {"global", "metrics"}
    assert redis_compat["global"] == {"backendImageDigest": manifest_digest}
    assert redis_compat["metrics"]["passwordFileInitImage"] == {
        "repository": IMAGE_REPOSITORY,
        "tag": "",
        "digest": manifest_digest,
        "pullPolicy": "Always",
    }
    assert "environment" not in revocation["global"]
    assert "environment" not in redis_compat["global"]

    expected_configs = {
        "revocation_config": (
            "security/trivy-revocation-values.yaml",
            "revocation-values.json",
        ),
        "university_config": (
            "security/trivy-university-values.yaml",
            "university-values.json",
        ),
        "redis_compat_config": (
            "security/trivy-redis-compat-values.yaml",
            "redis-compat-values.json",
        ),
    }
    dynamic_paths: set[Path] = set()
    for key, (base_values, generated_name) in expected_configs.items():
        config = _load_json(profiles[key])
        assert config["misconfiguration"]["scanners"] == ["helm"]
        value_paths = config["misconfiguration"]["helm"]["values"]
        assert value_paths[0].replace("\\", "/") == base_values
        generated_path = Path(value_paths[1]).resolve()
        assert generated_path == (output_dir / generated_name).resolve()
        assert generated_path not in dynamic_paths
        dynamic_paths.add(generated_path)
    assert dynamic_paths == {
        profiles["revocation_values"].resolve(),
        profiles["university_values"].resolve(),
        profiles["redis_compat_values"].resolve(),
    }


@pytest.mark.parametrize(
    (
        "case",
        "source",
        "revision",
        "repository",
        "platform_os",
        "architecture",
        "config_os",
    ),
    [
        ("missing-source", None, SOURCE_SHA, REPOSITORY, "linux", "amd64", "linux"),
        (
            "wrong-source",
            "https://example.invalid/other",
            SOURCE_SHA,
            REPOSITORY,
            "linux",
            "amd64",
            "linux",
        ),
        (
            "missing-revision",
            SOURCE_LABEL_VALUE,
            None,
            REPOSITORY,
            "linux",
            "amd64",
            "linux",
        ),
        (
            "wrong-revision",
            SOURCE_LABEL_VALUE,
            hashlib.sha256(b"other revision").hexdigest()[:40],
            REPOSITORY,
            "linux",
            "amd64",
            "linux",
        ),
        (
            "wrong-repository",
            SOURCE_LABEL_VALUE,
            SOURCE_SHA,
            "other/repository",
            "linux",
            "amd64",
            "linux",
        ),
        (
            "wrong-platform-os",
            SOURCE_LABEL_VALUE,
            SOURCE_SHA,
            REPOSITORY,
            "windows",
            "amd64",
            "linux",
        ),
        (
            "wrong-platform-architecture",
            SOURCE_LABEL_VALUE,
            SOURCE_SHA,
            REPOSITORY,
            "linux",
            "arm64",
            "linux",
        ),
        (
            "wrong-config-os",
            SOURCE_LABEL_VALUE,
            SOURCE_SHA,
            REPOSITORY,
            "linux",
            "amd64",
            "windows",
        ),
    ],
)
def test_prepare_profiles_rejects_unbound_or_unsupported_archives_without_outputs(
    tmp_path: Path,
    case: str,
    source: str | None,
    revision: str | None,
    repository: str,
    platform_os: str,
    architecture: str,
    config_os: str,
) -> None:
    archive = tmp_path / "backend.oci.tar"
    _archive_with_labels(
        archive,
        source=source,
        revision=revision,
        platform_os=platform_os,
        architecture=architecture,
        config_os=config_os,
    )
    output_dir = tmp_path / "trivy-inputs"

    with pytest.raises(
        (InvalidTrivyImageEvidence, resolve_oci_platform_digest.InvalidImageArchive)
    ):
        prepare_profiles(
            archive,
            repository,
            SOURCE_SHA,
            output_dir,
            repository_root=_profile_repository(tmp_path / "repository"),
        )

    assert not output_dir.exists(), case


def test_prepare_profiles_rejects_missing_archive_without_outputs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "trivy-inputs"
    with pytest.raises(InvalidTrivyImageEvidence):
        prepare_profiles(
            tmp_path / "backend.oci.tar",
            REPOSITORY,
            SOURCE_SHA,
            output_dir,
            repository_root=_profile_repository(tmp_path / "repository"),
        )
    assert not output_dir.exists()


def test_prepare_profiles_rejects_mismatched_config_digest_without_outputs(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "backend.oci.tar"
    _archive_with_labels(archive)
    _tamper_config_digest(archive)
    output_dir = tmp_path / "trivy-inputs"

    with pytest.raises(
        (InvalidTrivyImageEvidence, resolve_oci_platform_digest.InvalidImageArchive)
    ):
        prepare_profiles(
            archive,
            REPOSITORY,
            SOURCE_SHA,
            output_dir,
            repository_root=_profile_repository(tmp_path / "repository"),
        )

    assert not output_dir.exists()


def test_prepare_profiles_rejects_missing_config_digest_without_outputs(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "backend.oci.tar"
    _archive_with_labels(archive)
    _remove_config_digest(archive)
    output_dir = tmp_path / "trivy-inputs"

    with pytest.raises(InvalidTrivyImageEvidence):
        prepare_profiles(
            archive,
            REPOSITORY,
            SOURCE_SHA,
            output_dir,
            repository_root=_profile_repository(tmp_path / "repository"),
        )

    assert not output_dir.exists()


def test_prepare_profiles_rejects_broad_or_cross_chart_config_without_outputs(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "backend.oci.tar"
    _archive_with_labels(archive)
    repository_root = _profile_repository(tmp_path / "repository")
    config_path = repository_root / PROFILE_INPUTS["university"][0]
    config_path.write_text(
        json.dumps(
            {
                "misconfiguration": {
                    "scanners": ["helm", "kubernetes"],
                    "helm": {
                        "values": [PROFILE_INPUTS["revocation"][1]],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "trivy-inputs"

    with pytest.raises(InvalidTrivyImageEvidence):
        prepare_profiles(
            archive,
            REPOSITORY,
            SOURCE_SHA,
            output_dir,
            repository_root=repository_root,
        )

    assert not output_dir.exists()


def test_prepare_profiles_rejects_invalid_source_sha_and_existing_output(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "backend.oci.tar"
    _archive_with_labels(archive)
    repository_root = _profile_repository(tmp_path / "repository")
    output_dir = tmp_path / "trivy-inputs"

    with pytest.raises(InvalidTrivyImageEvidence):
        prepare_profiles(
            archive,
            REPOSITORY,
            "not-a-commit-sha",
            output_dir,
            repository_root=repository_root,
        )
    assert not output_dir.exists()

    output_dir.mkdir()
    (output_dir / "caller-owned.txt").write_text("preserve\n", encoding="utf-8")
    with pytest.raises(InvalidTrivyImageEvidence):
        prepare_profiles(
            archive,
            REPOSITORY,
            SOURCE_SHA,
            output_dir,
            repository_root=repository_root,
        )
    assert sorted(path.name for path in output_dir.iterdir()) == ["caller-owned.txt"]
