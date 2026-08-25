from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast
from xml.etree import ElementTree

from validate_quality_contract import (
    NORMALIZER_VERSION,
    validate_contract,
    validate_manifest_evidence,
)

DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = DEFAULT_REPOSITORY_ROOT
COMPONENTS = (
    "python",
    "frontend",
    "go-gateway",
    "go-ws-hub",
    "go-file-processor",
    "go-shared",
    "rust-native",
    "rust-pyo3-sanitizer",
    "rust-wasm-sanitizer",
    "rust-crypto",
    "infrastructure",
    "workflows",
    "scripts",
)
METRICS = ("lines", "statements", "branches", "functions")
COVERAGE_COMPONENTS = (
    "python",
    "frontend",
    "go-gateway",
    "go-ws-hub",
    "go-file-processor",
    "go-shared",
    "rust-native",
    "rust-pyo3-sanitizer",
    "rust-wasm-sanitizer",
    "rust-crypto",
)
SOURCE_ROOTS = {
    "python": ("app", "alembic/versions"),
    "frontend": ("frontend/src",),
    "go-gateway": ("services/gateway",),
    "go-ws-hub": ("services/ws-hub",),
    "go-file-processor": ("services/file-processor",),
    "go-shared": (
        "services/cmd/uni-cli",
        "services/pkg/spiffe",
        "services/pkg/spicedb",
    ),
    "rust-native": ("native/rust_ext",),
    "rust-pyo3-sanitizer": ("crates/pyo3-sanitizer",),
    "rust-wasm-sanitizer": ("frontend/wasm-sanitizer",),
    "rust-crypto": ("frontend/rust-crypto",),
    "infrastructure": ("infra", "infrastructure", "k8s", "charts"),
    "workflows": (".github/workflows",),
    "scripts": ("scripts",),
}
SUPPORTED_REPORTS = {
    "python": (
        ("cobertura-xml", "coverage.xml"),
        ("coverage-py-json", "artifacts/coverage/python/coverage.json"),
    ),
    "frontend": (
        ("lcov", "frontend/coverage/lcov.info"),
        ("istanbul-json", "frontend/coverage/coverage-final.json"),
    ),
    "go-gateway": (("go-coverprofile", "artifacts/coverage/go/gateway/coverage.out"),),
    "go-ws-hub": (("go-coverprofile", "artifacts/coverage/go/ws-hub/coverage.out"),),
    "go-file-processor": (
        ("go-coverprofile", "artifacts/coverage/go/file-processor/coverage.out"),
    ),
    "go-shared": (("go-coverprofile", "artifacts/coverage/go/shared/coverage.out"),),
    "rust-native": (
        ("llvm-cov-json", "artifacts/coverage/rust/rust-native/llvm.json"),
        (
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-native/branch-llvm.json",
        ),
    ),
    "rust-pyo3-sanitizer": (
        ("llvm-cov-json", "artifacts/coverage/rust/rust-pyo3-sanitizer/llvm.json"),
        (
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-pyo3-sanitizer/branch-llvm.json",
        ),
    ),
    "rust-wasm-sanitizer": (
        ("llvm-cov-json", "artifacts/coverage/rust/rust-wasm-sanitizer/llvm.json"),
        (
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-wasm-sanitizer/branch-llvm.json",
        ),
    ),
    "rust-crypto": (
        ("llvm-cov-json", "artifacts/coverage/rust/rust-crypto/llvm.json"),
        (
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-crypto/branch-llvm.json",
        ),
    ),
}
CANONICAL_REPORT_DECLARATIONS = frozenset(
    (component, report_format, path)
    for component, reports in SUPPORTED_REPORTS.items()
    for report_format, path in reports
)
CANONICAL_RAW_ARTIFACTS = frozenset(
    path for _, _, path in CANONICAL_REPORT_DECLARATIONS
)
GO_COMPONENTS = frozenset({"go-gateway", "go-ws-hub", "go-file-processor", "go-shared"})
RUST_COMPONENTS = frozenset(
    {"rust-native", "rust-pyo3-sanitizer", "rust-wasm-sanitizer", "rust-crypto"}
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
ASCII_DECIMAL_PATTERN = re.compile(r"^[0-9]+$")
CONDITION_COVERAGE_PATTERN = re.compile(
    r"^\s*[0-9]+(?:\.[0-9]+)?%\s+\((?P<covered>[0-9]+)\s*/\s*(?P<total>[0-9]+)\)\s*$"
)
GO_HEADER_PATTERN = re.compile(r"^mode: (?:set|count|atomic)$")
GO_RECORD_PATTERN = re.compile(
    r"^(?P<filename>.+):(?P<start_line>[0-9]+)\.(?P<start_column>[0-9]+),"
    r"(?P<end_line>[0-9]+)\.(?P<end_column>[0-9]+) "
    r"(?P<statements>[0-9]+) (?P<count>[0-9]+)$"
)
WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
# Go's profile parser uses signed int counters; use its portable 64-bit ceiling
# consistently for every native parser and for post-aggregation metric totals.
MAX_COVERAGE_COUNTER = (1 << 63) - 1
# This quantization is display-only; strict floor checks use integer arithmetic.
PERCENT_QUANTUM = Decimal("0.000001")
XML_DECLARATION_PATTERN = re.compile(
    r"^\s*<\?xml\b(?P<declaration>.*?)\?>",
    flags=re.IGNORECASE | re.DOTALL,
)
XML_ENCODING_PATTERN = re.compile(
    r"\bencoding\s*=\s*(?P<quote>['\"])(?P<encoding>[^'\"]+)(?P=quote)",
    flags=re.IGNORECASE,
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
    file_metrics: dict[str, dict[str, dict[str, object]]]
    sha256: str


@dataclass(frozen=True)
class _RawReport:
    component: str
    report_format: str
    path: Path
    raw: bytes
    sha256: str
    supplemental: tuple[_RawReport, ...] = ()


@dataclass(frozen=True)
class _PreparedInvocation:
    arguments: argparse.Namespace
    output_path: Path
    report_inputs: tuple[_ReportInput, ...]
    floors: dict[str, dict[str, int]]
    expected_reports: frozenset[tuple[str, str, str]]
    manifest_path: str
    provenance: dict[str, str]
    tool_versions: dict[str, str]
    contract: dict[str, object]
    source_inventory: dict[str, frozenset[str]]


@dataclass(frozen=True)
class _ContractConfiguration:
    floors: dict[str, dict[str, int]]
    source_roots: dict[str, tuple[str, ...]]
    expected_reports: frozenset[tuple[str, str, str]]
    manifest_path: str
    contract: dict[str, object]


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
    if covered > MAX_COVERAGE_COUNTER or total > MAX_COVERAGE_COUNTER:
        raise _InputError("report counter exceeds the maximum coverage counter")

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


def _vacuous_metric(derivation: str) -> dict[str, object]:
    """Represent a metric with no applicable units as a derived 100% result.

    A source file with no executable lines, branches, or functions has no
    uncovered unit.  Keeping the zero counters preserves the evidence while
    the explicit 100% display value lets the strict Tier0 policy distinguish
    an empty metric from an unavailable measurement.
    """
    return {
        "status": "derived",
        "covered": 0,
        "total": 0,
        "percent": 100.0,
        "derivation": derivation,
    }


def _parse_nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _InputError(f"{field} must be a non-negative integer")
    if value > MAX_COVERAGE_COUNTER:
        raise _InputError(f"{field} exceeds the maximum coverage counter")
    return value


def _parse_nonnegative_decimal(value: str | None, field: str) -> int:
    if value is None or ASCII_DECIMAL_PATTERN.fullmatch(value) is None:
        raise _InputError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except ValueError as error:
        raise _InputError(f"{field} must be a non-negative integer") from error
    return _parse_nonnegative_integer(parsed, field)


def _is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction()) if callable(is_junction) else False
    except OSError:
        return True


def _canonical_evidence_path(path: Path) -> str:
    root = REPOSITORY_ROOT.resolve(strict=True)
    candidate = path if path.is_absolute() else REPOSITORY_ROOT / path
    try:
        lexical = candidate.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise _InputError(f"report path is outside the repository: {path}") from error
    current = REPOSITORY_ROOT
    for part in lexical.parts:
        current /= part
        if _is_link_or_junction(current):
            raise _InputError(
                f"report path resolves through a symlink or junction: {path}"
            )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise _InputError(
            f"report is missing or unreadable: {path}: {error}"
        ) from error
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise _InputError(
            f"report path resolves outside the repository: {path}"
        ) from error
    canonical = relative.as_posix()
    if str(PurePosixPath(canonical)) != canonical or canonical in {"", "."}:
        raise _InputError(f"report path is not canonical: {path}")
    if not resolved.is_file():
        raise _InputError(f"report path must identify a regular file: {path}")
    return canonical


def _read_report_bytes(path: Path) -> bytes:
    _canonical_evidence_path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise _InputError(f"unable to read report {path}: {error}") from error
    if not raw:
        raise _InputError(f"report is empty: {path}")
    return raw


def _decode_report(
    raw: bytes,
    report_name: str,
    *,
    encoding: str = "utf-8",
) -> str:
    try:
        return raw.decode(encoding)
    except (LookupError, UnicodeDecodeError) as error:
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
        if (
            len(comparison_parts) > len(root_parts)
            and comparison_parts[: len(root_parts)] == root_parts
        ):
            return True
    return False


def _source_path_is_component_root(
    component: str,
    source_parts: Sequence[str],
) -> bool:
    comparison_parts = tuple(_source_path_key(part) for part in source_parts)
    return any(
        comparison_parts
        == tuple(_source_path_key(part) for part in root.split("/") if part)
        for root in SOURCE_ROOTS[component]
    )


def _canonical_source_identity(component: str, raw_path: str) -> str:
    """Validate and normalize one report-embedded source path for a component."""
    if not raw_path:
        raise _InputError("source path is empty")
    if any(unicodedata.category(character) == "Cc" for character in raw_path):
        raise _InputError("source path contains a control character")

    normalized_path = raw_path.replace("\\", "/")
    if normalized_path.startswith("//"):
        raise _InputError("source path must not use a UNC path")

    if WINDOWS_DRIVE_PATH_PATTERN.match(normalized_path):
        if len(normalized_path) < 3 or normalized_path[2] != "/":
            raise _InputError("source path must not be drive-relative")
        if os.name != "nt":
            raise _InputError("source path uses a foreign Windows drive")
        try:
            resolved_p = Path(normalized_path).resolve()
            resolved_root = REPOSITORY_ROOT.resolve()
            relative_parts = resolved_p.relative_to(resolved_root).parts
        except ValueError as error:
            raise _InputError("source path is outside the repository") from error
    elif normalized_path.startswith("/"):
        if os.name == "nt":
            raise _InputError("source path must not be root-relative on Windows")
        else:
            try:
                resolved_p = Path(normalized_path).resolve()
                resolved_root = REPOSITORY_ROOT.resolve()
                relative_parts = resolved_p.relative_to(resolved_root).parts
            except ValueError as error:
                raise _InputError("source path is outside the repository") from error
    else:
        relative_parts = tuple(normalized_path.split("/"))

    # Normalize relative parts to resolve . and ..
    source_parts = _normalize_relative_source_parts(relative_parts)

    # Strip leading repository name if it remains
    if source_parts and source_parts[0] in {
        "university_ecosystem",
        "university-ecosystem",
    }:
        source_parts = source_parts[1:]

    # Apply prefix adjustments for components to match local source layout
    OTHER_ROOTS = {
        "frontend",
        "services",
        "native",
        "crates",
        "infra",
        "infrastructure",
        "k8s",
        "charts",
        ".github",
        "scripts",
    }
    if component == "frontend":
        if source_parts and source_parts[0].casefold() != "frontend":
            if source_parts[0].casefold() == "src":
                source_parts = ("frontend", *source_parts)
    elif component == "python":
        if (
            source_parts
            and not _source_path_is_within_component_root(component, source_parts)
            and not _source_path_is_component_root(component, source_parts)
        ):
            if source_parts[0].casefold() not in OTHER_ROOTS:
                source_parts = ("app", *source_parts)
    elif component == "go-gateway":
        if len(source_parts) >= 3 and source_parts[:3] == (
            "github.com",
            "university-ecosystem",
            "gateway",
        ):
            source_parts = ("services", "gateway", *source_parts[3:])
    elif component == "go-ws-hub":
        if len(source_parts) >= 3 and source_parts[:3] == (
            "github.com",
            "university-ecosystem",
            "ws-hub",
        ):
            source_parts = ("services", "ws-hub", *source_parts[3:])
    elif component == "go-file-processor":
        if len(source_parts) >= 3 and source_parts[:3] == (
            "github.com",
            "university-ecosystem",
            "file-processor",
        ):
            source_parts = ("services", "file-processor", *source_parts[3:])
    elif component == "go-shared":
        if len(source_parts) >= 3 and source_parts[:3] == (
            "github.com",
            "university-ecosystem",
            "uni-cli",
        ):
            source_parts = ("services", "cmd", "uni-cli", *source_parts[3:])
        elif len(source_parts) >= 5 and source_parts[:5] == (
            "github.com",
            "university-ecosystem",
            "services",
            "pkg",
            "spiffe",
        ):
            source_parts = ("services", "pkg", "spiffe", *source_parts[5:])

    _reject_source_symlink_parts(source_parts)
    if not _source_path_is_within_component_root(component, source_parts):
        if _source_path_is_component_root(component, source_parts):
            raise _InputError(
                "source path must identify a file below configured roots "
                f"for component {component}"
            )
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
    ignore_outside_files: bool = False,
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
        try:
            source_identity = _canonical_source_identity(component, filename)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
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
    ignore_outside_files: bool = False,
) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "coverage XML", encoding="utf-8-sig")
    declaration = XML_DECLARATION_PATTERN.match(text)
    if declaration is not None:
        declared_encoding = XML_ENCODING_PATTERN.search(
            declaration.group("declaration")
        )
        if declared_encoding is not None and declared_encoding.group(
            "encoding"
        ).casefold() not in {"utf-8", "utf8"}:
            raise _InputError("coverage XML declaration must use UTF-8 encoding")
    if "<!doctype" in text.casefold() or "<!entity" in text.casefold():
        raise _InputError("coverage XML must not contain DTD or entity declarations")
    try:
        # DTD and entity declarations are rejected before using the required
        # standard-library Cobertura parser.
        root = ElementTree.fromstring(text)  # noqa: S314
    except (ElementTree.ParseError, LookupError, ValueError) as error:
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
    lines = _coverage_xml_source_lines(root, component, ignore_outside_files)

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
        if ignore_outside_files:
            line_metric = line_detail_metric
        else:
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
        if ignore_outside_files:
            branch_metric = branch_detail_metric
        else:
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
    count = sum(
        1
        for k in record.function_declarations
        if k == function_name or k.startswith(function_name + "#")
    )
    unique_name = f"{function_name}#{count}"
    record.function_declarations[unique_name] = (start_line, end_line)


def _parse_lcov_fnda(
    record: _LcovRecord,
    value: str,
    line_number: int,
) -> None:
    count_value, separator, function_name = value.partition(",")
    if not separator or not function_name:
        raise _InputError(f"LCOV FNDA at line {line_number} is malformed")
    count = sum(
        1
        for k in record.function_hits
        if k == function_name or k.startswith(function_name + "#")
    )
    unique_name = f"{function_name}#{count}"
    record.function_hits[unique_name] = _parse_lcov_counter(
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
        if has_total and record.summaries[total_name] == 0:
            return 0, 0
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
    ignore_outside_files: bool = False,
) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "LCOV report")
    records: list[_LcovRecord] = []
    current = _LcovRecord()
    current_has_content = False
    seen_sources: set[str] = set()
    source_spellings: dict[str, str] = {}
    counter_names = frozenset({"LF", "LH", "BRF", "BRH", "FNF", "FNH"})
    skip_record = False

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        if line == "end_of_record":
            if skip_record:
                current = _LcovRecord()
                skip_record = False
                current_has_content = False
                continue
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
        if skip_record:
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
            try:
                current.source = _canonical_source_identity(component, value)
            except _InputError as error:
                if ignore_outside_files and "configured roots" in str(error):
                    skip_record = True
                    continue
                raise
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


def _parse_istanbul_counter_map(
    value: object,
    field: str,
) -> list[int]:
    if not isinstance(value, dict):
        raise _InputError(f"Istanbul JSON {field} counters must be an object")
    counters: list[int] = []
    for key, counter in value.items():
        if not isinstance(key, str):
            raise _InputError(f"Istanbul JSON {field} counter key must be a string")
        counters.append(
            _parse_nonnegative_integer(counter, f"Istanbul JSON {field}[{key}]")
        )
    return counters


def _validate_istanbul_source_map(
    record: dict[str, object],
    *,
    counter_field: str,
    map_field: str,
    source: str,
) -> None:
    counters = record.get(counter_field)
    source_map = record.get(map_field)
    if not isinstance(counters, dict):
        raise _InputError(
            f"Istanbul JSON {counter_field} for {source} counters must be an object"
        )
    if not isinstance(source_map, dict):
        raise _InputError(f"Istanbul JSON {map_field} for {source} must be an object")
    if set(source_map) != set(counters):
        raise _InputError(
            f"Istanbul JSON {map_field} for {source} must match {counter_field} keys"
        )
    if not all(isinstance(value, dict) for value in source_map.values()):
        raise _InputError(
            f"Istanbul JSON {map_field} for {source} entries must be objects"
        )


def _coverage_py_summary_metric(
    summary: object,
    *,
    covered_key: str,
    total_key: str,
    field: str,
) -> dict[str, object]:
    if not isinstance(summary, dict):
        raise _InputError(f"coverage.py JSON {field} must be an object")
    covered = _parse_nonnegative_integer(
        summary.get(covered_key), f"coverage.py JSON {field}.{covered_key}"
    )
    total = _parse_nonnegative_integer(
        summary.get(total_key), f"coverage.py JSON {field}.{total_key}"
    )
    return _measured_metric("native", covered, total)


def _coverage_py_line_set(value: object, field: str) -> set[int]:
    if not isinstance(value, list):
        raise _InputError(f"coverage.py JSON {field} must be an array")
    result: set[int] = set()
    for index, raw_line in enumerate(value):
        line = _parse_nonnegative_integer(
            raw_line, f"coverage.py JSON {field}[{index}]"
        )
        if line == 0:
            raise _InputError(f"coverage.py JSON {field}[{index}] must be positive")
        if line in result:
            raise _InputError(
                f"coverage.py JSON {field} contains duplicate line {line}"
            )
        result.add(line)
    return result


def _coverage_py_branch_set(value: object, field: str) -> set[tuple[int, int]]:
    if not isinstance(value, list):
        raise _InputError(f"coverage.py JSON {field} must be an array")
    result: set[tuple[int, int]] = set()
    for index, raw_branch in enumerate(value):
        if not isinstance(raw_branch, list) or len(raw_branch) != 2:
            raise _InputError(
                f"coverage.py JSON {field}[{index}] must be a two-integer arc"
            )
        origin, destination = raw_branch
        if (
            isinstance(origin, bool)
            or not isinstance(origin, int)
            or origin <= 0
            or isinstance(destination, bool)
            or not isinstance(destination, int)
            or destination == 0
        ):
            raise _InputError(
                f"coverage.py JSON {field}[{index}] must be a valid source arc"
            )
        branch = (origin, destination)
        if branch in result:
            raise _InputError(
                f"coverage.py JSON {field} contains duplicate arc {branch!r}"
            )
        result.add(branch)
    return result


def _parse_python_coverage_json(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
) -> tuple[
    dict[str, dict[str, object]],
    dict[str, dict[str, dict[str, object]]],
]:
    text = _decode_report(raw, "coverage.py JSON report")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as error:
        raise _InputError(str(error)) from error
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise _InputError(f"malformed coverage.py JSON: {error}") from error
    if not isinstance(document, dict):
        raise _InputError("coverage.py JSON root must be an object")
    files = document.get("files")
    totals = document.get("totals")
    if not isinstance(files, dict) or not files:
        raise _InputError("coverage.py JSON files must be a non-empty object")
    if not isinstance(totals, dict):
        raise _InputError("coverage.py JSON totals must be an object")

    file_metrics: dict[str, dict[str, dict[str, object]]] = {}
    aggregate_statements_covered = 0
    aggregate_statements_total = 0
    aggregate_branches_covered = 0
    aggregate_branches_total = 0
    ignored_outside_file = False
    for raw_source, record in files.items():
        if not isinstance(raw_source, str) or not isinstance(record, dict):
            raise _InputError("coverage.py JSON contains an invalid file record")
        try:
            source = _canonical_source_identity(component, raw_source)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                ignored_outside_file = True
                continue
            raise
        if source in file_metrics:
            raise _InputError(f"coverage.py JSON has duplicate source {source}")
        summary = record.get("summary")
        statement_metric = _coverage_py_summary_metric(
            summary,
            covered_key="covered_lines",
            total_key="num_statements",
            field=f"files[{raw_source}].summary",
        )
        branch_metric = _coverage_py_summary_metric(
            summary,
            covered_key="covered_branches",
            total_key="num_branches",
            field=f"files[{raw_source}].summary",
        )
        executed_lines = _coverage_py_line_set(
            record.get("executed_lines"), f"files[{raw_source}].executed_lines"
        )
        missing_lines = _coverage_py_line_set(
            record.get("missing_lines"), f"files[{raw_source}].missing_lines"
        )
        if executed_lines & missing_lines:
            raise _InputError(
                f"coverage.py JSON files[{raw_source}] line inventories overlap"
            )
        if statement_metric["covered"] != len(executed_lines) or statement_metric[
            "total"
        ] != len(executed_lines | missing_lines):
            raise _InputError(
                f"coverage.py JSON files[{raw_source}] statement summary disagrees "
                "with executed_lines/missing_lines"
            )
        executed_branches = _coverage_py_branch_set(
            record.get("executed_branches"),
            f"files[{raw_source}].executed_branches",
        )
        missing_branches = _coverage_py_branch_set(
            record.get("missing_branches"),
            f"files[{raw_source}].missing_branches",
        )
        if executed_branches & missing_branches:
            raise _InputError(
                f"coverage.py JSON files[{raw_source}] branch inventories overlap"
            )
        if branch_metric["covered"] != len(executed_branches) or branch_metric[
            "total"
        ] != len(executed_branches | missing_branches):
            raise _InputError(
                f"coverage.py JSON files[{raw_source}] branch summary disagrees with "
                "executed_branches/missing_branches"
            )
        aggregate_statements_covered += len(executed_lines)
        aggregate_statements_total += len(executed_lines | missing_lines)
        aggregate_branches_covered += len(executed_branches)
        aggregate_branches_total += len(executed_branches | missing_branches)
        file_metrics[source] = {
            "lines": _unmeasured_metric(
                "unsupported", reason_code="coverage_json_line_counter_not_used"
            ),
            "statements": statement_metric,
            "branches": branch_metric,
            "functions": _unmeasured_metric(
                "unsupported", reason_code="coverage_json_has_no_function_counter"
            ),
        }
    if not file_metrics:
        raise _InputError("coverage.py JSON contains no in-scope file records")
    statement_totals = _coverage_py_summary_metric(
        totals,
        covered_key="covered_lines",
        total_key="num_statements",
        field="totals",
    )
    branch_totals = _coverage_py_summary_metric(
        totals,
        covered_key="covered_branches",
        total_key="num_branches",
        field="totals",
    )
    if not ignored_outside_file and (
        statement_totals["covered"] != aggregate_statements_covered
        or statement_totals["total"] != aggregate_statements_total
        or branch_totals["covered"] != aggregate_branches_covered
        or branch_totals["total"] != aggregate_branches_total
    ):
        raise _InputError(
            "coverage.py JSON totals disagree with the complete file inventory"
        )
    return (
        {
            "lines": _unmeasured_metric(
                "unsupported", reason_code="coverage_json_line_counter_not_used"
            ),
            "statements": statement_totals,
            "branches": branch_totals,
            "functions": _unmeasured_metric(
                "unsupported", reason_code="coverage_json_has_no_function_counter"
            ),
        },
        file_metrics,
    )


def _parse_istanbul_branch_map(value: object) -> list[int]:
    if not isinstance(value, dict):
        raise _InputError("Istanbul JSON branch counters must be an object")
    counters: list[int] = []
    for key, branch_counts in value.items():
        if not isinstance(key, str):
            raise _InputError("Istanbul JSON branch counter key must be a string")
        if not isinstance(branch_counts, list):
            raise _InputError(f"Istanbul JSON b[{key}] must be an array of counters")
        counters.extend(
            _parse_nonnegative_integer(counter, f"Istanbul JSON b[{key}]")
            for counter in branch_counts
        )
    return counters


def _metric_from_counters(
    counters: Sequence[int],
) -> dict[str, object]:
    return _measured_metric(
        "native",
        sum(counter > 0 for counter in counters),
        len(counters),
    )


def _parse_frontend_istanbul_json(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
) -> tuple[
    dict[str, dict[str, object]],
    dict[str, dict[str, dict[str, object]]],
]:
    text = _decode_report(raw, "Istanbul JSON report")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as error:
        raise _InputError(str(error)) from error
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise _InputError(f"malformed Istanbul JSON: {error}") from error
    if not isinstance(document, dict):
        raise _InputError("Istanbul JSON root must be an object")
    if not document:
        raise _InputError("Istanbul JSON contains no file records")

    total_statements: list[int] = []
    total_branches: list[int] = []
    total_functions: list[int] = []
    file_metrics: dict[str, dict[str, dict[str, object]]] = {}
    source_spellings: dict[str, str] = {}
    for raw_source, record in document.items():
        if not isinstance(raw_source, str):
            raise _InputError("Istanbul JSON source path must be a string")
        try:
            source = _canonical_source_identity(component, raw_source)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
        if source in file_metrics:
            raise _InputError(f"Istanbul JSON has duplicate source {source}")
        if not isinstance(record, dict):
            raise _InputError(
                f"Istanbul JSON record for {raw_source} must be an object"
            )

        record_path = record.get("path")
        if record_path is not None:
            if not isinstance(record_path, str):
                raise _InputError(
                    f"Istanbul JSON record for {raw_source}.path must be a string"
                )
            try:
                record_identity = _canonical_source_identity(component, record_path)
            except _InputError as error:
                if ignore_outside_files and "configured roots" in str(error):
                    continue
                raise
            if record_identity != source:
                raise _InputError(
                    f"Istanbul JSON record for {raw_source} has conflicting path"
                )
            _register_source_spelling(
                source_spellings,
                source,
                record_path,
                "Istanbul JSON report",
            )
        _register_source_spelling(
            source_spellings,
            source,
            raw_source,
            "Istanbul JSON report",
        )

        _validate_istanbul_source_map(
            record,
            counter_field="s",
            map_field="statementMap",
            source=source,
        )
        _validate_istanbul_source_map(
            record,
            counter_field="b",
            map_field="branchMap",
            source=source,
        )
        _validate_istanbul_source_map(
            record,
            counter_field="f",
            map_field="fnMap",
            source=source,
        )
        statement_counters = _parse_istanbul_counter_map(
            record.get("s"),
            f"s for {source}",
        )
        branch_counters = _parse_istanbul_branch_map(record.get("b"))
        function_counters = _parse_istanbul_counter_map(
            record.get("f"),
            f"f for {source}",
        )
        total_statements.extend(statement_counters)
        total_branches.extend(branch_counters)
        total_functions.extend(function_counters)
        file_metrics[source] = {
            "lines": _unmeasured_metric(
                "unsupported",
                reason_code="istanbul_json_line_counter_not_used",
            ),
            "statements": _metric_from_counters(statement_counters),
            "branches": _metric_from_counters(branch_counters),
            "functions": _metric_from_counters(function_counters),
        }

    if not file_metrics:
        raise _InputError("Istanbul JSON contains no in-scope file records")
    return (
        {
            "lines": _unmeasured_metric(
                "unsupported",
                reason_code="istanbul_json_line_counter_not_used",
            ),
            "statements": _metric_from_counters(total_statements),
            "branches": _metric_from_counters(total_branches),
            "functions": _metric_from_counters(total_functions),
        },
        file_metrics,
    )


def _inclusive_interval_union_length(intervals: Sequence[tuple[int, int]]) -> int:
    """Return the inclusive union size without materializing individual lines."""
    ordered = sorted(intervals)
    if not ordered:
        return 0

    start, end = ordered[0]
    if end < start:
        raise _InputError("Go coverprofile line range ends before it starts")
    length = 0
    for next_start, next_end in ordered[1:]:
        if next_end < next_start:
            raise _InputError("Go coverprofile line range ends before it starts")
        if next_start > end + 1:
            length += end - start + 1
            start, end = next_start, next_end
            continue
        end = max(end, next_end)
    return length + end - start + 1


def _go_line_coverage_counts(
    source_intervals: Mapping[str, Sequence[tuple[int, int, bool]]],
) -> tuple[int, int]:
    """Return covered/total unique source lines from grouped Go block ranges."""
    covered = 0
    total = 0
    for intervals in source_intervals.values():
        total += _inclusive_interval_union_length(
            [(start, end) for start, end, _ in intervals]
        )
        covered += _inclusive_interval_union_length(
            [(start, end) for start, end, is_covered in intervals if is_covered]
        )
    return covered, total


def _parse_go_coverprofile(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
) -> dict[str, dict[str, object]]:
    text = _decode_report(raw, "Go coverprofile")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or GO_HEADER_PATTERN.fullmatch(lines[0]) is None:
        raise _InputError("Go coverprofile must begin with a valid mode header")
    if len(lines) == 1:
        raise _InputError("Go coverprofile contains no coverage records")

    total_statements = 0
    covered_statements = 0
    source_intervals: defaultdict[str, list[tuple[int, int, bool]]] = defaultdict(list)
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
        if end_line < start_line:
            raise _InputError("Go coverprofile line range ends before it starts")
        raw_filename = match.group("filename")
        try:
            filename = _canonical_source_identity(component, raw_filename)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
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
        source_intervals[filename].append((start_line, end_line, count > 0))

    covered_lines, total_lines = _go_line_coverage_counts(source_intervals)

    return {
        "lines": _measured_metric(
            "derived",
            covered_lines,
            total_lines,
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
    ignore_outside_files: bool = False,
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
            is_outside = False
            for field_name in ("filename", "path"):
                if field_name not in entry:
                    continue
                value = entry[field_name]
                if not isinstance(value, str):
                    raise _InputError(
                        f"LLVM JSON files[{index}].{field_name} must be a string"
                    )
                try:
                    identity_val = _canonical_source_identity(component, value)
                except _InputError as error:
                    if ignore_outside_files and "configured roots" in str(error):
                        is_outside = True
                        break
                    raise
                identities.append((identity_val, value))
            if is_outside:
                continue
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


def _parse_rust_crypto_source_function_pair(
    document: dict[str, object],
    component: str,
    ignore_outside_files: bool,
) -> tuple[int, int] | None:
    """Count source functions without wasm-bindgen-generated glue symbols.

    ``cargo llvm-cov --all-targets`` includes generated wasm-bindgen wrapper
    monomorphizations in its function summary.  Those symbols are not source
    functions and can be unexecuted in the native test binary even when every
    Rust function is covered.  The detailed LLVM function list retains the
    source filename, source span, and execution count needed to deduplicate
    target-specific instantiations while excluding only the generated ``_RNC``
    symbols for the rust-crypto component.
    """
    if component != "rust-crypto" or "data" not in document:
        return None
    data = document["data"]
    if not isinstance(data, list) or len(data) != 1:
        return None
    entry = data[0]
    if not isinstance(entry, dict) or "functions" not in entry:
        return None
    reported_files = entry.get("files")
    if not isinstance(reported_files, list):
        return None
    reported_identities: set[str] = set()
    for file_index, file_entry in enumerate(reported_files):
        if not isinstance(file_entry, dict):
            raise _InputError(f"LLVM JSON files[{file_index}] must be an object")
        for field_name in ("filename", "path"):
            filename = file_entry.get(field_name)
            if filename is None:
                continue
            if not isinstance(filename, str):
                raise _InputError(
                    f"LLVM JSON files[{file_index}].{field_name} must be a string"
                )
            try:
                reported_identities.add(_canonical_source_identity(component, filename))
            except _InputError as error:
                if ignore_outside_files and (
                    "outside the repository" in str(error)
                    or "configured roots" in str(error)
                ):
                    continue
                raise
    if not reported_identities:
        return None
    function_entries = entry["functions"]
    if not isinstance(function_entries, list):
        raise _InputError("LLVM JSON data[0].functions must be a list")

    source_functions: dict[tuple[str, int, int], bool] = {}
    for index, function in enumerate(function_entries):
        if not isinstance(function, dict):
            raise _InputError(f"LLVM JSON functions[{index}] must be an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise _InputError(f"LLVM JSON functions[{index}].name must be a string")
        if name.startswith("_RNC"):
            continue

        filenames = function.get("filenames")
        if not isinstance(filenames, list) or not filenames:
            raise _InputError(
                f"LLVM JSON functions[{index}].filenames must be a non-empty list"
            )
        identities: list[str] = []
        for filename in filenames:
            if not isinstance(filename, str):
                raise _InputError(
                    f"LLVM JSON functions[{index}].filenames must contain strings"
                )
            try:
                identities.append(_canonical_source_identity(component, filename))
            except _InputError as error:
                if ignore_outside_files and (
                    "outside the repository" in str(error)
                    or "configured roots" in str(error)
                ):
                    continue
                raise
        if not identities or not any(
            identity in reported_identities for identity in identities
        ):
            continue

        regions = function.get("regions")
        if not isinstance(regions, list) or not regions:
            raise _InputError(
                f"LLVM JSON functions[{index}].regions must be a non-empty list"
            )
        line_spans: list[tuple[int, int]] = []
        for region_index, region in enumerate(regions):
            if not isinstance(region, list) or len(region) < 4:
                raise _InputError(
                    f"LLVM JSON functions[{index}].regions[{region_index}] must contain source "
                    "coordinates"
                )
            start_line = _parse_nonnegative_integer(
                region[0],
                f"LLVM functions[{index}].regions[{region_index}] start line",
            )
            end_line = _parse_nonnegative_integer(
                region[2],
                f"LLVM functions[{index}].regions[{region_index}] end line",
            )
            if end_line < start_line:
                raise _InputError(
                    f"LLVM functions[{index}].regions[{region_index}] has a reversed span"
                )
            line_spans.append((start_line, end_line))

        count = _parse_nonnegative_integer(
            function.get("count"), f"LLVM functions[{index}] count"
        )
        key = (
            identities[0],
            min(span[0] for span in line_spans),
            max(span[1] for span in line_spans),
        )
        source_functions[key] = source_functions.get(key, False) or count > 0

    if not source_functions:
        return None
    covered = sum(covered_function for covered_function in source_functions.values())
    return covered, len(source_functions)


def _parse_rust_llvm_json(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
    *,
    native_branches: bool = False,
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
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
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

    _validate_rust_file_identities(component, file_collections, ignore_outside_files)

    line_pairs = [_parse_rust_counter(totals, "lines") for totals in totals_entries]
    branch_pairs = (
        [_parse_rust_counter(totals, "branches") for totals in totals_entries]
        if native_branches
        else []
    )
    covered_branches = sum(covered for covered, _ in branch_pairs)
    total_branches = sum(total for _, total in branch_pairs)
    source_function_pair = _parse_rust_crypto_source_function_pair(
        document, component, ignore_outside_files
    )
    function_pairs = (
        [source_function_pair]
        if source_function_pair is not None
        else [_parse_rust_counter(totals, "functions") for totals in totals_entries]
    )
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
        "branches": (
            (
                _vacuous_metric("Nightly LLVM report contains no branch units")
                if total_branches == 0
                else _measured_metric("native", covered_branches, total_branches)
            )
            if native_branches
            else _unmeasured_metric(
                "experimental",
                reason_code="llvm_branch_coverage_unstable",
            )
        ),
        "functions": _measured_metric(
            "native",
            sum(covered for covered, _ in function_pairs),
            sum(total for _, total in function_pairs),
        ),
    }


def _rust_source_line_metric(
    entry: dict[str, object],
) -> dict[str, object] | None:
    """Derive source-line coverage from LLVM's non-gap segments.

    LLVM's file summary can count macro expansion fragments and generic
    instantiations as separate line obligations even when they map to one
    source line.  For Tier0 file evidence, source lines are the auditable
    unit: a line is covered when any non-gap segment on that line executed.
    The component-level metric continues to use LLVM's native summary.
    """
    raw_segments = entry.get("segments")
    if raw_segments is None:
        return None
    if not isinstance(raw_segments, list):
        raise _InputError("LLVM JSON file segments must be a list")

    source_lines: dict[int, bool] = {}
    for index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, list) or len(raw_segment) < 6:
            raise _InputError(
                f"LLVM JSON segments[{index}] must contain line, count, and flags"
            )
        line = _parse_nonnegative_integer(raw_segment[0], f"LLVM segment {index} line")
        count = _parse_nonnegative_integer(
            raw_segment[2], f"LLVM segment {index} count"
        )
        has_count = raw_segment[3]
        is_gap_region = raw_segment[5]
        if not isinstance(has_count, bool) or not isinstance(is_gap_region, bool):
            raise _InputError(f"LLVM segments[{index}] coverage flags must be booleans")
        if not has_count or is_gap_region:
            continue
        source_lines[line] = source_lines.get(line, False) or count > 0

    if not source_lines:
        return _vacuous_metric("LLVM source contains no executable line segments")
    return _measured_metric(
        "derived",
        sum(is_covered for is_covered in source_lines.values()),
        len(source_lines),
        derivation=(
            "unique source lines from non-gap LLVM segments; covered when any "
            "segment on the line is executed"
        ),
    )


def _rust_source_branch_metrics(
    document: dict[str, object],
    component: str,
    ignore_outside_files: bool,
) -> dict[str, dict[str, object]]:
    """Collapse LLVM branch records to source-level branch sites.

    Generic Rust functions can produce several LLVM branch records for the
    same source condition.  A source branch is covered when at least one
    instrumented instantiation exercises each outcome; counting every
    monomorphization would make the Tier0 result depend on compiler codegen.
    """
    entries: list[object] = []
    top_level_files = document.get("files")
    if isinstance(top_level_files, list):
        entries.extend(top_level_files)
    data = document.get("data")
    if (
        isinstance(data, list)
        and data
        and isinstance(data[0], dict)
        and isinstance(data[0].get("files"), list)
    ):
        entries.extend(cast(list[object], data[0]["files"]))

    result: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("filename", entry.get("path"))
        if not isinstance(raw_path, str):
            continue
        try:
            filename = _canonical_source_identity(component, raw_path)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
        branch_records = entry.get("branches", [])
        if not isinstance(branch_records, list):
            raise _InputError("LLVM JSON file branches must be a list")
        sites: dict[tuple[int, int, int, int], list[bool]] = {}
        for index, branch in enumerate(branch_records):
            if not isinstance(branch, list) or len(branch) < 6:
                raise _InputError(
                    f"LLVM JSON branches[{index}] must contain source coordinates "
                    "and both outcome counters"
                )
            coordinates: tuple[int, int, int, int] = (
                _parse_nonnegative_integer(
                    branch[0], f"LLVM branch {index} coordinate 0"
                ),
                _parse_nonnegative_integer(
                    branch[1], f"LLVM branch {index} coordinate 1"
                ),
                _parse_nonnegative_integer(
                    branch[2], f"LLVM branch {index} coordinate 2"
                ),
                _parse_nonnegative_integer(
                    branch[3], f"LLVM branch {index} coordinate 3"
                ),
            )
            true_count = _parse_nonnegative_integer(
                branch[4], f"LLVM branch {index} true count"
            )
            false_count = _parse_nonnegative_integer(
                branch[5], f"LLVM branch {index} false count"
            )
            outcomes = sites.setdefault(coordinates, [False, False])
            outcomes[0] = outcomes[0] or true_count > 0
            outcomes[1] = outcomes[1] or false_count > 0
        total = len(sites) * 2
        covered = sum(outcome for outcomes in sites.values() for outcome in outcomes)
        result[filename] = (
            _vacuous_metric("Nightly LLVM source contains no branch sites")
            if total == 0
            else _measured_metric(
                "derived",
                covered,
                total,
                derivation=(
                    "source branch sites deduplicated across LLVM generic "
                    "instantiations; each outcome covered by any instantiation"
                ),
            )
        )
    return result


def _load_python_source_tree(source: str) -> ast.Module | None:
    """Load a repository Python source file for derived Tier0 metrics."""
    source_path = REPOSITORY_ROOT / source
    try:
        source_text = source_path.read_text(encoding="utf-8")
        return ast.parse(source_text, filename=str(source_path))
    except (FileNotFoundError, OSError, SyntaxError, UnicodeDecodeError):
        return None


def _python_function_entry_line(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> int:
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body.pop(0)
    while body and isinstance(body[0], (ast.Global, ast.Nonlocal)):
        body.pop(0)
    return body[0].lineno if body else function.lineno


def _is_mutmut_generated_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Identify helper functions injected by mutmut's source trampoline.

    mutmut rewrites each source file in its isolated ``mutants/`` tree and
    appends one function per generated mutant.  Those helpers are execution
    machinery, not source-level coverage obligations.  Keeping this filter in
    the AST-derived path makes the normalizer measure the same source units in
    the regular and mutation-test environments.
    """
    return "_mutmut_" in node.name


def _derive_python_function_metric(
    source: str,
    line_hits: dict[int, bool],
) -> dict[str, object] | None:
    tree = _load_python_source_tree(source)
    if tree is None:
        return None
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not _is_mutmut_generated_function(node)
    ]
    if not functions:
        return _vacuous_metric("AST source contains no function definitions")
    covered = sum(
        line_hits.get(_python_function_entry_line(function), False)
        for function in functions
    )
    return _measured_metric(
        "derived",
        covered,
        len(functions),
        derivation=(
            "AST function entries covered when the first executable body line "
            "is reported as executed"
        ),
    )


def _python_has_branch_constructs(tree: ast.Module) -> bool:
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.IfExp,
        ast.Try,
        ast.Match,
        ast.BoolOp,
    )

    def _walk_runtime_nodes(node: ast.AST) -> Iterator[ast.AST]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                _is_mutmut_generated_function(child)
            ):
                # Mutmut's generated wrappers contain their own dispatch
                # branches.  They are not source-level branch obligations.
                continue
            if (
                isinstance(child, ast.If)
                and isinstance(child.test, ast.Name)
                and child.test.id == "TYPE_CHECKING"
            ):
                # TYPE_CHECKING blocks are erased at runtime and therefore do
                # not represent executable branch obligations in coverage.
                continue
            yield child
            yield from _walk_runtime_nodes(child)

    if any(isinstance(node, branch_nodes) for node in _walk_runtime_nodes(tree)):
        return True
    return any(
        isinstance(node, ast.comprehension) and bool(node.ifs)
        for node in _walk_runtime_nodes(tree)
    )


def _derive_python_branch_metric(source: str) -> dict[str, object] | None:
    tree = _load_python_source_tree(source)
    if tree is None or _python_has_branch_constructs(tree):
        return None
    return _vacuous_metric("AST source contains no branch construct")


def _parse_tier0_python_files(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
) -> dict[str, dict[str, dict[str, object]]]:
    """Extract file-level Python line/branch/function evidence from Cobertura."""

    text = _decode_report(raw, "coverage XML", encoding="utf-8-sig")
    try:
        root = ElementTree.fromstring(text)  # noqa: S314
    except (ElementTree.ParseError, LookupError, ValueError) as error:
        raise _InputError(f"malformed coverage XML: {error}") from error

    result: dict[str, dict[str, dict[str, object]]] = {}
    for class_element in root.iter():
        if _xml_local_name(class_element) != "class":
            continue
        filename = class_element.get("filename")
        if not filename:
            continue
        try:
            source = _canonical_source_identity(component, filename)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
        line_elements = [
            line
            for child in class_element
            if _xml_local_name(child) == "lines"
            for line in child
            if _xml_local_name(line) == "line"
        ]
        line_hits = {
            _parse_nonnegative_decimal(
                line.get("number"), "Tier0 Python line number"
            ): _parse_nonnegative_decimal(line.get("hits"), "Tier0 Python line hits")
            > 0
            for line in line_elements
        }
        branch_pairs: list[tuple[int, int]] = []
        for line in line_elements:
            condition = line.get("condition-coverage")
            if condition is None:
                continue
            match = CONDITION_COVERAGE_PATTERN.fullmatch(condition)
            if match is None:
                raise _InputError("coverage XML has malformed condition-coverage")
            branch_pairs.append(
                (
                    _parse_nonnegative_decimal(
                        match.group("covered"), "Tier0 branch covered"
                    ),
                    _parse_nonnegative_decimal(
                        match.group("total"), "Tier0 branch total"
                    ),
                )
            )
        methods = [
            method
            for child in class_element
            if _xml_local_name(child) == "methods"
            for method in child
            if _xml_local_name(method) == "method"
        ]
        method_hits: list[bool] = []
        for method in methods:
            method_lines = [
                line
                for child in method
                if _xml_local_name(child) == "lines"
                for line in child
                if _xml_local_name(line) == "line"
            ]
            method_hits.append(
                any(
                    _parse_nonnegative_decimal(line.get("hits"), "Tier0 method hits")
                    > 0
                    for line in method_lines
                )
            )
        functions = (
            _measured_metric("native", sum(method_hits), len(method_hits))
            if methods
            else _derive_python_function_metric(source, line_hits)
        )
        if functions is None:
            functions = _unmeasured_metric(
                "unsupported", reason_code="coverage_xml_has_no_method_breakdown"
            )
        branches = (
            _measured_metric(
                "native",
                sum(covered for covered, _ in branch_pairs),
                sum(total for _, total in branch_pairs),
            )
            if branch_pairs
            else _derive_python_branch_metric(source)
        )
        if branches is None:
            branches = _unmeasured_metric("missing")
        result[source] = {
            "lines": (
                _measured_metric("native", sum(line_hits.values()), len(line_hits))
                if line_hits
                else _vacuous_metric("Cobertura source contains no executable lines")
            ),
            "statements": _unmeasured_metric(
                "unsupported", reason_code="coverage_xml_has_no_statement_counter"
            ),
            "branches": branches,
            "functions": functions,
        }
    return result


def _parse_tier0_frontend_files(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
) -> dict[str, dict[str, dict[str, object]]]:
    """Extract file-level counters from the already-validated LCOV report."""

    text = _decode_report(raw, "LCOV report")
    result: dict[str, dict[str, dict[str, object]]] = {}
    source: str | None = None
    counters: dict[str, int] = {}
    for line in (*text.splitlines(), "end_of_record"):
        field, separator, value = line.partition(":")
        if field == "SF":
            try:
                source = _canonical_source_identity(component, value)
            except _InputError as error:
                if ignore_outside_files and "configured roots" in str(error):
                    source = None
                    counters = {}
                    continue
                raise
            counters = {}
        elif field in {"LF", "LH", "BRF", "BRH", "FNF", "FNH"} and separator:
            if source is not None:
                counters[field] = _parse_lcov_counter(value, f"Tier0 {field}")
        elif field == "end_of_record" and source is not None:
            line_metric = (
                _unmeasured_metric("missing")
                if "LF" not in counters or "LH" not in counters
                else (
                    _vacuous_metric("LCOV source contains no executable lines")
                    if counters["LF"] == 0
                    else _measured_metric("native", counters["LH"], counters["LF"])
                )
            )
            branch_metric = (
                _unmeasured_metric("missing")
                if "BRF" not in counters or "BRH" not in counters
                else (
                    _vacuous_metric("LCOV source contains no branch units")
                    if counters["BRF"] == 0
                    else _measured_metric("native", counters["BRH"], counters["BRF"])
                )
            )
            function_metric = (
                _unmeasured_metric("missing")
                if "FNF" not in counters or "FNH" not in counters
                else (
                    _vacuous_metric("LCOV source contains no function units")
                    if counters["FNF"] == 0
                    else _measured_metric("native", counters["FNH"], counters["FNF"])
                )
            )
            result[source] = {
                "lines": line_metric,
                "statements": _unmeasured_metric(
                    "unsupported", reason_code="lcov_has_no_statement_counter"
                ),
                "branches": branch_metric,
                "functions": function_metric,
            }
            source = None
            counters = {}
    return result


def _parse_tier0_go_files(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
) -> dict[str, dict[str, dict[str, object]]]:
    """Extract per-file line and statement counters from Go coverprofile."""

    text = _decode_report(raw, "Go coverprofile")
    statements: defaultdict[str, list[tuple[int, bool]]] = defaultdict(list)
    intervals: defaultdict[str, list[tuple[int, int, bool]]] = defaultdict(list)
    for line_number, line in enumerate(text.splitlines()[1:], start=2):
        if not line.strip():
            continue
        match = GO_RECORD_PATTERN.fullmatch(line)
        if match is None:
            raise _InputError(f"Go coverprofile record {line_number} is malformed")
        raw_filename = match.group("filename")
        try:
            filename = _canonical_source_identity(component, raw_filename)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
        start = _parse_nonnegative_decimal(
            match.group("start_line"), "Tier0 Go start line"
        )
        end = _parse_nonnegative_decimal(match.group("end_line"), "Tier0 Go end line")
        count = _parse_nonnegative_decimal(
            match.group("count"), "Tier0 Go execution count"
        )
        statement_count = _parse_nonnegative_decimal(
            match.group("statements"), "Tier0 Go statements"
        )
        statements[filename].append((statement_count, count > 0))
        intervals[filename].append((start, end, count > 0))

    result: dict[str, dict[str, dict[str, object]]] = {}
    for filename, entries in statements.items():
        covered_statements = sum(value for value, covered in entries if covered)
        total_statements = sum(value for value, _ in entries)
        covered_lines, total_lines = _go_line_coverage_counts(
            {filename: intervals[filename]}
        )
        result[filename] = {
            "lines": _measured_metric(
                "derived",
                covered_lines,
                total_lines,
                derivation=(
                    "unique source lines in coverprofile blocks; covered when any "
                    "overlapping block has count greater than zero"
                ),
            ),
            "statements": _measured_metric(
                "native", covered_statements, total_statements
            ),
            "branches": _unmeasured_metric(
                "unsupported", reason_code="go_coverprofile_has_no_branch_counter"
            ),
            "functions": _unmeasured_metric(
                "unsupported", reason_code="go_coverprofile_has_no_function_counter"
            ),
        }
    return result


def _parse_tier0_rust_files(
    raw: bytes,
    component: str,
    ignore_outside_files: bool = False,
    *,
    zero_branch_is_vacuous: bool = False,
) -> dict[str, dict[str, dict[str, object]]]:
    """Extract file summaries when llvm-cov JSON provides them."""

    text = _decode_report(raw, "LLVM JSON report")
    document = json.loads(
        text,
        object_pairs_hook=_duplicate_key_object,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(document, dict):
        raise _InputError("LLVM JSON root must be an object")
    source_branch_metrics = (
        _rust_source_branch_metrics(document, component, ignore_outside_files)
        if zero_branch_is_vacuous
        else {}
    )
    entries: list[object] = []
    if isinstance(document.get("files"), list):
        entries.extend(document["files"])
    data = document.get("data")
    if (
        isinstance(data, list)
        and data
        and isinstance(data[0], dict)
        and isinstance(data[0].get("files"), list)
    ):
        entries.extend(data[0]["files"])
    result: dict[str, dict[str, dict[str, object]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("filename", entry.get("path"))
        if not isinstance(raw_path, str):
            continue
        try:
            filename = _canonical_source_identity(component, raw_path)
        except _InputError as error:
            if ignore_outside_files and "configured roots" in str(error):
                continue
            raise
        summary = entry.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        source_line_metric = _rust_source_line_metric(entry)
        file_metrics: dict[str, dict[str, object]] = {}
        for metric_name in METRICS:
            if metric_name == "lines" and source_line_metric is not None:
                file_metrics[metric_name] = source_line_metric
                continue
            value = summary.get(metric_name)
            if isinstance(value, dict):
                try:
                    covered = _parse_nonnegative_integer(
                        value.get("covered"), f"Tier0 LLVM {metric_name} covered"
                    )
                    total = _parse_nonnegative_integer(
                        value.get("count"), f"Tier0 LLVM {metric_name} count"
                    )
                except _InputError:
                    file_metrics[metric_name] = _unmeasured_metric(
                        "unsupported", reason_code="llvm_file_summary_malformed"
                    )
                else:
                    if metric_name == "branches" and zero_branch_is_vacuous:
                        file_metrics[metric_name] = source_branch_metrics.get(
                            filename,
                            _vacuous_metric(
                                "Nightly LLVM source contains no branch sites"
                            ),
                        )
                    else:
                        file_metrics[metric_name] = _measured_metric(
                            "native", covered, total
                        )
            else:
                file_metrics[metric_name] = _unmeasured_metric(
                    "unsupported", reason_code=f"llvm_file_has_no_{metric_name}_counter"
                )
        result[filename] = file_metrics
    return result


def _parse_tier0_files(
    raw_report: _RawReport,
    *,
    ignore_outside_files: bool,
) -> dict[str, dict[str, dict[str, object]]]:
    if raw_report.report_format == "cobertura-xml":
        return _parse_tier0_python_files(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
    if raw_report.report_format == "lcov":
        return _parse_tier0_frontend_files(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
    if raw_report.report_format == "go-coverprofile":
        return _parse_tier0_go_files(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
    if raw_report.report_format == "llvm-cov-json":
        return _parse_tier0_rust_files(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
    if raw_report.report_format == "llvm-cov-branch-json":
        return _parse_tier0_rust_files(
            raw_report.raw,
            raw_report.component,
            ignore_outside_files,
            zero_branch_is_vacuous=True,
        )
    raise _InputError(f"unsupported report format: {raw_report.report_format}")


def _resolve_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    try:
        return Path(os.path.abspath(candidate))
    except OSError as error:
        raise _InputError(f"unable to resolve path {value}: {error}") from error


def _configure_repository_root(value: str | None) -> None:
    global REPOSITORY_ROOT
    candidate = Path(value) if value is not None else DEFAULT_REPOSITORY_ROOT
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise _InputError(
            f"unable to resolve repository root {candidate}: {error}"
        ) from error
    if not resolved.is_dir():
        raise _InputError(f"repository root must be a directory: {resolved}")
    REPOSITORY_ROOT = resolved


def _current_git_head() -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise _InputError(
            "unable to resolve current repository HEAD: git is unavailable"
        )
    try:
        result = subprocess.run(  # noqa: S603
            [git_executable, "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise _InputError(
            f"unable to resolve current repository HEAD: {error}"
        ) from error
    head = result.stdout.strip()
    if SHA_PATTERN.fullmatch(head) is None:
        raise _InputError("current repository HEAD is not a canonical Git SHA")
    return head


def _git_output(arguments: Sequence[str], operation: str) -> bytes:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise _InputError(f"unable to {operation}: git is unavailable")
    try:
        result = subprocess.run(  # noqa: S603
            [git_executable, *arguments],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise _InputError(f"unable to {operation}: {error}") from error
    return result.stdout


def _decode_git_paths(raw: bytes, operation: str) -> list[str]:
    try:
        return sorted(path.decode("utf-8") for path in raw.split(b"\0") if path)
    except UnicodeDecodeError as error:
        raise _InputError(f"unable to {operation}: Git path is not UTF-8") from error


def _source_control_scope(contract_path: Path) -> list[str]:
    contract_identity = _lexical_manifest_path(contract_path)
    return sorted(
        {
            contract_identity,
            "quality/coverage-manifest.schema.json",
            "quality/ownership-mapping.json",
            *(root for roots in SOURCE_ROOTS.values() for root in roots),
        }
    )


def _validate_clean_source_snapshot(contract_path: Path) -> None:
    scope = _source_control_scope(contract_path)
    tracked_changes = _decode_git_paths(
        _git_output(
            ["diff", "--name-only", "-z", "HEAD", "--", *scope],
            "inspect tracked source/control changes",
        ),
        "inspect tracked source/control changes",
    )
    untracked_sources = _decode_git_paths(
        _git_output(
            ["ls-files", "--others", "--exclude-standard", "-z", "--", *scope],
            "inspect untracked source/control files",
        ),
        "inspect untracked source/control files",
    )
    dirty_paths = sorted(set(tracked_changes + untracked_sources))
    if dirty_paths:
        raise _InputError(
            "clean tracked HEAD snapshot required; dirty source/control paths: "
            + ", ".join(dirty_paths)
        )


def _tracked_source_is_coverable(component: str, relative_path: str) -> bool:
    pure = PurePosixPath(relative_path)
    lowered_name = pure.name.casefold()
    if component == "python":
        return pure.suffix.casefold() == ".py"
    if component == "frontend":
        return (
            pure.suffix.casefold() in {".ts", ".tsx"}
            and not lowered_name.endswith(".d.ts")
            and lowered_name != "routetree.gen.ts"
            and ".test." not in lowered_name
            and ".spec." not in lowered_name
            and "__tests__" not in pure.parts
        )
    if component.startswith("go-"):
        return (
            pure.suffix.casefold() == ".go"
            and not lowered_name.endswith("_test.go")
            and not lowered_name.endswith(".pb.go")
            and not lowered_name.endswith("_mock.go")
            and not lowered_name.startswith("mock_")
        )
    if component.startswith("rust-"):
        return pure.suffix.casefold() == ".rs" and "tests" not in pure.parts
    return False


def _tracked_source_inventory() -> dict[str, frozenset[str]]:
    inventory: dict[str, frozenset[str]] = {}
    for component in COVERAGE_COMPONENTS:
        tracked = _decode_git_paths(
            _git_output(
                ["ls-files", "-z", "--", *SOURCE_ROOTS[component]],
                f"inventory tracked sources for {component}",
            ),
            f"inventory tracked sources for {component}",
        )
        inventory[component] = frozenset(
            path for path in tracked if _tracked_source_is_coverable(component, path)
        )
    return inventory


def _lexical_manifest_path(path: Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as error:
        raise _InputError(f"evidence path is outside the repository: {path}") from error


def _validate_output_path_confinement(output_path: Path) -> None:
    repository_root = REPOSITORY_ROOT.resolve(strict=True)
    try:
        relative = output_path.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise _InputError(
            f"output path is outside the repository: {output_path}"
        ) from error
    if not relative.parts:
        raise _InputError("output path must identify a repository file")

    current = REPOSITORY_ROOT
    for part in relative.parts:
        current /= part
        if not current.exists() and not current.is_symlink():
            continue
        if _is_link_or_junction(current):
            raise _InputError(
                f"output path traverses a symlink or junction: {output_path}"
            )
        try:
            resolved = current.resolve(strict=True)
        except OSError as error:
            raise _InputError(
                f"unable to inspect output path {output_path}: {error}"
            ) from error
        if not resolved.is_relative_to(repository_root):
            raise _InputError(
                f"output path resolves outside the repository: {output_path}"
            )

    existing_parent = output_path.parent
    while not existing_parent.exists():
        if existing_parent == REPOSITORY_ROOT:
            break
        existing_parent = existing_parent.parent
    try:
        resolved_parent = existing_parent.resolve(strict=True)
    except OSError as error:
        raise _InputError(
            f"unable to inspect output parent {existing_parent}: {error}"
        ) from error
    if not resolved_parent.is_relative_to(repository_root):
        raise _InputError(
            f"output parent resolves outside the repository: {output_path}"
        )


def _paths_alias(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first)) == os.path.normcase(str(second))


def _manifest_path(path: Path) -> str:
    return _lexical_manifest_path(path)


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
    parser.add_argument(
        "--repository-root",
        metavar="PATH",
        help="isolated Git checkout root (defaults to the checkout containing this script)",
    )
    parser.add_argument("--contract", metavar="PATH")
    parser.add_argument("--commit-sha", required=True, metavar="SHA")
    parser.add_argument("--generated-at", required=True, metavar="TIMESTAMP")
    parser.add_argument("--output", required=True, metavar="PATH")
    parser.add_argument(
        "--provenance-mode",
        required=True,
        choices=("local", "github-actions"),
    )
    parser.add_argument("--workflow-run-id", metavar="ID")
    parser.add_argument("--workflow-run-attempt", metavar="ATTEMPT")
    parser.add_argument("--workflow-event", metavar="EVENT")
    parser.add_argument("--workflow-repository", metavar="OWNER/REPO")
    parser.add_argument("--workflow-ref", metavar="REF")
    parser.add_argument("--workflow-job", metavar="JOB")
    parser.add_argument(
        "--tool-version",
        action="append",
        default=[],
        metavar="NAME=VERSION",
    )
    parser.add_argument("--python-xml", action="append", default=[], metavar="PATH")
    parser.add_argument("--python-json", action="append", default=[], metavar="PATH")
    parser.add_argument(
        "--frontend-lcov",
        action="append",
        default=[],
        metavar="PATH",
    )
    parser.add_argument("--frontend-json", action="append", default=[], metavar="PATH")
    parser.add_argument(
        "--go-report", action="append", default=[], metavar="COMPONENT=PATH"
    )
    parser.add_argument(
        "--rust-report",
        action="append",
        default=[],
        metavar="COMPONENT=PATH",
    )
    parser.add_argument(
        "--rust-branch-report",
        action="append",
        default=[],
        metavar="COMPONENT=PATH",
        help=(
            "Merge nightly LLVM branch counters into the matching stable Rust report."
        ),
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


def _load_contract(path: Path, generated_at: datetime) -> _ContractConfiguration:
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
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise _InputError(f"malformed contract: {error}") from error
    if not isinstance(contract, dict):
        raise _InputError("malformed contract: root must be an object")

    contract_errors = validate_contract(contract, today=generated_at.date())
    if contract_errors:
        raise _InputError(f"malformed contract: {'; '.join(contract_errors)}")

    coverage_reports = contract["coverage_reports"]
    if not isinstance(coverage_reports, list):
        raise _InputError("malformed contract: coverage_reports must be a list")
    expected_reports = frozenset(
        (
            str(declaration["component"]),
            str(declaration["format"]),
            str(declaration["path"]),
        )
        for declaration in coverage_reports
        if isinstance(declaration, dict)
    )
    if expected_reports != CANONICAL_REPORT_DECLARATIONS:
        raise _InputError(
            "malformed contract: coverage_reports registry is not canonical"
        )

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
    raw_source_roots = contract["source_roots"]
    if not isinstance(raw_source_roots, dict):
        raise _InputError("malformed contract: source_roots must be an object")
    source_roots: dict[str, tuple[str, ...]] = {}
    for component in COMPONENTS:
        roots = raw_source_roots[component]
        if not isinstance(roots, list) or not all(
            isinstance(root, str) for root in roots
        ):
            raise _InputError(
                f"malformed contract: source_roots.{component} must be a string array"
            )
        source_roots[component] = tuple(roots)
    manifest_path = contract["manifest_path"]
    if not isinstance(manifest_path, str):
        raise _InputError("malformed contract: manifest_path must be a string")
    return _ContractConfiguration(
        floors=floors,
        source_roots=source_roots,
        expected_reports=expected_reports,
        manifest_path=manifest_path,
        contract=contract,
    )


def _collect_report_inputs(arguments: argparse.Namespace) -> list[_ReportInput]:
    inputs: list[_ReportInput] = []
    for value in arguments.python_xml:
        inputs.append(_ReportInput("python", "cobertura-xml", _resolve_path(value)))
    for value in arguments.python_json:
        inputs.append(_ReportInput("python", "coverage-py-json", _resolve_path(value)))
    for value in arguments.frontend_lcov:
        inputs.append(_ReportInput("frontend", "lcov", _resolve_path(value)))
    for value in arguments.frontend_json:
        inputs.append(_ReportInput("frontend", "istanbul-json", _resolve_path(value)))
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
    for value in arguments.rust_branch_report:
        inputs.append(
            _parse_component_path(
                value,
                RUST_COMPONENTS,
                "--rust-branch-report",
                "llvm-cov-branch-json",
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


def _parse_report(
    raw_report: _RawReport, ignore_outside_files: bool = False
) -> _ParsedReport:
    file_metrics: dict[str, dict[str, dict[str, object]]]
    if raw_report.report_format == "cobertura-xml":
        metrics = _parse_python_xml(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
        file_metrics = _parse_tier0_files(
            raw_report,
            ignore_outside_files=ignore_outside_files,
        )
    elif raw_report.report_format == "coverage-py-json":
        metrics, file_metrics = _parse_python_coverage_json(
            raw_report.raw,
            raw_report.component,
            ignore_outside_files,
        )
    elif raw_report.report_format == "lcov":
        metrics = _parse_frontend_lcov(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
        file_metrics = _parse_tier0_files(
            raw_report,
            ignore_outside_files=ignore_outside_files,
        )
        istanbul_reports = [
            report
            for report in raw_report.supplemental
            if report.report_format == "istanbul-json"
        ]
        if istanbul_reports:
            if len(istanbul_reports) != 1:
                raise _InputError(
                    "frontend coverage must contain exactly one Istanbul JSON report"
                )
            istanbul_metrics, istanbul_file_metrics = _parse_frontend_istanbul_json(
                istanbul_reports[0].raw,
                raw_report.component,
                ignore_outside_files,
            )
            for metric_name in ("branches", "functions"):
                lcov_metric = metrics[metric_name]
                istanbul_metric = istanbul_metrics[metric_name]
                if (
                    lcov_metric["status"] == "native"
                    and istanbul_metric["status"] == "native"
                    and (
                        lcov_metric["covered"] != istanbul_metric["covered"]
                        or lcov_metric["total"] != istanbul_metric["total"]
                    )
                ):
                    raise _InputError(
                        f"frontend coverage reports disagree for {metric_name}"
                    )
                if lcov_metric["status"] != "native":
                    metrics[metric_name] = istanbul_metric
            metrics["statements"] = istanbul_metrics["statements"]
            for source, supplemental_metrics in istanbul_file_metrics.items():
                target_metrics = file_metrics.setdefault(
                    source,
                    {metric: _unmeasured_metric("missing") for metric in METRICS},
                )
                for metric_name in ("statements", "branches", "functions"):
                    lcov_metric = target_metrics[metric_name]
                    istanbul_metric = supplemental_metrics[metric_name]
                    if (
                        lcov_metric["status"] == "native"
                        and istanbul_metric["status"] == "native"
                        and (
                            lcov_metric["covered"] != istanbul_metric["covered"]
                            or lcov_metric["total"] != istanbul_metric["total"]
                        )
                    ):
                        raise _InputError(
                            f"frontend coverage reports disagree for "
                            f"{source}.{metric_name}"
                        )
                    if lcov_metric["status"] != "native":
                        preserve_vacuous_metric = (
                            lcov_metric["status"] == "derived"
                            and lcov_metric["total"] == 0
                            and istanbul_metric["status"] == "native"
                            and istanbul_metric["total"] == 0
                        )
                        if not preserve_vacuous_metric:
                            target_metrics[metric_name] = istanbul_metric
    elif raw_report.report_format == "istanbul-json":
        metrics, file_metrics = _parse_frontend_istanbul_json(
            raw_report.raw,
            raw_report.component,
            ignore_outside_files,
        )
    elif raw_report.report_format == "go-coverprofile":
        metrics = _parse_go_coverprofile(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
        file_metrics = _parse_tier0_files(
            raw_report,
            ignore_outside_files=ignore_outside_files,
        )
    elif raw_report.report_format == "llvm-cov-json":
        metrics = _parse_rust_llvm_json(
            raw_report.raw, raw_report.component, ignore_outside_files
        )
        file_metrics = _parse_tier0_files(
            raw_report,
            ignore_outside_files=ignore_outside_files,
        )
    elif raw_report.report_format == "llvm-cov-branch-json":
        metrics = _parse_rust_llvm_json(
            raw_report.raw,
            raw_report.component,
            ignore_outside_files,
            native_branches=True,
        )
        file_metrics = _parse_tier0_files(
            raw_report,
            ignore_outside_files=ignore_outside_files,
        )
    else:
        raise _InputError(f"unsupported report format: {raw_report.report_format}")
    return _ParsedReport(
        component=raw_report.component,
        report_format=raw_report.report_format,
        path=raw_report.path,
        metrics=metrics,
        file_metrics=file_metrics,
        sha256=raw_report.sha256,
    )


def _missing_metrics() -> dict[str, dict[str, object]]:
    return {metric: _unmeasured_metric("missing") for metric in METRICS}


def _metric_satisfies_floor(metric: dict[str, object], floor: int) -> bool:
    status = metric["status"]
    if status == "unsupported":
        return floor == 0
    if status in {"missing", "experimental"}:
        return False
    covered = metric["covered"]
    total = metric["total"]
    if (
        isinstance(covered, bool)
        or not isinstance(covered, int)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        return False
    if total == 0:
        return (
            metric["status"] == "derived"
            and covered == 0
            and metric.get("percent") == 100.0
        )
    if status not in {"native", "derived"}:
        return False
    return covered == total and metric.get("percent") == 100.0


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
        return f"{component}.{metric_name} trusted derivation is below 100%"
    if status != "native":
        return f"{component}.{metric_name} is {status} and cannot satisfy strict coverage floor"
    return f"{component}.{metric_name} is below required coverage floor {floor}"


def _component_entry(
    component: str,
    reports: list[_ParsedReport],
    floors: dict[str, int],
    supplied_count: int,
    required_count: int,
    evidence_errors: list[str],
) -> tuple[dict[str, object], list[str], dict[str, object] | None]:
    if required_count == 0:
        metrics = {
            metric: _unmeasured_metric(
                "unsupported", reason_code="component_uses_noncoverage_quality_gates"
            )
            for metric in METRICS
        }
        return (
            {
                "status": "not_applicable",
                "metrics": metrics,
                "errors": [],
            },
            [],
            None,
        )

    errors = list(evidence_errors)
    if supplied_count != required_count:
        errors.append(
            f"component {component} requires exactly {required_count} reports, "
            f"got {supplied_count}"
        )
    metrics = reports[0].metrics if reports else _missing_metrics()
    if reports:
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
            "status": (
                "passed"
                if not errors
                else "missing"
                if supplied_count == 0
                else "failed"
            ),
            "metrics": metrics,
            "errors": errors,
        },
        errors,
        None,
    )


def _merge_rust_branch_report(
    stable_report: _ParsedReport,
    branch_report: _ParsedReport,
) -> tuple[_ParsedReport, list[str]]:
    """Combine stable line/function evidence with nightly branch evidence.

    Rust branch instrumentation is nightly-only, while the stable report is
    the compatibility baseline for line and function counters.  The two
    reports are matched by the canonical source identity produced by each
    parser; no coverage counter is synthesized from the other report.
    """
    errors: list[str] = []
    branch_metrics = branch_report.metrics["branches"]
    if branch_metrics["status"] not in {"native", "derived"}:
        errors.append(
            f"{branch_report.component} nightly branch report did not provide "
            f"measured branches (status={branch_metrics['status']!r})"
        )

    merged_file_metrics: dict[str, dict[str, dict[str, object]]] = {}
    stable_sources = set(stable_report.file_metrics)
    nightly_sources = set(branch_report.file_metrics)
    for path in sorted(nightly_sources - stable_sources):
        errors.append(
            f"{stable_report.component} nightly branch report contains unexpected source {path}"
        )
    for path, stable_metrics in stable_report.file_metrics.items():
        nightly_metrics = branch_report.file_metrics.get(path)
        if nightly_metrics is None:
            errors.append(
                f"{stable_report.component} nightly branch report is missing source {path}"
            )
            merged_file_metrics[path] = stable_metrics
            continue
        merged_metrics = dict(stable_metrics)
        merged_metrics["branches"] = nightly_metrics["branches"]
        merged_file_metrics[path] = merged_metrics

    merged_metrics = dict(stable_report.metrics)
    merged_metrics["branches"] = branch_metrics
    return (
        _ParsedReport(
            component=stable_report.component,
            report_format=stable_report.report_format,
            path=stable_report.path,
            metrics=merged_metrics,
            file_metrics=merged_file_metrics,
            sha256=stable_report.sha256,
        ),
        errors,
    )


def _same_counter_pair(first: dict[str, object], second: dict[str, object]) -> bool:
    return first.get("covered") == second.get("covered") and first.get(
        "total"
    ) == second.get("total")


def _merge_python_reports(
    xml_report: _ParsedReport,
    json_report: _ParsedReport,
) -> tuple[_ParsedReport, list[str]]:
    errors: list[str] = []
    if not _same_counter_pair(
        xml_report.metrics["lines"], json_report.metrics["statements"]
    ):
        errors.append("python coverage XML and JSON disagree for statements/lines")
    if not _same_counter_pair(
        xml_report.metrics["branches"], json_report.metrics["branches"]
    ):
        errors.append("python coverage XML and JSON disagree for branches")
    xml_sources = set(xml_report.file_metrics)
    json_sources = set(json_report.file_metrics)
    for source in sorted(xml_sources - json_sources):
        errors.append(f"python coverage JSON is missing source {source}")
    for source in sorted(json_sources - xml_sources):
        errors.append(f"python coverage JSON contains unexpected source {source}")

    file_metrics: dict[str, dict[str, dict[str, object]]] = {}
    for source, xml_metrics in xml_report.file_metrics.items():
        merged_metrics = dict(xml_metrics)
        json_metrics = json_report.file_metrics.get(source)
        if json_metrics is not None:
            if not _same_counter_pair(xml_metrics["lines"], json_metrics["statements"]):
                errors.append(
                    f"python coverage XML and JSON disagree for {source}.statements/lines"
                )
            if not _same_counter_pair(
                xml_metrics["branches"], json_metrics["branches"]
            ):
                errors.append(
                    f"python coverage XML and JSON disagree for {source}.branches"
                )
            merged_metrics["statements"] = json_metrics["statements"]
        file_metrics[source] = merged_metrics
    metrics = dict(xml_report.metrics)
    metrics["statements"] = json_report.metrics["statements"]
    return (
        _ParsedReport(
            component=xml_report.component,
            report_format="cobertura-xml+coverage-py-json",
            path=xml_report.path,
            metrics=metrics,
            file_metrics=file_metrics,
            sha256=xml_report.sha256,
        ),
        errors,
    )


def _merge_frontend_reports(
    lcov_report: _ParsedReport,
    istanbul_report: _ParsedReport,
) -> tuple[_ParsedReport, list[str]]:
    errors: list[str] = []
    for metric_name in ("branches", "functions"):
        if not _same_counter_pair(
            lcov_report.metrics[metric_name], istanbul_report.metrics[metric_name]
        ):
            errors.append(f"frontend LCOV and Istanbul JSON disagree for {metric_name}")
    lcov_sources = set(lcov_report.file_metrics)
    istanbul_sources = set(istanbul_report.file_metrics)
    for source in sorted(lcov_sources - istanbul_sources):
        errors.append(f"frontend Istanbul JSON is missing source {source}")
    for source in sorted(istanbul_sources - lcov_sources):
        errors.append(f"frontend Istanbul JSON contains unexpected source {source}")

    file_metrics: dict[str, dict[str, dict[str, object]]] = {}
    for source, lcov_metrics in lcov_report.file_metrics.items():
        merged_metrics = dict(lcov_metrics)
        istanbul_metrics = istanbul_report.file_metrics.get(source)
        if istanbul_metrics is not None:
            for metric_name in ("branches", "functions"):
                if not _same_counter_pair(
                    lcov_metrics[metric_name], istanbul_metrics[metric_name]
                ):
                    errors.append(
                        f"frontend LCOV and Istanbul JSON disagree for "
                        f"{source}.{metric_name}"
                    )
            merged_metrics["statements"] = istanbul_metrics["statements"]
        file_metrics[source] = merged_metrics
    metrics = dict(lcov_report.metrics)
    metrics["statements"] = istanbul_report.metrics["statements"]
    return (
        _ParsedReport(
            component=lcov_report.component,
            report_format="lcov+istanbul-json",
            path=lcov_report.path,
            metrics=metrics,
            file_metrics=file_metrics,
            sha256=lcov_report.sha256,
        ),
        errors,
    )


def _load_tier0_rules() -> tuple[list[str], str | None]:
    path = REPOSITORY_ROOT / "quality" / "ownership-mapping.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [], f"unable to read Tier0 ownership rules: {error}"
    rules = document.get("tier0_rules") if isinstance(document, dict) else None
    if not isinstance(rules, list) or not all(
        isinstance(rule, str) and rule.strip() for rule in rules
    ):
        return [], "Tier0 ownership rules must be a non-empty string array"
    return sorted(set(rule.strip().replace("\\", "/") for rule in rules)), None


def _tier0_rule_matches(path: str, rule: str) -> bool:
    normalized = path.replace("\\", "/")
    return fnmatch.fnmatchcase(normalized, rule) or PurePosixPath(normalized).match(
        rule
    )


def _tier0_source_suffixes(component: str) -> frozenset[str]:
    if component == "python":
        return frozenset({".py"})
    if component == "frontend":
        return frozenset({".ts", ".tsx"})
    if component.startswith("go-"):
        return frozenset({".go"})
    if component.startswith("rust-"):
        return frozenset({".rs"})
    return frozenset()


def _expected_tier0_sources(rules: Sequence[str]) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for component, roots in SOURCE_ROOTS.items():
        suffixes = _tier0_source_suffixes(component)
        if not suffixes:
            continue
        for root_value in roots:
            root = REPOSITORY_ROOT / root_value
            if not root.is_dir() or _is_link_or_junction(root):
                continue
            for source in root.rglob("*"):
                if not source.is_file() or _is_link_or_junction(source):
                    continue
                relative = source.relative_to(REPOSITORY_ROOT).as_posix()
                pure = PurePosixPath(relative)
                if pure.suffix not in suffixes:
                    continue
                lowered = pure.name.lower()
                if component.startswith("go-") and lowered.endswith("_test.go"):
                    continue
                if component == "frontend" and (
                    ".test." in lowered
                    or ".spec." in lowered
                    or "__tests__" in pure.parts
                ):
                    continue
                if component.startswith("rust-") and "tests" in pure.parts:
                    continue
                if any(_tier0_rule_matches(relative, rule) for rule in rules):
                    expected.add((component, relative))
    return expected


def _aggregate_tier0(
    reports_by_component: defaultdict[str, list[_ParsedReport]],
    floors: dict[str, dict[str, int]],
) -> dict[str, object]:
    rules, rules_error = _load_tier0_rules()
    file_records: list[tuple[str, str, dict[str, dict[str, object]]]] = []
    for component in COMPONENTS:
        for report in reports_by_component[component]:
            for path, metrics in report.file_metrics.items():
                if any(_tier0_rule_matches(path, rule) for rule in rules):
                    file_records.append((path, component, metrics))

    deduplicated: dict[tuple[str, str], dict[str, dict[str, object]]] = {}
    for path, component, metrics in file_records:
        deduplicated[(path, component)] = metrics

    files: list[dict[str, object]] = []
    errors: list[str] = []
    if rules_error:
        errors.append(rules_error)
    actual_inventory = {(component, path) for path, component in deduplicated}
    expected_inventory = _expected_tier0_sources(rules)
    for _, path in sorted(expected_inventory - actual_inventory):
        errors.append(f"Tier0 source inventory is missing evidence for {path}")
    for _, path in sorted(actual_inventory - expected_inventory):
        errors.append(f"Tier0 evidence contains unexpected source {path}")

    measured_by_metric: dict[str, list[dict[str, object]]] = {
        metric: [] for metric in METRICS
    }
    not_applicable = {metric: 0 for metric in METRICS}
    for component, path in sorted(expected_inventory - actual_inventory):
        files.append(
            {"path": path, "component": component, "metrics": _missing_metrics()}
        )
    for (path, component), metrics in sorted(deduplicated.items()):
        files.append({"path": path, "component": component, "metrics": metrics})
        for metric_name in METRICS:
            metric = metrics[metric_name]
            status = metric["status"]
            if status in {"native", "derived"}:
                measured_by_metric[metric_name].append(metric)
                if not _metric_satisfies_floor(metric, 100):
                    errors.append(f"{path} ({component}).{metric_name} is below 100%")
            elif status == "unsupported" and floors[component][metric_name] == 0:
                not_applicable[metric_name] += 1
            elif status == "unsupported":
                errors.append(
                    f"{path} ({component}).{metric_name} is unsupported but its floor is 100"
                )
            else:
                errors.append(
                    f"{path} ({component}).{metric_name} is {status} and incomplete"
                )

    aggregate: dict[str, dict[str, object]] = {}
    metric_summary: dict[str, dict[str, int]] = {}
    for metric_name in METRICS:
        entries = measured_by_metric[metric_name]
        metric_summary[metric_name] = {
            "applicable_files": len(entries),
            "not_applicable_files": not_applicable[metric_name],
        }
        if not entries:
            aggregate[metric_name] = _unmeasured_metric(
                "unsupported", reason_code="tier0_metric_not_applicable"
            )
            continue
        covered = sum(cast(int, entry["covered"]) for entry in entries)
        total = sum(cast(int, entry["total"]) for entry in entries)
        if total == 0:
            aggregate[metric_name] = _vacuous_metric(
                "applicable Tier0 files contain no coverage units"
            )
        elif any(entry["status"] == "derived" for entry in entries):
            aggregate[metric_name] = _measured_metric(
                "derived",
                covered,
                total,
                derivation="sum of applicable Tier0 file metrics",
            )
        else:
            aggregate[metric_name] = _measured_metric("native", covered, total)

    files.sort(key=lambda entry: (str(entry["component"]), str(entry["path"])))
    errors = sorted(set(errors))
    return {
        "status": "ready" if files and not errors else "failed",
        "rules": rules,
        "coverage": aggregate,
        "metric_summary": metric_summary,
        "files": files,
        "errors": errors,
    }


def _parse_tool_versions(values: Sequence[str]) -> dict[str, str]:
    versions: dict[str, str] = {"quality-normalizer": NORMALIZER_VERSION}
    for value in values:
        name, separator, version = value.partition("=")
        if not separator or not name.strip() or not version.strip():
            raise _InputError("tool-version must use NAME=VERSION")
        name = name.strip()
        version = version.strip()
        if name in versions:
            raise _InputError(f"duplicate tool-version entry: {name}")
        versions[name] = version
    return dict(sorted(versions.items()))


def _build_provenance(arguments: argparse.Namespace) -> dict[str, str]:
    workflow_values = {
        "workflow_run_id": arguments.workflow_run_id,
        "workflow_run_attempt": arguments.workflow_run_attempt,
        "workflow_event": arguments.workflow_event,
        "workflow_repository": arguments.workflow_repository,
        "workflow_ref": arguments.workflow_ref,
        "workflow_job": arguments.workflow_job,
    }
    if arguments.provenance_mode == "local":
        if any(value is not None for value in workflow_values.values()):
            raise _InputError("workflow provenance flags are forbidden in local mode")
        return {"mode": "local", **dict.fromkeys(workflow_values, "local")}
    missing = [field for field, value in workflow_values.items() if not value]
    if missing:
        raise _InputError(
            "github-actions provenance requires: " + ", ".join(sorted(missing))
        )
    return {
        "mode": "github-actions",
        **{field: str(value) for field, value in workflow_values.items()},
    }


def _prepare_invocation(arguments: argparse.Namespace) -> _PreparedInvocation:
    _configure_repository_root(arguments.repository_root)
    if SHA_PATTERN.fullmatch(arguments.commit_sha) is None:
        raise _InputError("commit-sha must be a lowercase 40-character Git SHA")
    current_head = _current_git_head()
    if arguments.commit_sha != current_head:
        raise _InputError(
            f"commit-sha must equal current repository HEAD {current_head}, "
            f"got {arguments.commit_sha}"
        )
    generated_at = _parse_generated_at(arguments.generated_at)
    contract_path = (
        _resolve_path(arguments.contract)
        if arguments.contract
        else (REPOSITORY_ROOT / "quality" / "quality-contract.json")
    )
    output_path = _resolve_path(arguments.output)
    _validate_output_path_confinement(output_path)
    report_inputs = _collect_report_inputs(arguments)
    for path in [contract_path, *(entry.path for entry in report_inputs)]:
        if _paths_alias(output_path, path):
            raise _InputError(
                "output path must not alias the contract or an input report"
            )

    configuration = _load_contract(contract_path, generated_at)
    global SOURCE_ROOTS
    SOURCE_ROOTS = configuration.source_roots
    _validate_clean_source_snapshot(contract_path)
    source_inventory = _tracked_source_inventory()
    if _lexical_manifest_path(output_path) != configuration.manifest_path:
        raise _InputError(
            f"output must equal contract manifest_path {configuration.manifest_path}"
        )
    for entry in report_inputs:
        identity = (
            entry.component,
            entry.report_format,
            _lexical_manifest_path(entry.path),
        )
        if identity not in configuration.expected_reports:
            raise _InputError(
                "report input does not match the contract coverage_reports registry: "
                f"{identity[2]}"
            )
    return _PreparedInvocation(
        arguments=arguments,
        output_path=output_path,
        report_inputs=tuple(report_inputs),
        floors=configuration.floors,
        expected_reports=configuration.expected_reports,
        manifest_path=configuration.manifest_path,
        provenance=_build_provenance(arguments),
        tool_versions=_parse_tool_versions(arguments.tool_version),
        contract=configuration.contract,
        source_inventory=source_inventory,
    )


def _build_manifest(
    invocation: _PreparedInvocation,
) -> tuple[dict[str, object], list[str], list[str], Path]:
    arguments = invocation.arguments
    output_path = invocation.output_path
    report_inputs = invocation.report_inputs
    floors = invocation.floors
    reports_by_component: defaultdict[str, list[_ParsedReport]] = defaultdict(list)
    branch_reports_by_component: defaultdict[str, list[_ParsedReport]] = defaultdict(
        list
    )
    report_input_counts: defaultdict[str, int] = defaultdict(int)
    branch_input_counts: defaultdict[str, int] = defaultdict(int)
    evidence_errors_by_component: defaultdict[str, list[str]] = defaultdict(list)
    raw_reports: list[_RawReport] = []
    structural_errors: list[str] = []
    supplied_declarations: list[tuple[str, str, str]] = [
        (
            report_input.component,
            report_input.report_format,
            _lexical_manifest_path(report_input.path),
        )
        for report_input in report_inputs
    ]
    supplied_declaration_set = set(supplied_declarations)
    for declaration in sorted(invocation.expected_reports - supplied_declaration_set):
        component, _, path = declaration
        message = f"expected report not supplied for component {component}: {path}"
        evidence_errors_by_component[component].append(message)
    duplicate_declarations = sorted(
        {
            declaration
            for declaration in supplied_declarations
            if supplied_declarations.count(declaration) > 1
        }
    )
    for component, _, path in duplicate_declarations:
        message = f"report input must be supplied exactly once for {component}: {path}"
        evidence_errors_by_component[component].append(message)

    for report_input in report_inputs:
        report_input_counts[report_input.component] += 1
        is_branch_report = report_input.report_format == "llvm-cov-branch-json"
        if is_branch_report:
            branch_input_counts[report_input.component] += 1
        try:
            raw_report = _read_raw_report(report_input)
        except _InputError as error:
            message = str(error)
            evidence_errors_by_component[report_input.component].append(message)
            structural_errors.append(message)
            continue
        raw_reports.extend((raw_report, *raw_report.supplemental))
        try:
            report = _parse_report(raw_report)
        except _InputError as error:
            message = (
                f"malformed report for component {report_input.component}: {error}"
            )
            evidence_errors_by_component[report_input.component].append(message)
            structural_errors.append(message)
        else:
            if is_branch_report:
                branch_reports_by_component[report.component].append(report)
            else:
                reports_by_component[report.component].append(report)

    paired_components = (
        (
            "python",
            "cobertura-xml",
            "coverage-py-json",
            _merge_python_reports,
        ),
        (
            "frontend",
            "lcov",
            "istanbul-json",
            _merge_frontend_reports,
        ),
    )
    for (
        component,
        primary_format,
        supplemental_format,
        merge_reports,
    ) in paired_components:
        reports = reports_by_component[component]
        primary = [
            report for report in reports if report.report_format == primary_format
        ]
        supplemental = [
            report for report in reports if report.report_format == supplemental_format
        ]
        if len(primary) != 1 or len(supplemental) != 1:
            if (
                report_input_counts[component] == 2
                and not evidence_errors_by_component[component]
            ):
                message = (
                    f"component {component} requires one {primary_format} report and one "
                    f"{supplemental_format} report"
                )
                evidence_errors_by_component[component].append(message)
                structural_errors.append(message)
            continue
        merged_report, merge_errors = merge_reports(primary[0], supplemental[0])
        reports_by_component[component] = [merged_report]
        evidence_errors_by_component[component].extend(merge_errors)
        structural_errors.extend(merge_errors)

    for component in RUST_COMPONENTS:
        branch_count = branch_input_counts[component]
        if branch_count == 0:
            continue
        if branch_count > 1:
            evidence_errors_by_component[component].append(
                f"duplicate branch report input for component {component}"
            )
            continue
        stable_reports = reports_by_component[component]
        branch_reports = branch_reports_by_component[component]
        if len(stable_reports) != 1 or len(branch_reports) != 1:
            evidence_errors_by_component[component].append(
                f"Rust branch evidence for component {component} requires exactly "
                "one stable report and one branch report"
            )
            continue
        merged_report, merge_errors = _merge_rust_branch_report(
            stable_reports[0], branch_reports[0]
        )
        reports_by_component[component] = [merged_report]
        evidence_errors_by_component[component].extend(merge_errors)
        structural_errors.extend(merge_errors)

    for component in COVERAGE_COMPONENTS:
        component_reports = reports_by_component[component]
        if len(component_reports) != 1:
            continue
        if (
            component in {"python", "frontend"}
            and "+" not in component_reports[0].report_format
        ):
            continue
        if component in RUST_COMPONENTS and (
            branch_input_counts[component] != 1
            or len(branch_reports_by_component[component]) != 1
        ):
            continue
        reported_sources = set(component_reports[0].file_metrics)
        tracked_sources = set(invocation.source_inventory[component])
        inventory_errors = [
            *(
                f"{component} coverage is missing tracked source {source}"
                for source in sorted(tracked_sources - reported_sources)
            ),
            *(
                f"{component} coverage contains non-inventory source {source}"
                for source in sorted(reported_sources - tracked_sources)
            ),
        ]
        evidence_errors_by_component[component].extend(inventory_errors)
        structural_errors.extend(inventory_errors)

    components: dict[str, object] = {}
    missing_reports: list[dict[str, object]] = []
    validation_errors: list[str] = []
    for component in COMPONENTS:
        required_count = sum(
            declaration_component == component
            for declaration_component, _, _ in invocation.expected_reports
        )
        entry, errors, missing_report = _component_entry(
            component,
            reports_by_component[component],
            floors[component],
            report_input_counts[component],
            required_count,
            evidence_errors_by_component[component],
        )
        components[component] = entry
        validation_errors.extend(errors)
        if missing_report is not None:
            missing_reports.append(missing_report)

    validation_errors.extend(structural_errors)
    validation_errors = sorted(set(validation_errors))
    structural_errors = sorted(set(structural_errors))
    report_entries = [
        {
            "component": report.component,
            "format": report.report_format,
            "path": _manifest_path(report.path),
            "sha256": report.sha256,
            "size_bytes": len(report.raw),
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
    missing_reports = [
        {
            "component": component,
            "path": path,
            "reason_code": "expected_report_not_supplied",
        }
        for component, _, path in sorted(
            invocation.expected_reports - supplied_declaration_set
        )
    ]
    tier0 = _aggregate_tier0(reports_by_component, floors)
    tier0_errors = tier0["errors"]
    if isinstance(tier0_errors, list):
        validation_errors.extend(str(error) for error in tier0_errors)
        validation_errors = sorted(set(validation_errors))
    manifest: dict[str, object] = {
        "schema_version": 2,
        "commit_sha": arguments.commit_sha,
        "generated_at": arguments.generated_at,
        "manifest_path": invocation.manifest_path,
        "source_roots": {
            component: list(SOURCE_ROOTS[component]) for component in COMPONENTS
        },
        "tool_versions": invocation.tool_versions,
        "provenance": invocation.provenance,
        "generation": {
            "command": "scripts/quality/normalize_coverage_reports.py",
            "normalizer_version": NORMALIZER_VERSION,
        },
        "reports": report_entries,
        "components": components,
        "tier0": tier0,
        "missing_reports": missing_reports,
        "validation": {
            "valid": not validation_errors,
            "errors": validation_errors,
        },
    }
    if not validation_errors:
        evidence_errors = validate_manifest_evidence(
            manifest,
            contract=invocation.contract,
            manifest_path=output_path,
            repository_root=REPOSITORY_ROOT,
            schema_path=(REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"),
            expected_commit_sha=arguments.commit_sha,
            expected_provenance=invocation.provenance,
        )
        if evidence_errors:
            validation_errors = sorted(set(evidence_errors))
            manifest["validation"] = {
                "valid": False,
                "errors": validation_errors,
            }
    return manifest, validation_errors, structural_errors, output_path


def _write_manifest(output_path: Path, manifest: dict[str, object]) -> None:
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary_path: Path | None = None
    try:
        _validate_output_path_confinement(output_path)
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
        for validation_error in validation_errors:
            _print_error(validation_error)
        return 2 if structural_errors else 1

    print("Quality coverage artifacts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
