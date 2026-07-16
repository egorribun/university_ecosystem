from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn
from xml.etree import ElementTree

from validate_quality_contract import validate_contract

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    "python",
    "frontend",
    "go-gateway",
    "go-ws-hub",
    "go-file-processor",
    "rust-native",
    "rust-pyo3-sanitizer",
    "rust-wasm-sanitizer",
    "infrastructure",
    "workflows",
    "scripts",
)
METRICS = ("lines", "statements", "branches", "functions")
SOURCE_ROOTS = {
    "python": ("app",),
    "frontend": ("frontend/src",),
    "go-gateway": ("services/gateway",),
    "go-ws-hub": ("services/ws-hub",),
    "go-file-processor": ("services/file-processor",),
    "rust-native": ("native/rust_ext",),
    "rust-pyo3-sanitizer": ("crates/pyo3-sanitizer",),
    "rust-wasm-sanitizer": ("frontend/wasm-sanitizer",),
    "infrastructure": ("infra", "infrastructure", "k8s", "charts"),
    "workflows": (".github/workflows",),
    "scripts": ("scripts",),
}
SUPPORTED_REPORTS = {
    "python": ("cobertura-xml", "coverage.xml"),
    "frontend": ("lcov", "frontend/coverage/lcov.info"),
    "go-gateway": ("go-coverprofile", "artifacts/coverage/go/gateway/coverage.out"),
    "go-ws-hub": ("go-coverprofile", "artifacts/coverage/go/ws-hub/coverage.out"),
    "go-file-processor": (
        "go-coverprofile",
        "artifacts/coverage/go/file-processor/coverage.out",
    ),
    "rust-native": ("llvm-cov-json", "artifacts/coverage/rust/rust-native/llvm.json"),
    "rust-pyo3-sanitizer": (
        "llvm-cov-json",
        "artifacts/coverage/rust/rust-pyo3-sanitizer/llvm.json",
    ),
    "rust-wasm-sanitizer": (
        "llvm-cov-json",
        "artifacts/coverage/rust/rust-wasm-sanitizer/llvm.json",
    ),
}
CANONICAL_RAW_ARTIFACTS = frozenset(
    {
        "coverage.xml",
        "artifacts/coverage/python/coverage.json",
        "frontend/coverage/lcov.info",
        "frontend/coverage/coverage-final.json",
        "artifacts/coverage/go/gateway/coverage.out",
        "artifacts/coverage/go/ws-hub/coverage.out",
        "artifacts/coverage/go/file-processor/coverage.out",
        "artifacts/coverage/rust/rust-native/llvm.json",
        "artifacts/coverage/rust/rust-pyo3-sanitizer/llvm.json",
        "artifacts/coverage/rust/rust-wasm-sanitizer/llvm.json",
        "artifacts/coverage/quality-manifest.json",
    }
)
GO_COMPONENTS = frozenset({"go-gateway", "go-ws-hub", "go-file-processor"})
RUST_COMPONENTS = frozenset(
    {"rust-native", "rust-pyo3-sanitizer", "rust-wasm-sanitizer"}
)
SHA_PATTERN = re.compile(r"^[0-9A-Fa-f]{7,64}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
CONDITION_COVERAGE_PATTERN = re.compile(
    r"^\s*\d+(?:\.\d+)?%\s+\((?P<covered>\d+)\s*/\s*(?P<total>\d+)\)\s*$"
)
GO_HEADER_PATTERN = re.compile(r"^mode:\s*(?:set|count|atomic)\s*$")
GO_RECORD_PATTERN = re.compile(
    r"^(?P<filename>.+):(?P<start_line>\d+)\.(?P<start_column>\d+),"
    r"(?P<end_line>\d+)\.(?P<end_column>\d+)\s+"
    r"(?P<statements>\d+)\s+(?P<count>\d+)\s*$"
)


class _InputError(ValueError):
    """Raised for invalid CLI inputs or reports that cannot be normalized."""


class _ArgumentParsingError(ValueError):
    """Raised instead of printing argparse usage for invalid arguments."""


class _CoverageArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _ArgumentParsingError(message)


class _DuplicateKeyError(ValueError):
    """Raised when JSON input repeats an object key."""


@dataclass(frozen=True)
class _ReportInput:
    component: str
    report_format: str
    path: Path


@dataclass(frozen=True)
class _ParsedReport:
    component: str
    report_format: str
    path: Path
    metrics: dict[str, dict[str, object]]
    sha256: str


def _duplicate_key_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid JSON value: {value}")


def _measured_metric(
    status: str,
    covered: int,
    total: int,
    *,
    derivation: str | None = None,
) -> dict[str, object]:
    if covered < 0 or total < 0 or covered > total:
        raise _InputError("report counter has an invalid covered/total pair")

    metric: dict[str, object] = {
        "status": status,
        "covered": covered,
        "total": total,
        "percent": covered * 100 / total if total else 0.0,
    }
    if derivation is not None:
        metric["derivation"] = derivation
    return metric


def _unmeasured_metric(
    status: str,
    *,
    reason_code: str | None = None,
) -> dict[str, object]:
    metric: dict[str, object] = {
        "status": status,
        "covered": None,
        "total": None,
        "percent": None,
    }
    if reason_code is not None:
        metric["reason_code"] = reason_code
    return metric


def _parse_nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _InputError(f"{field} must be a non-negative integer")
    return value


def _parse_nonnegative_decimal(value: str | None, field: str) -> int:
    if value is None or not value.isdecimal():
        raise _InputError(f"{field} must be a non-negative integer")
    return int(value)


def _read_report_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise _InputError(f"unable to read report {path}: {error}") from error


def _decode_report(raw: bytes, report_name: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _InputError(f"{report_name} must be UTF-8 encoded: {error}") from error


def _counter_from_xml_attributes(
    root: ElementTree.Element,
    covered_name: str,
    total_name: str,
    metric_name: str,
) -> dict[str, object] | None:
    covered_value = root.get(covered_name)
    total_value = root.get(total_name)
    if covered_value is None and total_value is None:
        return None
    if covered_value is None or total_value is None:
        raise _InputError(f"coverage XML has incomplete {metric_name} counters")

    covered = _parse_nonnegative_decimal(covered_value, f"{metric_name} covered")
    total = _parse_nonnegative_decimal(total_value, f"{metric_name} total")
    return _measured_metric("native", covered, total)


def _parse_python_xml(raw: bytes) -> dict[str, dict[str, object]]:
    if b"<!doctype" in raw.lower() or b"<!entity" in raw.lower():
        raise _InputError("coverage XML must not contain DTD or entity declarations")
    try:
        # DTD and entity declarations are rejected before using the required
        # standard-library Cobertura parser.
        root = ElementTree.fromstring(raw)  # noqa: S314
    except ElementTree.ParseError as error:
        raise _InputError(f"malformed coverage XML: {error}") from error

    if root.tag.rsplit("}", maxsplit=1)[-1] != "coverage":
        raise _InputError("coverage XML root element must be coverage")

    line_metric = _counter_from_xml_attributes(
        root,
        "lines-covered",
        "lines-valid",
        "line",
    )
    branch_metric = _counter_from_xml_attributes(
        root,
        "branches-covered",
        "branches-valid",
        "branch",
    )
    lines = list(root.iterfind(".//line"))

    if line_metric is None:
        if lines:
            covered = 0
            for line in lines:
                hits = _parse_nonnegative_decimal(
                    line.get("hits"), "coverage XML line hits"
                )
                if hits > 0:
                    covered += 1
            line_metric = _measured_metric("native", covered, len(lines))
        else:
            line_metric = _unmeasured_metric("missing")

    if branch_metric is None:
        branch_pairs: list[tuple[int, int]] = []
        for line in lines:
            condition_coverage = line.get("condition-coverage")
            branch = line.get("branch")
            if condition_coverage is None:
                if branch == "true":
                    raise _InputError(
                        "coverage XML branch line lacks condition-coverage counter"
                    )
                continue
            match = CONDITION_COVERAGE_PATTERN.fullmatch(condition_coverage)
            if match is None:
                raise _InputError("coverage XML has malformed condition-coverage")
            branch_pairs.append(
                (
                    _parse_nonnegative_decimal(
                        match.group("covered"), "branch covered"
                    ),
                    _parse_nonnegative_decimal(match.group("total"), "branch total"),
                )
            )
        if branch_pairs:
            branch_metric = _measured_metric(
                "native",
                sum(covered for covered, _ in branch_pairs),
                sum(total for _, total in branch_pairs),
            )
        else:
            branch_metric = _unmeasured_metric("missing")

    return {
        "lines": line_metric,
        "statements": _unmeasured_metric(
            "unsupported",
            reason_code="coverage_xml_has_no_statement_counter",
        ),
        "branches": branch_metric,
        "functions": _unmeasured_metric(
            "unsupported",
            reason_code="coverage_xml_has_no_function_counter",
        ),
    }


def _parse_lcov_counter(value: str, field: str) -> int:
    return _parse_nonnegative_decimal(value, f"LCOV {field}")


def _parse_frontend_lcov(raw: bytes) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "LCOV report")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    counter_names = frozenset({"LF", "LH", "BRF", "BRH", "FNF", "FNH"})

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        if line == "end_of_record":
            if "SF" not in current:
                raise _InputError(f"LCOV record ending at line {line_number} lacks SF")
            records.append(current)
            current = {}
            continue
        if ":" not in line:
            raise _InputError(f"LCOV line {line_number} is malformed")
        field, value = line.split(":", maxsplit=1)
        if field == "SF" and "SF" in current:
            raise _InputError(f"LCOV record has duplicate SF at line {line_number}")
        if field in counter_names:
            if field in current:
                raise _InputError(
                    f"LCOV record has duplicate {field} at line {line_number}"
                )
            _parse_lcov_counter(value, field)
        current[field] = value

    if current:
        raise _InputError("LCOV report is missing end_of_record")
    if not records:
        raise _InputError("LCOV report contains no records")

    metrics: dict[str, dict[str, object]] = {
        "statements": _unmeasured_metric(
            "unsupported",
            reason_code="lcov_has_no_statement_counter",
        )
    }
    for metric_name, covered_name, total_name in (
        ("lines", "LH", "LF"),
        ("branches", "BRH", "BRF"),
        ("functions", "FNH", "FNF"),
    ):
        present = [
            covered_name in record and total_name in record for record in records
        ]
        partial = [
            (covered_name in record) != (total_name in record) for record in records
        ]
        if any(partial):
            raise _InputError(
                f"LCOV {metric_name} counters must include both "
                f"{covered_name} and {total_name}"
            )
        if not all(present):
            metrics[metric_name] = _unmeasured_metric("missing")
            continue

        covered = sum(
            _parse_lcov_counter(record[covered_name], covered_name)
            for record in records
        )
        total = sum(
            _parse_lcov_counter(record[total_name], total_name) for record in records
        )
        metrics[metric_name] = _measured_metric("native", covered, total)

    return {metric: metrics[metric] for metric in METRICS}


def _parse_go_coverprofile(raw: bytes) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "Go coverprofile")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or GO_HEADER_PATTERN.fullmatch(lines[0]) is None:
        raise _InputError("Go coverprofile must begin with a valid mode header")
    if len(lines) == 1:
        raise _InputError("Go coverprofile contains no coverage records")

    total_statements = 0
    covered_statements = 0
    source_lines: dict[tuple[str, int], bool] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        match = GO_RECORD_PATTERN.fullmatch(line)
        if match is None:
            raise _InputError(f"Go coverprofile record {line_number} is malformed")
        start_line = _parse_nonnegative_decimal(
            match.group("start_line"), "Go start line"
        )
        end_line = _parse_nonnegative_decimal(match.group("end_line"), "Go end line")
        start_column = _parse_nonnegative_decimal(
            match.group("start_column"), "Go start column"
        )
        end_column = _parse_nonnegative_decimal(
            match.group("end_column"), "Go end column"
        )
        statements = _parse_nonnegative_decimal(
            match.group("statements"), "Go numStatements"
        )
        count = _parse_nonnegative_decimal(match.group("count"), "Go execution count")
        if start_line == 0 or end_line == 0:
            raise _InputError("Go source line numbers must be positive")
        if (end_line, end_column) < (start_line, start_column):
            raise _InputError("Go coverprofile range ends before it starts")

        total_statements += statements
        if count > 0:
            covered_statements += statements
        filename = match.group("filename")
        for source_line in range(start_line, end_line + 1):
            identity = (filename, source_line)
            source_lines[identity] = source_lines.get(identity, False) or count > 0

    return {
        "lines": _measured_metric(
            "derived",
            sum(source_lines.values()),
            len(source_lines),
            derivation=(
                "unique source lines in coverprofile blocks; covered when any "
                "overlapping block has count greater than zero"
            ),
        ),
        "statements": _measured_metric(
            "native",
            covered_statements,
            total_statements,
        ),
        "branches": _unmeasured_metric(
            "unsupported",
            reason_code="go_coverprofile_has_no_branch_counter",
        ),
        "functions": _unmeasured_metric(
            "unsupported",
            reason_code="go_coverprofile_has_no_function_counter",
        ),
    }


def _parse_rust_counter(
    totals: dict[str, object],
    metric_name: str,
) -> tuple[int, int]:
    value = totals.get(metric_name)
    if not isinstance(value, dict):
        raise _InputError(f"LLVM JSON totals lacks {metric_name} counters")
    count = _parse_nonnegative_integer(value.get("count"), f"LLVM {metric_name} count")
    covered = _parse_nonnegative_integer(
        value.get("covered"),
        f"LLVM {metric_name} covered",
    )
    if covered > count:
        raise _InputError(f"LLVM {metric_name} covered exceeds count")
    return covered, count


def _parse_rust_llvm_json(raw: bytes) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "LLVM JSON report")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as error:
        raise _InputError(str(error)) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise _InputError(f"malformed LLVM JSON: {error}") from error
    if not isinstance(document, dict):
        raise _InputError("LLVM JSON root must be an object")

    totals_entries: list[dict[str, object]] = []
    if "data" in document:
        data = document["data"]
        if not isinstance(data, list) or not data:
            raise _InputError("LLVM JSON data must be a non-empty list")
        for index, entry in enumerate(data):
            if not isinstance(entry, dict) or not isinstance(entry.get("totals"), dict):
                raise _InputError(f"LLVM JSON data[{index}] lacks totals")
            totals_entries.append(entry["totals"])
    elif isinstance(document.get("totals"), dict):
        totals_entries.append(document["totals"])
    else:
        raise _InputError("LLVM JSON must contain data[].totals or totals")

    line_pairs = [_parse_rust_counter(totals, "lines") for totals in totals_entries]
    function_pairs = [
        _parse_rust_counter(totals, "functions") for totals in totals_entries
    ]
    return {
        "lines": _measured_metric(
            "native",
            sum(covered for covered, _ in line_pairs),
            sum(total for _, total in line_pairs),
        ),
        "statements": _unmeasured_metric(
            "unsupported",
            reason_code="llvm_json_has_no_statement_counter",
        ),
        "branches": _unmeasured_metric(
            "experimental",
            reason_code="llvm_branch_coverage_unstable",
        ),
        "functions": _measured_metric(
            "native",
            sum(covered for covered, _ in function_pairs),
            sum(total for _, total in function_pairs),
        ),
    }


def _resolve_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    try:
        return candidate.resolve(strict=False)
    except OSError as error:
        raise _InputError(f"unable to resolve path {value}: {error}") from error


def _paths_alias(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first)) == os.path.normcase(str(second))


def _manifest_path(path: Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_component_path(
    value: str,
    allowed_components: frozenset[str],
    option_name: str,
    report_format: str,
) -> _ReportInput:
    component, separator, path_value = value.partition("=")
    if not separator or not component or not path_value:
        raise _InputError(f"{option_name} must use COMPONENT=PATH")
    if component not in allowed_components:
        raise _InputError(f"unsupported {option_name} component: {component}")
    return _ReportInput(component, report_format, _resolve_path(path_value))


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _CoverageArgumentParser(
        description="Normalize native coverage evidence into a quality manifest."
    )
    parser.add_argument("--contract", metavar="PATH")
    parser.add_argument("--commit-sha", required=True, metavar="SHA")
    parser.add_argument("--generated-at", required=True, metavar="TIMESTAMP")
    parser.add_argument("--output", required=True, metavar="PATH")
    parser.add_argument("--python-xml", action="append", default=[], metavar="PATH")
    parser.add_argument(
        "--frontend-lcov",
        action="append",
        default=[],
        metavar="PATH",
    )
    parser.add_argument(
        "--go-report", action="append", default=[], metavar="COMPONENT=PATH"
    )
    parser.add_argument(
        "--rust-report",
        action="append",
        default=[],
        metavar="COMPONENT=PATH",
    )
    return parser.parse_args(argv)


def _parse_generated_at(value: str) -> datetime:
    if TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise _InputError("generated-at must be a UTC ISO-8601 timestamp ending in Z")
    try:
        return datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise _InputError(
            "generated-at must be a UTC ISO-8601 timestamp ending in Z"
        ) from error


def _load_contract(path: Path, generated_at: datetime) -> dict[str, dict[str, int]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _InputError(f"unable to read contract {path}: {error}") from error
    try:
        contract = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as error:
        raise _InputError(f"malformed contract: {error}") from error
    except (json.JSONDecodeError, ValueError) as error:
        raise _InputError(f"malformed contract: {error}") from error
    if not isinstance(contract, dict):
        raise _InputError("malformed contract: root must be an object")

    contract_errors = validate_contract(contract, today=generated_at.date())
    if contract_errors:
        raise _InputError(f"malformed contract: {'; '.join(contract_errors)}")

    required_artifacts = contract["required_artifacts"]
    if not isinstance(required_artifacts, list):
        raise _InputError("malformed contract: required_artifacts must be a list")
    missing_artifacts = CANONICAL_RAW_ARTIFACTS - set(required_artifacts)
    if missing_artifacts:
        paths = ", ".join(sorted(missing_artifacts))
        raise _InputError(f"malformed contract: missing canonical artifacts: {paths}")

    components = contract["components"]
    if not isinstance(components, dict):
        raise _InputError("malformed contract: components must be an object")
    floors: dict[str, dict[str, int]] = {}
    for component in COMPONENTS:
        component_config = components[component]
        if not isinstance(component_config, dict):
            raise _InputError(
                f"malformed contract: component {component} must be an object"
            )
        coverage = component_config["coverage"]
        if not isinstance(coverage, dict):
            raise _InputError(
                f"malformed contract: {component} coverage must be an object"
            )
        component_floors: dict[str, int] = {}
        for metric in METRICS:
            value = coverage[metric]
            if isinstance(value, bool) or not isinstance(value, int):
                raise _InputError(
                    f"malformed contract: {component} {metric} floor must be an integer"
                )
            component_floors[metric] = value
        floors[component] = component_floors
    return floors


def _collect_report_inputs(arguments: argparse.Namespace) -> list[_ReportInput]:
    inputs: list[_ReportInput] = []
    for value in arguments.python_xml:
        inputs.append(_ReportInput("python", "cobertura-xml", _resolve_path(value)))
    for value in arguments.frontend_lcov:
        inputs.append(_ReportInput("frontend", "lcov", _resolve_path(value)))
    for value in arguments.go_report:
        inputs.append(
            _parse_component_path(
                value,
                GO_COMPONENTS,
                "--go-report",
                "go-coverprofile",
            )
        )
    for value in arguments.rust_report:
        inputs.append(
            _parse_component_path(
                value,
                RUST_COMPONENTS,
                "--rust-report",
                "llvm-cov-json",
            )
        )
    return inputs


def _parse_report(report_input: _ReportInput) -> _ParsedReport:
    raw = _read_report_bytes(report_input.path)
    if report_input.report_format == "cobertura-xml":
        metrics = _parse_python_xml(raw)
    elif report_input.report_format == "lcov":
        metrics = _parse_frontend_lcov(raw)
    elif report_input.report_format == "go-coverprofile":
        metrics = _parse_go_coverprofile(raw)
    elif report_input.report_format == "llvm-cov-json":
        metrics = _parse_rust_llvm_json(raw)
    else:
        raise _InputError(f"unsupported report format: {report_input.report_format}")
    return _ParsedReport(
        component=report_input.component,
        report_format=report_input.report_format,
        path=report_input.path,
        metrics=metrics,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _missing_metrics() -> dict[str, dict[str, object]]:
    return {metric: _unmeasured_metric("missing") for metric in METRICS}


def _metric_satisfies_floor(metric: dict[str, object], floor: int) -> bool:
    if metric["status"] != "native":
        return False
    covered = metric["covered"]
    total = metric["total"]
    if (
        isinstance(covered, bool)
        or not isinstance(covered, int)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total <= 0
    ):
        return False
    return covered * 100 >= total * floor


def _metric_failure(
    component: str,
    metric_name: str,
    metric: dict[str, object],
    floor: int,
) -> str | None:
    if _metric_satisfies_floor(metric, floor):
        return None
    status = metric["status"]
    if status == "derived":
        return f"{component}.{metric_name} is derived and cannot satisfy strict coverage floor"
    if status != "native":
        return f"{component}.{metric_name} is {status} and cannot satisfy strict coverage floor"
    return f"{component}.{metric_name} is below required coverage floor {floor}"


def _component_entry(
    component: str,
    reports: list[_ParsedReport],
    floors: dict[str, int],
) -> tuple[dict[str, object], list[str], dict[str, object] | None]:
    if not reports:
        if component in SUPPORTED_REPORTS:
            _, expected_path = SUPPORTED_REPORTS[component]
            error = f"expected report for component {component} was not supplied"
            missing_report: dict[str, object] | None = {
                "component": component,
                "path": expected_path,
                "reason_code": "expected_report_not_supplied",
            }
        else:
            error = f"component {component} requires an alternative quality gate"
            missing_report = {
                "component": component,
                "reason_code": "alternative_gate_required",
            }
        entry = {
            "status": "missing",
            "metrics": _missing_metrics(),
            "errors": [error],
        }
        return entry, [error], missing_report

    metrics = reports[0].metrics
    errors = [
        failure
        for metric_name in METRICS
        if (
            failure := _metric_failure(
                component,
                metric_name,
                metrics[metric_name],
                floors[metric_name],
            )
        )
        is not None
    ]
    if len(reports) > 1:
        errors.append(f"duplicate report input for component {component}")
    errors.sort()
    return (
        {
            "status": "passed" if not errors else "failed",
            "metrics": metrics,
            "errors": errors,
        },
        errors,
        None,
    )


def _build_manifest(
    arguments: argparse.Namespace,
) -> tuple[dict[str, object], list[str], Path]:
    if SHA_PATTERN.fullmatch(arguments.commit_sha) is None:
        raise _InputError("commit-sha must be a 7-64 character hexadecimal Git SHA")
    generated_at = _parse_generated_at(arguments.generated_at)
    contract_path = (
        _resolve_path(arguments.contract)
        if arguments.contract
        else (REPOSITORY_ROOT / "quality" / "quality-contract.json")
    )
    output_path = _resolve_path(arguments.output)
    report_inputs = _collect_report_inputs(arguments)
    for path in [contract_path, *(entry.path for entry in report_inputs)]:
        if _paths_alias(output_path, path):
            raise _InputError(
                "output path must not alias the contract or an input report"
            )

    floors = _load_contract(contract_path, generated_at)
    reports_by_component: defaultdict[str, list[_ParsedReport]] = defaultdict(list)
    parsed_reports: list[_ParsedReport] = []
    for report_input in report_inputs:
        report = _parse_report(report_input)
        parsed_reports.append(report)
        reports_by_component[report.component].append(report)

    components: dict[str, object] = {}
    missing_reports: list[dict[str, object]] = []
    validation_errors: list[str] = []
    for component in COMPONENTS:
        entry, errors, missing_report = _component_entry(
            component,
            reports_by_component[component],
            floors[component],
        )
        components[component] = entry
        validation_errors.extend(errors)
        if missing_report is not None:
            missing_reports.append(missing_report)

    validation_errors = sorted(set(validation_errors))
    report_entries = [
        {
            "component": report.component,
            "format": report.report_format,
            "path": _manifest_path(report.path),
            "sha256": report.sha256,
        }
        for report in parsed_reports
    ]
    report_entries.sort(
        key=lambda entry: (
            str(entry["component"]),
            str(entry["format"]),
            str(entry["path"]),
            str(entry["sha256"]),
        )
    )
    missing_reports.sort(
        key=lambda entry: (str(entry["component"]), str(entry.get("path", "")))
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "commit_sha": arguments.commit_sha,
        "generated_at": arguments.generated_at,
        "source_roots": {
            component: list(SOURCE_ROOTS[component]) for component in COMPONENTS
        },
        "reports": report_entries,
        "components": components,
        "missing_reports": missing_reports,
        "validation": {
            "valid": not validation_errors,
            "errors": validation_errors,
        },
    }
    return manifest, validation_errors, output_path


def _write_manifest(output_path: Path, manifest: dict[str, object]) -> None:
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary_path: Path | None = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            delete=False,
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        ) as output_file:
            temporary_path = Path(output_file.name)
            output_file.write(payload)
        os.replace(temporary_path, output_path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise _InputError(
            f"unable to write output manifest {output_path}: {error}"
        ) from error


def _print_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Normalize native coverage reports and return a documented process status."""
    try:
        arguments = _parse_arguments(argv)
    except _ArgumentParsingError as error:
        _print_error(str(error))
        return 2
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2

    try:
        manifest, validation_errors, output_path = _build_manifest(arguments)
        _write_manifest(output_path, manifest)
    except _InputError as error:
        _print_error(str(error))
        return 2

    if validation_errors:
        for error in validation_errors:
            _print_error(error)
        return 1

    print("Quality coverage artifacts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
