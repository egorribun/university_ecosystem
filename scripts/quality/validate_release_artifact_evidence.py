#!/usr/bin/env python3
"""Fail closed on incomplete or ambiguous release artifact pagination."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_IMAGE_NAMES = (
    "backend",
    "caddy",
    "file-processor",
    "frontend",
    "gateway",
    "ws-hub",
)
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_IMAGE_ARTIFACT_NAME = re.compile(
    r"^image-digest-evidence-"
    r"(?P<image>backend|caddy|file-processor|frontend|gateway|ws-hub)-"
    r"(?P<source_sha>[0-9a-f]{40})-attempt-(?P<attempt>[1-9][0-9]*)$"
)
_CERTIFICATION_ARTIFACT_NAME = re.compile(
    r"^quality-certification-"
    r"(?P<source_sha>[0-9a-f]{40})-attempt-(?P<attempt>[1-9][0-9]*)$"
)


def _non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _artifact_inventory(pages: object) -> list[dict[str, Any]]:
    """Return a complete, unambiguous GitHub Actions artifact inventory."""
    if not isinstance(pages, list) or not pages:
        raise ValueError("GitHub returned no artifact pages")
    if any(not isinstance(page, dict) for page in pages):
        raise ValueError("GitHub artifact pagination response is malformed")

    totals = {page.get("total_count") for page in pages}
    if len(totals) != 1 or not all(_non_negative_integer(total) for total in totals):
        raise ValueError("GitHub artifact total_count is missing or inconsistent")
    page_artifacts = [page.get("artifacts") for page in pages]
    if any(not isinstance(artifacts, list) for artifacts in page_artifacts):
        raise ValueError("GitHub artifact page has no artifacts array")
    artifacts = [artifact for page in page_artifacts for artifact in page]
    expected_total = totals.pop()
    if len(artifacts) != expected_total:
        raise ValueError(
            f"artifact pagination was truncated: got {len(artifacts)}, "
            f"expected {expected_total}"
        )
    if any(not isinstance(artifact, dict) for artifact in artifacts):
        raise ValueError("GitHub artifact response contains a non-object artifact")

    artifact_ids = [artifact.get("id") for artifact in artifacts]
    if any(not _positive_integer(artifact_id) for artifact_id in artifact_ids):
        raise ValueError("GitHub artifact response contains an invalid artifact ID")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("GitHub artifact pagination returned duplicate artifact IDs")
    if any(
        not isinstance(artifact.get("name"), str) or not artifact["name"]
        for artifact in artifacts
    ):
        raise ValueError("GitHub artifact response contains an invalid artifact name")
    if any(not isinstance(artifact.get("expired"), bool) for artifact in artifacts):
        raise ValueError("GitHub artifact response contains an invalid expiry state")
    return artifacts


def validate_artifact_pages(pages: object, *, expected_name: str) -> dict[str, Any]:
    """Return the unique live expected artifact from a complete page inventory."""
    if not expected_name:
        raise ValueError("expected artifact name must not be empty")
    artifacts = _artifact_inventory(pages)

    matches = [artifact for artifact in artifacts if artifact["name"] == expected_name]
    if not matches:
        raise ValueError(f"required artifact {expected_name!r} is missing")
    if len(matches) != 1:
        raise ValueError(f"required artifact {expected_name!r} has duplicate entries")
    selected = matches[0]
    if selected["expired"]:
        raise ValueError(f"required artifact {expected_name!r} is expired")
    return selected


def _selection_entry(artifact: dict[str, Any], attempt: int) -> dict[str, Any]:
    return {
        "artifact_id": artifact["id"],
        "artifact_name": artifact["name"],
        "producer_run_attempt": attempt,
    }


def select_release_artifact_cohort(
    pages: object,
    *,
    expected_repository: str,
    expected_sha: str,
    build_run_id: int,
    consumer_run_attempt: int,
) -> dict[str, Any]:
    """Choose one deterministic, same-run evidence artifact for each producer.

    GitHub increments ``run_attempt`` when only failed jobs are re-run, while
    successful jobs retain their immutable artifacts from an earlier attempt.
    Selection therefore uses the highest live, uniquely named producer attempt
    for each required image and certification, but never accepts a future
    producer attempt.  The API inventory is scoped to ``build_run_id`` by the
    calling workflow; the returned cohort records every selected artifact ID
    and producer attempt for payload validation after download.
    """
    if not _REPOSITORY.fullmatch(expected_repository):
        raise ValueError("expected repository must be an owner/name pair")
    if not _COMMIT_SHA.fullmatch(expected_sha):
        raise ValueError(
            "expected source SHA must be 40 lowercase hexadecimal characters"
        )
    if not _positive_integer(build_run_id):
        raise ValueError("build run id must be a positive integer")
    if not _positive_integer(consumer_run_attempt):
        raise ValueError("consumer run attempt must be a positive integer")

    images: dict[str, dict[int, dict[str, Any]]] = {
        image_name: {} for image_name in EXPECTED_IMAGE_NAMES
    }
    certifications: dict[int, dict[str, Any]] = {}
    for artifact in _artifact_inventory(pages):
        name = artifact["name"]
        if name.startswith("image-digest-evidence-"):
            match = _IMAGE_ARTIFACT_NAME.fullmatch(name)
            if match is None:
                raise ValueError("malformed image evidence artifact candidate")
            source_sha = match["source_sha"]
            if source_sha != expected_sha:
                raise ValueError(
                    "image evidence artifact candidate has a foreign source SHA"
                )
            attempt = int(match["attempt"])
            if attempt > consumer_run_attempt:
                raise ValueError(
                    "image evidence artifact candidate has a future producer attempt"
                )
            if artifact["expired"]:
                raise ValueError("image evidence artifact candidate is expired")
            image_name = match["image"]
            if attempt in images[image_name]:
                raise ValueError("duplicate image evidence artifact candidate")
            images[image_name][attempt] = artifact
        elif name.startswith("quality-certification-"):
            match = _CERTIFICATION_ARTIFACT_NAME.fullmatch(name)
            if match is None:
                raise ValueError("malformed certification artifact candidate")
            source_sha = match["source_sha"]
            if source_sha != expected_sha:
                raise ValueError(
                    "certification artifact candidate has a foreign source SHA"
                )
            attempt = int(match["attempt"])
            if attempt > consumer_run_attempt:
                raise ValueError(
                    "certification artifact candidate has a future producer attempt"
                )
            if artifact["expired"]:
                raise ValueError("certification artifact candidate is expired")
            if attempt in certifications:
                raise ValueError("duplicate certification artifact candidate")
            certifications[attempt] = artifact

    selected_images: list[dict[str, Any]] = []
    for image_name in EXPECTED_IMAGE_NAMES:
        candidates = images[image_name]
        if not candidates:
            raise ValueError(
                f"required image evidence artifact is missing: {image_name}"
            )
        attempt = max(candidates)
        selected_images.append(
            {"image_name": image_name, **_selection_entry(candidates[attempt], attempt)}
        )
    if not certifications:
        raise ValueError("required certification artifact is missing")
    certification_attempt = max(certifications)
    return {
        "schema_version": 1,
        "repository": expected_repository,
        "source_sha": expected_sha,
        "build_run_id": build_run_id,
        "consumer_run_attempt": consumer_run_attempt,
        "images": selected_images,
        "certification": _selection_entry(
            certifications[certification_attempt], certification_attempt
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--expected-name")
    parser.add_argument("--select-release-cohort", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--source-sha")
    parser.add_argument("--build-run-id", type=int)
    parser.add_argument("--consumer-run-attempt", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        pages = json.loads(args.pages.read_text(encoding="utf-8"))
        if args.select_release_cohort:
            if None in {
                args.repository,
                args.source_sha,
                args.build_run_id,
                args.consumer_run_attempt,
                args.output,
            }:
                raise ValueError(
                    "release cohort selection requires repository, source SHA, run ID, "
                    "consumer attempt, and output"
                )
            selected = select_release_artifact_cohort(
                pages,
                expected_repository=args.repository,
                expected_sha=args.source_sha,
                build_run_id=args.build_run_id,
                consumer_run_attempt=args.consumer_run_attempt,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(selected, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            print("selected retry-safe release artifact cohort")
        else:
            if args.expected_name is None:
                raise ValueError("expected artifact name must not be empty")
            selected = validate_artifact_pages(pages, expected_name=args.expected_name)
            print(f"validated release artifact id {selected['id']}")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
