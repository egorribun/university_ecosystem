"""Create a hash-bound map of manifest digests from local, unpublished OCI builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import tempfile
from collections.abc import Iterable
from pathlib import Path

import resolve_oci_platform_digest as oci_resolver

REQUIRED_IMAGES = ("backend", "frontend", "gateway", "ws-hub", "file-processor")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", re.ASCII)
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
SOURCE_LABEL = "org.opencontainers.image.source"
REVISION_LABEL = "org.opencontainers.image.revision"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verified_image_config_labels(archive_path: Path) -> tuple[str, str, str]:
    """Read labels from the config blob selected by the verified manifest."""
    manifest_digest = oci_resolver.resolve_linux_amd64_manifest_digest(archive_path)
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = {}
            for member in archive:
                if member.name in members:
                    raise ValueError("OCI archive contains duplicate entries")
                members[member.name] = member
            index = oci_resolver._load_json(
                oci_resolver._read_file(archive, members, "index.json")
            )
            descriptors = index.get("manifests")
            if not isinstance(descriptors, list) or len(descriptors) != 1:
                raise ValueError("OCI index must contain exactly one manifest")
            manifest_hash, manifest_size = oci_resolver._descriptor(
                descriptors[0], {oci_resolver.OCI_MANIFEST_MEDIA_TYPE}
            )
            if manifest_hash != manifest_digest:
                raise ValueError("OCI manifest changed while reading image labels")
            manifest = oci_resolver._load_json(
                oci_resolver._read_verified_blob(
                    archive, members, manifest_hash, manifest_size
                )
            )
            config_hash, config_size = oci_resolver._descriptor(
                manifest.get("config"), {oci_resolver.OCI_CONFIG_MEDIA_TYPE}
            )
            config = oci_resolver._load_json(
                oci_resolver._read_verified_blob(
                    archive, members, config_hash, config_size
                )
            )
    except (OSError, tarfile.TarError, ValueError) as error:
        raise ValueError("OCI config metadata cannot be verified") from error

    image_config = config.get("config")
    labels = image_config.get("Labels") if isinstance(image_config, dict) else None
    if not isinstance(labels, dict):
        raise ValueError("OCI image config does not contain a labels object")
    source = labels.get(SOURCE_LABEL)
    revision = labels.get(REVISION_LABEL)
    if not isinstance(source, str) or not isinstance(revision, str):
        raise ValueError("OCI image config is missing source or revision labels")
    return manifest_digest, source, revision


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    temporary.replace(path)


def _archive_map(items: Iterable[str]) -> dict[str, Path]:
    archives: dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError("each archive must use IMAGE=PATH")
        name, raw_path = item.split("=", 1)
        if name not in REQUIRED_IMAGES or name in archives:
            raise ValueError(
                "archive names must be the exact unique required image set"
            )
        path = Path(raw_path)
        if path.name != f"{name}.oci.tar" or path.is_symlink() or not path.is_file():
            raise ValueError(f"{name} archive must be a regular {name}.oci.tar file")
        archives[name] = path
    if set(archives) != set(REQUIRED_IMAGES):
        raise ValueError("all five local first-party OCI archives are required")
    if len({path.parent.resolve() for path in archives.values()}) != 1:
        raise ValueError("OCI archives must share one dedicated private directory")
    return archives


def create_evidence(
    repository: str, source_sha: str, archives: Iterable[str], output: Path
) -> str:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("repository must be a canonical owner/name value")
    if not SOURCE_SHA_PATTERN.fullmatch(source_sha):
        raise ValueError("source SHA must be exactly 40 lowercase hex characters")
    archive_paths = _archive_map(archives)
    expected_source = f"https://github.com/{repository}"
    images = {}
    for name in REQUIRED_IMAGES:
        archive = archive_paths[name]
        manifest_digest, source_label, revision_label = _verified_image_config_labels(
            archive
        )
        if source_label != expected_source or revision_label != source_sha:
            raise ValueError(
                f"OCI source/revision labels do not match this run for {name}"
            )
        images[name] = {
            "repository": f"ghcr.io/{repository}/{name}",
            "manifest_digest": manifest_digest,
            "archive_sha256": _sha256(archive),
            "source_label": source_label,
            "revision_label": revision_label,
        }
    document = {
        "schema": "checkov-local-oci-image-evidence/v2",
        "source_sha": source_sha,
        "repository": repository,
        "images": images,
    }
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    evidence_sha = hashlib.sha256(payload).hexdigest()
    _write_atomic(output, payload)
    _write_atomic(
        Path(f"{output}.sha256"), f"{evidence_sha}  {output.name}\n".encode("ascii")
    )
    return evidence_sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--archive", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        digest = create_evidence(
            args.repository, args.source_sha, args.archive, args.output
        )
    except (OSError, ValueError) as error:
        print(f"error: local OCI evidence generation failed: {error}", file=sys.stderr)
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
