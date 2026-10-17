"""Fail-closed contracts for dependency audit policy metadata."""

from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import audit_dependencies
from scripts.audit_dependencies import (
    AuditFailure,
    audit_npm,
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


def test_advisory_allowlist_entry_without_expiry_fails_closed() -> None:
    with pytest.raises(
        AuditFailure,
        match="npm advisory allowlist entry missing expiry date",
    ):
        check_allowances(
            {"GHSA-example"},
            [
                {
                    "id": "GHSA-example",
                    "package": "example-package",
                    "owner": "frontend@university.example",
                }
            ],
            ecosystem="npm",
        )


def test_expired_advisory_allowlist_entry_fails_closed() -> None:
    with pytest.raises(AuditFailure, match="expired on 2000-01-01"):
        check_allowances(
            {"GHSA-example"},
            [
                {
                    "id": "GHSA-example",
                    "package": "example-package",
                    "owner": "frontend@university.example",
                    "expires": "2000-01-01",
                }
            ],
            ecosystem="npm",
        )


def test_expired_npm_override_fails_before_running_npm_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    npm_audit = Mock()
    monkeypatch.setattr(audit_dependencies, "collect_npm_advisory_ids", npm_audit)
    package_dir = tmp_path / "missing-npm-project"
    assert not (package_dir / "package.json").exists()

    with pytest.raises(AuditFailure, match="NPM override entry for 'glob' expired"):
        audit_npm(
            Namespace(npm=str(package_dir)),
            {
                "npm": {
                    "overrides": [
                        {
                            "package": "glob",
                            "pinned_version": "13.0.6",
                            "owner": "frontend@university.example",
                            "expires": "2000-01-01",
                        }
                    ]
                }
            },
        )

    npm_audit.assert_not_called()
