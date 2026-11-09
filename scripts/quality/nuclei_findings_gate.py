"""Fail-closed gate for Nuclei DAST exports (AUD-381).

The workflow uses Nuclei's native ``-json-export``, which writes one JSON array
(``[]`` when nothing matched). Any other shape, ambiguous JSON, an empty export,
or a record without a recognised severity makes the scan result unknown, so
the gate fails.

Owner decision (2026-11-04): findings of severity medium, high or critical fail
the job.  Info, low and unknown findings are published but do not fail it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn

ALLOWED_SEVERITIES = frozenset({"info", "low", "medium", "high", "critical", "unknown"})
BLOCKING_SEVERITIES = frozenset({"medium", "high", "critical"})


class ExportError(ValueError):
    """Raised when a Nuclei export is empty, malformed, or unrecognised."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExportError("JSON object has a duplicate key")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> NoReturn:
    raise ExportError(f"invalid JSON constant: {value}")


def parse_records(text: str) -> list[dict[str, Any]]:
    """Return the finding records of exactly one complete native JSON array."""

    try:
        raw_records = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except json.JSONDecodeError as error:
        raise ExportError("export is not valid JSON") from error
    if not isinstance(raw_records, list):
        raise ExportError("export must be a JSON array")

    records: list[dict[str, Any]] = []
    for record in raw_records:
        if not isinstance(record, dict):
            raise ExportError("finding record must be a JSON object")
        info = record.get("info")
        if not isinstance(info, dict):
            raise ExportError("finding record must carry an info object")
        severity = info.get("severity")
        if not isinstance(severity, str) or severity not in ALLOWED_SEVERITIES:
            raise ExportError("finding record has an unrecognised severity")
        records.append(record)
    return records


def severity_counts(records: list[dict[str, Any]]) -> Counter[str]:
    """Count validated findings by their exact Nuclei severity."""

    return Counter(str(record["info"]["severity"]) for record in records)


def blocking_count(counts: Counter[str]) -> int:
    return sum(counts[severity] for severity in BLOCKING_SEVERITIES)


def _write_summary(summary_path: Path | None, lines: list[str]) -> None:
    if summary_path is None:
        return
    with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def _read_export(export_path: Path) -> list[dict[str, Any]]:
    if not export_path.is_file():
        raise ExportError("Nuclei produced no JSON export; the scan result is unknown.")
    try:
        return parse_records(export_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ExportError) as error:
        raise ExportError(
            "Could not validate Nuclei JSON export; the scan result is unknown."
        ) from error


def check_sarif(export_path: Path, sarif_path: Path) -> int:
    """Require SARIF for findings; Nuclei omits it for a clean export."""

    try:
        records = _read_export(export_path)
    except ExportError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    if records and not sarif_path.is_file():
        print("::error::Nuclei produced findings but no SARIF report.", file=sys.stderr)
        return 1
    return 0


def run_gate(export_path: Path, summary_path: Path | None) -> int:
    """Validate the export, publish a summary, and return the exit status."""

    try:
        records = _read_export(export_path)
    except ExportError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1

    counts = severity_counts(records)
    blocking = blocking_count(counts)
    summary = [
        "### Nuclei DAST findings",
        "",
        "| Severity | Count | Blocks the job |",
        "| --- | ---: | --- |",
    ]
    for severity in ("critical", "high", "medium", "low", "info", "unknown"):
        summary.append(
            f"| {severity} | {counts[severity]} | "
            f"{'yes' if severity in BLOCKING_SEVERITIES else 'no'} |"
        )
    _write_summary(summary_path, summary)

    if blocking:
        print(
            f"::error::Nuclei reported {blocking} medium, high or critical finding(s).",
            file=sys.stderr,
        )
        return 1
    print("Nuclei reported no medium, high or critical findings.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path, help="Nuclei native JSON array export")
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Markdown job summary file to append to (for GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--check-sarif",
        type=Path,
        help="Require this SARIF file when the validated JSON has findings",
    )
    arguments = parser.parse_args(argv)
    if arguments.check_sarif is not None:
        return check_sarif(arguments.export, arguments.check_sarif)
    return run_gate(arguments.export, arguments.summary_file)


if __name__ == "__main__":
    raise SystemExit(main())
