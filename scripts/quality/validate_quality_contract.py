from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NoReturn

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
    "rust-crypto",
    "infrastructure",
    "workflows",
    "scripts",
)
COMPONENT_FLOORS = (
    ("lines", 88),
    ("statements", 90),
    ("branches", 82),
    ("functions", 80),
)
TIER0_FLOORS = (
    ("lines", 100),
    ("statements", 100),
    ("branches", 100),
    ("functions", 100),
)
COVERAGE_MINIMUMS = (
    ("lines", 91),
    ("statements", 91),
    ("branches", 82),
    ("functions", 82),
    ("tier0", 100),
)
TOP_LEVEL_KEYS = frozenset(
    {
        "version",
        "policy",
        "coverage_minimums",
        "components",
        "tier0",
        "required_artifacts",
        "exclusions",
        "quarantines",
    }
)
POLICY_KEYS = frozenset({"patch_coverage", "viable_mutant_score", "required_pr_matrix"})
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
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
WILDCARD_CHARACTERS = "*?[]"


class _ArgumentParsingError(ValueError):
    """Raised when command-line parsing finds an invalid argument."""


class _QualityArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _ArgumentParsingError(message)


class _DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


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
        if path is not None and register_name == "exclusions":
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


def _validate_required_artifacts(value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("required_artifacts must be a list")
        return
    if not value:
        errors.append("required_artifacts must contain at least one path")
        return

    seen_paths: dict[str, int] = {}
    for index, artifact in enumerate(value):
        field = f"required_artifacts[{index}]"
        path = _validate_repository_path(artifact, field, errors)
        if path is None:
            continue
        previous_path = seen_paths.get(path)
        if previous_path is None:
            seen_paths[path] = index
        else:
            errors.append(f"{field} duplicates required_artifacts[{previous_path}]")


def validate_contract(contract: dict[str, object], *, today: date) -> list[str]:
    """Return every policy violation found in a version 1 quality contract."""
    errors: list[str] = []
    _validate_exact_keys(contract, "contract", TOP_LEVEL_KEYS, errors)

    if "version" in contract:
        version = contract["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            errors.append("version must equal 1")
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
    if "required_artifacts" in contract:
        _validate_required_artifacts(contract["required_artifacts"], errors)
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
        description="Validate a version 1 quality contract."
    )
    parser.add_argument("--contract", type=Path, metavar="PATH")
    return parser.parse_args(argv)


def _print_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


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
        for error in errors:
            _print_error(error)
        return 1

    print("Quality contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
