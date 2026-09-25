"""Build and verify the fail-closed SQLAlchemy model-default inventory.

This check is deliberately source- and metadata-only.  It does not connect to
PostgreSQL and therefore cannot be used as a substitute for the catalog
preflight required by ADR-036.  Its purpose is to make the current model
surface, migration head, and reviewed exceptions reproducible before a live
database migration is attempted.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPOSITORY_ROOT / "quality" / "model-default-policy.json"
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT / "artifacts" / "quality" / "model-default-inventory.json"
)
SCHEMA_VERSION = 1
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
CLASSIFICATIONS = frozenset({"both", "python_only", "server_only", "computed"})
SOURCE_CLASSIFICATIONS = frozenset({"both", "python_only", "server_only"})
EXCEPTION_KINDS = frozenset(
    {
        "application_secret",
        "inherited_uuid7_primary_key",
        "json_application_default",
    }
)
_GIT = shutil.which("git") or "git"

POLICY_FIELDS = frozenset({"schema_version", "expected", "exceptions"})
POLICY_EXPECTED_FIELDS = frozenset(
    {
        "computed_columns",
        "effective_counts",
        "effective_default_count",
        "migration_head",
        "source_counts",
        "source_default_none_columns",
        "source_mapped_column_count",
        "table_count",
    }
)
POLICY_EXCEPTION_FIELDS = frozenset({"column", "kind", "owner", "reason"})
INVENTORY_FIELDS = frozenset(
    {
        "columns",
        "exceptions",
        "postgres_catalog",
        "schema_version",
        "source",
        "source_declarations",
        "summary",
    }
)
INVENTORY_SOURCE_FIELDS = frozenset(
    {"generated_at_utc", "git_sha", "migration_head", "repository"}
)


class InventoryError(ValueError):
    """Raised when the model inventory or its policy is incomplete or stale."""


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise InventoryError(f"invalid JSON constant: {value}")


def _load_json(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InventoryError(f"unable to read JSON {path}: {error}") from error


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InventoryError(f"{field} must be an object")
    return value


def _require_exact_fields(
    value: Mapping[str, object], expected: frozenset[str], field: str
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise InventoryError(f"{field} missing fields: {', '.join(missing)}")
    if unexpected:
        raise InventoryError(f"{field} has unexpected fields: {', '.join(unexpected)}")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InventoryError(f"{field} must be a non-empty string")
    if any(char in value for char in ("\x00", "\r", "\n")):
        raise InventoryError(f"{field} contains forbidden control characters")
    return value


def _require_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InventoryError(f"{field} must be a non-negative integer")
    return value


def _require_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise InventoryError(f"{field} must be an array")
    result = [
        _require_text(item, f"{field}[{index}]") for index, item in enumerate(value)
    ]
    if result != sorted(result) or len(result) != len(set(result)):
        raise InventoryError(f"{field} must be sorted and unique")
    return result


def _validate_counts(value: object, field: str) -> dict[str, int]:
    mapping = _require_mapping(value, field)
    expected = {"both", "python_only", "server_only"}
    if set(mapping) != expected:
        raise InventoryError(
            f"{field} must contain exactly both/python_only/server_only"
        )
    return {
        key: _require_integer(mapping[key], f"{field}.{key}")
        for key in sorted(expected)
    }


def _validate_policy(path: Path) -> dict[str, Any]:
    raw = _require_mapping(_load_json(path), "policy")
    _require_exact_fields(raw, POLICY_FIELDS, "policy")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise InventoryError("policy schema_version is unsupported")

    expected = _require_mapping(raw["expected"], "policy.expected")
    _require_exact_fields(expected, POLICY_EXPECTED_FIELDS, "policy.expected")
    computed_columns = _require_string_list(
        expected["computed_columns"], "policy.expected.computed_columns"
    )
    source_none = _require_string_list(
        expected["source_default_none_columns"],
        "policy.expected.source_default_none_columns",
    )
    migration_head = _require_text(
        expected["migration_head"], "policy.expected.migration_head"
    )
    normalized_expected = {
        "computed_columns": computed_columns,
        "effective_counts": _validate_counts(
            expected["effective_counts"], "policy.expected.effective_counts"
        ),
        "effective_default_count": _require_integer(
            expected["effective_default_count"],
            "policy.expected.effective_default_count",
        ),
        "migration_head": migration_head,
        "source_counts": _validate_counts(
            expected["source_counts"], "policy.expected.source_counts"
        ),
        "source_default_none_columns": source_none,
        "source_mapped_column_count": _require_integer(
            expected["source_mapped_column_count"],
            "policy.expected.source_mapped_column_count",
        ),
        "table_count": _require_integer(
            expected["table_count"], "policy.expected.table_count"
        ),
    }

    raw_exceptions = raw["exceptions"]
    if not isinstance(raw_exceptions, list):
        raise InventoryError("policy.exceptions must be an array")
    exceptions: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_exceptions):
        exception = _require_mapping(item, f"policy.exceptions[{index}]")
        _require_exact_fields(
            exception, POLICY_EXCEPTION_FIELDS, f"policy.exceptions[{index}]"
        )
        column = _require_text(
            exception["column"], f"policy.exceptions[{index}].column"
        )
        if column in seen:
            raise InventoryError(f"duplicate exception column: {column}")
        seen.add(column)
        kind = _require_text(exception["kind"], f"policy.exceptions[{index}].kind")
        if kind not in EXCEPTION_KINDS:
            raise InventoryError(f"unknown exception kind: {kind}")
        exceptions.append(
            {
                "column": column,
                "kind": kind,
                "owner": _require_text(
                    exception["owner"], f"policy.exceptions[{index}].owner"
                ),
                "reason": _require_text(
                    exception["reason"], f"policy.exceptions[{index}].reason"
                ),
            }
        )
    if [item["column"] for item in exceptions] != sorted(seen):
        raise InventoryError("policy.exceptions must be sorted by column")

    return {
        "schema_version": SCHEMA_VERSION,
        "expected": normalized_expected,
        "exceptions": exceptions,
    }


def _literal_revision(
    value: ast.AST, field: str, path: Path
) -> str | None | tuple[str, ...]:
    if isinstance(value, ast.Constant):
        if field == "revision" and isinstance(value.value, str) and value.value:
            return value.value
        if field == "down_revision" and value.value is None:
            return None
        if field == "down_revision" and isinstance(value.value, str) and value.value:
            return value.value
    if field == "down_revision" and isinstance(value, (ast.Tuple, ast.List)):
        revisions: list[str] = []
        for item in value.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                break
            if not item.value:
                break
            revisions.append(item.value)
        else:
            if revisions and len(revisions) == len(set(revisions)):
                return tuple(revisions)
    raise InventoryError(f"{path}: {field} must be a non-empty literal revision value")


def _parse_migration_file(path: Path) -> tuple[str, tuple[str, ...]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        raise InventoryError(f"unable to parse migration {path}: {error}") from error

    values: dict[str, str | None | tuple[str, ...]] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in {
                "revision",
                "down_revision",
            }:
                continue
            if target.id in values:
                raise InventoryError(f"{path}: duplicate {target.id} assignment")
            value = statement.value
            if value is None:
                raise InventoryError(f"{path}: {target.id} must have a literal value")
            values[target.id] = _literal_revision(value, target.id, path)

    if "revision" not in values or "down_revision" not in values:
        raise InventoryError(f"{path}: revision and down_revision are required")
    revision = values["revision"]
    down_revision = values["down_revision"]
    if not isinstance(revision, str):
        raise InventoryError(f"{path}: revision must be a string literal")
    if down_revision is None:
        parents: tuple[str, ...] = ()
    elif isinstance(down_revision, str):
        parents = (down_revision,)
    else:
        parents = down_revision
    return revision, parents


def read_migration_head(versions_path: Path) -> str:
    """Return the sole static Alembic head without importing revision modules."""

    if not versions_path.is_dir():
        raise InventoryError(
            f"migration versions directory is missing: {versions_path}"
        )
    files = sorted(
        path for path in versions_path.glob("*.py") if path.name != "__init__.py"
    )
    if not files:
        raise InventoryError(f"no migration files found in {versions_path}")

    revisions: dict[str, Path] = {}
    parents: set[str] = set()
    for path in files:
        revision, down_revisions = _parse_migration_file(path)
        if revision in revisions:
            raise InventoryError(
                f"duplicate migration revision {revision}: {revisions[revision]} and {path}"
            )
        revisions[revision] = path
        parents.update(down_revisions)
    unknown_parents = sorted(parents - set(revisions))
    if unknown_parents:
        raise InventoryError(
            "migration graph references unknown parents: " + ", ".join(unknown_parents)
        )
    heads = sorted(set(revisions) - parents)
    if len(heads) != 1:
        raise InventoryError(
            "migration graph must have exactly one head; found " + ", ".join(heads)
        )
    return heads[0]


def _git_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - fixed local git command
            [_GIT, "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InventoryError(f"unable to resolve current git SHA: {error}") from error
    sha = result.stdout.strip()
    if SHA_PATTERN.fullmatch(sha) is None:
        raise InventoryError("git rev-parse HEAD did not return a full lowercase SHA")
    return sha


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise InventoryError(f"model path escapes repository root: {path}") from error


def _is_mapped_column_call(value: ast.AST) -> bool:
    return isinstance(value, ast.Call) and (
        (isinstance(value.func, ast.Name) and value.func.id == "mapped_column")
        or (
            isinstance(value.func, ast.Attribute) and value.func.attr == "mapped_column"
        )
    )


def _class_table_name(node: ast.ClassDef, path: Path) -> str | None:
    table_name: str | None = None
    for statement in node.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in targets
        ):
            continue
        if table_name is not None:
            raise InventoryError(f"{path}:{statement.lineno}: duplicate __tablename__")
        value = statement.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            raise InventoryError(
                f"{path}:{statement.lineno}: __tablename__ must be literal"
            )
        table_name = value.value
    return table_name


def _source_declarations(repo_root: Path) -> list[dict[str, object]]:
    declarations: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in sorted((repo_root / "app" / "models").glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as error:
            raise InventoryError(
                f"unable to parse model source {path}: {error}"
            ) from error
        relative_path = _relative_path(path, repo_root)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            table_name = _class_table_name(node, path)
            for statement in node.body:
                target: ast.AST
                value: ast.AST | None
                if isinstance(statement, ast.AnnAssign):
                    target = statement.target
                    value = statement.value
                elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                    target = statement.targets[0]
                    value = statement.value
                else:
                    continue
                if value is None:
                    continue
                if not _is_mapped_column_call(value):
                    continue
                if not isinstance(target, ast.Name):
                    raise InventoryError(
                        f"{path}:{statement.lineno}: mapped_column target must be a name"
                    )
                call = cast(ast.Call, value)
                keywords: dict[str, ast.AST] = {}
                for keyword in call.keywords:
                    if keyword.arg is None:
                        raise InventoryError(
                            f"{path}:{statement.lineno}: mapped_column **kwargs are not inspectable"
                        )
                    if keyword.arg in keywords:
                        raise InventoryError(
                            f"{path}:{statement.lineno}: duplicate {keyword.arg} keyword"
                        )
                    keywords[keyword.arg] = keyword.value
                has_python = "default" in keywords
                has_server = "server_default" in keywords
                if not (has_python or has_server):
                    continue
                if has_python and has_server:
                    classification = "both"
                elif has_python:
                    classification = "python_only"
                else:
                    classification = "server_only"
                column_name = target.id
                if call.args and isinstance(call.args[0], ast.Constant):
                    if isinstance(call.args[0].value, str) and call.args[0].value:
                        column_name = call.args[0].value
                if table_name is None:
                    if node.name != "UUID7PrimaryKeyMixin" or column_name != "id":
                        raise InventoryError(
                            f"{path}:{statement.lineno}: default-bearing class has no literal table"
                        )
                    column_key = f"{node.name}.{column_name}"
                    table_value: str | None = None
                else:
                    column_key = f"{table_name}.{column_name}"
                    table_value = table_name
                if column_key in seen:
                    raise InventoryError(
                        f"duplicate source default declaration: {column_key}"
                    )
                seen.add(column_key)
                declarations.append(
                    {
                        "column": column_key,
                        "table": table_value,
                        "name": column_name,
                        "file": relative_path,
                        "line": statement.lineno,
                        "classification": classification,
                        "default_is_none": bool(
                            has_python
                            and isinstance(keywords["default"], ast.Constant)
                            and keywords["default"].value is None
                        ),
                    }
                )
    return sorted(
        declarations, key=lambda item: (str(item["column"]), str(item["file"]))
    )


def _metadata_columns(
    repo_root: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    repository_text = str(repo_root.resolve())
    if repository_text not in sys.path:
        sys.path.insert(0, repository_text)
    os.environ.setdefault("ENVIRONMENT", "testing")
    import app.models  # noqa: F401
    from app.core.database import Base

    columns: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    computed_columns: list[str] = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        for column in sorted(table.columns, key=lambda item: item.name):
            computed = column.computed is not None
            has_python = column.default is not None
            has_server = column.server_default is not None
            if computed:
                classification = "computed"
                computed_columns.append(f"{table.name}.{column.name}")
            elif has_python and has_server:
                classification = "both"
            elif has_python:
                classification = "python_only"
            elif has_server:
                classification = "server_only"
            else:
                continue
            if classification != "computed":
                counts[classification] += 1
            columns.append(
                {
                    "column": f"{table.name}.{column.name}",
                    "table": table.name,
                    "name": column.name,
                    "classification": classification,
                    "nullable": bool(column.nullable),
                    "primary_key": bool(column.primary_key),
                    "python_default_present": has_python,
                    "server_default_present": has_server,
                    "exception_kind": None,
                    "exception_owner": None,
                    "exception_reason": None,
                }
            )
    summary = {
        "table_count": len(Base.metadata.tables),
        "effective_default_count": sum(counts.values()),
        "effective_counts": {
            key: counts[key] for key in sorted(SOURCE_CLASSIFICATIONS)
        },
        "computed_columns": sorted(computed_columns),
    }
    return columns, summary


def _validate_inventory_state(
    *,
    columns: list[dict[str, object]],
    source_declarations: list[dict[str, object]],
    metadata_summary: Mapping[str, object],
    policy: Mapping[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    expected = cast(Mapping[str, object], policy["expected"])
    actual_summary = {
        "computed_columns": cast(list[str], metadata_summary["computed_columns"]),
        "effective_counts": cast(dict[str, int], metadata_summary["effective_counts"]),
        "effective_default_count": metadata_summary["effective_default_count"],
        "source_counts": {
            key: sum(
                1
                for declaration in source_declarations
                if declaration["classification"] == key
            )
            for key in sorted(SOURCE_CLASSIFICATIONS)
        },
        "source_default_none_count": sum(
            1
            for declaration in source_declarations
            if declaration["default_is_none"] is True
        ),
        "source_mapped_column_count": len(source_declarations),
        "table_count": metadata_summary["table_count"],
    }
    for field in (
        "computed_columns",
        "effective_counts",
        "effective_default_count",
        "source_counts",
        "source_default_none_count",
        "source_mapped_column_count",
        "table_count",
    ):
        expected_value: object
        if field == "source_default_none_count":
            expected_value = len(
                cast(list[object], expected["source_default_none_columns"])
            )
        else:
            expected_value = expected[field]
        if actual_summary[field] != expected_value:
            raise InventoryError(
                f"policy summary mismatch for {field}: expected {expected_value!r}, "
                f"found {actual_summary[field]!r}"
            )
    default_none_columns = sorted(
        str(declaration["column"])
        for declaration in source_declarations
        if declaration["default_is_none"] is True
    )
    if default_none_columns != expected["source_default_none_columns"]:
        raise InventoryError(
            "policy source_default_none_columns mismatch: "
            f"expected {expected['source_default_none_columns']!r}, found {default_none_columns!r}"
        )

    raw_exceptions = cast(list[dict[str, str]], policy["exceptions"])
    exception_by_column = {item["column"]: item for item in raw_exceptions}
    metadata_by_column = {str(item["column"]): item for item in columns}
    source_by_column = {
        str(item["column"]): item
        for item in source_declarations
        if item["table"] is not None
    }
    for exception in raw_exceptions:
        column = exception["column"]
        metadata = metadata_by_column.get(column)
        if metadata is None:
            raise InventoryError(f"exception references unknown column: {column}")
        if metadata["classification"] != "python_only":
            raise InventoryError(f"exception is not python_only: {column}")
        source = source_by_column.get(column)
        if exception["kind"] == "inherited_uuid7_primary_key":
            if source is not None:
                raise InventoryError(
                    f"inherited UUID7 exception has a direct source declaration: {column}"
                )
        elif source is None:
            raise InventoryError(
                f"non-inherited exception has no source declaration: {column}"
            )

    for column, item in metadata_by_column.items():
        column_exception = exception_by_column.get(column)
        if item["classification"] == "python_only" and column_exception is None:
            raise InventoryError(f"unreviewed python_only default: {column}")
        if column_exception is not None:
            item["exception_kind"] = column_exception["kind"]
            item["exception_owner"] = column_exception["owner"]
            item["exception_reason"] = column_exception["reason"]
        if item["classification"] == "computed" and column_exception is not None:
            raise InventoryError(f"computed column cannot be an exception: {column}")

    effective_columns = {
        column
        for column, item in metadata_by_column.items()
        if item["classification"] != "computed"
    }
    source_effective_columns = {
        str(item["column"])
        for item in source_declarations
        if item["table"] is not None and item["default_is_none"] is not True
    }
    missing_source = sorted(
        effective_columns
        - source_effective_columns
        - {
            column
            for column, exception in exception_by_column.items()
            if exception["kind"] == "inherited_uuid7_primary_key"
        }
    )
    if missing_source:
        raise InventoryError(
            "effective defaults missing source declarations: "
            + ", ".join(missing_source)
        )
    extra_source = sorted(source_effective_columns - effective_columns)
    if extra_source:
        raise InventoryError(
            "source defaults absent from SQLAlchemy metadata: "
            + ", ".join(extra_source)
        )
    return columns, actual_summary


def build_inventory(
    repo_root: Path = REPOSITORY_ROOT,
    *,
    policy_path: Path = POLICY_PATH,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    """Build and validate a deterministic model-default inventory."""

    root = repo_root.resolve()
    policy = _validate_policy(policy_path.resolve())
    migration_head = read_migration_head(root / "alembic" / "versions")
    expected_head = cast(Mapping[str, object], policy["expected"])["migration_head"]
    if migration_head != expected_head:
        raise InventoryError(
            f"migration head mismatch: policy expects {expected_head}, found {migration_head}"
        )
    source_declarations = _source_declarations(root)
    columns, metadata_summary = _metadata_columns(root)
    columns, summary = _validate_inventory_state(
        columns=columns,
        source_declarations=source_declarations,
        metadata_summary=metadata_summary,
        policy=policy,
    )
    sha = _git_sha(root)
    timestamp = generated_at_utc or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    _require_text(timestamp, "generated_at_utc")
    exceptions = cast(list[dict[str, str]], policy["exceptions"])
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "repository": root.name,
            "git_sha": sha,
            "migration_head": migration_head,
            "generated_at_utc": timestamp,
        },
        "summary": summary,
        "columns": sorted(columns, key=lambda item: str(item["column"])),
        "source_declarations": source_declarations,
        "exceptions": exceptions,
        "postgres_catalog": {"status": "not_checked", "required_for_release": True},
    }


def _inventory_without_timestamp(payload: Mapping[str, object]) -> dict[str, object]:
    result = cast(dict[str, object], json.loads(json.dumps(payload)))
    source = result.get("source")
    if isinstance(source, dict):
        source.pop("generated_at_utc", None)
    return result


def check_inventory(
    inventory_path: Path,
    *,
    repo_root: Path = REPOSITORY_ROOT,
    policy_path: Path = POLICY_PATH,
) -> list[str]:
    """Return validation errors for a generated artifact; never accept partial data."""

    errors: list[str] = []
    try:
        expected = build_inventory(repo_root, policy_path=policy_path)
    except InventoryError as error:
        return [str(error)]
    try:
        actual = _require_mapping(_load_json(inventory_path), "inventory")
        _require_exact_fields(actual, INVENTORY_FIELDS, "inventory")
        source = _require_mapping(actual["source"], "inventory.source")
        _require_exact_fields(source, INVENTORY_SOURCE_FIELDS, "inventory.source")
        actual_sha = source["git_sha"]
        expected_sha = cast(Mapping[str, object], expected["source"])["git_sha"]
        if actual_sha != expected_sha:
            errors.append(
                f"git_sha mismatch: expected {expected_sha}, found {actual_sha}"
            )
        actual_head = source["migration_head"]
        expected_head = cast(Mapping[str, object], expected["source"])["migration_head"]
        if actual_head != expected_head:
            errors.append(
                f"migration_head mismatch: expected {expected_head}, found {actual_head}"
            )
        if _inventory_without_timestamp(actual) != _inventory_without_timestamp(
            expected
        ):
            errors.append(
                "inventory payload drift: artifact is partial, stale, or non-deterministic"
            )
    except InventoryError as error:
        errors.append(str(error))
    return errors


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="write the generated inventory to this path",
    )
    parser.add_argument(
        "--check",
        type=Path,
        help="validate an existing inventory against the current source and SHA",
    )
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_arguments(argv)
    if args.check is not None:
        errors = check_inventory(
            args.check,
            repo_root=REPOSITORY_ROOT,
            policy_path=args.policy,
        )
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(f"model-default inventory is current: {args.check}")
        return 0
    try:
        inventory = build_inventory(REPOSITORY_ROOT, policy_path=args.policy)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (InventoryError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"wrote model-default inventory: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
