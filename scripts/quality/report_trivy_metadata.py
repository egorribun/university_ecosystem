#!/usr/bin/env python3
"""Print bounded vulnerability metadata without exposing SARIF source or secrets."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MAX_BYTES = 8 * 1024 * 1024
MAX_RESULTS = 100
MAX_FIELD = 256
LABELS = {
    "Package": "package",
    "Installed Version": "installed_version",
    "Severity": "severity",
    "Fixed Version": "fixed_version",
}
VULNERABILITY_CLASSES = {
    "OsPackageVulnerability",
    "LanguageSpecificPackageVulnerability",
}


def _bounded(value: object) -> str:
    return value[:MAX_FIELD] if isinstance(value, str) else ""


def summarize_report(report: dict[str, Any]) -> list[str]:
    """Project only allowlisted vulnerability fields; never return raw messages."""
    lines: list[str] = []
    total = vulnerabilities = printed = omitted = 0
    for run in report.get("runs", []):
        rules = {
            rule.get("id"): rule
            for rule in run.get("tool", {}).get("driver", {}).get("rules", [])
        }
        for result in run.get("results", []):
            total += 1
            rule_id = result.get("ruleId", "")
            if rules.get(rule_id, {}).get("name") not in VULNERABILITY_CLASSES:
                omitted += 1
                continue
            vulnerabilities += 1
            if printed >= MAX_RESULTS:
                continue
            record = {"rule_id": _bounded(rule_id)}
            for line in result.get("message", {}).get("text", "").splitlines():
                label, separator, value = line.partition(": ")
                if separator and label in LABELS:
                    record[LABELS[label]] = _bounded(value)
            locations = result.get("locations", [])
            if locations:
                physical = locations[0].get("physicalLocation", {})
                record["location"] = _bounded(
                    physical.get("artifactLocation", {}).get("uri", "")
                )
            lines.append("TRIVY_VULNERABILITY " + json.dumps(record, sort_keys=True))
            printed += 1
    summary = {
        "results": total,
        "vulnerabilities": vulnerabilities,
        "printed": printed,
        "omitted_non_vulnerability": omitted,
    }
    lines.append("TRIVY_SUMMARY " + json.dumps(summary, sort_keys=True))
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Read one size-bounded SARIF file and emit only the metadata projection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sarif_path", type=Path)
    args = parser.parse_args(argv)
    try:
        with args.sarif_path.open("rb") as report_file:
            raw = report_file.read(MAX_BYTES + 1)
    except OSError:
        raise SystemExit("Unable to read SARIF report") from None
    if len(raw) > MAX_BYTES:
        raise SystemExit("SARIF report exceeds diagnostic size limit")
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SystemExit("Invalid SARIF report") from None
    if not isinstance(report, dict):
        raise SystemExit("Invalid SARIF report")
    for line in summarize_report(report):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
