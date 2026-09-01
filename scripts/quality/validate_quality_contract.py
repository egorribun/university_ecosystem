from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NoReturn, cast

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

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
COMPONENT_FLOORS = (
    ("lines", 100),
    ("statements", 100),
    ("branches", 100),
    ("functions", 100),
)
TIER0_FLOORS = (
    ("lines", 100),
    ("statements", 100),
    ("branches", 100),
    ("functions", 100),
)
COVERAGE_MINIMUMS = (
    ("lines", 100),
    ("statements", 100),
    ("branches", 100),
    ("functions", 100),
    ("tier0", 100),
)
TOP_LEVEL_KEYS = frozenset(
    {
        "version",
        "policy",
        "coverage_minimums",
        "components",
        "tier0",
        "source_roots",
        "coverage_scope",
        "coverage_reports",
        "coverage_manifest",
        "manifest_path",
        "exclusions",
        "quarantines",
    }
)
POLICY_KEYS = frozenset({"patch_coverage", "viable_mutant_score", "required_pr_matrix"})
COVERAGE_MANIFEST_FIELDS = frozenset({"schema_version", "normalizer_version"})
EXCLUSION_FIELDS = frozenset(
    {
        "id",
        "path",
        "reason",
        "owner",
        "issue",
        "created_on",
        "expires_on",
        "evidence",
    }
)
QUARANTINE_FIELDS = EXCLUSION_FIELDS | {"test"}
MUTATION_REGISTRY_FIELDS = frozenset({"version", "exclusions"})
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
WILDCARD_CHARACTERS = "*?[]"
MAX_JSON_NESTING_DEPTH = 1_024
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
METRICS = ("lines", "statements", "branches", "functions")
NORMALIZER_VERSION = "3.0.0"
REPORT_FORMATS = frozenset(
    {
        "cobertura-xml",
        "coverage-py-json",
        "lcov",
        "istanbul-json",
        "go-coverprofile",
        "llvm-cov-json",
        "llvm-cov-branch-json",
    }
)
VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")
REPORT_FORMAT_TO_TOOLS = {
    "cobertura-xml": frozenset({"coverage.py", "python"}),
    "coverage-py-json": frozenset({"coverage.py", "python"}),
    "lcov": frozenset({"node", "vitest"}),
    "istanbul-json": frozenset({"node", "vitest"}),
    "go-coverprofile": frozenset({"go"}),
    "llvm-cov-json": frozenset({"cargo-llvm-cov", "rustc"}),
    "llvm-cov-branch-json": frozenset({"cargo-llvm-cov", "rustc-nightly"}),
}
TRUSTED_DERIVATIONS = frozenset(
    {
        "AST function entries covered when the first executable body line is reported as executed",
        "AST source contains no branch construct",
        "AST source contains no function definitions",
        "Cobertura source contains no executable lines",
        "coverage.py JSON contains no num_statements units",
        "LCOV source contains no branch units",
        "LCOV source contains no executable lines",
        "LCOV source contains no function units",
        "Istanbul JSON contains no statement units",
        "LLVM source contains no executable line segments",
        "Nightly LLVM report contains no branch units",
        "Nightly LLVM source contains no branch sites",
        "source branch sites deduplicated across LLVM generic instantiations; each outcome covered by any instantiation",
        "sum of applicable Tier0 file metrics",
        "unique source lines from non-gap LLVM segments; covered when any segment on the line is executed",
        "unique source lines in coverprofile blocks; covered when any overlapping block has count greater than zero",
    }
)
EXPECTED_COVERAGE_REPORTS = frozenset(
    {
        ("python", "cobertura-xml", "coverage.xml"),
        (
            "python",
            "coverage-py-json",
            "artifacts/coverage/python/coverage.json",
        ),
        ("frontend", "lcov", "frontend/coverage/lcov.info"),
        ("frontend", "istanbul-json", "frontend/coverage/coverage-final.json"),
        (
            "go-gateway",
            "go-coverprofile",
            "artifacts/coverage/go/gateway/coverage.out",
        ),
        (
            "go-ws-hub",
            "go-coverprofile",
            "artifacts/coverage/go/ws-hub/coverage.out",
        ),
        (
            "go-file-processor",
            "go-coverprofile",
            "artifacts/coverage/go/file-processor/coverage.out",
        ),
        (
            "go-shared",
            "go-coverprofile",
            "artifacts/coverage/go/shared/coverage.out",
        ),
        (
            "rust-native",
            "llvm-cov-json",
            "artifacts/coverage/rust/rust-native/llvm.json",
        ),
        (
            "rust-native",
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-native/branch-llvm.json",
        ),
        (
            "rust-pyo3-sanitizer",
            "llvm-cov-json",
            "artifacts/coverage/rust/rust-pyo3-sanitizer/llvm.json",
        ),
        (
            "rust-pyo3-sanitizer",
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-pyo3-sanitizer/branch-llvm.json",
        ),
        (
            "rust-wasm-sanitizer",
            "llvm-cov-json",
            "artifacts/coverage/rust/rust-wasm-sanitizer/llvm.json",
        ),
        (
            "rust-wasm-sanitizer",
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-wasm-sanitizer/branch-llvm.json",
        ),
        (
            "rust-crypto",
            "llvm-cov-json",
            "artifacts/coverage/rust/rust-crypto/llvm.json",
        ),
        (
            "rust-crypto",
            "llvm-cov-branch-json",
            "artifacts/coverage/rust/rust-crypto/branch-llvm.json",
        ),
    }
)


class _ArgumentParsingError(ValueError):
    """Raised when command-line parsing finds an invalid argument."""


class _QualityArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _ArgumentParsingError(message)


class _DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


def _reject_excessive_json_nesting(text: str) -> None:
    """Reject deeply nested JSON before interpreter-specific decoding limits.

    CPython's JSON decoder does not guarantee the same recursion boundary on
    every platform/build.  A small lexical pass keeps the validator's
    fail-closed depth limit deterministic without treating braces inside JSON
    strings as structure.
    """

    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING_DEPTH:
                raise RecursionError("JSON nesting exceeds supported depth")
        elif character in "]}":
            depth = max(0, depth - 1)


def _require_object(
    value: object,
    field: str,
    errors: list[str],
) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value

    errors.append(f"{field} must be an object")
    return None


def _validate_exact_keys(
    value: dict[str, object],
    field: str,
    expected_keys: frozenset[str],
    errors: list[str],
) -> None:
    actual_keys = set(value)
    for key in sorted(expected_keys - actual_keys):
        errors.append(f"{field} is missing required key: {key}")
    for key in sorted(actual_keys - expected_keys):
        errors.append(f"{field} contains unsupported key: {key}")


def _validate_percentage(
    value: object,
    field: str,
    errors: list[str],
) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a numeric value between 0 and 100")
        return None
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{field} must be a numeric value between 0 and 100")
        return None
    if value < 0 or value > 100:
        errors.append(f"{field} must be a numeric value between 0 and 100")
        return None
    return value


def _validate_coverage_values(
    value: object,
    field: str,
    expected_values: tuple[tuple[str, int], ...],
    *,
    exact: bool,
    errors: list[str],
) -> None:
    coverage = _require_object(value, field, errors)
    if coverage is None:
        return

    expected_keys = frozenset(metric for metric, _ in expected_values)
    _validate_exact_keys(coverage, field, expected_keys, errors)
    for metric, threshold in expected_values:
        if metric not in coverage:
            continue
        metric_field = f"{field}.{metric}"
        percentage = _validate_percentage(coverage[metric], metric_field, errors)
        if percentage is None:
            continue
        if not exact and percentage == 0:
            continue
        if exact and percentage != threshold:
            errors.append(f"{metric_field} must equal {threshold}")
        elif not exact and percentage < threshold:
            errors.append(f"{metric_field} must be at least {threshold}")


def _validate_policy(value: object, errors: list[str]) -> None:
    policy = _require_object(value, "policy", errors)
    if policy is None:
        return

    _validate_exact_keys(policy, "policy", POLICY_KEYS, errors)
    for field in ("patch_coverage", "viable_mutant_score"):
        if field not in policy:
            continue
        value = _validate_percentage(policy[field], f"policy.{field}", errors)
        if value is not None and value != 100:
            errors.append(f"policy.{field} must equal 100")
    if "required_pr_matrix" in policy and policy["required_pr_matrix"] is not True:
        errors.append("policy.required_pr_matrix must be true")


def _validate_components(value: object, errors: list[str]) -> None:
    components = _require_object(value, "components", errors)
    if components is None:
        return

    component_names = frozenset(COMPONENTS)
    actual_names = set(components)
    for component in COMPONENTS:
        if component not in components:
            errors.append(f"components is missing required component: {component}")
    for component in sorted(actual_names - component_names):
        errors.append(f"components contains unsupported component: {component}")

    for component in COMPONENTS:
        if component not in components:
            continue
        component_config = _require_object(
            components[component],
            f"components.{component}",
            errors,
        )
        if component_config is None:
            continue
        _validate_exact_keys(
            component_config,
            f"components.{component}",
            frozenset({"coverage"}),
            errors,
        )
        if "coverage" in component_config:
            _validate_coverage_values(
                component_config["coverage"],
                f"{component}.coverage",
                COMPONENT_FLOORS,
                exact=False,
                errors=errors,
            )


def _validate_tier0(value: object, errors: list[str]) -> None:
    tier0 = _require_object(value, "tier0", errors)
    if tier0 is None:
        return

    _validate_exact_keys(tier0, "tier0", frozenset({"coverage"}), errors)
    if "coverage" in tier0:
        _validate_coverage_values(
            tier0["coverage"],
            "tier0.coverage",
            TIER0_FLOORS,
            exact=True,
            errors=errors,
        )


def _require_non_empty_string(
    value: object,
    field: str,
    errors: list[str],
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return None
    return value.strip()


def _contains_wildcard(value: str) -> bool:
    return any(character in value for character in WILDCARD_CHARACTERS)


def _is_absolute_path(value: str) -> bool:
    windows_path = PureWindowsPath(value)
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    )


def _contains_parent_traversal(value: str) -> bool:
    return any(part == ".." for part in re.split(r"[\\/]+", value))


def _is_repository_root_path(value: str) -> bool:
    return str(PurePosixPath(value)) == "." or str(PureWindowsPath(value)) == "."


def _validate_repository_path(
    value: object,
    field: str,
    errors: list[str],
) -> str | None:
    path = _require_non_empty_string(value, field, errors)
    if path is None:
        return None
    if _contains_wildcard(path):
        errors.append(f"{field} must not contain a wildcard")
    if _is_absolute_path(path):
        errors.append(f"{field} must be a repository-relative path")
    if _contains_parent_traversal(path):
        errors.append(f"{field} must not contain parent traversal")
    if _is_repository_root_path(path):
        errors.append(f"{field} must not refer to the repository root")
    return path


def _parse_iso_date(value: object, field: str, errors: list[str]) -> date | None:
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        errors.append(f"{field} must be an ISO date")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be an ISO date")
        return None


def _validate_register(
    value: object,
    register_name: str,
    *,
    today: date,
    errors: list[str],
) -> None:
    if not isinstance(value, list):
        errors.append(f"{register_name} must be a list")
        return

    seen_ids: dict[str, int] = {}
    seen_paths: dict[str, int] = {}
    seen_quarantine_identities: dict[tuple[str, str], int] = {}
    for index, record_value in enumerate(value):
        record_field = f"{register_name}[{index}]"
        record = _require_object(record_value, record_field, errors)
        if record is None:
            continue

        expected_fields = (
            QUARANTINE_FIELDS if register_name == "quarantines" else EXCLUSION_FIELDS
        )
        _validate_exact_keys(record, record_field, expected_fields, errors)

        record_id = _require_non_empty_string(
            record.get("id"), f"{record_field}.id", errors
        )
        if record_id is not None:
            if _contains_wildcard(record_id):
                errors.append(f"{record_field}.id must not contain a wildcard")
            previous_id = seen_ids.get(record_id)
            if previous_id is None:
                seen_ids[record_id] = index
            else:
                errors.append(
                    f"{record_field}.id duplicates {register_name}[{previous_id}].id"
                )

        path = _validate_repository_path(
            record.get("path"), f"{record_field}.path", errors
        )
        if path is not None and register_name in {"exclusions", "mutation_exclusions"}:
            previous_path = seen_paths.get(path)
            if previous_path is None:
                seen_paths[path] = index
            else:
                errors.append(
                    f"{record_field}.path duplicates "
                    f"{register_name}[{previous_path}].path"
                )

        test = None
        if register_name == "quarantines":
            test = _validate_repository_path(
                record.get("test"),
                f"{record_field}.test",
                errors,
            )
            if test is not None and path is not None:
                identity = (test, path)
                previous_identity = seen_quarantine_identities.get(identity)
                if previous_identity is None:
                    seen_quarantine_identities[identity] = index
                else:
                    errors.append(
                        f"{record_field}.test and path duplicate "
                        f"{register_name}[{previous_identity}].test and path"
                    )

        for metadata_field in ("reason", "owner", "issue", "evidence"):
            _require_non_empty_string(
                record.get(metadata_field),
                f"{record_field}.{metadata_field}",
                errors,
            )

        created_on = _parse_iso_date(
            record.get("created_on"),
            f"{record_field}.created_on",
            errors,
        )
        expires_on = _parse_iso_date(
            record.get("expires_on"),
            f"{record_field}.expires_on",
            errors,
        )
        if expires_on is not None and expires_on <= today:
            errors.append(f"{record_field}.expires_on must be after validation day")
        if created_on is not None and expires_on is not None:
            if expires_on <= created_on:
                errors.append(f"{record_field}.expires_on must be after created_on")
            elif (expires_on - created_on).days > 30:
                errors.append(
                    f"{record_field}.expires_on must be at most 30 days after created_on"
                )


def _validate_source_roots(value: object, errors: list[str]) -> None:
    roots = _require_object(value, "source_roots", errors)
    if roots is None:
        return
    _validate_exact_keys(roots, "source_roots", frozenset(COMPONENTS), errors)
    for component in COMPONENTS:
        if component not in roots:
            continue
        component_roots = roots[component]
        if not isinstance(component_roots, list) or not component_roots:
            errors.append(f"source_roots.{component} must be a non-empty array")
            continue
        seen: set[str] = set()
        for index, root in enumerate(component_roots):
            field = f"source_roots.{component}[{index}]"
            path = _validate_repository_path(root, field, errors)
            if path is None:
                continue
            if "\\" in path or PurePosixPath(path).as_posix() != path:
                errors.append(f"{field} must use canonical POSIX separators")
            if path in seen:
                errors.append(f"{field} duplicates an earlier source root")
            seen.add(path)


def _validate_coverage_scope(
    value: object,
    source_roots_value: object,
    errors: list[str],
) -> None:
    """Validate the toolchain-measured subset of each source root.

    ``source_roots`` is the identity boundary for report paths.  A coverage
    producer may intentionally measure a narrower, independently verified
    subset: the Python producer uses ``--cov=app`` while Alembic revisions are
    exercised by the dedicated PostgreSQL migration gate.  Keeping this scope
    explicit prevents a filesystem walk from silently turning an unmeasured
    structural source into a false coverage obligation.
    """
    scope = _require_object(value, "coverage_scope", errors)
    if scope is None:
        return
    _validate_exact_keys(
        scope, "coverage_scope", frozenset(COVERAGE_COMPONENTS), errors
    )

    source_roots = source_roots_value if isinstance(source_roots_value, dict) else {}
    for component in COVERAGE_COMPONENTS:
        if component not in scope:
            continue
        roots = scope[component]
        if not isinstance(roots, list) or not roots:
            errors.append(f"coverage_scope.{component} must be a non-empty array")
            continue
        seen: set[str] = set()
        configured_source_roots = source_roots.get(component, ())
        if not isinstance(configured_source_roots, list):
            configured_source_roots = ()
        for index, root in enumerate(roots):
            field = f"coverage_scope.{component}[{index}]"
            path = _validate_repository_path(root, field, errors)
            if path is None:
                continue
            if "\\" in path or PurePosixPath(path).as_posix() != path:
                errors.append(f"{field} must use canonical POSIX separators")
            if path in seen:
                errors.append(f"{field} duplicates an earlier coverage root")
            seen.add(path)
            if not any(
                path == source_root or path.startswith(f"{source_root}/")
                for source_root in configured_source_roots
                if isinstance(source_root, str)
            ):
                errors.append(f"{field} must be contained by source_roots.{component}")


def _validate_coverage_reports(value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("coverage_reports must be a list")
        return
    if not value:
        errors.append("coverage_reports must contain at least one declaration")
        return

    seen_paths: dict[str, int] = {}
    declarations: set[tuple[str, str, str]] = set()
    for index, declaration_value in enumerate(value):
        field = f"coverage_reports[{index}]"
        declaration = _require_object(declaration_value, field, errors)
        if declaration is None:
            continue
        _validate_exact_keys(
            declaration,
            field,
            frozenset({"component", "format", "path"}),
            errors,
        )
        component = _require_non_empty_string(
            declaration.get("component"), f"{field}.component", errors
        )
        report_format = _require_non_empty_string(
            declaration.get("format"), f"{field}.format", errors
        )
        path = _validate_repository_path(
            declaration.get("path"), f"{field}.path", errors
        )
        if component is not None and component not in COMPONENTS:
            errors.append(f"{field}.component is unsupported: {component}")
        if report_format is not None and report_format not in REPORT_FORMATS:
            errors.append(f"{field}.format is unsupported: {report_format}")
        if path is None:
            continue
        if "\\" in path or PurePosixPath(path).as_posix() != path:
            errors.append(f"{field}.path must use canonical POSIX separators")
        previous_path = seen_paths.get(path)
        if previous_path is None:
            seen_paths[path] = index
        else:
            errors.append(
                f"{field}.path duplicates coverage_reports[{previous_path}].path"
            )
        if component is not None and report_format is not None:
            declarations.add((component, report_format, path))

    missing = EXPECTED_COVERAGE_REPORTS - declarations
    unexpected = declarations - EXPECTED_COVERAGE_REPORTS
    if missing:
        errors.append(
            "coverage_reports is missing required declarations: "
            + ", ".join(path for _, _, path in sorted(missing))
        )
    if unexpected:
        errors.append(
            "coverage_reports contains unexpected declarations: "
            + ", ".join(path for _, _, path in sorted(unexpected))
        )


def validate_contract(contract: dict[str, object], *, today: date) -> list[str]:
    """Return policy violations in the v2 contract and v3 manifest declaration."""
    errors: list[str] = []
    _validate_exact_keys(contract, "contract", TOP_LEVEL_KEYS, errors)

    if "version" in contract:
        version = contract["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version != 2:
            errors.append("version must equal 2")
    if "policy" in contract:
        _validate_policy(contract["policy"], errors)
    if "coverage_minimums" in contract:
        _validate_coverage_values(
            contract["coverage_minimums"],
            "coverage_minimums",
            COVERAGE_MINIMUMS,
            exact=True,
            errors=errors,
        )
    if "components" in contract:
        _validate_components(contract["components"], errors)
    if "tier0" in contract:
        _validate_tier0(contract["tier0"], errors)
    if "source_roots" in contract:
        _validate_source_roots(contract["source_roots"], errors)
    if "coverage_scope" in contract:
        _validate_coverage_scope(
            contract["coverage_scope"],
            contract.get("source_roots"),
            errors,
        )
    if "coverage_reports" in contract:
        _validate_coverage_reports(contract["coverage_reports"], errors)
    if "coverage_manifest" in contract:
        manifest_declaration = _require_object(
            contract["coverage_manifest"], "coverage_manifest", errors
        )
        if manifest_declaration is not None:
            _validate_exact_keys(
                manifest_declaration,
                "coverage_manifest",
                COVERAGE_MANIFEST_FIELDS,
                errors,
            )
            schema_version = manifest_declaration.get("schema_version")
            if (
                not isinstance(schema_version, int)
                or isinstance(schema_version, bool)
                or schema_version != 3
            ):
                errors.append("coverage_manifest.schema_version must equal 3")
            normalizer_version = manifest_declaration.get("normalizer_version")
            if (
                not isinstance(normalizer_version, str)
                or re.fullmatch(r"3\.[0-9]+\.[0-9]+", normalizer_version) is None
            ):
                errors.append("coverage_manifest.normalizer_version must match 3.x.y")
    if "manifest_path" in contract:
        manifest_path = _validate_repository_path(
            contract["manifest_path"], "manifest_path", errors
        )
        if manifest_path is not None:
            if (
                "\\" in manifest_path
                or PurePosixPath(manifest_path).as_posix() != manifest_path
            ):
                errors.append("manifest_path must use canonical POSIX separators")
            coverage_reports = contract.get("coverage_reports")
            if isinstance(coverage_reports, list) and any(
                isinstance(report, dict) and report.get("path") == manifest_path
                for report in coverage_reports
            ):
                errors.append("manifest_path must not be included in coverage_reports")
    if "exclusions" in contract:
        _validate_register(
            contract["exclusions"],
            "exclusions",
            today=today,
            errors=errors,
        )
    if "quarantines" in contract:
        _validate_register(
            contract["quarantines"],
            "quarantines",
            today=today,
            errors=errors,
        )
    return errors


def _validate_mutation_registry(
    value: object,
    *,
    today: date,
) -> list[str]:
    """Validate the separate equivalent-mutant register.

    Mutation exclusions are deliberately kept outside the quality contract so
    adding an equivalent mutant cannot alter coverage policy metadata.  They
    still use the same short-lived, evidence-backed register discipline as
    contract exclusions and quarantines.
    """
    errors: list[str] = []
    registry = _require_object(value, "mutation registry", errors)
    if registry is None:
        return errors

    _validate_exact_keys(
        registry,
        "mutation registry",
        MUTATION_REGISTRY_FIELDS,
        errors,
    )
    version = registry.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        errors.append("mutation registry.version must equal 1")

    _validate_register(
        registry.get("exclusions"),
        "mutation_exclusions",
        today=today,
        errors=errors,
    )
    return errors


def _duplicate_key_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    object_value: dict[str, object] = {}
    for key, value in pairs:
        if key in object_value:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        object_value[key] = value
    return object_value


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid JSON value: {value}")


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _QualityArgumentParser(
        description="Validate the v2 quality contract and its current v3 evidence."
    )
    parser.add_argument("--contract", type=Path, metavar="PATH")
    parser.add_argument(
        "--schema",
        type=Path,
        metavar="PATH",
        help="explicit coverage manifest JSON schema",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        metavar="PATH",
        help="Git checkout root containing every canonical evidence path",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        metavar="PATH",
        help=(
            "also enforce 100%% line/branch/function coverage for every "
            "Tier0 file in a normalized coverage manifest"
        ),
    )
    parser.add_argument(
        "--mutation-registry",
        type=Path,
        metavar="PATH",
        default=REPOSITORY_ROOT / "quality" / "mutation-exclusions.json",
        help="validate the equivalent-mutant exclusion register",
    )
    parser.add_argument("--expected-commit-sha", metavar="SHA")
    parser.add_argument("--expected-source-head-sha", metavar="SHA")
    parser.add_argument("--expected-tested-commit-sha", metavar="SHA")
    parser.add_argument("--expected-base-sha", metavar="SHA")
    parser.add_argument("--expected-base-ref", metavar="REF")
    parser.add_argument("--expected-workflow-run-id", metavar="ID")
    parser.add_argument("--expected-workflow-run-attempt", metavar="ATTEMPT")
    parser.add_argument("--expected-workflow-event", metavar="EVENT")
    parser.add_argument("--expected-workflow-repository", metavar="OWNER/REPO")
    parser.add_argument("--expected-workflow-ref", metavar="REF")
    parser.add_argument("--expected-workflow-job", metavar="JOB")
    return parser.parse_args(argv)


def _print_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def _git_head(repository_root: Path) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ValueError(
            "unable to resolve current repository HEAD: git is unavailable"
        )
    try:
        result = subprocess.run(  # noqa: S603
            [git_executable, "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            f"unable to resolve current repository HEAD: {error}"
        ) from error
    head = result.stdout.strip()
    if SHA_PATTERN.fullmatch(head) is None:
        raise ValueError("current repository HEAD is not a canonical 40-character SHA")
    return head


def _is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction()) if callable(is_junction) else False
    except OSError:
        return True


def _safe_repository_file(
    repository_root: Path,
    value: object,
    field: str,
    errors: list[str],
) -> Path | None:
    path = _validate_repository_path(value, field, errors)
    if path is None:
        return None
    if "\\" in path or PurePosixPath(path).as_posix() != path:
        errors.append(f"{field} must use canonical POSIX separators")
        return None
    root = repository_root.resolve(strict=True)
    candidate = repository_root.joinpath(*PurePosixPath(path).parts)
    current = repository_root
    for part in PurePosixPath(path).parts:
        current = current / part
        if _is_link_or_junction(current):
            errors.append(f"{field} resolves through a symlink or junction: {path}")
            return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        errors.append(f"{field} is missing or unreadable: {path} ({error})")
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append(f"{field} resolves outside the repository: {path}")
        return None
    if not resolved.is_file():
        errors.append(f"{field} must identify a regular file: {path}")
        return None
    return resolved


def _schema_errors(manifest: object, schema_path: Path) -> list[str]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"coverage manifest schema is unreadable: {error}"]
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for violation in sorted(
        validator.iter_errors(manifest), key=lambda item: list(item.path)
    ):
        path = ".".join(str(part) for part in violation.absolute_path) or "root"
        errors.append(f"schema {path}: {violation.message}")
    return errors


def _contract_component_floors(
    contract: dict[str, object], component: str
) -> dict[str, int]:
    components = cast(dict[str, object], contract["components"])
    config = cast(dict[str, object], components[component])
    coverage = cast(dict[str, object], config["coverage"])
    return {metric: cast(int, coverage[metric]) for metric in METRICS}


def _validate_metric_for_floor(
    metric: dict[str, object],
    *,
    floor: int,
    field: str,
) -> list[str]:
    status = metric["status"]
    if status in {"missing", "experimental"}:
        return [f"{field} is {status}; incomplete evidence is never acceptable"]
    if status == "unsupported":
        if floor != 0:
            return [f"{field} is unsupported but its component floor is {floor}"]
        return []
    if status not in {"native", "derived"}:
        return [f"{field} has unsupported status {status!r}"]
    covered = cast(int, metric["covered"])
    total = cast(int, metric["total"])
    percent = metric["percent"]
    metric_errors: list[str] = []
    if status == "derived" and metric.get("derivation") not in TRUSTED_DERIVATIONS:
        metric_errors.append(f"{field} uses an untrusted derived-metric algorithm")
    if total == 0:
        expected_percent = 100.0
        if status != "derived" or covered != 0:
            metric_errors.append(
                f"{field} zero-unit evidence must be an explicit trusted derivation"
            )
    else:
        with localcontext() as context:
            context.prec = max(28, len(str(covered)) + len(str(total)) + 8)
            expected_percent = float(
                (Decimal(covered) * Decimal(100) / Decimal(total)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )
            )
    if percent != expected_percent:
        metric_errors.append(
            f"{field}.percent does not match covered/total counters "
            f"(expected {expected_percent}, got {percent!r})"
        )
    # A measured metric is applicable by definition. The platform-wide quality
    # floor is 100 for every applicable measurement; component floor 0 means
    # the toolchain may report explicit unsupported/N/A, not undercoverage.
    if covered != total or percent != 100:
        metric_errors.append(
            f"{field} is applicable and must equal 100% "
            f"(covered={covered}, total={total}, percent={percent!r})"
        )
    return metric_errors


def _tier0_rule_matches(path: str, rule: str) -> bool:
    return fnmatch.fnmatchcase(path, rule) or PurePosixPath(path).match(rule)


def _source_suffixes(component: str) -> frozenset[str]:
    if component == "python":
        return frozenset({".py"})
    if component == "frontend":
        return frozenset({".ts", ".tsx"})
    if component.startswith("go-"):
        return frozenset({".go"})
    if component.startswith("rust-"):
        return frozenset({".rs"})
    return frozenset()


def _expand_source_policy_braces(pattern: str) -> tuple[str, ...]:
    """Expand the small brace-pattern dialect used by the Vitest policy."""
    match = re.search(r"\{([^{}]+)\}", pattern)
    if match is None:
        return (pattern,)
    return tuple(
        expanded
        for alternative in match.group(1).split(",")
        for expanded in _expand_source_policy_braces(
            pattern[: match.start()] + alternative + pattern[match.end() :]
        )
    )


def _source_policy_glob_matches(path: str, pattern: str) -> bool:
    """Match a POSIX repository path with ``**`` also matching zero folders."""
    candidates = {pattern}
    pending = [pattern]
    while pending:
        candidate = pending.pop()
        start = 0
        while (index := candidate.find("/**/", start)) >= 0:
            shortened = candidate[:index] + "/" + candidate[index + 4 :]
            if shortened not in candidates:
                candidates.add(shortened)
                pending.append(shortened)
            start = index + 1
    return any(fnmatch.fnmatchcase(path, candidate) for candidate in candidates)


def _path_is_under_root(path: str, root: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized_root = root.replace("\\", "/").rstrip("/")
    return normalized_path == normalized_root or normalized_path.startswith(
        f"{normalized_root}/"
    )


def _tier0_source_requires_coverage(
    component: str,
    path: str,
    coverage_scope: Mapping[str, object],
) -> bool:
    """Whether the active producer is expected to emit coverage for a file.

    Applicability is deliberately contract-driven.  ``source_roots`` remains
    the report identity boundary, while ``coverage_scope`` is the exact set of
    roots instrumented by the producer (Python uses ``--cov=app``).  No
    component-specific filename exception is allowed here: a future toolchain
    change must update the contract and its producer together.
    """
    roots = coverage_scope.get(component)
    return isinstance(roots, list) and any(
        isinstance(root, str) and _path_is_under_root(path, root) for root in roots
    )


def _load_frontend_source_policy(
    repository_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Load the canonical frontend production-source policy.

    A malformed or absent policy is represented as ``None``.  The caller then
    falls back to conservative filename filters; any resulting manifest drift
    is still rejected by the Tier0 inventory comparison.
    """
    path = repository_root / "quality" / "coverage-source-policy.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        frontend = document["frontend"]
        include = frontend["include"]
        exclude = frontend["exclude"]
        if (
            not isinstance(include, list)
            or not isinstance(exclude, list)
            or not include
            or not exclude
            or not all(isinstance(value, str) and value for value in include)
            or not all(isinstance(value, str) and value for value in exclude)
        ):
            return None
    except (OSError, UnicodeDecodeError, TypeError, KeyError, ValueError):
        return None
    return (
        tuple(
            expanded
            for value in include
            for expanded in _expand_source_policy_braces(f"frontend/{value}")
        ),
        tuple(
            expanded
            for value in exclude
            for expanded in _expand_source_policy_braces(f"frontend/{value}")
        ),
    )


def _is_production_source(
    path: str,
    component: str,
    frontend_policy: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
) -> bool:
    pure = PurePosixPath(path)
    if pure.suffix not in _source_suffixes(component):
        return False
    lowered = pure.name.lower()
    if component.startswith("go-") and lowered.endswith("_test.go"):
        return False
    if component == "frontend":
        if frontend_policy is not None:
            include, exclude = frontend_policy
            return any(
                _source_policy_glob_matches(path, pattern) for pattern in include
            ) and not any(
                _source_policy_glob_matches(path, pattern) for pattern in exclude
            )
        if (
            ".test." in lowered
            or ".spec." in lowered
            or ".stories." in lowered
            or "__tests__" in pure.parts
            or "test" in pure.parts
            or ("api" in pure.parts and "generated" in pure.parts)
            or lowered in {"setuptests.ts", "routetree.gen.ts"}
            or lowered.endswith(".d.ts")
        ):
            return False
    if component.startswith("rust-"):
        lowered_parts = {part.casefold() for part in pure.parts}
        if lowered_parts.intersection({"tests", "benches", "fuzz", "target"}):
            return False
        if lowered in {"tests.rs", "test.rs"}:
            return False
    return True


def _tracked_source_paths(
    repository_root: Path,
    roots: Sequence[str],
) -> tuple[str, ...]:
    """Read source paths from Git's index, never from mutable build output."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ValueError("unable to inventory tracked sources: git is unavailable")
    try:
        result = subprocess.run(  # noqa: S603
            [git_executable, "ls-files", "-z", "--", *roots],
            cwd=repository_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            f"unable to inventory tracked sources with git ls-files: {error}"
        ) from error
    try:
        return tuple(
            sorted(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)
        )
    except UnicodeDecodeError as error:
        raise ValueError(
            "unable to inventory tracked sources: Git path is not UTF-8"
        ) from error


def _expected_tier0_inventory(
    repository_root: Path,
    source_roots: dict[str, object],
    rules: list[str],
    coverage_scope: dict[str, object],
) -> set[tuple[str, str]]:
    """Return Tier0 files that the active coverage producers can measure.

    ``source_roots`` remains the report identity boundary, while
    ``coverage_scope`` is the explicit producer scope.  In particular, the
    Python report is produced with ``--cov=app``; Alembic revisions remain
    structurally validated by the migration job and are not fabricated as
    Python coverage evidence.
    """
    inventory: set[tuple[str, str]] = set()
    frontend_policy = _load_frontend_source_policy(repository_root)
    scope = coverage_scope
    for component in COMPONENTS:
        if component not in COVERAGE_COMPONENTS or component not in scope:
            continue
        roots = cast(list[object], scope[component])
        root_values = [root for root in roots if isinstance(root, str)]
        for relative in _tracked_source_paths(repository_root, root_values):
            if not _is_production_source(relative, component, frontend_policy):
                continue
            if not _tier0_source_requires_coverage(component, relative, scope):
                continue
            if any(_tier0_rule_matches(relative, rule) for rule in rules):
                inventory.add((component, relative))
    return inventory


def _validate_reports(
    manifest: dict[str, object],
    contract: dict[str, object],
    repository_root: Path,
) -> list[str]:
    errors: list[str] = []
    declarations = cast(list[object], contract["coverage_reports"])
    expected = {
        (item["component"], item["format"], item["path"])
        for item in declarations
        if isinstance(item, dict)
    }
    reports = cast(list[object], manifest["reports"])
    actual: list[tuple[object, object, object]] = [
        (item["component"], item["format"], item["path"])
        for item in reports
        if isinstance(item, dict)
    ]
    actual_set = set(actual)
    if len(actual) != len(actual_set):
        errors.append("reports contains duplicate component/format/path evidence")
    for missing in sorted(expected - actual_set):
        errors.append(f"reports is missing required report: {missing[2]}")
    for extra in sorted(actual_set - expected):
        errors.append(f"reports contains unexpected report: {extra[2]}")
    if len(reports) != len(expected):
        errors.append(
            f"reports cardinality must equal coverage_reports ({len(expected)}), got {len(reports)}"
        )

    seen_paths: set[str] = set()
    for index, report in enumerate(reports):
        report = cast(dict[str, object], report)
        path_value = cast(str, report["path"])
        if path_value in seen_paths:
            errors.append(
                f"reports[{index}].path duplicates another report: {path_value}"
            )
        seen_paths.add(path_value)
        resolved = _safe_repository_file(
            repository_root, path_value, f"reports[{index}].path", errors
        )
        if resolved is None:
            continue
        try:
            raw = resolved.read_bytes()
        except OSError as error:
            errors.append(f"report {path_value} cannot be read: {error}")
            continue
        if not raw:
            errors.append(f"report {path_value} must be non-empty")
            continue
        size = report["size_bytes"]
        if size != len(raw):
            errors.append(
                f"report {path_value} size mismatch: manifest={size}, actual={len(raw)}"
            )
        digest = hashlib.sha256(raw).hexdigest()
        if report["sha256"] != digest:
            errors.append(f"report {path_value} sha256 mismatch")
    return errors


def _validate_components_manifest(
    manifest: dict[str, object], contract: dict[str, object]
) -> list[str]:
    errors: list[str] = []
    reports = cast(list[object], manifest["reports"])
    components = cast(dict[str, object], manifest["components"])
    report_components = {
        report["component"] for report in reports if isinstance(report, dict)
    }
    for component in COMPONENTS:
        entry = cast(dict[str, object], components[component])
        expected_status = (
            "passed" if component in report_components else "not_applicable"
        )
        if entry["status"] != expected_status:
            errors.append(
                f"components.{component}.status must be {expected_status!r}, "
                f"got {entry['status']!r}"
            )
        if entry["errors"]:
            errors.append(f"components.{component}.errors must be empty")
        metrics = cast(dict[str, object], entry["metrics"])
        floors = _contract_component_floors(contract, component)
        for metric_name in METRICS:
            metric = cast(dict[str, object], metrics[metric_name])
            errors.extend(
                _validate_metric_for_floor(
                    metric,
                    floor=floors[metric_name],
                    field=f"components.{component}.{metric_name}",
                )
            )
    return errors


def _load_canonical_tier0_rules(repository_root: Path, errors: list[str]) -> list[str]:
    path = _safe_repository_file(
        repository_root,
        "quality/ownership-mapping.json",
        "canonical ownership-mapping",
        errors,
    )
    if path is None:
        return []
    try:
        text = path.read_text(encoding="utf-8")
        _reject_excessive_json_nesting(text)
        document = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        errors.append(f"canonical ownership-mapping is invalid: {error}")
        return []
    if not isinstance(document, dict):
        errors.append("canonical ownership-mapping root must be an object")
        return []
    rules = document.get("tier0_rules")
    if (
        not isinstance(rules, list)
        or not rules
        or not all(isinstance(rule, str) and rule.strip() for rule in rules)
    ):
        errors.append(
            "canonical ownership-mapping tier0_rules must be a non-empty string array"
        )
        return []
    normalized = [cast(str, rule).strip().replace("\\", "/") for rule in rules]
    if len(normalized) != len(set(normalized)):
        errors.append("canonical ownership-mapping tier0_rules contains duplicates")
    return sorted(set(normalized))


def _validate_tier0_manifest(
    manifest: dict[str, object],
    contract: dict[str, object],
    repository_root: Path,
) -> list[str]:
    errors: list[str] = []
    tier0 = cast(dict[str, object], manifest["tier0"])
    if tier0["status"] != "ready":
        errors.append(f"tier0.status must be 'ready', got {tier0['status']!r}")
    if tier0["errors"]:
        errors.append("tier0.errors must be empty")
    manifest_rules = cast(list[str], tier0["rules"])
    rules = _load_canonical_tier0_rules(repository_root, errors)
    if manifest_rules != rules:
        errors.append(
            "tier0.rules must exactly equal canonical ownership-mapping tier0_rules"
        )
    files = cast(list[object], tier0["files"])
    source_roots = cast(dict[str, object], manifest["source_roots"])
    manifest_scope_value = manifest.get("coverage_scope")
    contract_scope_value = contract.get("coverage_scope")
    if manifest_scope_value != contract_scope_value:
        errors.append("coverage_scope does not match the quality contract")
    # Schema validation already requires an object.  Keep a fail-closed empty
    # scope for malformed direct callers so no unscoped source can silently
    # become an expected Tier0 obligation.
    coverage_scope = (
        cast(dict[str, object], manifest_scope_value)
        if isinstance(manifest_scope_value, dict)
        else {}
    )
    try:
        expected_inventory = _expected_tier0_inventory(
            repository_root,
            source_roots,
            rules,
            coverage_scope,
        )
    except ValueError as error:
        # A missing/failed Git inventory is not equivalent to an empty source
        # tree.  Continue collecting schema/metric diagnostics, but fail
        # closed with an explicit evidence error.
        errors.append(str(error))
        expected_inventory = set()
    actual_inventory: set[tuple[str, str]] = set()
    measured_by_metric: dict[str, list[dict[str, object]]] = {
        metric: [] for metric in METRICS
    }
    not_applicable: dict[str, int] = {metric: 0 for metric in METRICS}
    for index, record in enumerate(files):
        record = cast(dict[str, object], record)
        component = cast(str, record["component"])
        path = cast(str, record["path"])
        identity = (component, path)
        if identity in actual_inventory:
            errors.append(f"tier0.files[{index}] duplicates {component}:{path}")
        actual_inventory.add(identity)
        source = _safe_repository_file(
            repository_root,
            path,
            f"tier0.files[{index}].path",
            errors,
        )
        if source is None:
            continue
        component_roots = cast(list[object], source_roots[component])
        if not any(
            path == root or path.startswith(f"{root}/")
            for root in component_roots
            if isinstance(root, str)
        ):
            errors.append(f"tier0 file {path} is outside source_roots.{component}")
        if not _tier0_source_requires_coverage(component, path, coverage_scope):
            errors.append(f"tier0 file {path} is outside coverage_scope.{component}")
        if not any(_tier0_rule_matches(path, rule) for rule in rules):
            errors.append(f"tier0 file {path} does not match a declared Tier0 rule")
        floors = _contract_component_floors(contract, component)
        metrics = cast(dict[str, object], record["metrics"])
        for metric_name in METRICS:
            metric = cast(dict[str, object], metrics[metric_name])
            errors.extend(
                _validate_metric_for_floor(
                    metric,
                    floor=floors[metric_name],
                    field=f"{path}.{metric_name}",
                )
            )
            if metric["status"] in {"native", "derived"}:
                measured_by_metric[metric_name].append(metric)
            elif metric["status"] == "unsupported":
                not_applicable[metric_name] += 1

    for missing in sorted(expected_inventory - actual_inventory):
        errors.append(f"Tier0 source inventory is missing evidence for {missing[1]}")
    for component, extra_path in sorted(actual_inventory - expected_inventory):
        if not _tier0_source_requires_coverage(component, extra_path, coverage_scope):
            continue
        errors.append(f"tier0.files contains unexpected source {extra_path}")

    summaries = cast(dict[str, object], tier0["metric_summary"])
    aggregate = cast(dict[str, object], tier0["coverage"])
    for metric_name in METRICS:
        entries = measured_by_metric[metric_name]
        expected_summary = {
            "applicable_files": len(entries),
            "not_applicable_files": not_applicable[metric_name],
        }
        if summaries[metric_name] != expected_summary:
            errors.append(
                f"tier0.metric_summary.{metric_name} must equal {expected_summary!r}"
            )
        aggregate_metric = cast(dict[str, object], aggregate[metric_name])
        if not entries:
            if aggregate_metric["status"] != "unsupported":
                errors.append(
                    f"tier0.coverage.{metric_name} must be N/A when no files are applicable"
                )
            continue
        errors.extend(
            _validate_metric_for_floor(
                aggregate_metric,
                floor=100,
                field=f"tier0.coverage.{metric_name}",
            )
        )
        covered = sum(cast(int, entry["covered"]) for entry in entries)
        total = sum(cast(int, entry["total"]) for entry in entries)
        expected_status = (
            "derived"
            if any(entry["status"] == "derived" for entry in entries)
            else "native"
        )
        if (
            aggregate_metric["status"] != expected_status
            or aggregate_metric["covered"] != covered
            or aggregate_metric["total"] != total
            or aggregate_metric["percent"] != 100
        ):
            errors.append(
                f"tier0.coverage.{metric_name} does not equal the applicable-file aggregate"
            )
    return errors


def _validate_provenance(
    provenance: dict[str, object],
    expected_provenance: dict[str, str] | None,
) -> list[str]:
    errors: list[str] = []
    mode = provenance["mode"]
    workflow_fields = (
        "workflow_run_id",
        "workflow_run_attempt",
        "workflow_event",
        "workflow_repository",
        "workflow_ref",
        "workflow_job",
    )
    if mode == "local":
        for field in workflow_fields:
            if provenance[field] != "local":
                errors.append(f"provenance.{field} must equal 'local' in local mode")
    else:
        if not str(provenance["workflow_run_id"]).isdigit():
            errors.append(
                "provenance.workflow_run_id must be numeric in github-actions mode"
            )
        if not str(provenance["workflow_run_attempt"]).isdigit():
            errors.append(
                "provenance.workflow_run_attempt must be numeric in github-actions mode"
            )
        for field in workflow_fields[2:]:
            if provenance[field] == "local":
                errors.append(
                    f"provenance.{field} must identify the current workflow run"
                )
    if expected_provenance is not None:
        for field, expected in expected_provenance.items():
            if provenance.get(field) != expected:
                errors.append(
                    f"provenance.{field} mismatch: expected {expected!r}, "
                    f"got {provenance.get(field)!r}"
                )
    return errors


def _validate_manifest_identity(
    manifest: Mapping[str, object],
    *,
    current_head: str,
    expected_source_head_sha: str | None,
    expected_tested_commit_sha: str | None,
    expected_base_sha: str | None,
    expected_base_ref: str | None,
) -> list[str]:
    """Validate the v3 source/test/base identity carried by a manifest.

    ``commit_sha`` remains a deliberately boring compatibility alias for the
    commit that was actually tested.  It is never treated as the PR source
    head: on ``pull_request`` runs that value is supplied separately by
    ``source_head_sha`` and the checkout is represented by
    ``tested_commit_sha``.
    """

    errors: list[str] = []
    fields = ("source_head_sha", "tested_commit_sha", "base_sha")
    values: dict[str, str] = {}
    for field in fields:
        value = manifest.get(field)
        if not isinstance(value, str) or SHA_PATTERN.fullmatch(value) is None:
            errors.append(f"{field} must be a lowercase 40-character Git SHA")
        else:
            values[field] = value
    base_ref = manifest.get("base_ref")
    if not isinstance(base_ref, str) or not base_ref.strip():
        errors.append("base_ref must be a non-empty workflow ref")
    elif any(character in base_ref for character in "\x00\r\n"):
        errors.append("base_ref contains forbidden control characters")

    commit_sha = manifest.get("commit_sha")
    tested_sha = values.get("tested_commit_sha")
    if (
        isinstance(commit_sha, str)
        and tested_sha is not None
        and commit_sha != tested_sha
    ):
        errors.append("commit_sha must equal tested_commit_sha")
    if tested_sha is not None and tested_sha != current_head:
        errors.append(
            f"tested_commit_sha must equal current repository HEAD {current_head}, "
            f"got {tested_sha}"
        )

    expected_values = {
        "source_head_sha": expected_source_head_sha,
        "tested_commit_sha": expected_tested_commit_sha,
        "base_sha": expected_base_sha,
        "base_ref": expected_base_ref,
    }
    for field, expected in expected_values.items():
        if expected is not None and manifest.get(field) != expected:
            errors.append(
                f"{field} mismatch: expected {expected!r}, got {manifest.get(field)!r}"
            )

    provenance = manifest.get("provenance")
    event = (
        provenance.get("workflow_event") if isinstance(provenance, Mapping) else None
    )
    mode = provenance.get("mode") if isinstance(provenance, Mapping) else None
    if mode == "local":
        if values.get("source_head_sha") != current_head:
            errors.append("local source_head_sha must equal current repository HEAD")
        if values.get("base_sha") != current_head:
            errors.append("local base_sha must equal current repository HEAD")
        if base_ref != "local":
            errors.append("local base_ref must equal 'local'")
    elif mode == "github-actions":
        if event == "pull_request":
            if base_ref in {None, "local"}:
                errors.append("pull_request base_ref must identify the target branch")
        elif tested_sha is not None and values.get("source_head_sha") != tested_sha:
            errors.append(
                "non-pull_request source_head_sha must equal tested_commit_sha"
            )
        if base_ref == "local":
            errors.append("github-actions base_ref must not be 'local'")
    return errors


def _validate_tool_versions(manifest: dict[str, object]) -> list[str]:
    reports = cast(list[object], manifest["reports"])
    required_tools = {"quality-normalizer"}
    for report_value in reports:
        report = cast(dict[str, object], report_value)
        report_format = cast(str, report["format"])
        required_tools.update(REPORT_FORMAT_TO_TOOLS[report_format])
    tool_versions = cast(dict[str, object], manifest["tool_versions"])
    actual_tools = set(tool_versions)
    errors: list[str] = []
    missing = required_tools - actual_tools
    unexpected = actual_tools - required_tools
    if missing:
        errors.append(
            "tool_versions is missing required tools: " + ", ".join(sorted(missing))
        )
    if unexpected:
        errors.append(
            "tool_versions contains unexpected tools: " + ", ".join(sorted(unexpected))
        )
    for tool, version_value in tool_versions.items():
        if (
            not isinstance(version_value, str)
            or VERSION_PATTERN.fullmatch(version_value) is None
        ):
            errors.append(f"tool_versions.{tool} must be a concrete version-like value")
    if tool_versions.get("quality-normalizer") != NORMALIZER_VERSION:
        errors.append(
            f"tool_versions.quality-normalizer must equal {NORMALIZER_VERSION}"
        )
    return errors


def validate_manifest_evidence(
    manifest: object,
    *,
    contract: dict[str, object],
    manifest_path: Path,
    repository_root: Path,
    schema_path: Path,
    expected_commit_sha: str | None = None,
    expected_source_head_sha: str | None = None,
    expected_tested_commit_sha: str | None = None,
    expected_base_sha: str | None = None,
    expected_base_ref: str | None = None,
    expected_provenance: dict[str, str] | None = None,
) -> list[str]:
    """Validate a v3 manifest against current files, Git state, and provenance."""
    schema_errors = _schema_errors(manifest, schema_path)
    if schema_errors:
        return schema_errors
    manifest = cast(dict[str, object], manifest)
    errors: list[str] = []
    commit_sha = cast(str, manifest["commit_sha"])
    if SHA_PATTERN.fullmatch(commit_sha) is None:
        errors.append("commit_sha must be a lowercase 40-character Git SHA")
    current_head: str | None = None
    try:
        current_head = _git_head(repository_root)
    except ValueError as error:
        errors.append(str(error))
    else:
        if commit_sha != current_head:
            errors.append(
                f"commit_sha must equal current repository HEAD {current_head}, got {commit_sha}"
            )
    if expected_commit_sha is not None and commit_sha != expected_commit_sha:
        errors.append(
            f"commit_sha mismatch: expected workflow checkout {expected_commit_sha}, got {commit_sha}"
        )

    manifest_relative = cast(str, manifest["manifest_path"])
    if manifest_relative != contract["manifest_path"]:
        errors.append("manifest_path does not match the quality contract")
    try:
        actual_manifest_relative = (
            manifest_path.resolve(strict=False)
            .relative_to(repository_root.resolve(strict=True))
            .as_posix()
        )
    except (OSError, ValueError):
        errors.append("manifest file is outside the repository")
    else:
        if actual_manifest_relative != manifest_relative:
            errors.append(
                f"manifest file path mismatch: expected {manifest_relative}, "
                f"got {actual_manifest_relative}"
            )

    if manifest["source_roots"] != contract["source_roots"]:
        errors.append("source_roots do not match the quality contract")
    if manifest["coverage_scope"] != contract["coverage_scope"]:
        errors.append("coverage_scope does not match the quality contract")
    validation = cast(dict[str, object], manifest["validation"])
    if validation["valid"] is not True:
        errors.append("validation.valid must be true")
    if validation["errors"]:
        errors.append("validation.errors must be empty")
    if manifest["missing_reports"]:
        errors.append("missing_reports must be empty")
    generation = cast(dict[str, object], manifest["generation"])
    if generation["command"] != "scripts/quality/normalize_coverage_reports.py":
        errors.append(
            "generation.command must equal scripts/quality/normalize_coverage_reports.py"
        )
    if generation["normalizer_version"] != NORMALIZER_VERSION:
        errors.append(f"generation.normalizer_version must equal {NORMALIZER_VERSION}")
    provenance = cast(dict[str, object], manifest["provenance"])
    errors.extend(_validate_provenance(provenance, expected_provenance))
    if current_head is not None:
        errors.extend(
            _validate_manifest_identity(
                manifest,
                current_head=current_head,
                expected_source_head_sha=expected_source_head_sha,
                expected_tested_commit_sha=(
                    expected_tested_commit_sha or expected_commit_sha
                ),
                expected_base_sha=expected_base_sha,
                expected_base_ref=expected_base_ref,
            )
        )
    errors.extend(_validate_tool_versions(manifest))
    errors.extend(_validate_reports(manifest, contract, repository_root))
    errors.extend(_validate_components_manifest(manifest, contract))
    errors.extend(_validate_tier0_manifest(manifest, contract, repository_root))
    return sorted(set(errors))


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the requested contract and return its process exit status."""
    try:
        arguments = _parse_arguments(argv)
    except _ArgumentParsingError as error:
        _print_error(str(error))
        return 2
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2

    contract_path = (
        arguments.contract or REPOSITORY_ROOT / "quality" / "quality-contract.json"
    )
    try:
        contract_text = contract_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        _print_error(f"unable to read contract: {error}")
        return 2

    try:
        _reject_excessive_json_nesting(contract_text)
        contract = json.loads(
            contract_text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as error:
        _print_error(str(error))
        return 2
    except RecursionError:
        _print_error("invalid JSON: nesting exceeds supported depth")
        return 2
    except (json.JSONDecodeError, ValueError) as error:
        _print_error(f"invalid JSON: {error}")
        return 2

    if not isinstance(contract, dict):
        _print_error("contract root must be a JSON object")
        return 1

    errors = validate_contract(contract, today=date.today())
    if errors:
        for violation in errors:
            _print_error(violation)
        return 1

    try:
        mutation_registry_text = arguments.mutation_registry.read_text(encoding="utf-8")
        _reject_excessive_json_nesting(mutation_registry_text)
        mutation_registry = json.loads(
            mutation_registry_text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as error:
        _print_error(f"invalid mutation registry: {error}")
        return 1
    except RecursionError:
        _print_error("invalid mutation registry: nesting exceeds supported depth")
        return 1
    except (OSError, UnicodeDecodeError) as error:
        _print_error(f"unable to read mutation registry: {error}")
        return 2
    except (json.JSONDecodeError, ValueError) as error:
        _print_error(f"invalid mutation registry: {error}")
        return 1

    registry_errors = _validate_mutation_registry(
        mutation_registry,
        today=date.today(),
    )
    if registry_errors:
        for violation in registry_errors:
            _print_error(violation)
        return 1

    if arguments.manifest is not None:
        try:
            manifest_text = arguments.manifest.read_text(encoding="utf-8")
            _reject_excessive_json_nesting(manifest_text)
            manifest = json.loads(
                manifest_text,
                object_pairs_hook=_duplicate_key_object,
                parse_constant=_reject_json_constant,
            )
        except _DuplicateKeyError as error:
            _print_error(f"invalid coverage manifest: {error}")
            return 1
        except RecursionError:
            _print_error("invalid coverage manifest: nesting exceeds supported depth")
            return 1
        except (OSError, UnicodeDecodeError) as error:
            _print_error(f"unable to read coverage manifest: {error}")
            return 2
        except (json.JSONDecodeError, ValueError) as error:
            _print_error(f"invalid coverage manifest: {error}")
            return 1

        expected_provenance = {
            field.removeprefix("expected_"): value
            for field, value in vars(arguments).items()
            if field.startswith("expected_workflow_") and value is not None
        }
        artifact_root = arguments.artifact_root or REPOSITORY_ROOT
        schema_path = (
            arguments.schema
            or REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"
        )
        manifest_errors = validate_manifest_evidence(
            manifest,
            contract=contract,
            manifest_path=arguments.manifest,
            repository_root=artifact_root,
            schema_path=schema_path,
            expected_commit_sha=arguments.expected_commit_sha,
            expected_source_head_sha=arguments.expected_source_head_sha,
            expected_tested_commit_sha=arguments.expected_tested_commit_sha,
            expected_base_sha=arguments.expected_base_sha,
            expected_base_ref=arguments.expected_base_ref,
            expected_provenance=expected_provenance or None,
        )
        if manifest_errors:
            for violation in manifest_errors:
                _print_error(violation)
            return 1

    print("Quality contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
