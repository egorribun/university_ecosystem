"""Fail-closed contracts for dependency audit policy metadata."""

import json
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


def test_storybook_security_floor_and_aligned_lock() -> None:
    frontend = REPOSITORY_ROOT / "frontend"
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    family = (
        "storybook",
        "eslint-plugin-storybook",
        "@storybook/addon-a11y",
        "@storybook/addon-docs",
        "@storybook/addon-onboarding",
        "@storybook/addon-vitest",
        "@storybook/builder-vite",
        "@storybook/react",
        "@storybook/react-dom-shim",
        "@storybook/react-vite",
    )
    versions = {lock["packages"][f"node_modules/{name}"]["version"] for name in family}
    assert len(versions) == 1
    version = versions.pop()
    parts = tuple(int(part) for part in version.split("."))
    assert len(parts) == 3 and parts >= (10, 6, 2)
    for name in family:
        if name in manifest["devDependencies"]:
            assert manifest["devDependencies"][name] == f"^{version}"
            assert lock["packages"][""]["devDependencies"][name] == f"^{version}"
        assert name not in manifest["dependencies"]

    chromatic = "@chromatic-com/storybook"
    chromatic_version = lock["packages"][f"node_modules/{chromatic}"]["version"]
    chromatic_parts = tuple(int(part) for part in chromatic_version.split("."))
    assert len(chromatic_parts) == 3 and chromatic_parts >= (5, 5, 1)
    assert manifest["devDependencies"][chromatic] == f"^{chromatic_version}"
    assert lock["packages"][""]["devDependencies"][chromatic] == f"^{chromatic_version}"
    assert chromatic not in manifest["dependencies"]
