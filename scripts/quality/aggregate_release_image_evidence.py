#!/usr/bin/env python3
"""Build a deterministic, fail-closed release image digest manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_IMAGE_NAMES = frozenset(
    {"backend", "frontend", "ws-hub", "gateway", "file-processor"}
)
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_image_evidence(
    evidence_dir: Path,
    *,
    expected_repository: str,
    expected_sha: str,
    certification_path: Path,
) -> dict[str, Any]:
    """Validate exactly five signed image records and bind them to certification."""
    if not _REPOSITORY.fullmatch(expected_repository):
        raise ValueError("expected repository must be an owner/name pair")
    if not _COMMIT_SHA.fullmatch(expected_sha):
        raise ValueError(
            "expected source SHA must be 40 lowercase hexadecimal characters"
        )
    if not evidence_dir.is_dir():
        raise ValueError(f"image evidence directory does not exist: {evidence_dir}")
    if not certification_path.is_file():
        raise ValueError(f"certification record does not exist: {certification_path}")

    certification = _load_object(certification_path)
    if certification.get("commit_sha") != expected_sha:
        raise ValueError("certification record belongs to a foreign source SHA")

    paths = sorted(evidence_dir.glob("*.json"), key=lambda path: path.name)
    if len(paths) != len(EXPECTED_IMAGE_NAMES):
        raise ValueError(
            "release evidence must contain the exact image inventory: "
            f"found {len(paths)}, expected {len(EXPECTED_IMAGE_NAMES)}"
        )

    images: list[dict[str, str]] = []
    seen_names: set[str] = set()
    seen_digests: set[str] = set()
    for path in paths:
        evidence = _load_object(path)
        image_name = evidence.get("image_name")
        digest = evidence.get("digest")
        subject_name = evidence.get("subject_name")
        reference = evidence.get("reference")
        if image_name not in EXPECTED_IMAGE_NAMES or image_name in seen_names:
            raise ValueError(
                "release evidence does not match the exact image inventory"
            )
        if evidence.get("schema_version") != 1:
            raise ValueError(f"{image_name} evidence has an unsupported schema version")
        if evidence.get("source_sha") != expected_sha:
            raise ValueError(f"{image_name} evidence belongs to a foreign source SHA")
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ValueError(f"{image_name} evidence has an invalid image digest")
        if digest in seen_digests:
            raise ValueError("release image evidence contains a duplicate image digest")
        expected_subject = f"ghcr.io/{expected_repository}/{image_name}"
        if (
            subject_name != expected_subject
            or reference != f"{expected_subject}@{digest}"
        ):
            raise ValueError(
                f"{image_name} evidence has a non-canonical digest reference"
            )
        if not (
            evidence.get("signature_verified") is True
            and evidence.get("attestation_verified") is True
        ):
            raise ValueError(
                f"{image_name} evidence requires a verified signature and attestation"
            )
        seen_names.add(image_name)
        seen_digests.add(digest)
        images.append(
            {
                "image_name": image_name,
                "subject_name": expected_subject,
                "digest": digest,
                "reference": reference,
            }
        )

    if seen_names != EXPECTED_IMAGE_NAMES:
        raise ValueError("release evidence does not match the exact image inventory")
    return {
        "schema_version": 1,
        "source_sha": expected_sha,
        "certification_sha256": _sha256(certification_path),
        "images": sorted(images, key=lambda item: item["image_name"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--certification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = aggregate_image_evidence(
            args.evidence_dir,
            expected_repository=args.repository,
            expected_sha=args.source_sha,
            certification_path=args.certification,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
