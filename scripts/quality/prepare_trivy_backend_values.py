"""Prepare source-bound, chart-specific Trivy Helm inputs from a local backend OCI archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
_script_directory_added = str(SCRIPT_DIRECTORY) not in sys.path
if _script_directory_added:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))
try:
    import create_checkov_oci_image_evidence as checkov_evidence
finally:
    if _script_directory_added:
        sys.path.remove(str(SCRIPT_DIRECTORY))

REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", re.ASCII)
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.ASCII)
PROFILES = {
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


class InvalidTrivyImageEvidence(ValueError):
    """The backend archive or chart profile inputs are missing or inconsistent."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidTrivyImageEvidence("duplicate JSON key")
        result[key] = value
    return result


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise InvalidTrivyImageEvidence(f"{label} must be a regular non-symlink file")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_profile_config(
    repository_root: Path, name: str
) -> tuple[str, dict[str, Any]]:
    config_relative, values_relative = PROFILES[name]
    config_path = repository_root / config_relative
    values_path = repository_root / values_relative
    _regular_file(config_path, f"{name} Trivy config")
    _regular_file(values_path, f"{name} values")
    try:
        value = json.loads(
            config_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InvalidTrivyImageEvidence(f"{name} Trivy config is invalid") from error
    expected = {
        "misconfiguration": {
            "scanners": ["helm"],
            "helm": {"values": [values_relative]},
        }
    }
    if value != expected:
        raise InvalidTrivyImageEvidence(
            f"{name} Trivy config must select Helm and its single chart-specific values file"
        )
    return values_relative, value


def _profile_values(name: str, image_repository: str, digest: str) -> dict[str, Any]:
    if name == "revocation":
        return {
            "global": {
                "backendImageRepository": image_repository,
                "backendImageDigest": digest,
            },
            "redis": {
                "metrics": {
                    "passwordFileInitImage": {
                        "repository": image_repository,
                        "tag": "",
                        "digest": digest,
                        "pullPolicy": "Always",
                    }
                }
            },
        }
    if name == "university":
        image = {"repository": image_repository, "digest": digest}
        return {
            "global": {"backendImageDigest": digest},
            "backend": {"image": image},
            "outboxWorker": {"image": dict(image)},
            "redis": {"metrics": {"passwordFileInitImage": dict(image)}},
        }
    if name == "redis-compat":
        return {
            "global": {"backendImageDigest": digest},
            "metrics": {
                "passwordFileInitImage": {
                    "repository": image_repository,
                    "tag": "",
                    "digest": digest,
                    "pullPolicy": "Always",
                }
            },
        }
    raise InvalidTrivyImageEvidence("unknown Trivy profile")


def prepare_profiles(
    archive: Path,
    repository: str,
    source_sha: str,
    output_dir: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Path]:
    """Verify one backend OCI archive and atomically write three isolated chart profiles."""
    archive = Path(archive)
    output_dir = Path(output_dir)
    root = Path.cwd() if repository_root is None else Path(repository_root)
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise InvalidTrivyImageEvidence("repository must be canonical owner/name")
    if not SOURCE_SHA_PATTERN.fullmatch(source_sha):
        raise InvalidTrivyImageEvidence(
            "source SHA must be 40 lowercase hexadecimal characters"
        )
    if archive.name != "backend.oci.tar":
        raise InvalidTrivyImageEvidence("archive must be named backend.oci.tar")
    _regular_file(archive, "backend OCI archive")
    if output_dir.exists() or output_dir.is_symlink():
        raise InvalidTrivyImageEvidence("output directory must not already exist")

    profile_configs: dict[str, tuple[str, dict[str, Any]]] = {}
    for name in PROFILES:
        profile_configs[name] = _load_profile_config(root, name)

    archive_hash_before = _sha256(archive)
    try:
        manifest_digest, source_label, revision_label = (
            checkov_evidence._verified_image_config_labels(archive)
        )
    except (OSError, ValueError, tarfile.TarError) as error:
        raise InvalidTrivyImageEvidence(
            "backend OCI labels or manifest are invalid"
        ) from error
    archive_hash_after = _sha256(archive)
    if archive_hash_before != archive_hash_after:
        raise InvalidTrivyImageEvidence(
            "backend OCI archive changed during verification"
        )
    if not DIGEST_PATTERN.fullmatch(manifest_digest):
        raise InvalidTrivyImageEvidence("backend OCI manifest digest is invalid")
    expected_source = f"https://github.com/{repository}"
    if source_label != expected_source or revision_label != source_sha:
        raise InvalidTrivyImageEvidence(
            "backend OCI source/revision labels do not match this checkout"
        )

    image_repository = f"ghcr.io/{repository.lower()}/backend"
    generated: dict[str, bytes] = {}
    receipt = {
        "schema": "trivy-source-bound-backend-oci/v1",
        "repository": repository,
        "source_sha": source_sha,
        "image_repository": image_repository,
        "manifest_digest": manifest_digest,
        "archive_sha256": archive_hash_after,
        "source_label": source_label,
        "revision_label": revision_label,
    }
    generated["backend-evidence.json"] = _json_bytes(receipt)

    result_paths: dict[str, Path] = {"evidence": output_dir / "backend-evidence.json"}
    for name, (values_relative, config) in profile_configs.items():
        profile_filename = name
        values_name = f"{profile_filename}-values.json"
        config_name = f"trivy-{profile_filename}-config.json"
        values_payload = _profile_values(name, image_repository, manifest_digest)
        generated[values_name] = _json_bytes(values_payload)
        config_values = config["misconfiguration"]["helm"]["values"]
        config_values.append((output_dir / values_name).resolve().as_posix())
        generated[config_name] = _json_bytes(config)
        key = name.replace("-", "_")
        result_paths[f"{key}_values"] = output_dir / values_name
        result_paths[f"{key}_config"] = output_dir / config_name

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=str(parent)))
    try:
        for filename, payload in generated.items():
            (staging / filename).write_bytes(payload)
        os.replace(staging, output_dir)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result_paths


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        paths = prepare_profiles(
            args.archive,
            args.repository,
            args.source_sha,
            args.output_dir,
            repository_root=args.repository_root,
        )
    except (OSError, InvalidTrivyImageEvidence) as error:
        print(f"error: Trivy Helm input preparation failed: {error}", file=sys.stderr)
        return 2
    print(paths["evidence"].read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
