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
    {"backend", "caddy", "frontend", "ws-hub", "gateway", "file-processor"}
)
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WORKFLOW_PATH = ".github/workflows/build-release-images.yml"
_SOURCE_REF = "refs/heads/main"
_EVENT = "workflow_dispatch"
_VERIFICATION = {
    "trivy_version": "0.73.0",
    "sbom_format": "cyclonedx-json",
    "signature": "cosign-keyless",
    "attestation": "github-build-provenance",
}


def _positive_integer(value: Any, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_name(image_name: str, source_sha: str, attempt: int) -> str:
    return f"image-digest-evidence-{image_name}-{source_sha}-attempt-{attempt}"


def _certification_artifact_name(source_sha: str, attempt: int) -> str:
    return f"quality-certification-{source_sha}-attempt-{attempt}"


def _producer(
    *,
    repository: str,
    source_sha: str,
    build_run_id: int,
    attempt: int,
    artifact_name: str,
) -> dict[str, Any]:
    return {
        "repository": repository,
        "workflow_path": _WORKFLOW_PATH,
        "workflow_ref": f"{repository}/{_WORKFLOW_PATH}@refs/heads/main",
        "workflow_sha": source_sha,
        "source_ref": _SOURCE_REF,
        "event": _EVENT,
        "run_id": build_run_id,
        "run_attempt": attempt,
        "artifact_name": artifact_name,
    }


def _validate_cohort(
    cohort_path: Path,
    *,
    expected_repository: str,
    expected_sha: str,
    build_run_id: int,
    build_run_attempt: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cohort = _load_object(cohort_path)
    if cohort.get("schema_version") != 1:
        raise ValueError("release artifact cohort has an unsupported schema version")
    if cohort.get("repository") != expected_repository:
        raise ValueError("release artifact cohort belongs to a foreign repository")
    if cohort.get("source_sha") != expected_sha:
        raise ValueError("release artifact cohort belongs to a foreign source SHA")
    if cohort.get("build_run_id") != build_run_id:
        raise ValueError("release artifact cohort belongs to a foreign build run")
    if cohort.get("consumer_run_attempt") != build_run_attempt:
        raise ValueError("release artifact cohort has a mismatched consumer attempt")

    entries = cohort.get("images")
    if not isinstance(entries, list) or len(entries) != len(EXPECTED_IMAGE_NAMES):
        raise ValueError(
            "release artifact cohort does not match the exact image inventory"
        )
    selected_images: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("release artifact cohort contains a malformed image entry")
        image_name = entry.get("image_name")
        artifact_id = entry.get("artifact_id")
        artifact_name = entry.get("artifact_name")
        attempt = entry.get("producer_run_attempt")
        if image_name not in EXPECTED_IMAGE_NAMES or image_name in selected_images:
            raise ValueError("release artifact cohort has a duplicate or unknown image")
        if not _positive_integer(artifact_id, name="image artifact id"):
            raise ValueError("release artifact cohort has an invalid image artifact id")
        if not _positive_integer(attempt, name="image producer attempt"):
            raise ValueError(
                "release artifact cohort has an invalid image producer attempt"
            )
        if attempt > build_run_attempt:
            raise ValueError(
                "release artifact cohort has a future image producer attempt"
            )
        if artifact_name != _artifact_name(image_name, expected_sha, attempt):
            raise ValueError(
                "release artifact cohort has a mismatched image artifact name"
            )
        selected_images[image_name] = entry
    if set(selected_images) != EXPECTED_IMAGE_NAMES:
        raise ValueError(
            "release artifact cohort does not match the exact image inventory"
        )

    certification = cohort.get("certification")
    if not isinstance(certification, dict):
        raise ValueError("release artifact cohort has no certification entry")
    certification_id = certification.get("artifact_id")
    certification_name = certification.get("artifact_name")
    certification_attempt = certification.get("producer_run_attempt")
    if not _positive_integer(certification_id, name="certification artifact id"):
        raise ValueError(
            "release artifact cohort has an invalid certification artifact id"
        )
    if not _positive_integer(
        certification_attempt, name="certification producer attempt"
    ):
        raise ValueError(
            "release artifact cohort has an invalid certification producer attempt"
        )
    if certification_attempt > build_run_attempt:
        raise ValueError(
            "release artifact cohort has a future certification producer attempt"
        )
    if certification_name != _certification_artifact_name(
        expected_sha, certification_attempt
    ):
        raise ValueError(
            "release artifact cohort has a mismatched certification artifact name"
        )
    return selected_images, certification


def _validate_certification(
    certification_path: Path,
    certification_provenance_path: Path,
    quality_contract_path: Path,
    check_policy_path: Path,
    *,
    expected_repository: str,
    expected_sha: str,
    build_run_id: int,
    quality_run_id: int,
    quality_run_attempt: int,
    certification_selection: dict[str, Any],
) -> dict[str, Any]:
    certification = _load_object(certification_path)
    if certification.get("schema_version") != 1:
        raise ValueError("certification record has an unsupported schema version")
    if certification.get("commit_sha") != expected_sha:
        raise ValueError("certification record belongs to a foreign source SHA")
    contract_sha256 = _sha256(quality_contract_path)
    policy_sha256 = _sha256(check_policy_path)
    if certification.get("contract_sha256") != contract_sha256:
        raise ValueError(
            "certification record has mismatched quality contract metadata"
        )
    if certification.get("check_policy_sha256") != policy_sha256:
        raise ValueError("certification record has mismatched release policy metadata")
    if certification.get("check_event") != "push_main":
        raise ValueError("certification record has mismatched quality event metadata")
    if not all(
        isinstance(certification.get(field), str)
        and _SHA256.fullmatch(certification[field])
        for field in ("record_sha256", "hmac_sha256")
    ):
        raise ValueError("certification record has malformed signed metadata")

    provenance = _load_object(certification_provenance_path)
    attempt = certification_selection["producer_run_attempt"]
    artifact_name = certification_selection["artifact_name"]
    expected_producer = _producer(
        repository=expected_repository,
        source_sha=expected_sha,
        build_run_id=build_run_id,
        attempt=attempt,
        artifact_name=artifact_name,
    )
    expected_quality = {
        "run_id": quality_run_id,
        "run_attempt": quality_run_attempt,
        "evidence_artifact_name": f"quality-evidence-{expected_sha}",
        "contract_sha256": contract_sha256,
        "check_policy_sha256": policy_sha256,
        "check_event": "push_main",
    }
    if provenance.get("schema_version") != 1:
        raise ValueError("certification provenance has an unsupported schema version")
    if provenance.get("certification_sha256") != _sha256(certification_path):
        raise ValueError(
            "certification provenance does not bind the certification content"
        )
    if provenance.get("producer") != expected_producer:
        raise ValueError("certification producer provenance is invalid")
    if provenance.get("quality") != expected_quality:
        raise ValueError("certification quality provenance is invalid")
    return {"producer": expected_producer, "quality": expected_quality}


def aggregate_image_evidence(
    evidence_dir: Path,
    *,
    expected_repository: str,
    expected_sha: str,
    certification_path: Path,
    certification_provenance_path: Path,
    cohort_path: Path,
    quality_contract_path: Path,
    check_policy_path: Path,
    build_run_id: int,
    build_run_attempt: int,
    quality_run_id: int,
    quality_run_attempt: int,
) -> dict[str, Any]:
    """Validate a selected retry-safe image cohort and bind it to certification."""
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
    if not certification_provenance_path.is_file():
        raise ValueError(
            "certification provenance record does not exist: "
            f"{certification_provenance_path}"
        )
    if not cohort_path.is_file():
        raise ValueError(f"release artifact cohort does not exist: {cohort_path}")
    if not quality_contract_path.is_file() or not check_policy_path.is_file():
        raise ValueError("trusted quality contract or release policy does not exist")
    _positive_integer(build_run_id, name="build run id")
    _positive_integer(build_run_attempt, name="build run attempt")
    _positive_integer(quality_run_id, name="quality run id")
    _positive_integer(quality_run_attempt, name="quality run attempt")
    selected_images, certification_selection = _validate_cohort(
        cohort_path,
        expected_repository=expected_repository,
        expected_sha=expected_sha,
        build_run_id=build_run_id,
        build_run_attempt=build_run_attempt,
    )
    certification_metadata = _validate_certification(
        certification_path,
        certification_provenance_path,
        quality_contract_path,
        check_policy_path,
        expected_repository=expected_repository,
        expected_sha=expected_sha,
        build_run_id=build_run_id,
        quality_run_id=quality_run_id,
        quality_run_attempt=quality_run_attempt,
        certification_selection=certification_selection,
    )

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
        if evidence.get("schema_version") != 2:
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
        selection = selected_images[image_name]
        attempt = selection["producer_run_attempt"]
        expected_producer = _producer(
            repository=expected_repository,
            source_sha=expected_sha,
            build_run_id=build_run_id,
            attempt=attempt,
            artifact_name=selection["artifact_name"],
        )
        if evidence.get("producer") != expected_producer:
            raise ValueError(f"{image_name} evidence producer provenance is invalid")
        if evidence.get("verification") != _VERIFICATION:
            raise ValueError(f"{image_name} evidence verification metadata is invalid")
        if evidence.get("build_contract") != {
            "canonical_frontend": image_name == "frontend",
            "release_sha": expected_sha,
        }:
            raise ValueError(f"{image_name} evidence build contract is invalid")
        seen_names.add(image_name)
        seen_digests.add(digest)
        images.append(
            {
                "image_name": image_name,
                "subject_name": expected_subject,
                "digest": digest,
                "reference": reference,
                "producer": expected_producer,
            }
        )

    if seen_names != EXPECTED_IMAGE_NAMES:
        raise ValueError("release evidence does not match the exact image inventory")
    return {
        "schema_version": 2,
        "repository": expected_repository,
        "source_sha": expected_sha,
        "source_ref": "refs/heads/main",
        "builder": {
            "workflow_path": ".github/workflows/build-release-images.yml",
            "workflow_ref": (
                f"{expected_repository}/.github/workflows/"
                "build-release-images.yml@refs/heads/main"
            ),
            "event": "workflow_dispatch",
            "run_id": build_run_id,
            "run_attempt": build_run_attempt,
        },
        "quality_run_id": quality_run_id,
        "quality_run_attempt": quality_run_attempt,
        "certification_sha256": _sha256(certification_path),
        "certification": certification_metadata,
        "frontend_build_contract": {
            "VITE_APP_RELEASE": expected_sha,
            "VITE_ENABLE_WEB_VITALS": "true",
            "VITE_CWV_TRUSTED_RUM": "true",
            "VITE_WEB_VITALS_ENDPOINT": "/api/v1/cwv",
        },
        "images": sorted(images, key=lambda item: item["image_name"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--certification", type=Path, required=True)
    parser.add_argument("--certification-provenance", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--quality-contract", type=Path, required=True)
    parser.add_argument("--check-policy", type=Path, required=True)
    parser.add_argument("--build-run-id", type=int, required=True)
    parser.add_argument("--build-run-attempt", type=int, required=True)
    parser.add_argument("--quality-run-id", type=int, required=True)
    parser.add_argument("--quality-run-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = aggregate_image_evidence(
            args.evidence_dir,
            expected_repository=args.repository,
            expected_sha=args.source_sha,
            certification_path=args.certification,
            certification_provenance_path=args.certification_provenance,
            cohort_path=args.cohort,
            quality_contract_path=args.quality_contract,
            check_policy_path=args.check_policy,
            build_run_id=args.build_run_id,
            build_run_attempt=args.build_run_attempt,
            quality_run_id=args.quality_run_id,
            quality_run_attempt=args.quality_run_attempt,
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
