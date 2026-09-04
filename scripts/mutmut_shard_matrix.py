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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_LOAD_SCALE = 1_000_000


class PlanValidationError(ValueError):
    """Raised when a mutmut plan cannot safely drive the execution matrix."""


@dataclass(frozen=True, slots=True)
class _ShardSelection:
    shard_id: int
    names: tuple[str, ...]
    estimated_load_seconds: float
    estimated_load_micros: int


@dataclass(frozen=True, slots=True)
class _ValidatedPlan:
    selections: tuple[_ShardSelection, ...]
    universe_count: int
    universe_sha256: str


def _selection_digest(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def _group_digest(selections: Iterable[_ShardSelection]) -> str:
    """Return a stable digest for a logical-shard grouping.

    The digest binds the physical group to both its logical shard IDs and the
    exact per-shard selections.  A consumer can therefore reject a descriptor
    whose IDs are replayed with a different canonical plan.
    """

    canonical = "\n".join(
        f"{selection.shard_id}\t{_selection_digest(selection.names)}"
        for selection in selections
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_nonnegative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlanValidationError(f"{label} must be a non-negative integer")
    return value


def _seconds_to_micros(value: object, *, label: str) -> int:
    """Convert a finite JSON duration to a transport-safe integer.

    GitHub expression interpolation serializes matrix numbers through a
    decimal representation before exposing them to the shell.  Comparing the
    original binary float therefore made an otherwise intact descriptor fail
    closed.  The plan still keeps its human-readable seconds estimate, but the
    matrix contract uses rounded microseconds so every producer/consumer sees
    the same exact integer and no tolerance can broaden the selection.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanValidationError(f"{label} is invalid")
    # ``float(10**400)`` raises ``OverflowError`` instead of returning an
    # infinity.  Keep that parser/validation boundary fail-closed by mapping
    # every non-finite or unrepresentable numeric input to the domain error
    # rather than leaking a builtin conversion exception to callers.
    try:
        numeric_value = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise PlanValidationError(f"{label} is invalid") from error
    if not math.isfinite(numeric_value) or numeric_value < 0:
        raise PlanValidationError(f"{label} is invalid")
    try:
        scaled = Decimal(str(value)) * _LOAD_SCALE
        micros = int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise PlanValidationError(f"{label} is invalid") from error
    if micros < 0:
        raise PlanValidationError(f"{label} is invalid")
    return micros


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
) -> _ValidatedPlan:
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
        estimated_load_micros = _seconds_to_micros(
            estimated_load, label=f"{label} estimated load"
        )

        names = _read_selection(plan_directory / filename, label=label)
        if len(names) != selected_count:
            raise PlanValidationError(f"{label} selected count does not match file")
        if _selection_digest(names) != selection_digest:
            raise PlanValidationError(f"{label} selection digest does not match file")
        selections.append(
            _ShardSelection(
                shard_id=expected_id,
                names=names,
                estimated_load_seconds=float(estimated_load),
                estimated_load_micros=estimated_load_micros,
            )
        )
        all_names.extend(names)

    if len(all_names) != len(set(all_names)):
        raise PlanValidationError("plan contains a duplicate mutant across shards")
    if len(all_names) != universe_count:
        raise PlanValidationError("plan universe count does not match selections")
    if _selection_digest(all_names) != universe_digest:
        raise PlanValidationError("plan universe digest does not match selections")
    return _ValidatedPlan(
        selections=tuple(selections),
        universe_count=universe_count,
        universe_sha256=universe_digest,
    )


def build_execution_matrix(
    plan_directory: Path, *, expected_shards: int
) -> dict[str, object]:
    """Return a GitHub matrix containing exactly the plan's nonempty entries."""

    selections = _load_validated_plan(
        plan_directory, expected_shards=expected_shards
    ).selections
    entries = [
        {"shard": selection.shard_id, "has_python": "true", "has_mutants": "true"}
        for selection in selections
        if selection.names
    ]
    if not entries:
        entries = [{"shard": 0, "has_python": "true", "has_mutants": "false"}]
    return {"include": entries}


def build_execution_groups(
    plan_directory: Path, *, expected_shards: int, target_groups: int = 64
) -> dict[str, object]:
    """Coalesce validated logical shards into bounded physical executions.

    The fixed-width plan remains the source of truth: this function only
    describes a deterministic execution topology over its nonempty entries.
    Each group carries the logical shard IDs and their canonical file names so
    a consumer can read the exact mutant names without re-planning or using a
    glob.  Empty logical shards are not emitted and cannot hide a mutant.
    """

    if (
        isinstance(target_groups, bool)
        or not isinstance(target_groups, int)
        or target_groups < 1
    ):
        raise PlanValidationError("target physical group count must be positive")

    plan = _load_validated_plan(plan_directory, expected_shards=expected_shards)
    nonempty = [selection for selection in plan.selections if selection.names]
    if not nonempty:
        groups: list[dict[str, object]] = []
    else:
        physical_count = min(target_groups, len(nonempty))
        bins: list[list[_ShardSelection]] = [[] for _ in range(physical_count)]
        loads = [0] * physical_count
        # Place the most expensive logical shards first, then use the least
        # loaded physical bin.  Stable IDs make every tie deterministic.
        for selection in sorted(
            nonempty,
            key=lambda item: (-item.estimated_load_micros, item.shard_id),
        ):
            bin_index = min(
                range(physical_count), key=lambda index: (loads[index], index)
            )
            bins[bin_index].append(selection)
            loads[bin_index] += selection.estimated_load_micros

        ordered_bins = sorted(
            (
                tuple(sorted(bin_items, key=lambda item: item.shard_id))
                for bin_items in bins
            ),
            key=lambda items: items[0].shard_id,
        )
        groups = []
        for group_id, selections in enumerate(ordered_bins, start=1):
            names = tuple(name for selection in selections for name in selection.names)
            groups.append(
                {
                    "group_id": group_id,
                    "logical_shards": [selection.shard_id for selection in selections],
                    "selection_files": [
                        f"shard-{selection.shard_id:02d}.txt"
                        for selection in selections
                    ],
                    "selected_count": len(names),
                    "selection_sha256": _selection_digest(names),
                    "group_sha256": _group_digest(selections),
                    "estimated_load_micros": sum(
                        selection.estimated_load_micros for selection in selections
                    ),
                }
            )

    return {
        "schema_version": 1,
        "expected_shards": expected_shards,
        "target_groups": target_groups,
        "group_count": len(groups),
        "universe_count": plan.universe_count,
        "universe_sha256": plan.universe_sha256,
        "groups": groups,
    }


def build_execution_groups_matrix(
    plan_directory: Path, *, expected_shards: int, target_groups: int = 64
) -> dict[str, object]:
    """Return a dynamic matrix over validated physical execution groups.

    The returned descriptors intentionally carry the complete logical-group
    metadata.  Consumers validate that descriptor against the fixed plan
    before concatenating any mutant IDs, so the matrix is only a transport
    optimization and never an alternate source of mutation scope.
    """

    topology = build_execution_groups(
        plan_directory,
        expected_shards=expected_shards,
        target_groups=target_groups,
    )
    groups = topology["groups"]
    if not isinstance(groups, list):  # pragma: no cover - internal contract
        raise PlanValidationError("execution topology groups are invalid")
    if not groups:
        return {
            "include": [
                {
                    "group_id": 0,
                    "logical_shards": [],
                    "selection_files": [],
                    "selected_count": 0,
                    "selection_sha256": "",
                    "group_sha256": "",
                    "estimated_load_micros": 0,
                    "has_python": "true",
                    "has_mutants": "false",
                }
            ]
        }
    return {
        "include": [
            {
                **group,
                "has_python": "true",
                "has_mutants": "true",
            }
            for group in groups
        ]
    }


def resolve_execution_group(
    plan_directory: Path,
    *,
    expected_shards: int,
    group: Mapping[str, Any],
) -> tuple[str, ...]:
    """Validate one physical-group descriptor and return exact mutant IDs.

    Consumers pass the JSON descriptor emitted by
    :func:`build_execution_groups`.  The canonical plan is loaded and checked
    again before IDs are resolved, so a stale or tampered matrix cannot broaden
    the selected population.
    """

    if not isinstance(group, Mapping):
        raise PlanValidationError("execution group descriptor must be an object")
    group_id = group.get("group_id")
    if isinstance(group_id, bool) or not isinstance(group_id, int) or group_id < 1:
        raise PlanValidationError("execution group identifier is invalid")

    logical_ids = group.get("logical_shards")
    if not isinstance(logical_ids, list) or not logical_ids:
        raise PlanValidationError("execution group logical shards are invalid")
    if any(
        isinstance(shard_id, bool)
        or not isinstance(shard_id, int)
        or shard_id < 1
        or shard_id > expected_shards
        for shard_id in logical_ids
    ):
        raise PlanValidationError("execution group logical shard ID is invalid")
    if logical_ids != sorted(logical_ids) or len(logical_ids) != len(set(logical_ids)):
        raise PlanValidationError(
            "execution group logical shard IDs must be sorted and unique"
        )

    expected_files = [f"shard-{shard_id:02d}.txt" for shard_id in logical_ids]
    if group.get("selection_files") != expected_files:
        raise PlanValidationError("execution group selection files are invalid")

    plan = _load_validated_plan(plan_directory, expected_shards=expected_shards)
    by_id = {selection.shard_id: selection for selection in plan.selections}
    selections = tuple(by_id[shard_id] for shard_id in logical_ids)
    if any(not selection.names for selection in selections):
        raise PlanValidationError("execution group contains an empty logical shard")
    names = tuple(name for selection in selections for name in selection.names)

    selected_count = group.get("selected_count")
    if (
        isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or selected_count != len(names)
        or selected_count < 1
    ):
        raise PlanValidationError("execution group selected count is invalid")

    selection_digest = group.get("selection_sha256")
    if not isinstance(selection_digest, str) or not _SHA256_PATTERN.fullmatch(
        selection_digest
    ):
        raise PlanValidationError("execution group selection digest is invalid")
    if _selection_digest(names) != selection_digest:
        raise PlanValidationError("execution group selection digest does not match")

    group_digest = group.get("group_sha256")
    if not isinstance(group_digest, str) or not _SHA256_PATTERN.fullmatch(group_digest):
        raise PlanValidationError("execution group digest is invalid")
    if _group_digest(selections) != group_digest:
        raise PlanValidationError("execution group digest does not match")

    estimated_load = group.get("estimated_load_micros")
    expected_load = sum(selection.estimated_load_micros for selection in selections)
    if (
        not isinstance(estimated_load, int)
        or isinstance(estimated_load, bool)
        or estimated_load < 0
    ):
        raise PlanValidationError("execution group estimated load is invalid")
    if estimated_load != expected_load:
        raise PlanValidationError(
            "execution group estimated load does not match logical shards"
        )
    return names


def validate_execution_group_descriptor(
    plan_directory: Path,
    *,
    expected_shards: int,
    target_groups: int,
    group_id: int,
    logical_shards: str,
    selected_count: int,
    selection_sha256: str,
    group_sha256: str,
    estimated_load_micros: int,
) -> tuple[str, ...]:
    """Validate a shell-transported matrix group and return exact mutant IDs."""

    if not isinstance(logical_shards, str) or not logical_shards:
        raise PlanValidationError("execution group logical shards are invalid")
    raw_ids = logical_shards.split(",")
    if any(not re.fullmatch(r"[1-9][0-9]*", value) for value in raw_ids):
        raise PlanValidationError("execution group logical shards are invalid")
    try:
        logical_ids = [int(value) for value in raw_ids]
    except ValueError as error:
        raise PlanValidationError(
            "execution group logical shards are invalid"
        ) from error
    if logical_ids != sorted(logical_ids) or len(logical_ids) != len(set(logical_ids)):
        raise PlanValidationError("execution group logical shards are invalid")
    descriptor = {
        "group_id": group_id,
        "logical_shards": logical_ids,
        "selection_files": [f"shard-{shard_id:02d}.txt" for shard_id in logical_ids],
        "selected_count": selected_count,
        "selection_sha256": selection_sha256,
        "group_sha256": group_sha256,
        "estimated_load_micros": estimated_load_micros,
    }
    topology = build_execution_groups(
        plan_directory,
        expected_shards=expected_shards,
        target_groups=target_groups,
    )
    groups = topology["groups"]
    if not isinstance(groups, list):  # pragma: no cover - internal contract
        raise PlanValidationError("execution topology groups are invalid")
    expected = next(
        (
            group
            for group in groups
            if isinstance(group, dict) and group.get("group_id") == group_id
        ),
        None,
    )
    if expected != descriptor:
        raise PlanValidationError("execution group membership or digest does not match")
    return resolve_execution_group(
        plan_directory,
        expected_shards=expected_shards,
        group=descriptor,
    )


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
    selections = _load_validated_plan(
        plan_directory, expected_shards=expected_shards
    ).selections
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
    for command in ("matrix", "groups", "validate-entry", "validate-group"):
        command_parser = commands.add_parser(command)
        command_parser.add_argument("--plan-directory", type=Path, required=True)
        command_parser.add_argument("--expected-shards", type=int, required=True)
        if command == "groups":
            command_parser.add_argument("--target-groups", type=int, default=64)
    validate = commands.choices["validate-entry"]
    validate.add_argument("--shard-id", type=int, required=True)
    validate.add_argument("--has-python", choices=("true", "false"), required=True)
    validate.add_argument("--has-mutants", choices=("true", "false"), required=True)
    group = commands.choices["validate-group"]
    group.add_argument("--target-groups", type=int, required=True)
    group.add_argument("--group-id", type=int, required=True)
    group.add_argument("--logical-shards", required=True)
    group.add_argument("--selected-count", type=int, required=True)
    group.add_argument("--selection-sha256", required=True)
    group.add_argument("--group-sha256", required=True)
    group.add_argument("--estimated-load-micros", type=int, required=True)
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
        if args.command == "groups":
            print(
                json.dumps(
                    build_execution_groups_matrix(
                        args.plan_directory,
                        expected_shards=args.expected_shards,
                        target_groups=args.target_groups,
                    ),
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return
        if args.command == "validate-group":
            validate_execution_group_descriptor(
                args.plan_directory,
                expected_shards=args.expected_shards,
                target_groups=args.target_groups,
                group_id=args.group_id,
                logical_shards=args.logical_shards,
                selected_count=args.selected_count,
                selection_sha256=args.selection_sha256,
                group_sha256=args.group_sha256,
                estimated_load_micros=args.estimated_load_micros,
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
