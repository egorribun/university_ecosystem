"""Fail-closed contracts for dependency audit policy metadata."""

from pathlib import Path

import pytest

from scripts.audit_dependencies import (
    AuditFailure,
    check_allowances,
    load_allowlist,
    validate_npm_overrides,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_repository_npm_override_pins_match_package_json() -> None:
    allowlist = load_allowlist(REPOSITORY_ROOT / "security/audit-allowlist.yaml")

    validate_npm_overrides(REPOSITORY_ROOT / "frontend", allowlist)


def test_unapproved_high_severity_advisory_remains_fail_closed() -> None:
    with pytest.raises(AuditFailure, match="not in the allowlist"):
        check_allowances({"unapproved-advisory"}, [], ecosystem="npm")
