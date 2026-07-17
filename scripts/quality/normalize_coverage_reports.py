from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
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
WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
# This quantization is display-only; strict floor checks use integer arithmetic.
PERCENT_QUANTUM = Decimal("0.000001")


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


@dataclass(frozen=True)
class _RawReport:
    component: str
    report_format: str
    path: Path
    raw: bytes
    sha256: str


@dataclass(frozen=True)
class _PreparedInvocation:
    arguments: argparse.Namespace
    output_path: Path
    report_inputs: tuple[_ReportInput, ...]
    floors: dict[str, dict[str, int]]


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
        "percent": _display_percent(covered, total),
    }
    if derivation is not None:
        metric["derivation"] = derivation
    return metric


def _display_percent(covered: int, total: int) -> float:
    """Return a six-decimal display value; policy gates retain integer arithmetic."""
    if total == 0:
        return 0.0
    with localcontext() as context:
        context.prec = max(28, len(str(covered)) + len(str(total)) + 8)
        percentage = Decimal(covered) * Decimal(100) / Decimal(total)
        return float(percentage.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP))


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


def _source_path_key(value: str) -> str:
    """Return a platform-aware comparison key without changing path syntax."""
    return value.casefold() if os.name == "nt" else value


def _reject_source_symlink_parts(parts: Sequence[str]) -> None:
    """Reject existing link or junction ancestors without resolving untrusted paths."""
    candidate = REPOSITORY_ROOT
    for part in parts:
        candidate /= part
        try:
            if candidate.is_symlink() or candidate.is_junction():
                raise _InputError("source path traverses a symbolic link or junction")
        except OSError as error:
            raise _InputError("unable to inspect source path links") from error


def _normalize_relative_source_parts(parts: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not normalized:
                raise _InputError("source path escapes the repository")
            _reject_source_symlink_parts(normalized)
            normalized.pop()
            continue
        if os.name == "nt" and (part.endswith((" ", ".")) or ":" in part):
            raise _InputError("source path contains an unsafe Windows path segment")
        normalized.append(part)
    if not normalized:
        raise _InputError("source path must identify a repository-relative file")
    return tuple(normalized)


def _source_path_is_within_component_root(
    component: str,
    source_parts: Sequence[str],
) -> bool:
    comparison_parts = tuple(_source_path_key(part) for part in source_parts)
    for configured_root in SOURCE_ROOTS[component]:
        root_parts = tuple(
            _source_path_key(part) for part in configured_root.split("/") if part
        )
        if comparison_parts[: len(root_parts)] == root_parts:
            return True
    return False


def _canonical_source_identity(component: str, raw_path: str) -> str:
    """Validate and normalize one report-embedded source path for a component."""
    if not raw_path:
        raise _InputError("source path is empty")
    if any(unicodedata.category(character) == "Cc" for character in raw_path):
        raise _InputError("source path contains a control character")

    normalized_path = raw_path.replace("\\", "/")
    if normalized_path.startswith("//"):
        raise _InputError("source path must not use a UNC path")
    if os.name == "nt" and normalized_path.startswith("/"):
        raise _InputError("source path must not be root-relative on Windows")

    if WINDOWS_DRIVE_PATH_PATTERN.match(normalized_path):
        if len(normalized_path) < 3 or normalized_path[2] != "/":
            raise _InputError("source path must not be drive-relative")
        if os.name != "nt":
            raise _InputError("source path uses a foreign Windows drive")
        absolute_path = Path(normalized_path)
        try:
            relative_parts = absolute_path.relative_to(REPOSITORY_ROOT).parts
        except ValueError as error:
            raise _InputError("source path is outside the repository") from error
    elif normalized_path.startswith("/"):
        if os.name == "nt":
            if not REPOSITORY_ROOT.drive:
                raise _InputError("source path cannot be anchored to this repository")
            absolute_path = Path(f"{REPOSITORY_ROOT.drive}{normalized_path}")
        else:
            absolute_path = Path(normalized_path)
        try:
            relative_parts = absolute_path.relative_to(REPOSITORY_ROOT).parts
        except ValueError as error:
            raise _InputError("source path is outside the repository") from error
    else:
        relative_parts = tuple(normalized_path.split("/"))

    source_parts = _normalize_relative_source_parts(relative_parts)
    _reject_source_symlink_parts(source_parts)
    if not _source_path_is_within_component_root(component, source_parts):
        raise _InputError(
            f"source path is outside configured roots for component {component}"
        )
    return "/".join(_source_path_key(part) for part in source_parts)


def _register_source_spelling(
    spellings: dict[str, str],
    source_identity: str,
    raw_path: str,
    report_name: str,
) -> None:
    existing = spellings.setdefault(source_identity, raw_path)
    if existing != raw_path:
        raise _InputError(
            f"{report_name} has conflicting source spellings for {source_identity}"
        )


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


def _xml_local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", maxsplit=1)[-1]


def _coverage_xml_source_lines(
    root: ElementTree.Element,
    component: str,
) -> list[ElementTree.Element]:
    source_lines: list[ElementTree.Element] = []
    seen_identities: set[tuple[str, int]] = set()
    source_spellings: dict[str, str] = {}
    for class_element in root.iter():
        if _xml_local_name(class_element) != "class":
            continue
        filename = class_element.get("filename")
        if not filename:
            raise _InputError("coverage XML class line is missing a filename")
        source_identity = _canonical_source_identity(component, filename)
        _register_source_spelling(
            source_spellings,
            source_identity,
            filename,
            "coverage XML",
        )
        for lines_element in class_element:
            if _xml_local_name(lines_element) != "lines":
                continue
            for line in lines_element:
                if _xml_local_name(line) != "line":
                    continue
                line_number = _parse_nonnegative_decimal(
                    line.get("number"),
                    "coverage XML line number",
                )
                if line_number == 0:
                    raise _InputError("coverage XML line number must be positive")
                identity = (source_identity, line_number)
                if identity in seen_identities:
                    raise _InputError(
                        "duplicate coverage XML source line "
                        f"{source_identity}:{line_number}"
                    )
                seen_identities.add(identity)
                source_lines.append(line)
    return source_lines


def _parse_python_xml(
    raw: bytes,
    component: str,
) -> dict[str, dict[str, object]]:
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
    lines = _coverage_xml_source_lines(root, component)

    line_detail_metric: dict[str, object] | None = None
    if lines:
        covered = sum(
            _parse_nonnegative_decimal(line.get("hits"), "coverage XML line hits") > 0
            for line in lines
        )
        line_detail_metric = _measured_metric("native", covered, len(lines))

    if line_metric is None:
        line_metric = line_detail_metric or _unmeasured_metric("missing")
    elif line_detail_metric is not None and (
        line_metric["covered"] != line_detail_metric["covered"]
        or line_metric["total"] != line_detail_metric["total"]
    ):
        raise _InputError(
            "coverage XML line root counters disagree with source line details"
        )

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
        covered = _parse_nonnegative_decimal(match.group("covered"), "branch covered")
        total = _parse_nonnegative_decimal(match.group("total"), "branch total")
        if covered > total:
            raise _InputError("coverage XML branch covered counter exceeds total")
        branch_pairs.append((covered, total))

    branch_detail_metric: dict[str, object] | None = None
    if branch_pairs:
        branch_detail_metric = _measured_metric(
            "native",
            sum(covered for covered, _ in branch_pairs),
            sum(total for _, total in branch_pairs),
        )
    if branch_metric is None:
        branch_metric = branch_detail_metric or _unmeasured_metric("missing")
    elif branch_detail_metric is not None and (
        branch_metric["covered"] != branch_detail_metric["covered"]
        or branch_metric["total"] != branch_detail_metric["total"]
    ):
        raise _InputError(
            "coverage XML branch root counters disagree with source line details"
        )

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


@dataclass
class _LcovRecord:
    source: str | None = None
    summaries: dict[str, int] = field(default_factory=dict)
    line_hits: dict[int, int] = field(default_factory=dict)
    branch_hits: dict[tuple[int, str, str], int | None] = field(default_factory=dict)
    function_declarations: dict[str, tuple[int, int | None]] = field(
        default_factory=dict
    )
    function_hits: dict[str, int] = field(default_factory=dict)


def _parse_lcov_positive_line(value: str, field: str) -> int:
    line_number = _parse_lcov_counter(value, field)
    if line_number == 0:
        raise _InputError(f"LCOV {field} must be positive")
    return line_number


def _lcov_require_source(record: _LcovRecord, field: str, line_number: int) -> None:
    if record.source is None:
        raise _InputError(f"LCOV {field} at line {line_number} precedes SF")


def _parse_lcov_da(
    record: _LcovRecord,
    value: str,
    line_number: int,
) -> None:
    values = value.split(",")
    if len(values) not in (2, 3) or (len(values) == 3 and not values[2]):
        raise _InputError(f"LCOV DA at line {line_number} is malformed")
    source_line = _parse_lcov_positive_line(values[0], "DA line")
    hits = _parse_lcov_counter(values[1], "DA hits")
    if source_line in record.line_hits:
        raise _InputError(f"LCOV record has duplicate DA at line {line_number}")
    record.line_hits[source_line] = hits


def _parse_lcov_brda(
    record: _LcovRecord,
    value: str,
    line_number: int,
) -> None:
    prefix, separator, taken_value = value.rpartition(",")
    if not separator:
        raise _InputError(f"LCOV BRDA at line {line_number} is malformed")
    fields = prefix.split(",", maxsplit=2)
    if len(fields) != 3 or not fields[1] or not fields[2]:
        raise _InputError(f"LCOV BRDA at line {line_number} is malformed")
    source_line = _parse_lcov_positive_line(fields[0], "BRDA line")
    taken = (
        None if taken_value == "-" else _parse_lcov_counter(taken_value, "BRDA taken")
    )
    identity = (source_line, fields[1], fields[2])
    if identity in record.branch_hits:
        raise _InputError(f"LCOV record has duplicate BRDA at line {line_number}")
    record.branch_hits[identity] = taken


def _parse_lcov_fn(
    record: _LcovRecord,
    value: str,
    line_number: int,
) -> None:
    fields = value.split(",", maxsplit=2)
    if len(fields) < 2:
        raise _InputError(f"LCOV FN at line {line_number} is malformed")
    start_line = _parse_lcov_positive_line(fields[0], "FN start line")
    end_line: int | None = None
    if len(fields) == 3 and fields[1].isdecimal():
        end_line = _parse_lcov_positive_line(fields[1], "FN end line")
        function_name = fields[2]
        if end_line < start_line:
            raise _InputError(f"LCOV FN at line {line_number} ends before it starts")
    else:
        function_name = value.split(",", maxsplit=1)[1]
    if not function_name:
        raise _InputError(f"LCOV FN at line {line_number} has an empty function name")
    if function_name in record.function_declarations:
        raise _InputError(f"LCOV record has duplicate FN at line {line_number}")
    record.function_declarations[function_name] = (start_line, end_line)


def _parse_lcov_fnda(
    record: _LcovRecord,
    value: str,
    line_number: int,
) -> None:
    count_value, separator, function_name = value.partition(",")
    if not separator or not function_name:
        raise _InputError(f"LCOV FNDA at line {line_number} is malformed")
    if function_name in record.function_hits:
        raise _InputError(f"LCOV record has duplicate FNDA at line {line_number}")
    record.function_hits[function_name] = _parse_lcov_counter(
        count_value,
        "FNDA hits",
    )


def _lcov_detail_pair(record: _LcovRecord, metric_name: str) -> tuple[int, int] | None:
    if metric_name == "lines":
        if not record.line_hits:
            return None
        return (
            sum(hits > 0 for hits in record.line_hits.values()),
            len(record.line_hits),
        )
    if metric_name == "branches":
        if not record.branch_hits:
            return None
        return (
            sum((taken or 0) > 0 for taken in record.branch_hits.values()),
            len(record.branch_hits),
        )

    if not record.function_declarations and not record.function_hits:
        return None
    if not record.function_declarations:
        raise _InputError("LCOV FNDA records have no matching FN declarations")
    declaration_names = set(record.function_declarations)
    hit_names = set(record.function_hits)
    missing_hits = declaration_names - hit_names
    unknown_hits = hit_names - declaration_names
    if missing_hits or unknown_hits:
        raise _InputError("LCOV FN and FNDA records do not describe the same functions")
    return (
        sum(hits > 0 for hits in record.function_hits.values()),
        len(record.function_declarations),
    )


def _lcov_metric_pair(
    record: _LcovRecord,
    metric_name: str,
    covered_name: str,
    total_name: str,
) -> tuple[int, int] | None:
    detail_pair = _lcov_detail_pair(record, metric_name)
    has_covered = covered_name in record.summaries
    has_total = total_name in record.summaries
    if has_covered != has_total:
        raise _InputError(
            f"LCOV {metric_name} counters must include both "
            f"{covered_name} and {total_name}"
        )
    if not has_covered:
        return detail_pair

    if detail_pair is None:
        raise _InputError(
            f"LCOV {metric_name} summary counters require detailed records"
        )

    summary_pair = (
        record.summaries[covered_name],
        record.summaries[total_name],
    )
    if summary_pair[0] > summary_pair[1]:
        raise _InputError(f"LCOV {metric_name} covered counter exceeds total")
    if detail_pair is not None and summary_pair != detail_pair:
        raise _InputError(
            f"LCOV {metric_name} summary counters disagree with detailed records"
        )
    return summary_pair


def _parse_frontend_lcov(
    raw: bytes,
    component: str,
) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "LCOV report")
    records: list[_LcovRecord] = []
    current = _LcovRecord()
    current_has_content = False
    seen_sources: set[str] = set()
    source_spellings: dict[str, str] = {}
    counter_names = frozenset({"LF", "LH", "BRF", "BRH", "FNF", "FNH"})

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        if line == "end_of_record":
            if current.source is None:
                raise _InputError(f"LCOV record ending at line {line_number} lacks SF")
            if current.source in seen_sources:
                raise _InputError(
                    f"LCOV report has duplicate SF for {current.source} "
                    f"at line {line_number}"
                )
            seen_sources.add(current.source)
            records.append(current)
            current = _LcovRecord()
            current_has_content = False
            continue
        if ":" not in line:
            raise _InputError(f"LCOV line {line_number} is malformed")
        field, value = line.split(":", maxsplit=1)
        current_has_content = True
        if field == "SF":
            if current.source is not None:
                raise _InputError(f"LCOV record has duplicate SF at line {line_number}")
            if not value:
                raise _InputError(f"LCOV SF at line {line_number} is empty")
            current.source = _canonical_source_identity(component, value)
            _register_source_spelling(
                source_spellings,
                current.source,
                value,
                "LCOV report",
            )
            continue
        if field in counter_names:
            _lcov_require_source(current, field, line_number)
            if field in current.summaries:
                raise _InputError(
                    f"LCOV record has duplicate {field} at line {line_number}"
                )
            current.summaries[field] = _parse_lcov_counter(value, field)
            continue
        if field == "DA":
            _lcov_require_source(current, field, line_number)
            _parse_lcov_da(current, value, line_number)
            continue
        if field == "BRDA":
            _lcov_require_source(current, field, line_number)
            _parse_lcov_brda(current, value, line_number)
            continue
        if field == "FN":
            _lcov_require_source(current, field, line_number)
            _parse_lcov_fn(current, value, line_number)
            continue
        if field == "FNDA":
            _lcov_require_source(current, field, line_number)
            _parse_lcov_fnda(current, value, line_number)

    if current_has_content:
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
        pairs = [
            _lcov_metric_pair(record, metric_name, covered_name, total_name)
            for record in records
        ]
        if any(pair is None for pair in pairs):
            metrics[metric_name] = _unmeasured_metric("missing")
            continue
        measured_pairs = [pair for pair in pairs if pair is not None]
        covered = sum(pair[0] for pair in measured_pairs)
        total = sum(pair[1] for pair in measured_pairs)
        metrics[metric_name] = _measured_metric("native", covered, total)

    return {metric: metrics[metric] for metric in METRICS}


def _parse_go_coverprofile(
    raw: bytes,
    component: str,
) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "Go coverprofile")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or GO_HEADER_PATTERN.fullmatch(lines[0]) is None:
        raise _InputError("Go coverprofile must begin with a valid mode header")
    if len(lines) == 1:
        raise _InputError("Go coverprofile contains no coverage records")

    total_statements = 0
    covered_statements = 0
    source_lines: dict[tuple[str, int], bool] = {}
    seen_blocks: set[tuple[str, int, int, int, int]] = set()
    source_spellings: dict[str, str] = {}
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

        raw_filename = match.group("filename")
        filename = _canonical_source_identity(component, raw_filename)
        _register_source_spelling(
            source_spellings,
            filename,
            raw_filename,
            "Go coverprofile",
        )
        block_identity = (
            filename,
            start_line,
            start_column,
            end_line,
            end_column,
        )
        if block_identity in seen_blocks:
            raise _InputError(
                f"duplicate Go coverprofile block at record {line_number}"
            )
        seen_blocks.add(block_identity)
        total_statements += statements
        if count > 0:
            covered_statements += statements
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


def _validate_rust_file_identities(
    component: str,
    file_collections: Sequence[object],
) -> None:
    seen_identities: set[str] = set()
    source_spellings: dict[str, str] = {}
    for files in file_collections:
        if not isinstance(files, list):
            raise _InputError("LLVM JSON files must be a list")
        for index, entry in enumerate(files):
            if not isinstance(entry, dict):
                raise _InputError(f"LLVM JSON files[{index}] must be an object")
            identities: list[tuple[str, str]] = []
            for field_name in ("filename", "path"):
                if field_name not in entry:
                    continue
                value = entry[field_name]
                if not isinstance(value, str):
                    raise _InputError(
                        f"LLVM JSON files[{index}].{field_name} must be a string"
                    )
                identities.append((_canonical_source_identity(component, value), value))
            if not identities:
                raise _InputError(f"LLVM JSON files[{index}] lacks a filename or path")
            if len({identity for identity, _ in identities}) != 1:
                raise _InputError(
                    f"LLVM JSON files[{index}] has conflicting filename and path"
                )
            identity = identities[0][0]
            for identity_value, raw_path in identities:
                _register_source_spelling(
                    source_spellings,
                    identity_value,
                    raw_path,
                    "LLVM JSON files",
                )
            if identity in seen_identities:
                raise _InputError(f"LLVM JSON files has duplicate source {identity}")
            seen_identities.add(identity)


def _parse_rust_llvm_json(
    raw: bytes,
    component: str,
) -> dict[str, dict[str, object]]:
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

    has_data = "data" in document
    has_totals = "totals" in document
    if has_data == has_totals:
        raise _InputError("LLVM JSON must contain exactly one of data or totals")

    totals_entries: list[dict[str, object]] = []
    file_collections: list[object] = []
    if "files" in document:
        file_collections.append(document["files"])
    if has_data:
        data = document["data"]
        if not isinstance(data, list) or len(data) != 1:
            raise _InputError("LLVM JSON data must contain exactly one entry")
        entry = data[0]
        if not isinstance(entry, dict) or not isinstance(entry.get("totals"), dict):
            raise _InputError("LLVM JSON data[0] lacks totals")
        totals_entries.append(entry["totals"])
        if "files" in entry:
            file_collections.append(entry["files"])
    elif isinstance(document["totals"], dict):
        totals_entries.append(document["totals"])
    else:
        raise _InputError("LLVM JSON totals must be an object")

    _validate_rust_file_identities(component, file_collections)

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


def _read_raw_report(report_input: _ReportInput) -> _RawReport:
    raw = _read_report_bytes(report_input.path)
    return _RawReport(
        component=report_input.component,
        report_format=report_input.report_format,
        path=report_input.path,
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _parse_report(raw_report: _RawReport) -> _ParsedReport:
    if raw_report.report_format == "cobertura-xml":
        metrics = _parse_python_xml(raw_report.raw, raw_report.component)
    elif raw_report.report_format == "lcov":
        metrics = _parse_frontend_lcov(raw_report.raw, raw_report.component)
    elif raw_report.report_format == "go-coverprofile":
        metrics = _parse_go_coverprofile(raw_report.raw, raw_report.component)
    elif raw_report.report_format == "llvm-cov-json":
        metrics = _parse_rust_llvm_json(raw_report.raw, raw_report.component)
    else:
        raise _InputError(f"unsupported report format: {raw_report.report_format}")
    return _ParsedReport(
        component=raw_report.component,
        report_format=raw_report.report_format,
        path=raw_report.path,
        metrics=metrics,
        sha256=raw_report.sha256,
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
    input_count: int,
    evidence_errors: list[str],
) -> tuple[dict[str, object], list[str], dict[str, object] | None]:
    if input_count == 0:
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

    errors = list(evidence_errors)
    if input_count > 1:
        errors.append(f"duplicate report input for component {component}")
    if errors:
        metrics = _missing_metrics()
    else:
        metrics = reports[0].metrics if reports else _missing_metrics()
        errors.extend(
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
        )
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


def _prepare_invocation(arguments: argparse.Namespace) -> _PreparedInvocation:
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
    return _PreparedInvocation(
        arguments=arguments,
        output_path=output_path,
        report_inputs=tuple(report_inputs),
        floors=floors,
    )


def _build_manifest(
    invocation: _PreparedInvocation,
) -> tuple[dict[str, object], list[str], list[str], Path]:
    arguments = invocation.arguments
    output_path = invocation.output_path
    report_inputs = invocation.report_inputs
    floors = invocation.floors
    reports_by_component: defaultdict[str, list[_ParsedReport]] = defaultdict(list)
    report_input_counts: defaultdict[str, int] = defaultdict(int)
    evidence_errors_by_component: defaultdict[str, list[str]] = defaultdict(list)
    raw_reports: list[_RawReport] = []
    structural_errors: list[str] = []
    for report_input in report_inputs:
        report_input_counts[report_input.component] += 1
        try:
            raw_report = _read_raw_report(report_input)
        except _InputError as error:
            message = str(error)
            evidence_errors_by_component[report_input.component].append(message)
            structural_errors.append(message)
            continue
        raw_reports.append(raw_report)
        try:
            report = _parse_report(raw_report)
        except _InputError as error:
            message = (
                f"malformed report for component {report_input.component}: {error}"
            )
            evidence_errors_by_component[report_input.component].append(message)
            structural_errors.append(message)
        else:
            reports_by_component[report.component].append(report)

    components: dict[str, object] = {}
    missing_reports: list[dict[str, object]] = []
    validation_errors: list[str] = []
    for component in COMPONENTS:
        entry, errors, missing_report = _component_entry(
            component,
            reports_by_component[component],
            floors[component],
            report_input_counts[component],
            evidence_errors_by_component[component],
        )
        components[component] = entry
        validation_errors.extend(errors)
        if missing_report is not None:
            missing_reports.append(missing_report)

    validation_errors = sorted(set(validation_errors))
    structural_errors = sorted(set(structural_errors))
    report_entries = [
        {
            "component": report.component,
            "format": report.report_format,
            "path": _manifest_path(report.path),
            "sha256": report.sha256,
        }
        for report in raw_reports
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
    return manifest, validation_errors, structural_errors, output_path


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
    escaped = "".join(
        (
            f"\\x{ord(character):02x}"
            if ord(character) <= 0xFF
            else f"\\u{ord(character):04x}"
            if ord(character) <= 0xFFFF
            else f"\\U{ord(character):08x}"
        )
        if unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
        else character
        for character in message
    )
    print(f"ERROR: {escaped}", file=sys.stderr)


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
        invocation = _prepare_invocation(arguments)
    except _InputError as error:
        _print_error(str(error))
        return 2

    try:
        manifest, validation_errors, structural_errors, output_path = _build_manifest(
            invocation
        )
        _write_manifest(output_path, manifest)
    except _InputError as error:
        _print_error(str(error))
        return 2

    if validation_errors:
        for error in validation_errors:
            _print_error(error)
        return 2 if structural_errors else 1

    print("Quality coverage artifacts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
