"""Validate Semgrep SARIF and its narrowly scoped in-source suppressions.

Semgrep's SARIF writer intentionally keeps ``# nosemgrep`` findings in the
report, while the normal scan exit status can remain zero.  This validator is
the blocking contract: every result must either be absent or match an
explicit, line-bound entry in the reviewed suppression ledger.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote


class ValidationError(ValueError):
    """Raised when scanner evidence is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class FindingKey:
    """Stable identity for one source-backed Semgrep result."""

    rule_id: str
    path: str
    start_line: int
    end_line: int


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"unable to read {label}: {path}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def _text_field(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"policy field {field!r} must be non-empty text")
    return value.strip()


def _positive_line(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(f"policy field {field!r} must be a positive integer")
    return value


def _policy_keys(policy: dict[str, Any]) -> set[FindingKey]:
    if policy.get("version") != 1:
        raise ValidationError("suppression policy version must be 1")
    entries = policy.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValidationError("suppression policy entries must be non-empty")

    keys: set[FindingKey] = set()
    today = date.today()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValidationError("suppression policy entry must be an object")
        rule_id = _text_field(entry.get("rule_id"), "rule_id")
        path = _text_field(entry.get("path"), "path").replace("\\", "/")
        start_line = _positive_line(entry.get("start_line"), "start_line")
        end_line = _positive_line(entry.get("end_line"), "end_line")
        if end_line < start_line:
            raise ValidationError(
                "suppression policy end_line must not precede start_line"
            )
        _text_field(entry.get("owner"), "owner")
        _text_field(entry.get("reason"), "reason")
        expires_text = _text_field(entry.get("expires"), "expires")
        try:
            expires = date.fromisoformat(expires_text)
        except ValueError as error:
            raise ValidationError(
                "suppression policy expires must be ISO date"
            ) from error
        if expires < today:
            raise ValidationError(
                f"suppression policy entry is expired: {path}:{start_line}"
            )
        key = FindingKey(rule_id, path, start_line, end_line)
        if key in keys:
            raise ValidationError(
                f"duplicate suppression policy entry: {path}:{start_line}"
            )
        keys.add(key)
    return keys


def _finding_key(result: dict[str, Any]) -> FindingKey:
    rule_id = result.get("ruleId")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ValidationError("Semgrep result has no ruleId")
    locations = result.get("locations")
    if not isinstance(locations, list) or not locations:
        raise ValidationError(f"Semgrep result {rule_id!r} has no location")
    first = locations[0]
    if not isinstance(first, dict):
        raise ValidationError(f"Semgrep result {rule_id!r} has an invalid location")
    physical = first.get("physicalLocation")
    if not isinstance(physical, dict):
        raise ValidationError(f"Semgrep result {rule_id!r} has no physical location")
    artifact = physical.get("artifactLocation")
    region = physical.get("region")
    if not isinstance(artifact, dict) or not isinstance(region, dict):
        raise ValidationError(f"Semgrep result {rule_id!r} has an incomplete location")
    raw_path = artifact.get("uri")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValidationError(f"Semgrep result {rule_id!r} has no source path")
    path = unquote(raw_path).replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    start_line = region.get("startLine")
    end_line = region.get("endLine", start_line)
    if (
        isinstance(start_line, bool)
        or not isinstance(start_line, int)
        or start_line < 1
        or isinstance(end_line, bool)
        or not isinstance(end_line, int)
        or end_line < start_line
    ):
        raise ValidationError(f"Semgrep result {rule_id!r} has invalid line range")
    return FindingKey(rule_id.strip(), path, start_line, end_line)


def _is_line_bound_in_source_suppression(result: dict[str, Any]) -> bool:
    suppressions = result.get("suppressions", [])
    if not isinstance(suppressions, list) or len(suppressions) != 1:
        return False
    suppression = suppressions[0]
    return isinstance(suppression, dict) and suppression.get("kind") == "inSource"


def validate_report(
    report_path: Path, policy_path: Path, *, scanner_status: int
) -> None:
    """Raise :class:`ValidationError` unless the complete scan is admissible."""

    if scanner_status not in (0, 1):
        raise ValidationError(
            f"scanner exit status {scanner_status} indicates a scan error"
        )
    report = _load_object(report_path, "Semgrep SARIF report")
    policy = _load_object(policy_path, "Semgrep suppression policy")
    if report.get("version") != "2.1.0":
        raise ValidationError("Semgrep SARIF version must be 2.1.0")
    runs = report.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValidationError("Semgrep SARIF runs must be non-empty")
    allowed = _policy_keys(policy)
    observed: set[FindingKey] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ValidationError("Semgrep SARIF run must be an object")
        invocations = run.get("invocations", [])
        if not isinstance(invocations, list) or not invocations:
            raise ValidationError("Semgrep SARIF run has no invocation evidence")
        if any(
            not isinstance(invocation, dict)
            or invocation.get("executionSuccessful") is not True
            for invocation in invocations
        ):
            raise ValidationError("Semgrep execution was not successful")
        results = run.get("results", [])
        if not isinstance(results, list):
            raise ValidationError("Semgrep SARIF results must be a list")
        for result in results:
            if not isinstance(result, dict):
                raise ValidationError("Semgrep SARIF result must be an object")
            key = _finding_key(result)
            if not _is_line_bound_in_source_suppression(result) or key not in allowed:
                raise ValidationError(
                    f"Semgrep result {key.rule_id} at {key.path}:{key.start_line} is not covered by the reviewed suppression ledger"
                )
            observed.add(key)
    missing = allowed - observed
    if missing:
        first = sorted(missing, key=lambda item: (item.path, item.start_line))[0]
        raise ValidationError(
            f"suppression policy entry was not observed in this scan: {first.path}:{first.start_line}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--scanner-status", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        validate_report(args.report, args.policy, scanner_status=args.scanner_status)
    except ValidationError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print("Semgrep SARIF and suppression ledger are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
