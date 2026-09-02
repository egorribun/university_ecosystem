"""Validate a fixed mutmut plan and emit only its executable CI shards.

The mutation universe producer owns a complete fixed-width plan, but a small
incremental change normally leaves most assignments empty.  This helper makes
the plan itself the authority for a dynamic GitHub Actions matrix: every
nonempty entry is emitted, while the full plan is revalidated by each consumer.
It never derives a new selection, so it cannot silently omit mutants.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PlanValidationError(ValueError):
    """Raised when a mutmut plan cannot safely drive the execution matrix."""


@dataclass(frozen=True, slots=True)
class _ShardSelection:
    shard_id: int
    names: tuple[str, ...]


def _selection_digest(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def _require_nonnegative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlanValidationError(f"{label} must be a non-negative integer")
    return value


def _read_manifest(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PlanValidationError("plan manifest is missing or unsafe")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlanValidationError("plan manifest is invalid") from error
    if not isinstance(raw, dict):
        raise PlanValidationError("plan manifest must be a JSON object")
    return raw


def _read_selection(path: Path, *, label: str) -> tuple[str, ...]:
    if path.is_symlink() or not path.is_file():
        raise PlanValidationError(f"{label} selection file is missing or unsafe")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise PlanValidationError(f"{label} selection file is invalid") from error
    if any(
        not line or line.strip() != line or any(char.isspace() for char in line)
        for line in lines
    ):
        raise PlanValidationError(f"{label} selection contains an invalid mutant name")
    if len(lines) != len(set(lines)):
        raise PlanValidationError(f"{label} selection contains duplicate mutant names")
    return tuple(lines)


def _load_validated_plan(
    plan_directory: Path, *, expected_shards: int
) -> tuple[_ShardSelection, ...]:
    if expected_shards < 1:
        raise PlanValidationError("expected shard count must be positive")
    if plan_directory.is_symlink() or not plan_directory.is_dir():
        raise PlanValidationError("plan directory is missing or unsafe")

    manifest = _read_manifest(plan_directory / "plan-manifest.json")
    if manifest.get("schema_version") != 1:
        raise PlanValidationError("plan manifest schema mismatch")
    if manifest.get("num_shards") != expected_shards:
        raise PlanValidationError("plan manifest shard count mismatch")
    universe_count = _require_nonnegative_int(
        manifest.get("universe_count"), label="plan universe count"
    )
    universe_digest = manifest.get("universe_sha256")
    if not isinstance(universe_digest, str) or not _SHA256_PATTERN.fullmatch(
        universe_digest
    ):
        raise PlanValidationError("plan universe digest is invalid")
    descriptors = manifest.get("shards")
    if not isinstance(descriptors, list) or len(descriptors) != expected_shards:
        raise PlanValidationError("plan manifest does not describe every shard")

    selections: list[_ShardSelection] = []
    all_names: list[str] = []
    for expected_id, descriptor in enumerate(descriptors, start=1):
        label = f"plan shard {expected_id}"
        if not isinstance(descriptor, dict):
            raise PlanValidationError(f"{label} descriptor is invalid")
        if descriptor.get("shard_id") != expected_id:
            raise PlanValidationError(f"{label} identifier is invalid")
        filename = f"shard-{expected_id:02d}.txt"
        if descriptor.get("path") != filename:
            raise PlanValidationError(f"{label} path is invalid")
        selected_count = _require_nonnegative_int(
            descriptor.get("selected_count"), label=f"{label} selected count"
        )
        selection_digest = descriptor.get("selection_sha256")
        if not isinstance(selection_digest, str) or not _SHA256_PATTERN.fullmatch(
            selection_digest
        ):
            raise PlanValidationError(f"{label} selection digest is invalid")
        estimated_load = descriptor.get("estimated_load_seconds")
        if (
            isinstance(estimated_load, bool)
            or not isinstance(estimated_load, (int, float))
            or not math.isfinite(float(estimated_load))
            or float(estimated_load) < 0
        ):
            raise PlanValidationError(f"{label} estimated load is invalid")

        names = _read_selection(plan_directory / filename, label=label)
        if len(names) != selected_count:
            raise PlanValidationError(f"{label} selected count does not match file")
        if _selection_digest(names) != selection_digest:
            raise PlanValidationError(f"{label} selection digest does not match file")
        selections.append(_ShardSelection(shard_id=expected_id, names=names))
        all_names.extend(names)

    if len(all_names) != len(set(all_names)):
        raise PlanValidationError("plan contains a duplicate mutant across shards")
    if len(all_names) != universe_count:
        raise PlanValidationError("plan universe count does not match selections")
    if _selection_digest(all_names) != universe_digest:
        raise PlanValidationError("plan universe digest does not match selections")
    return tuple(selections)


def build_execution_matrix(
    plan_directory: Path, *, expected_shards: int
) -> dict[str, object]:
    """Return a GitHub matrix containing exactly the plan's nonempty entries."""

    selections = _load_validated_plan(plan_directory, expected_shards=expected_shards)
    entries = [
        {"shard": selection.shard_id, "has_python": "true", "has_mutants": "true"}
        for selection in selections
        if selection.names
    ]
    if not entries:
        entries = [{"shard": 0, "has_python": "true", "has_mutants": "false"}]
    return {"include": entries}


def validate_matrix_entry(
    plan_directory: Path,
    *,
    expected_shards: int,
    shard_id: int,
    has_python: bool,
    has_mutants: bool,
) -> None:
    """Reject a consumer matrix entry unless it exactly matches the plan."""

    if not has_python:
        raise PlanValidationError("a mutmut plan entry must declare Python source")
    selections = _load_validated_plan(plan_directory, expected_shards=expected_shards)
    nonempty_ids = {selection.shard_id for selection in selections if selection.names}
    if has_mutants:
        if shard_id not in nonempty_ids:
            raise PlanValidationError("matrix shard is not selected for execution")
        return
    if nonempty_ids:
        raise PlanValidationError("matrix empty flag does not match the validated plan")
    if shard_id != 0:
        raise PlanValidationError("matrix empty sentinel must use shard 0")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("matrix", "validate-entry"):
        command_parser = commands.add_parser(command)
        command_parser.add_argument("--plan-directory", type=Path, required=True)
        command_parser.add_argument("--expected-shards", type=int, required=True)
    validate = commands.choices["validate-entry"]
    validate.add_argument("--shard-id", type=int, required=True)
    validate.add_argument("--has-python", choices=("true", "false"), required=True)
    validate.add_argument("--has-mutants", choices=("true", "false"), required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        if args.command == "matrix":
            print(
                json.dumps(
                    build_execution_matrix(
                        args.plan_directory, expected_shards=args.expected_shards
                    ),
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return
        validate_matrix_entry(
            args.plan_directory,
            expected_shards=args.expected_shards,
            shard_id=args.shard_id,
            has_python=args.has_python == "true",
            has_mutants=args.has_mutants == "true",
        )
    except PlanValidationError as error:
        raise SystemExit(
            f"mutmut execution matrix validation failed: {error}"
        ) from error


if __name__ == "__main__":
    main()
