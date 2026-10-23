#!/usr/bin/env python3
"""Fail-closed preflight for the pinned Kyverno negative-test fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

EXPECTED_FIXTURE = PurePosixPath(
    "k8s/kyverno/tests/disallow-host-access/host-access.yaml"
)
EXPECTED_FIXTURE_SHA256 = (
    "866376024f7d68dc94ffa11e3ad010f5edbcd610af7f61342c46f33b7400cd45"
)
EXPECTED_IGNORE_POLICY_SHA256 = (
    "4eef1ee1d1560fade64ec1d7b7e3a2b7d91c58e29d4f0607bb08a04fa39f4e66"
)
EXPECTED_IGNORE_EXPIRY = date(2026, 11, 22)
MAX_IGNORE_DAYS = 30
EXPECTED_REPORT_TARGET = "host-access.yaml"

# These are the only existing global ignore identities that occur in this
# fixture's unfiltered report. The policy-file digest below binds their exact
# unchanged baseline entries as well as the two proposed path-scoped entries.
EXISTING_GLOBAL_IGNORE_IDS = frozenset({"KSV-0009", "KSV-0010", "KSV-0014", "KSV-0118"})

Finding = tuple[str, str, int, int]

# Full no-ignore Trivy 0.75.0 output for the pinned source bytes. Checking this
# entire multiset prevents a new finding from being hidden by the old global
# ignore rules while deriving the five residual tuples that need new policy.
EXPECTED_RAW_FINDINGS: Counter[Finding] = Counter(
    [
        ("KSV-0008", "HIGH", 30, 35),
        ("KSV-0009", "HIGH", 6, 11),
        ("KSV-0009", "HIGH", 89, 102),
        ("KSV-0010", "HIGH", 18, 23),
        ("KSV-0010", "HIGH", 89, 102),
        ("KSV-0014", "HIGH", 33, 35),
        ("KSV-0014", "HIGH", 9, 11),
        ("KSV-0014", "HIGH", 48, 50),
        ("KSV-0014", "HIGH", 21, 23),
        ("KSV-0014", "HIGH", 59, 64),
        ("KSV-0014", "HIGH", 80, 82),
        ("KSV-0014", "HIGH", 73, 78),
        ("KSV-0014", "HIGH", 97, 102),
        ("KSV-0024", "HIGH", 59, 64),
        ("KSV-0024", "HIGH", 80, 82),
        ("KSV-0024", "HIGH", 73, 78),
        ("KSV-0024", "HIGH", 97, 102),
        ("KSV-0118", "HIGH", 33, 35),
        ("KSV-0118", "HIGH", 9, 11),
        ("KSV-0118", "HIGH", 48, 50),
        ("KSV-0118", "HIGH", 21, 23),
        ("KSV-0118", "HIGH", 59, 64),
        ("KSV-0118", "HIGH", 80, 82),
        ("KSV-0118", "HIGH", 73, 78),
        ("KSV-0118", "HIGH", 97, 102),
        ("KSV-0118", "HIGH", 30, 35),
        ("KSV-0118", "HIGH", 6, 11),
        ("KSV-0118", "HIGH", 42, 50),
        ("KSV-0118", "HIGH", 18, 23),
        ("KSV-0118", "HIGH", 57, 64),
        ("KSV-0118", "HIGH", 71, 82),
        ("KSV-0118", "HIGH", 89, 102),
    ]
)
EXPECTED_RESIDUAL_FINDINGS: Counter[Finding] = Counter(
    [
        ("KSV-0008", "HIGH", 30, 35),
        ("KSV-0024", "HIGH", 59, 64),
        ("KSV-0024", "HIGH", 73, 78),
        ("KSV-0024", "HIGH", 80, 82),
        ("KSV-0024", "HIGH", 97, 102),
    ]
)


class ValidationError(ValueError):
    """Input failed the exact source-bound preflight contract."""


def resolve_repo_target(repo_root: Path, target: Path | str) -> tuple[Path, Path]:
    """Resolve one exact fixture, rejecting traversal, aliases, and outside paths."""
    try:
        root = Path(repo_root).resolve(strict=True)
    except OSError as exc:
        raise ValidationError("repository root is unavailable") from exc

    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValidationError("fixture target is unavailable") from exc

    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError(
            "fixture target resolves outside repository root"
        ) from exc

    if PurePosixPath(relative.as_posix()) != EXPECTED_FIXTURE:
        raise ValidationError("fixture target is not the pinned repository path")
    if not resolved.is_file():
        raise ValidationError("fixture target is not a regular file")
    return root, resolved


def _resolve_policy(root: Path) -> Path:
    policy = root / ".trivyignore.yaml"
    try:
        resolved = policy.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValidationError(
            "Trivy ignore policy is missing or outside repository root"
        ) from exc
    if PurePosixPath(relative.as_posix()) != PurePosixPath(".trivyignore.yaml"):
        raise ValidationError("Trivy ignore policy resolves to an unexpected path")
    return resolved


def _check_sha256(path: Path, expected: str, label: str) -> None:
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValidationError(f"cannot read {label}") from exc
    if actual != expected:
        raise ValidationError(f"{label} SHA-256 does not match the approved source")


def validate_expiry(today: date | None = None) -> None:
    """Require the pinned exception date to be live and at most 90 days away."""
    if today is None:
        today = datetime.now(UTC).date()
    days_remaining = (EXPECTED_IGNORE_EXPIRY - today).days
    if days_remaining < 1:
        raise ValidationError("fixture exception has expired")
    if days_remaining > MAX_IGNORE_DAYS:
        raise ValidationError(
            f"fixture exception expiry is more than {MAX_IGNORE_DAYS} days away"
        )


def _finding_from_json(value: Any) -> Finding:
    if not isinstance(value, dict):
        raise ValidationError("misconfiguration entry is not an object")
    rule_id = value.get("ID")
    severity = value.get("Severity")
    metadata = value.get("CauseMetadata")
    if not isinstance(rule_id, str) or re.fullmatch(r"KSV-[0-9]{4}", rule_id) is None:
        raise ValidationError("misconfiguration entry has a malformed rule ID")
    if not isinstance(severity, str):
        raise ValidationError("misconfiguration entry has a malformed severity")
    if not isinstance(metadata, dict):
        raise ValidationError("misconfiguration entry has no location metadata")
    start = metadata.get("StartLine")
    end = metadata.get("EndLine")
    if type(start) is not int or type(end) is not int or start < 1 or end < start:
        raise ValidationError("misconfiguration entry has a malformed line range")
    return rule_id, severity, start, end


def _format_findings(findings: Counter[Finding]) -> str:
    return (
        ", ".join(
            f"{rule}/{severity}:{start}-{end} x{count}"
            for (rule, severity, start, end), count in sorted(findings.items())
        )
        or "none"
    )


def validate_report(report_path: Path) -> None:
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Trivy JSON report is missing or malformed") from exc

    if not isinstance(report, dict) or not isinstance(report.get("Results"), list):
        raise ValidationError("Trivy JSON report has no Results array")
    results = report["Results"]
    if len(results) != 1 or not isinstance(results[0], dict):
        raise ValidationError(
            "report must contain exactly the single-file fixture result"
        )
    result = results[0]
    if result.get("Target") != EXPECTED_REPORT_TARGET:
        raise ValidationError(
            "Trivy single-file target does not match host-access.yaml"
        )
    raw_values = result.get("Misconfigurations")
    if not isinstance(raw_values, list):
        raise ValidationError("fixture result has no Misconfigurations array")

    raw = Counter(_finding_from_json(value) for value in raw_values)
    if raw != EXPECTED_RAW_FINDINGS:
        missing = EXPECTED_RAW_FINDINGS - raw
        extra = raw - EXPECTED_RAW_FINDINGS
        raise ValidationError(
            "raw finding multiset differs; "
            f"missing=[{_format_findings(missing)}], extra=[{_format_findings(extra)}]"
        )

    residual = Counter(
        finding
        for finding in raw.elements()
        if finding[0] not in EXISTING_GLOBAL_IGNORE_IDS
    )
    if residual != EXPECTED_RESIDUAL_FINDINGS:
        raise ValidationError(
            "residual finding multiset differs after unchanged global ignores; "
            f"got=[{_format_findings(residual)}]"
        )


def validate_preflight(
    repo_root: Path,
    target: Path | str,
    report_path: Path,
    *,
    today: date | None = None,
) -> None:
    root, fixture = resolve_repo_target(repo_root, target)
    _check_sha256(fixture, EXPECTED_FIXTURE_SHA256, "fixture")
    _check_sha256(
        _resolve_policy(root), EXPECTED_IGNORE_POLICY_SHA256, "Trivy ignore policy"
    )
    validate_expiry(today)
    validate_report(report_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_preflight(args.repo_root, args.target, args.report)
    except ValidationError as exc:
        print(f"Trivy fixture preflight failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Trivy fixture preflight verified: pinned source and exact five residual findings."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
