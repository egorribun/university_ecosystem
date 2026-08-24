from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import cast


class AuditReportError(Exception):
    """Raised when scanner output or dependency policy is invalid."""


@dataclass(frozen=True)
class PipFinding:
    package: str
    identifier: str
    aliases: frozenset[str]


@dataclass(frozen=True)
class PipAllowance:
    package: str
    identifier: str


_PACKAGE_NORMALIZER = re.compile(r"[-_.]+")

_CVSS_V3_METRICS: dict[str, frozenset[str]] = {
    "AV": frozenset({"N", "A", "L", "P"}),
    "AC": frozenset({"L", "H"}),
    "PR": frozenset({"N", "L", "H"}),
    "UI": frozenset({"N", "R"}),
    "S": frozenset({"U", "C"}),
    "C": frozenset({"N", "L", "H"}),
    "I": frozenset({"N", "L", "H"}),
    "A": frozenset({"N", "L", "H"}),
    "E": frozenset({"X", "U", "P", "F", "H"}),
    "RL": frozenset({"X", "O", "T", "W", "U"}),
    "RC": frozenset({"X", "U", "R", "C"}),
    "CR": frozenset({"X", "H", "M", "L"}),
    "IR": frozenset({"X", "H", "M", "L"}),
    "AR": frozenset({"X", "H", "M", "L"}),
    "MAV": frozenset({"X", "N", "A", "L", "P"}),
    "MAC": frozenset({"X", "L", "H"}),
    "MPR": frozenset({"X", "N", "L", "H"}),
    "MUI": frozenset({"X", "N", "R"}),
    "MS": frozenset({"X", "U", "C"}),
    "MC": frozenset({"X", "N", "L", "H"}),
    "MI": frozenset({"X", "N", "L", "H"}),
    "MA": frozenset({"X", "N", "L", "H"}),
}
_CVSS_V3_REQUIRED = frozenset({"AV", "AC", "PR", "UI", "S", "C", "I", "A"})

_CVSS_V4_METRICS: dict[str, frozenset[str]] = {
    "AV": frozenset({"N", "A", "L", "P"}),
    "AC": frozenset({"L", "H"}),
    "AT": frozenset({"N", "P"}),
    "PR": frozenset({"N", "L", "H"}),
    "UI": frozenset({"N", "P", "A"}),
    "VC": frozenset({"H", "L", "N"}),
    "VI": frozenset({"H", "L", "N"}),
    "VA": frozenset({"H", "L", "N"}),
    "SC": frozenset({"H", "L", "N"}),
    "SI": frozenset({"H", "L", "N"}),
    "SA": frozenset({"H", "L", "N"}),
    "E": frozenset({"X", "A", "P", "U"}),
    "CR": frozenset({"X", "H", "M", "L"}),
    "IR": frozenset({"X", "H", "M", "L"}),
    "AR": frozenset({"X", "H", "M", "L"}),
    "MAV": frozenset({"X", "N", "A", "L", "P"}),
    "MAC": frozenset({"X", "L", "H"}),
    "MAT": frozenset({"X", "N", "P"}),
    "MPR": frozenset({"X", "N", "L", "H"}),
    "MUI": frozenset({"X", "N", "P", "A"}),
    "MVC": frozenset({"X", "H", "L", "N"}),
    "MVI": frozenset({"X", "H", "L", "N"}),
    "MVA": frozenset({"X", "H", "L", "N"}),
    "MSC": frozenset({"X", "H", "L", "N"}),
    "MSI": frozenset({"X", "S", "H", "L", "N"}),
    "MSA": frozenset({"X", "S", "H", "L", "N"}),
    "S": frozenset({"X", "N", "P"}),
    "AU": frozenset({"X", "N", "Y"}),
    "R": frozenset({"X", "A", "U", "I"}),
    "V": frozenset({"X", "D", "C"}),
    "RE": frozenset({"X", "L", "M", "H"}),
    "U": frozenset({"X", "Clear", "Green", "Amber", "Red"}),
}
_CVSS_V4_REQUIRED = frozenset(
    {"AV", "AC", "AT", "PR", "UI", "VC", "VI", "VA", "SC", "SI", "SA"}
)


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AuditReportError(f"{label} must be a JSON/YAML object")
    return cast(dict[str, object], value)


def _list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise AuditReportError(f"{label} must be a list")
    return cast(list[object], value)


def _nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditReportError(f"{label} must be a nonempty string")
    return value.strip()


def _string_list(value: object, *, label: str) -> list[str]:
    values = _list(value, label=label)
    return [
        _nonempty_string(item, label=f"{label}[{index}]")
        for index, item in enumerate(values)
    ]


def _canonical_package(name: str) -> str:
    return _PACKAGE_NORMALIZER.sub("-", name).casefold()


def _load_json_report(path: pathlib.Path) -> object:
    if not path.is_file():
        raise AuditReportError(f"audit report is missing: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuditReportError(f"could not read audit report {path}: {exc}") from exc
    if not raw.strip():
        raise AuditReportError(f"audit report is empty: {path}")
    try:
        return cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise AuditReportError(f"audit report is not valid JSON: {exc}") from exc


def _load_pip_allowlist(path: pathlib.Path) -> list[PipAllowance]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise AuditReportError(
            "pip allowlist validation requires the PyYAML package"
        ) from exc

    if not path.is_file():
        raise AuditReportError(f"audit allowlist is missing: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AuditReportError(f"could not load audit allowlist {path}: {exc}") from exc

    root = _mapping(raw, label="allowlist")
    pip_policy = _mapping(root.get("pip"), label="allowlist.pip")
    entries = _list(pip_policy.get("advisories"), label="allowlist.pip.advisories")
    today = dt.datetime.now(dt.UTC).date()
    allowances: list[PipAllowance] = []
    for index, raw_entry in enumerate(entries):
        label = f"allowlist.pip.advisories[{index}]"
        entry = _mapping(raw_entry, label=label)
        identifier = _nonempty_string(entry.get("id"), label=f"{label}.id")
        package = _nonempty_string(entry.get("package"), label=f"{label}.package")
        _nonempty_string(entry.get("owner"), label=f"{label}.owner")
        _nonempty_string(entry.get("reason"), label=f"{label}.reason")

        expires_raw = entry.get("expires")
        if isinstance(expires_raw, dt.date):
            expires = expires_raw
        else:
            expires_text = _nonempty_string(expires_raw, label=f"{label}.expires")
            try:
                expires = dt.date.fromisoformat(expires_text)
            except ValueError as exc:
                raise AuditReportError(f"{label}.expires must use YYYY-MM-DD") from exc
        if expires < today:
            raise AuditReportError(
                f"{label} expired on {expires.isoformat()} and is invalid"
            )
        allowances.append(
            PipAllowance(
                package=_canonical_package(package),
                identifier=identifier.casefold(),
            )
        )
    return allowances


def _validate_scanner_status(scanner_status: int) -> None:
    if scanner_status not in {0, 1}:
        raise AuditReportError(
            f"scanner exited with operational status {scanner_status}; expected 0 or 1"
        )


def _parse_pip_findings(payload: object) -> list[PipFinding]:
    root = _mapping(payload, label="pip-audit report")
    dependencies = _list(
        root.get("dependencies"), label="pip-audit report.dependencies"
    )
    if not dependencies:
        raise AuditReportError("pip-audit report.dependencies must not be empty")
    fixes = _list(root.get("fixes"), label="pip-audit report.fixes")
    if fixes:
        raise AuditReportError(
            "pip-audit report.fixes must be empty for a read-only audit"
        )

    findings: list[PipFinding] = []
    for dependency_index, raw_dependency in enumerate(dependencies):
        label = f"pip-audit report.dependencies[{dependency_index}]"
        dependency = _mapping(raw_dependency, label=label)
        if "skip_reason" in dependency:
            reason = dependency.get("skip_reason")
            raise AuditReportError(f"{label} was skipped and is unaudited: {reason!r}")
        package = _nonempty_string(dependency.get("name"), label=f"{label}.name")
        _nonempty_string(dependency.get("version"), label=f"{label}.version")
        vulnerabilities = _list(dependency.get("vulns"), label=f"{label}.vulns")

        for vulnerability_index, raw_vulnerability in enumerate(vulnerabilities):
            finding_label = f"{label}.vulns[{vulnerability_index}]"
            vulnerability = _mapping(raw_vulnerability, label=finding_label)
            identifier = _nonempty_string(
                vulnerability.get("id"), label=f"{finding_label}.id"
            )
            aliases = _string_list(
                vulnerability.get("aliases"), label=f"{finding_label}.aliases"
            )
            _string_list(
                vulnerability.get("fix_versions"),
                label=f"{finding_label}.fix_versions",
            )
            findings.append(
                PipFinding(
                    package=_canonical_package(package),
                    identifier=identifier,
                    aliases=frozenset(aliases),
                )
            )
    return findings


def validate_pip_report(
    payload: object,
    *,
    scanner_status: int,
    allowlist_path: pathlib.Path,
) -> None:
    _validate_scanner_status(scanner_status)
    findings = _parse_pip_findings(payload)
    if scanner_status == 0 and findings:
        raise AuditReportError("pip-audit exited 0 but its report contains advisories")
    if scanner_status == 1 and not findings:
        raise AuditReportError(
            "pip-audit exited 1 but its report contains no advisories"
        )

    allowances = _load_pip_allowlist(allowlist_path)
    unapproved: list[PipFinding] = []
    matched_allowance_indexes: set[int] = set()
    for finding in findings:
        finding_ids = {
            finding.identifier.casefold(),
            *(alias.casefold() for alias in finding.aliases),
        }
        matching_indexes = {
            index
            for index, allowance in enumerate(allowances)
            if allowance.package == finding.package
            and allowance.identifier in finding_ids
        }
        if matching_indexes:
            matched_allowance_indexes.update(matching_indexes)
        else:
            unapproved.append(finding)

    if unapproved:
        formatted = ", ".join(
            f"{finding.package}:{finding.identifier}" for finding in unapproved
        )
        raise AuditReportError(f"unapproved Python advisories: {formatted}")

    dormant = [
        allowance
        for index, allowance in enumerate(allowances)
        if index not in matched_allowance_indexes
    ]
    if dormant:
        formatted = ", ".join(
            f"{allowance.package}:{allowance.identifier}" for allowance in dormant
        )
        raise AuditReportError(f"dormant Python advisory allowances: {formatted}")


def _validate_cvss_vector(value: object, *, label: str) -> None:
    if value is None:
        return
    vector = _nonempty_string(value, label=label)
    if vector != value:
        raise AuditReportError(f"{label} must not contain surrounding whitespace")
    components = vector.split("/")
    version = components[0]
    if version in {"CVSS:3.0", "CVSS:3.1"}:
        allowed_metrics = _CVSS_V3_METRICS
        required_metrics = _CVSS_V3_REQUIRED
    elif version == "CVSS:4.0":
        allowed_metrics = _CVSS_V4_METRICS
        required_metrics = _CVSS_V4_REQUIRED
    else:
        raise AuditReportError(f"{label} must be a documented CVSS v3 or v4 vector")

    seen: set[str] = set()
    for component in components[1:]:
        if component.count(":") != 1:
            raise AuditReportError(
                f"{label} contains a malformed metric: {component!r}"
            )
        metric, metric_value = component.split(":", maxsplit=1)
        if metric in seen:
            raise AuditReportError(f"{label} contains duplicate metric {metric}")
        accepted_values = allowed_metrics.get(metric)
        if accepted_values is None or metric_value not in accepted_values:
            raise AuditReportError(
                f"{label} contains unsupported metric {metric}:{metric_value}"
            )
        seen.add(metric)
    missing = sorted(required_metrics - seen)
    if missing:
        raise AuditReportError(
            f"{label} is missing required metrics: {', '.join(missing)}"
        )


def _parse_cargo_findings(payload: object) -> list[dict[str, object]]:
    root = _mapping(payload, label="cargo-audit report")
    required_sections = {
        "database",
        "lockfile",
        "settings",
        "vulnerabilities",
        "warnings",
    }
    if set(root) != required_sections:
        missing = sorted(required_sections - set(root))
        unexpected = sorted(set(root) - required_sections)
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise AuditReportError(
            f"cargo-audit report root sections do not match schema ({'; '.join(details)})"
        )

    database = _mapping(root.get("database"), label="cargo-audit report.database")
    advisory_count = database.get("advisory-count")
    if (
        isinstance(advisory_count, bool)
        or not isinstance(advisory_count, int)
        or advisory_count <= 0
    ):
        raise AuditReportError(
            "cargo-audit report.database.advisory-count must be a positive integer"
        )

    lockfile = _mapping(root.get("lockfile"), label="cargo-audit report.lockfile")
    dependency_count = lockfile.get("dependency-count")
    if (
        isinstance(dependency_count, bool)
        or not isinstance(dependency_count, int)
        or dependency_count <= 0
    ):
        raise AuditReportError(
            "cargo-audit report.lockfile.dependency-count must be a positive integer"
        )

    settings = _mapping(root.get("settings"), label="cargo-audit report.settings")
    if settings.get("severity") != "high":
        raise AuditReportError(
            "cargo-audit report.settings.severity must be exactly 'high'"
        )
    ignored_advisories = _list(
        settings.get("ignore"), label="cargo-audit report.settings.ignore"
    )
    if ignored_advisories:
        raise AuditReportError("cargo-audit report.settings.ignore must be empty")

    _mapping(root.get("warnings"), label="cargo-audit report.warnings")
    vulnerabilities = _mapping(
        root.get("vulnerabilities"), label="cargo-audit report.vulnerabilities"
    )
    found = vulnerabilities.get("found")
    if not isinstance(found, bool):
        raise AuditReportError(
            "cargo-audit report.vulnerabilities.found must be boolean"
        )
    count = vulnerabilities.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise AuditReportError(
            "cargo-audit report.vulnerabilities.count must be a nonnegative integer"
        )
    raw_findings = _list(
        vulnerabilities.get("list"), label="cargo-audit report.vulnerabilities.list"
    )
    if count != len(raw_findings) or found != bool(raw_findings):
        raise AuditReportError(
            "cargo-audit found/count/list fields are internally inconsistent"
        )

    findings: list[dict[str, object]] = []
    for index, raw_finding in enumerate(raw_findings):
        label = f"cargo-audit report.vulnerabilities.list[{index}]"
        finding = _mapping(raw_finding, label=label)
        advisory = _mapping(finding.get("advisory"), label=f"{label}.advisory")
        package = _mapping(finding.get("package"), label=f"{label}.package")
        _nonempty_string(advisory.get("id"), label=f"{label}.advisory.id")
        _nonempty_string(package.get("name"), label=f"{label}.package.name")
        _nonempty_string(package.get("version"), label=f"{label}.package.version")
        if "cvss" in advisory:
            _validate_cvss_vector(advisory.get("cvss"), label=f"{label}.advisory.cvss")
        findings.append(finding)
    return findings


def validate_cargo_report(
    payload: object,
    *,
    scanner_status: int,
    report_only: bool,
) -> None:
    _validate_scanner_status(scanner_status)
    findings = _parse_cargo_findings(payload)
    if scanner_status == 0 and findings:
        raise AuditReportError("cargo-audit exited 0 but its report contains findings")
    if scanner_status == 1 and not findings:
        raise AuditReportError(
            "cargo-audit exited 1 but its report contains no findings"
        )
    if findings and not report_only:
        identifiers = ", ".join(
            _nonempty_string(
                _mapping(finding["advisory"], label="cargo advisory").get("id"),
                label="cargo advisory.id",
            )
            for finding in findings
        )
        raise AuditReportError(
            f"Rust high/critical/unknown vulnerability findings: {identifiers}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate dependency scanner reports and enforce audit policy."
    )
    parser.add_argument("mode", choices=("pip", "cargo"))
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--scanner-status", type=int, required=True)
    parser.add_argument("--allowlist", type=pathlib.Path)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Validate cargo findings without enforcing the vulnerability gate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _load_json_report(args.report)
        if args.mode == "pip":
            if args.allowlist is None:
                raise AuditReportError("pip mode requires --allowlist")
            if args.report_only:
                raise AuditReportError("--report-only is supported only in cargo mode")
            validate_pip_report(
                payload,
                scanner_status=args.scanner_status,
                allowlist_path=args.allowlist,
            )
            print("pip-audit report passed the known-vulnerability allowlist policy.")
        else:
            if args.allowlist is not None:
                raise AuditReportError("cargo mode does not accept --allowlist")
            validate_cargo_report(
                payload,
                scanner_status=args.scanner_status,
                report_only=args.report_only,
            )
            if args.report_only:
                print(
                    "cargo-audit report is structurally valid and operationally complete."
                )
            else:
                print("cargo-audit report contains no blocking findings.")
    except AuditReportError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
