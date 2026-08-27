#!/usr/bin/env python3
"""Fail closed on incomplete or ambiguous release artifact pagination."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_artifact_pages(pages: object, *, expected_name: str) -> dict[str, Any]:
    """Return the unique live expected artifact from a complete page inventory."""
    if not expected_name:
        raise ValueError("expected artifact name must not be empty")
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

    matches = [artifact for artifact in artifacts if artifact["name"] == expected_name]
    if not matches:
        raise ValueError(f"required artifact {expected_name!r} is missing")
    if len(matches) != 1:
        raise ValueError(f"required artifact {expected_name!r} has duplicate entries")
    selected = matches[0]
    if selected["expired"]:
        raise ValueError(f"required artifact {expected_name!r} is expired")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--expected-name", required=True)
    args = parser.parse_args()
    try:
        pages = json.loads(args.pages.read_text(encoding="utf-8"))
        selected = validate_artifact_pages(pages, expected_name=args.expected_name)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(f"validated release artifact id {selected['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
