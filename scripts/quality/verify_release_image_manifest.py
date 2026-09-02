#!/usr/bin/env python3
"""Fail closed while resolving a canonical six-image release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_IMAGE_NAMES = frozenset(
    {"backend", "caddy", "frontend", "ws-hub", "gateway", "file-processor"}
)
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([^/\\\r\n]+)\n?$")


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def verify_manifest(
    manifest: object,
    *,
    expected_repository: str,
    expected_sha: str,
    expected_build_run_id: int,
    expected_build_run_attempt: int,
    expected_quality_run_id: int,
) -> dict[str, str]:
    """Return exact image digests after validating all promotion provenance."""
    if not _REPOSITORY.fullmatch(expected_repository):
        raise ValueError("expected repository must be an owner/name pair")
    if not _COMMIT_SHA.fullmatch(expected_sha):
        raise ValueError("expected source SHA must be 40 lowercase hex characters")
    if not all(
        _positive_integer(value)
        for value in (
            expected_build_run_id,
            expected_build_run_attempt,
            expected_quality_run_id,
        )
    ):
        raise ValueError("workflow run ids and attempts must be positive integers")
    if not isinstance(manifest, dict):
        raise ValueError("release image manifest must be a JSON object")

    expected_builder = {
        "workflow_path": ".github/workflows/build-release-images.yml",
        "workflow_ref": (
            f"{expected_repository}/.github/workflows/"
            "build-release-images.yml@refs/heads/main"
        ),
        "event": "workflow_dispatch",
        "run_id": expected_build_run_id,
        "run_attempt": expected_build_run_attempt,
    }
    expected_frontend = {
        "VITE_APP_RELEASE": expected_sha,
        "VITE_ENABLE_WEB_VITALS": "true",
        "VITE_CWV_TRUSTED_RUM": "true",
        "VITE_WEB_VITALS_ENDPOINT": "/api/v1/cwv",
    }
    if manifest.get("schema_version") != 2:
        raise ValueError("release image manifest schema version is unsupported")
    if manifest.get("repository") != expected_repository:
        raise ValueError("release image manifest belongs to a foreign repository")
    if (
        manifest.get("source_sha") != expected_sha
        or manifest.get("source_ref") != "refs/heads/main"
    ):
        raise ValueError("release image manifest belongs to a foreign source")
    if manifest.get("builder") != expected_builder:
        raise ValueError("release image manifest builder provenance is invalid")
    if manifest.get("quality_run_id") != expected_quality_run_id:
        raise ValueError("release image manifest quality run is invalid")
    certification_hash = manifest.get("certification_sha256")
    if not isinstance(certification_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", certification_hash
    ):
        raise ValueError("release image manifest certification hash is invalid")
    if manifest.get("frontend_build_contract") != expected_frontend:
        raise ValueError("release image manifest frontend build contract is invalid")

    images = manifest.get("images")
    if not isinstance(images, list) or len(images) != len(EXPECTED_IMAGE_NAMES):
        raise ValueError(
            "release image manifest requires the exact six-image inventory"
        )
    outputs: dict[str, str] = {}
    seen_digests: set[str] = set()
    for image in images:
        if not isinstance(image, dict):
            raise ValueError("release image manifest contains a non-object image")
        image_name = image.get("image_name")
        digest = image.get("digest")
        if not isinstance(image_name, str) or image_name not in EXPECTED_IMAGE_NAMES:
            raise ValueError("release image manifest contains an unknown image")
        if image_name in outputs:
            raise ValueError("release image manifest contains a duplicate image")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ValueError("release image manifest contains an invalid digest")
        if digest in seen_digests:
            raise ValueError("release image manifest contains a duplicate digest")
        subject = f"ghcr.io/{expected_repository}/{image_name}"
        if image.get("subject_name") != subject or image.get("reference") != (
            f"{subject}@{digest}"
        ):
            raise ValueError(
                "release image manifest contains a non-canonical reference"
            )
        outputs[f"{image_name}-digest"] = digest
        seen_digests.add(digest)
    if set(outputs) != {f"{name}-digest" for name in EXPECTED_IMAGE_NAMES}:
        raise ValueError("release image manifest image inventory is incomplete")
    return outputs


def verify_checksum(manifest_path: Path, checksum_path: Path) -> str:
    """Verify the exact sha256sum record and return the manifest digest."""
    line = checksum_path.read_text(encoding="utf-8")
    match = _CHECKSUM_LINE.fullmatch(line)
    if match is None or match.group(2) != manifest_path.name:
        raise ValueError("release image manifest checksum record is malformed")
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if match.group(1) != actual:
        raise ValueError("release image manifest checksum does not match")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--build-run-id", type=int, required=True)
    parser.add_argument("--build-run-attempt", type=int, required=True)
    parser.add_argument("--quality-run-id", type=int, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest_sha256 = verify_checksum(args.manifest, args.checksum)
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        outputs = verify_manifest(
            manifest,
            expected_repository=args.repository,
            expected_sha=args.source_sha,
            expected_build_run_id=args.build_run_id,
            expected_build_run_attempt=args.build_run_attempt,
            expected_quality_run_id=args.quality_run_id,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
        for name in sorted(outputs):
            output.write(f"{name}={outputs[name]}\n")
        output.write(f"manifest-sha256={manifest_sha256}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
