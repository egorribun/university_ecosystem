#!/usr/bin/env python3
"""Resolve one verified linux/amd64 OCI manifest as a Checkov values file."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

OCI_LAYOUT_VERSION = "1.0.0"
OCI_INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
OCI_CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
MAX_METADATA_BYTES = 4 * 1024 * 1024
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class InvalidImageArchive(ValueError):
    """The archive is ambiguous, malformed, or does not contain the requested image."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidImageArchive("duplicate JSON key")
        result[key] = value
    return result


def _load_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise InvalidImageArchive("expected JSON object")
    return value


def _read_file(
    archive: tarfile.TarFile, members: dict[str, tarfile.TarInfo], name: str
) -> bytes:
    member = members.get(name)
    if member is None or not member.isfile() or member.size > MAX_METADATA_BYTES:
        raise InvalidImageArchive("required metadata blob is missing or invalid")
    stream = archive.extractfile(member)
    if stream is None:
        raise InvalidImageArchive("metadata blob cannot be read")
    with stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    if len(raw) != member.size or len(raw) > MAX_METADATA_BYTES:
        raise InvalidImageArchive("metadata blob size is inconsistent")
    return raw


def _descriptor(value: Any, expected_media_types: set[str]) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise InvalidImageArchive("descriptor is not an object")
    digest = value.get("digest")
    size = value.get("size")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        raise InvalidImageArchive("descriptor digest is not a sha256 digest")
    if type(size) is not int or size < 0:
        raise InvalidImageArchive("descriptor size is invalid")
    if value.get("mediaType") not in expected_media_types:
        raise InvalidImageArchive("descriptor media type is not an OCI image type")
    return digest, size


def _read_verified_blob(
    archive: tarfile.TarFile,
    members: dict[str, tarfile.TarInfo],
    digest: str,
    size: int,
) -> bytes:
    algorithm, encoded = digest.split(":", 1)
    raw = _read_file(archive, members, f"blobs/{algorithm}/{encoded}")
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != encoded:
        raise InvalidImageArchive(
            "descriptor does not match its content-addressed blob"
        )
    return raw


def resolve_linux_amd64_manifest_digest(archive_path: Path) -> str:
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members: dict[str, tarfile.TarInfo] = {}
            for member in archive:
                name = member.name
                path = PurePosixPath(name)
                if (
                    not name
                    or "\\" in name
                    or path.is_absolute()
                    or ".." in path.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise InvalidImageArchive(
                        "archive contains an unsafe or unsupported entry"
                    )
                if name in members:
                    raise InvalidImageArchive("archive contains a duplicate entry")
                members[name] = member

            layout = _load_json(_read_file(archive, members, "oci-layout"))
            if layout.get("imageLayoutVersion") != OCI_LAYOUT_VERSION:
                raise InvalidImageArchive("unsupported OCI image layout version")

            index = _load_json(_read_file(archive, members, "index.json"))
            if index.get("schemaVersion") != 2:
                raise InvalidImageArchive("unsupported OCI index schema version")
            if index.get("mediaType") not in (None, OCI_INDEX_MEDIA_TYPE):
                raise InvalidImageArchive("index media type is not OCI")
            descriptors = index.get("manifests")
            if not isinstance(descriptors, list) or len(descriptors) != 1:
                raise InvalidImageArchive(
                    "OCI index must contain exactly one image manifest"
                )

            descriptor = descriptors[0]
            platform = (
                descriptor.get("platform") if isinstance(descriptor, dict) else None
            )
            if not isinstance(platform, dict):
                raise InvalidImageArchive("image manifest has no platform")
            if platform.get("os") != "linux" or platform.get("architecture") != "amd64":
                raise InvalidImageArchive("image platform is not linux/amd64")
            if platform.get("variant") not in (None, ""):
                raise InvalidImageArchive("unexpected linux/amd64 platform variant")

            manifest_digest, manifest_size = _descriptor(
                descriptor, {OCI_MANIFEST_MEDIA_TYPE}
            )
            manifest_raw = _read_verified_blob(
                archive, members, manifest_digest, manifest_size
            )
            manifest = _load_json(manifest_raw)
            if (
                manifest.get("schemaVersion") != 2
                or manifest.get("mediaType") != OCI_MANIFEST_MEDIA_TYPE
            ):
                raise InvalidImageArchive("image manifest is not OCI schema version 2")

            config_digest, config_size = _descriptor(
                manifest.get("config"), {OCI_CONFIG_MEDIA_TYPE}
            )
            config = _load_json(
                _read_verified_blob(archive, members, config_digest, config_size)
            )
            if config.get("os") != "linux" or config.get("architecture") != "amd64":
                raise InvalidImageArchive("image config is not linux/amd64")
            if config.get("variant") not in (None, ""):
                raise InvalidImageArchive("unexpected image config platform variant")
            if not isinstance(manifest.get("layers"), list):
                raise InvalidImageArchive("image manifest has no layer list")
            return manifest_digest
    except (OSError, tarfile.TarError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidImageArchive("OCI image archive cannot be read") from exc


def render_checkov_values(digest: str) -> str:
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        raise InvalidImageArchive("resolved digest is invalid")
    return f'global:\n  backendImageDigest: "{digest}"\n'


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("usage: resolve_oci_platform_digest.py OCI_ARCHIVE\n")
        return 2
    try:
        digest = resolve_linux_amd64_manifest_digest(Path(args[0]))
        sys.stdout.write(render_checkov_values(digest))
    except (InvalidImageArchive, OSError, tarfile.TarError, json.JSONDecodeError):
        sys.stderr.write(
            "error: backend OCI archive did not contain one verified linux/amd64 manifest\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
