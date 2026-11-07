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

    assert (validate_npm_overrides(REPOSITORY_ROOT / "frontend", allowlist)) is None


def test_unapproved_high_severity_advisory_remains_fail_closed() -> None:
    with pytest.raises(AuditFailure, match="not in the allowlist"):
        check_allowances({"unapproved-advisory"}, [], ecosystem="npm")


def test_glob_security_pin_matches_manifest_and_lock() -> None:
    frontend = REPOSITORY_ROOT / "frontend"
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    allowlist = load_allowlist(REPOSITORY_ROOT / "security/audit-allowlist.yaml")
    entries = allowlist["npm"]["overrides"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["package"] == "glob"
    version = entry["pinned_version"]
    assert tuple(int(part) for part in version.split(".")) >= (14, 0, 2)
    assert manifest["devDependencies"]["glob"] == version
    assert manifest["overrides"]["glob"] == version
    assert lock["packages"][""]["devDependencies"]["glob"] == version
    assert lock["packages"]["node_modules/glob"]["version"] == version
    assert entry["owner"] == "frontend@university.example"
    assert str(entry["expires"]) == "2026-12-31"
    assert allowlist["npm"]["advisories"] == []


def test_modern_minimatch_override_preserves_legacy_api_boundaries() -> None:
    frontend = REPOSITORY_ROOT / "frontend"
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    packages = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))[
        "packages"
    ]
    overrides = manifest["overrides"]
    assert "minimatch" not in overrides
    modern_version = overrides["minimatch@>=10"]
    assert tuple(int(part) for part in modern_version.split(".")) >= (11, 0, 2)
    assert packages["node_modules/minimatch"]["version"] == modern_version
    # eslint-plugin-react and eslint-plugin-jsx-a11y call minimatch@3's CommonJS
    # function export. minimatch@11 exports an object instead, so a direct
    # registry replacement fails at the call site. Both consumers therefore
    # resolve to the repository-owned adapter, which keeps the legacy call shape
    # over the patched minimatch@11 engine.
    adapter_path = "scripts/minimatch-3-compat"
    adapter_name = "@university-ecosystem/minimatch-3-compat"
    adapter_spec = "file:./scripts/minimatch-3-compat"
    assert overrides["minimatch@3.1.5"] == adapter_spec
    assert manifest["devDependencies"]["minimatch"] == modern_version
    assert packages[""]["devDependencies"]["minimatch"] == modern_version
    # The root anchor keeps npm's file: link at the frontend-relative adapter path.
    assert manifest["devDependencies"][adapter_name] == adapter_spec
    assert packages[""]["devDependencies"][adapter_name] == adapter_spec
    adapter = packages[adapter_path]
    assert adapter["name"] == adapter_name
    assert adapter["dependencies"] == {"minimatch": modern_version}
    for consumer in ("eslint-plugin-react", "eslint-plugin-jsx-a11y"):
        edge = packages[f"node_modules/{consumer}/node_modules/minimatch"]
        assert edge == {"resolved": adapter_path, "link": True}, (
            f"{consumer} minimatch must resolve to the repository-owned adapter"
        )
    assert not any(
        f"/node_modules/{removed}/" in f"/{package_path}/"
        for package_path in packages
        for removed in ("jake", "filelist")
    ), "obsolete Jake/filelist dependency chain must remain absent"
    matcher = "@isaacs/nonrecursive-glob-match"
    assert overrides[matcher] == "1.0.2"
    assert packages[f"node_modules/{matcher}"]["version"] == overrides[matcher]
    # Every registry minimatch record must be at or above the GHSA-g3hv-75wg-m249 fix.
    for package_path, metadata in packages.items():
        if not package_path.endswith("node_modules/minimatch") or metadata.get("link"):
            continue
        installed = tuple(int(part) for part in metadata["version"].split("."))
        assert installed >= (11, 0, 1), f"{package_path} is below minimatch 11.0.1"


@pytest.mark.parametrize(
    "package_path",
    [
        "node_modules/jake",
        "node_modules/filelist",
        "node_modules/ejs/node_modules/jake",
        "node_modules/jake/node_modules/filelist",
        "node_modules/filelist/node_modules/minimatch",
    ],
)
def test_removed_jake_filelist_chain_cannot_return(
    package_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    source = REPOSITORY_ROOT / "frontend"
    (frontend / "package.json").write_bytes((source / "package.json").read_bytes())
    lock = json.loads((source / "package-lock.json").read_text(encoding="utf-8"))
    lock["packages"][package_path] = {"version": "1.0.0"}
    (frontend / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    monkeypatch.setitem(globals(), "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(AssertionError, match="obsolete Jake/filelist"):
        test_modern_minimatch_override_preserves_legacy_api_boundaries()


@pytest.mark.parametrize("consumer", ["eslint-plugin-react", "eslint-plugin-jsx-a11y"])
def test_legacy_eslint_minimatch_cannot_be_replaced_by_modern_registry_major(
    consumer: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A direct minimatch@11 registry edge breaks the legacy CommonJS call shape."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    source = REPOSITORY_ROOT / "frontend"
    (frontend / "package.json").write_bytes((source / "package.json").read_bytes())
    lock = json.loads((source / "package-lock.json").read_text(encoding="utf-8"))
    modern = lock["packages"]["node_modules/minimatch"]
    lock["packages"][f"node_modules/{consumer}/node_modules/minimatch"] = {
        "version": modern["version"],
        "resolved": modern["resolved"],
        "integrity": modern["integrity"],
    }
    (frontend / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    monkeypatch.setitem(globals(), "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(
        AssertionError,
        match=f"{consumer} minimatch must resolve to the repository-owned adapter",
    ):
        test_modern_minimatch_override_preserves_legacy_api_boundaries()


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
