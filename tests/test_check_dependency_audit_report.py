from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "check_dependency_audit_report.py"
_MISSING = object()
_CVSS_MISSING = object()


def _pip_vulnerability(
    *,
    identifier: str = "PYSEC-2099-1",
    aliases: list[str] | None = None,
    fix_versions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "aliases": aliases if aliases is not None else ["CVE-2099-0001"],
        "fix_versions": fix_versions if fix_versions is not None else [],
    }


def _pip_dependency(
    *,
    name: str = "demo-package",
    vulnerabilities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0.0",
        "vulns": vulnerabilities if vulnerabilities is not None else [],
    }


def _pip_report(dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    return {"dependencies": dependencies, "fixes": []}


def _allowlist_entry(*, identifier: str = "PYSEC-2099-1") -> dict[str, str]:
    return {
        "id": identifier,
        "package": "demo-package",
        "owner": "security@example.test",
        "reason": "Accepted temporarily while the dependency update is reviewed.",
        "expires": "2099-12-31",
    }


def _allowlist(*entries: dict[str, str]) -> dict[str, Any]:
    return {"pip": {"advisories": list(entries)}}


def _cargo_finding(*, cvss: object = _CVSS_MISSING) -> dict[str, Any]:
    advisory: dict[str, Any] = {"id": "RUSTSEC-2099-0001"}
    if cvss is not _CVSS_MISSING:
        advisory["cvss"] = cvss
    return {
        "advisory": advisory,
        "package": {"name": "demo-crate", "version": "1.0.0"},
    }


def _cargo_report(
    findings: list[dict[str, Any]],
    *,
    found: bool | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    return {
        "database": {"advisory-count": 1},
        "lockfile": {"dependency-count": 1},
        "settings": {"severity": "high", "ignore": []},
        "vulnerabilities": {
            "found": bool(findings) if found is None else found,
            "count": len(findings) if count is None else count,
            "list": findings,
        },
        "warnings": {},
    }


def _run_validator(
    tmp_path: Path,
    mode: str,
    *,
    payload: object = _MISSING,
    scanner_status: int = 0,
    allowlist: dict[str, Any] | None = None,
    report_only: bool = False,
    block_yaml_import: bool = False,
) -> subprocess.CompletedProcess[str]:
    report_path = tmp_path / f"{mode}-audit.json"
    if payload is not _MISSING:
        content = payload if isinstance(payload, str) else json.dumps(payload)
        report_path.write_text(content, encoding="utf-8")

    command = [
        sys.executable,
        str(VALIDATOR),
        mode,
        "--report",
        str(report_path),
        "--scanner-status",
        str(scanner_status),
    ]
    if mode == "pip":
        allowlist_path = tmp_path / "audit-allowlist.yaml"
        allowlist_path.write_text(
            yaml.safe_dump(allowlist if allowlist is not None else _allowlist()),
            encoding="utf-8",
        )
        command.extend(["--allowlist", str(allowlist_path)])
    if report_only:
        command.append("--report-only")

    environment = None
    if block_yaml_import:
        blocked_imports = tmp_path / "blocked-imports"
        blocked_imports.mkdir()
        (blocked_imports / "yaml.py").write_text(
            'raise ModuleNotFoundError("yaml intentionally unavailable")\n',
            encoding="utf-8",
        )
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            path
            for path in (str(blocked_imports), existing_pythonpath)
            if path is not None
        )

    return subprocess.run(  # noqa: S603
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


@pytest.mark.parametrize("mode", ["pip", "cargo"])
@pytest.mark.parametrize(
    "payload",
    [_MISSING, "", " \n\t", "{", [], {}, {"dependencies": [], "fixes": []}],
)
def test_common_invalid_reports_fail_closed(
    tmp_path: Path, mode: str, payload: object
) -> None:
    result = _run_validator(tmp_path, mode, payload=payload)
    assert result.returncode != 0


@pytest.mark.parametrize("mode", ["pip", "cargo"])
@pytest.mark.parametrize("scanner_status", [2, 127])
def test_operational_scanner_failures_are_rejected(
    tmp_path: Path, mode: str, scanner_status: int
) -> None:
    payload = _pip_report([_pip_dependency()]) if mode == "pip" else _cargo_report([])
    result = _run_validator(
        tmp_path,
        mode,
        payload=payload,
        scanner_status=scanner_status,
        report_only=mode == "cargo",
    )
    assert result.returncode != 0


def test_pip_clean_inventory_matches_zero_status(tmp_path: Path) -> None:
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([_pip_dependency()]),
        scanner_status=0,
    )
    assert result.returncode == 0, result.stderr


def test_cargo_mode_does_not_require_pyyaml(tmp_path: Path) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report([]),
        scanner_status=0,
        block_yaml_import=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("fix_versions", [[], ["2.0.0"]])
def test_pip_blocks_unapproved_advisories_regardless_of_fix_availability(
    tmp_path: Path, fix_versions: list[str]
) -> None:
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report(
            [
                _pip_dependency(
                    vulnerabilities=[_pip_vulnerability(fix_versions=fix_versions)]
                )
            ]
        ),
        scanner_status=1,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("allowed_id", ["PYSEC-2099-1", "CVE-2099-0001"])
def test_pip_allowlist_matches_primary_and_alias_ids(
    tmp_path: Path, allowed_id: str
) -> None:
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([_pip_dependency(vulnerabilities=[_pip_vulnerability()])]),
        scanner_status=1,
        allowlist=_allowlist(_allowlist_entry(identifier=allowed_id)),
    )
    assert result.returncode == 0, result.stderr


def test_pip_allowlist_requires_matching_package(tmp_path: Path) -> None:
    entry = _allowlist_entry()
    entry["package"] = "different-package"
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([_pip_dependency(vulnerabilities=[_pip_vulnerability()])]),
        scanner_status=1,
        allowlist=_allowlist(entry),
    )
    assert result.returncode != 0


def test_pip_allowlist_rejects_dormant_entries(tmp_path: Path) -> None:
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([_pip_dependency()]),
        scanner_status=0,
        allowlist=_allowlist(_allowlist_entry()),
    )
    assert result.returncode != 0
    assert "dormant Python advisory allowances" in result.stderr


@pytest.mark.parametrize("field", ["id", "package", "owner", "reason", "expires"])
@pytest.mark.parametrize("missing", [True, False])
def test_pip_allowlist_fields_are_mandatory_and_nonempty(
    tmp_path: Path, field: str, missing: bool
) -> None:
    entry = _allowlist_entry()
    if missing:
        entry.pop(field)
    else:
        entry[field] = "   "
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([_pip_dependency()]),
        allowlist=_allowlist(entry),
    )
    assert result.returncode != 0


def test_pip_allowlist_rejects_expired_entries(tmp_path: Path) -> None:
    entry = _allowlist_entry()
    entry["expires"] = "2000-01-01"
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([_pip_dependency()]),
        allowlist=_allowlist(entry),
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    ("scanner_status", "dependencies"),
    [
        (0, [_pip_dependency(vulnerabilities=[_pip_vulnerability()])]),
        (1, [_pip_dependency()]),
    ],
)
def test_pip_rejects_exit_report_status_mismatches(
    tmp_path: Path,
    scanner_status: int,
    dependencies: list[dict[str, Any]],
) -> None:
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report(dependencies),
        scanner_status=scanner_status,
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "dependency",
    [
        {"name": "skipped", "skip_reason": "Dependency could not be audited"},
        {"name": "", "version": "1.0", "vulns": []},
        {"name": "demo-package", "vulns": []},
        {"name": "demo-package", "version": "1.0", "vulns": {}},
        {
            "name": "demo-package",
            "version": "1.0",
            "vulns": [{"aliases": [], "fix_versions": []}],
        },
        {
            "name": "demo-package",
            "version": "1.0",
            "vulns": [{"id": "PYSEC-1", "aliases": "CVE-1", "fix_versions": []}],
        },
        {
            "name": "demo-package",
            "version": "1.0",
            "vulns": [{"id": "PYSEC-1", "aliases": [], "fix_versions": "2.0"}],
        },
    ],
)
def test_pip_rejects_skipped_and_malformed_dependency_records(
    tmp_path: Path, dependency: dict[str, Any]
) -> None:
    result = _run_validator(
        tmp_path,
        "pip",
        payload=_pip_report([dependency]),
        scanner_status=0,
    )
    assert result.returncode != 0


CVSS_V3 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
CVSS_V4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def test_cargo_consistent_clean_report_matches_zero_status(tmp_path: Path) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report([]),
        scanner_status=0,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "section", ["database", "lockfile", "settings", "vulnerabilities", "warnings"]
)
def test_cargo_requires_exact_root_sections(tmp_path: Path, section: str) -> None:
    payload = _cargo_report([])
    payload.pop(section)
    result = _run_validator(tmp_path, "cargo", payload=payload, scanner_status=0)
    assert result.returncode != 0

    payload = _cargo_report([])
    payload["unexpected"] = {}
    result = _run_validator(tmp_path, "cargo", payload=payload, scanner_status=0)
    assert result.returncode != 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"advisory-count": 0},
        {"advisory-count": True},
        {"advisory-count": "1"},
    ],
)
def test_cargo_requires_positive_database_advisory_count(
    tmp_path: Path, value: object
) -> None:
    payload = _cargo_report([])
    payload["database"] = value
    result = _run_validator(tmp_path, "cargo", payload=payload, scanner_status=0)
    assert result.returncode != 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"dependency-count": 0},
        {"dependency-count": True},
        {"dependency-count": "1"},
    ],
)
def test_cargo_requires_positive_lockfile_dependency_count(
    tmp_path: Path, value: object
) -> None:
    payload = _cargo_report([])
    payload["lockfile"] = value
    result = _run_validator(tmp_path, "cargo", payload=payload, scanner_status=0)
    assert result.returncode != 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"severity": "medium", "ignore": []},
        {"severity": "high", "ignore": ["RUSTSEC-2099-0001"]},
    ],
)
def test_cargo_requires_effective_high_severity_and_empty_ignore_policy(
    tmp_path: Path, value: object
) -> None:
    payload = _cargo_report([])
    payload["settings"] = value
    result = _run_validator(tmp_path, "cargo", payload=payload, scanner_status=0)
    assert result.returncode != 0


@pytest.mark.parametrize("value", [None, [], "warnings"])
def test_cargo_requires_warnings_object(tmp_path: Path, value: object) -> None:
    payload = _cargo_report([])
    payload["warnings"] = value
    result = _run_validator(tmp_path, "cargo", payload=payload, scanner_status=0)
    assert result.returncode != 0


@pytest.mark.parametrize("cvss", [_CVSS_MISSING, None, CVSS_V3, CVSS_V4])
def test_cargo_report_only_accepts_valid_v3_v4_and_unknown_findings(
    tmp_path: Path, cvss: object
) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report([_cargo_finding(cvss=cvss)]),
        scanner_status=1,
        report_only=True,
    )
    assert result.returncode == 0, result.stderr


def test_cargo_policy_gate_blocks_valid_findings(tmp_path: Path) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report([_cargo_finding(cvss=CVSS_V3)]),
        scanner_status=1,
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "cvss",
    [7.5, "7.5", "CVSS:2.0/AV:N/AC:L/Au:N/C:C/I:C/A:C", "CVSS:3.1/AV:N"],
)
def test_cargo_rejects_numeric_and_malformed_cvss(tmp_path: Path, cvss: object) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report([_cargo_finding(cvss=cvss)]),
        scanner_status=1,
        report_only=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    ("found", "count", "findings"),
    [
        (False, 1, [_cargo_finding()]),
        (True, 0, [_cargo_finding()]),
        (True, 1, []),
    ],
)
def test_cargo_rejects_count_found_list_mismatches(
    tmp_path: Path,
    found: bool,
    count: int,
    findings: list[dict[str, Any]],
) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report(findings, found=found, count=count),
        scanner_status=1,
        report_only=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    ("scanner_status", "findings"),
    [(0, [_cargo_finding()]), (1, [])],
)
def test_cargo_rejects_exit_report_status_mismatches(
    tmp_path: Path,
    scanner_status: int,
    findings: list[dict[str, Any]],
) -> None:
    result = _run_validator(
        tmp_path,
        "cargo",
        payload=_cargo_report(findings),
        scanner_status=scanner_status,
        report_only=True,
    )
    assert result.returncode != 0
