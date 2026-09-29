"""Validate grouped mutmut execution budgets in one stats-loaded pass.

The incremental mutation producer owns a complete logical plan (currently 128
assignments) but executes it through fewer physical runners.  This helper binds
the emitted matrix to that plan, materializes every exact group in memory, and
checks both the logical assignments and their coalesced physical groups against
the same conservative timeout calculation.  It intentionally loads the merged
stats once: invoking ``mutmut_shard_budget.py`` separately for every logical
and physical shard would add avoidable producer latency while providing no
stronger evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# The CI workflow invokes this file directly (like the other mutation helpers),
# while unit tests import it as ``scripts.validate_mutmut_group_budgets``.  Make
# both entry points resolve sibling ``scripts`` modules without relying on the
# caller's current-directory import path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mutmut_shard_budget import (
    ShardBudget,
    _load_stats,
    calculate_shard_budget,
)
from scripts.mutmut_shard_matrix import (
    PlanValidationError,
    build_execution_groups,
    build_execution_groups_matrix,
    resolve_execution_group,
)


class GroupBudgetValidationError(ValueError):
    """Raised when grouped mutation evidence cannot be trusted."""


def _require_int(value: object, *, label: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GroupBudgetValidationError(f"{label} must be an integer >= {minimum}")
    return value


def _calculate_budget(
    selected_names: tuple[str, ...],
    tests_by_function: dict[str, list[str]],
    durations: dict[str, float],
    *,
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_and_startup_reserve_seconds: int,
) -> ShardBudget:
    try:
        return calculate_shard_budget(
            selected_names,
            tests_by_function,
            durations,
            max_children=max_children,
            control_cycle_reserve_seconds=control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=metadata_and_startup_reserve_seconds,
        )
    except (TypeError, ValueError) as error:
        raise GroupBudgetValidationError(str(error)) from error


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GroupBudgetValidationError(f"{label} is missing or unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GroupBudgetValidationError(f"{label} is invalid") from error
    if not isinstance(payload, dict):
        raise GroupBudgetValidationError(f"{label} must be a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    if path.is_symlink():
        raise GroupBudgetValidationError(
            f"output manifest is an unsafe symlink: {path}"
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as error:
        raise GroupBudgetValidationError(
            f"unable to write output manifest {path}"
        ) from error


def validate_group_budgets(
    *,
    matrix_path: Path,
    plan_directory: Path,
    stats_path: Path,
    output_manifest: Path,
    expected_shards: int,
    target_groups: int,
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_startup_reserve_seconds: int,
    max_timeout_seconds: int,
) -> dict[str, Any]:
    """Validate the matrix topology and all logical/physical timeout budgets."""

    expected_shards = _require_int(
        expected_shards, label="expected shard count", minimum=1
    )
    target_groups = _require_int(
        target_groups, label="target physical group count", minimum=1
    )
    max_children = _require_int(max_children, label="max children", minimum=1)
    control_cycle_reserve_seconds = _require_int(
        control_cycle_reserve_seconds,
        label="control-cycle reserve",
        minimum=1,
    )
    metadata_startup_reserve_seconds = _require_int(
        metadata_startup_reserve_seconds,
        label="metadata/startup reserve",
        minimum=0,
    )
    max_timeout_seconds = _require_int(
        max_timeout_seconds, label="maximum timeout", minimum=1
    )

    actual_matrix = _read_json_object(matrix_path, label="mutation matrix")
    try:
        expected_matrix = build_execution_groups_matrix(
            plan_directory,
            expected_shards=expected_shards,
            target_groups=target_groups,
        )
    except PlanValidationError as error:
        raise GroupBudgetValidationError(str(error)) from error
    if actual_matrix != expected_matrix:
        raise GroupBudgetValidationError(
            "mutation matrix does not match the validated logical plan topology"
        )

    topology = build_execution_groups(
        plan_directory,
        expected_shards=expected_shards,
        target_groups=target_groups,
    )
    groups = topology.get("groups")
    if not isinstance(groups, list):  # pragma: no cover - internal contract
        raise GroupBudgetValidationError("validated execution topology is invalid")

    # An empty Python scope has one explicit sentinel and no stats are needed.
    if not groups:
        _write_json(
            output_manifest,
            {
                "schema_version": 1,
                "expected_shards": expected_shards,
                "target_groups": target_groups,
                "group_count": 0,
                "logical_nonempty_count": 0,
                "max_timeout_seconds": max_timeout_seconds,
                "groups": [],
            },
        )
        return {
            "group_count": 0,
            "logical_nonempty_count": 0,
        }

    try:
        tests_by_function, durations = _load_stats(stats_path)
    except (OSError, UnicodeError, ValueError) as error:
        raise GroupBudgetValidationError(str(error)) from error

    # Build a one-logical-shard topology once.  It gives us an exact source
    # descriptor for every nonempty assignment without repeatedly rebuilding
    # the same plan inside the physical-group loop.
    logical_topology = build_execution_groups(
        plan_directory,
        expected_shards=expected_shards,
        target_groups=expected_shards,
    )
    logical_sources: dict[int, dict[str, Any]] = {}
    logical_groups = logical_topology.get("groups")
    if not isinstance(logical_groups, list):  # pragma: no cover - internal contract
        raise GroupBudgetValidationError("logical execution topology is invalid")
    for item in logical_groups:
        if not isinstance(item, dict):  # pragma: no cover - internal contract
            raise GroupBudgetValidationError("logical group descriptor is invalid")
        logical_ids = item.get("logical_shards")
        if not isinstance(logical_ids, list) or len(logical_ids) != 1:
            raise GroupBudgetValidationError(
                "logical execution topology did not preserve one-shard entries"
            )
        shard_id = logical_ids[0]
        if not isinstance(shard_id, int) or isinstance(shard_id, bool):
            raise GroupBudgetValidationError("logical shard identifier is invalid")
        logical_sources[shard_id] = item

    group_reports: list[dict[str, Any]] = []
    seen_logical_ids: set[int] = set()
    for raw_group in groups:
        if not isinstance(raw_group, dict):  # pragma: no cover - internal contract
            raise GroupBudgetValidationError("validated group descriptor is invalid")
        try:
            names = resolve_execution_group(
                plan_directory,
                expected_shards=expected_shards,
                group=raw_group,
            )
        except PlanValidationError as error:
            raise GroupBudgetValidationError(str(error)) from error
        logical_ids = raw_group.get("logical_shards")
        if not isinstance(logical_ids, list) or not all(
            isinstance(shard_id, int) and not isinstance(shard_id, bool)
            for shard_id in logical_ids
        ):
            raise GroupBudgetValidationError("validated logical shard IDs are invalid")
        if seen_logical_ids.intersection(logical_ids):
            raise GroupBudgetValidationError("logical shard appears in multiple groups")
        seen_logical_ids.update(logical_ids)

        # Validate every logical assignment as well as the coalesced physical
        # group.  The stats mapping is already in memory, so this is cheap and
        # preserves a complete budget audit without repeated JSON parsing.
        logical_reports: list[dict[str, int]] = []
        for shard_id in logical_ids:
            logical_source = logical_sources.get(shard_id)
            if logical_source is None:
                raise GroupBudgetValidationError(
                    f"logical shard {shard_id} is missing from the complete plan"
                )
            try:
                logical_names = resolve_execution_group(
                    plan_directory,
                    expected_shards=expected_shards,
                    group=logical_source,
                )
            except PlanValidationError as error:
                raise GroupBudgetValidationError(str(error)) from error
            logical_budget = _calculate_budget(
                logical_names,
                tests_by_function,
                durations,
                max_children=max_children,
                control_cycle_reserve_seconds=control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=metadata_startup_reserve_seconds,
            )
            if logical_budget.outer_timeout_seconds > max_timeout_seconds:
                raise GroupBudgetValidationError(
                    "logical shard budget exceeds configured maximum: "
                    f"shard {shard_id} requires "
                    f"{logical_budget.outer_timeout_seconds}s, maximum "
                    f"{max_timeout_seconds}s"
                )
            logical_reports.append(
                {
                    "shard_id": shard_id,
                    "selected_count": logical_budget.selected_count,
                    "outer_timeout_seconds": logical_budget.outer_timeout_seconds,
                    "total_wall_cap_seconds": logical_budget.total_wall_cap_seconds,
                }
            )

        group_budget = _calculate_budget(
            names,
            tests_by_function,
            durations,
            max_children=max_children,
            control_cycle_reserve_seconds=control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=metadata_startup_reserve_seconds,
        )
        if group_budget.outer_timeout_seconds > max_timeout_seconds:
            raise GroupBudgetValidationError(
                "physical group budget exceeds configured maximum: "
                f"group {raw_group.get('group_id')} requires "
                f"{group_budget.outer_timeout_seconds}s, maximum "
                f"{max_timeout_seconds}s"
            )
        group_reports.append(
            {
                "group_id": raw_group["group_id"],
                "logical_shards": logical_ids,
                "selected_count": group_budget.selected_count,
                "outer_timeout_seconds": group_budget.outer_timeout_seconds,
                "total_wall_cap_seconds": group_budget.total_wall_cap_seconds,
                "logical_budgets": logical_reports,
            }
        )

    expected_logical_count = sum(
        len(group.get("logical_shards", []))
        for group in groups
        if isinstance(group, dict)
    )
    if len(seen_logical_ids) != expected_logical_count:
        raise GroupBudgetValidationError("logical shard inventory is incomplete")

    report: dict[str, Any] = {
        "schema_version": 1,
        "expected_shards": expected_shards,
        "target_groups": target_groups,
        "group_count": len(group_reports),
        "logical_nonempty_count": len(seen_logical_ids),
        "max_timeout_seconds": max_timeout_seconds,
        "groups": group_reports,
    }
    _write_json(output_manifest, report)
    return {
        "group_count": len(group_reports),
        "logical_nonempty_count": len(seen_logical_ids),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-file", type=Path, required=True)
    parser.add_argument("--plan-directory", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--expected-shards", type=int, required=True)
    parser.add_argument("--target-groups", type=int, required=True)
    parser.add_argument("--max-children", type=int, required=True)
    parser.add_argument("--control-cycle-reserve-seconds", type=int, required=True)
    parser.add_argument("--metadata-startup-reserve-seconds", type=int, required=True)
    parser.add_argument("--max-timeout-seconds", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        summary = validate_group_budgets(
            matrix_path=args.matrix_file,
            plan_directory=args.plan_directory,
            stats_path=args.stats,
            output_manifest=args.output_manifest,
            expected_shards=args.expected_shards,
            target_groups=args.target_groups,
            max_children=args.max_children,
            control_cycle_reserve_seconds=args.control_cycle_reserve_seconds,
            metadata_startup_reserve_seconds=args.metadata_startup_reserve_seconds,
            max_timeout_seconds=args.max_timeout_seconds,
        )
    except (GroupBudgetValidationError, OSError, UnicodeError, ValueError) as error:
        raise SystemExit(
            f"ERROR: unable to validate grouped mutmut budgets: {error}"
        ) from error
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
