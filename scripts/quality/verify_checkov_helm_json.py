"""Fail closed unless pinned Checkov emitted nonempty Helm coverage JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CHECK_LISTS = ("passed_checks", "failed_checks", "skipped_checks")
SUMMARY_COUNTS = ("passed", "failed", "skipped")


class CoverageError(ValueError):
    """The Checkov JSON does not prove a nonempty, parse-clean Helm scan."""


def verify_document(document: Any) -> dict[str, int]:
    if isinstance(document, dict):
        reports = [document]
    elif isinstance(document, list) and all(
        isinstance(item, dict) for item in document
    ):
        reports = document
        other_types = {
            item.get("check_type")
            for item in reports
            if item.get("check_type") != "helm"
        }
        if not other_types.issubset({"sca_image"}):
            raise CoverageError(
                "report list contains an unexpected non-Helm scanner type"
            )
    else:
        raise CoverageError(
            "top-level report must be a Checkov report object or report list"
        )

    helm_reports = [item for item in reports if item.get("check_type") == "helm"]
    if len(helm_reports) != 1:
        raise CoverageError(
            "report must contain exactly one report with check_type 'helm'"
        )
    report = helm_reports[0]

    results = report.get("results")
    if not isinstance(results, dict):
        raise CoverageError("results must be an object")
    for name in (*CHECK_LISTS, "parsing_errors"):
        if not isinstance(results.get(name), list):
            raise CoverageError(f"results.{name} must be an array")
    if results["parsing_errors"]:
        raise CoverageError("results.parsing_errors must be empty")
    for name in CHECK_LISTS:
        if any(not isinstance(record, dict) for record in results[name]):
            raise CoverageError(f"results.{name} contains a non-object record")

    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise CoverageError("summary must be an object")
    counts: dict[str, int] = {}
    for summary_name, result_name in zip(SUMMARY_COUNTS, CHECK_LISTS, strict=True):
        value = summary.get(summary_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CoverageError(f"summary.{summary_name} must be a nonnegative integer")
        if value != len(results[result_name]):
            raise CoverageError(
                f"summary.{summary_name} does not match the results array"
            )
        counts[summary_name] = value

    parse_count = summary.get("parsing_errors")
    if (
        isinstance(parse_count, bool)
        or not isinstance(parse_count, int)
        or parse_count != 0
    ):
        raise CoverageError("summary.parsing_errors must be the integer zero")
    resource_count = summary.get("resource_count")
    if (
        isinstance(resource_count, bool)
        or not isinstance(resource_count, int)
        or resource_count <= 0
    ):
        raise CoverageError("summary.resource_count must be a positive integer")
    counts["resource_count"] = resource_count
    counts["total_checks"] = sum(counts[name] for name in SUMMARY_COUNTS)
    if counts["total_checks"] <= 0:
        raise CoverageError("Helm report contains no passed, failed, or skipped checks")
    if counts["passed"] + counts["failed"] <= 0:
        raise CoverageError(
            "Helm report contains no evaluated checks; skipped-only coverage is insufficient"
        )
    counts["evaluated_checks"] = counts["passed"] + counts["failed"]
    return counts


def verify_file(path: Path) -> dict[str, int]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageError(f"cannot read a valid JSON report from {path}") from error
    return verify_document(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        counts = verify_file(args.report)
    except CoverageError as error:
        print(f"error: Checkov Helm coverage failed: {error}", file=sys.stderr)
        return 2
    print(
        "Checkov Helm JSON coverage verified: "
        f"resources={counts['resource_count']} checks={counts['total_checks']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
