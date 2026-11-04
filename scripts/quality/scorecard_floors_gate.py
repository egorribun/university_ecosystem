"""Gate OpenSSF Scorecard results on per-check score floors (AUD-381).

The gate reads the native Scorecard JSON result and compares each gated check
with the floor recorded in ``quality/scorecard-floors.json``.  It does not use
the aggregate score.  A gated check that is missing, not applicable (-1), or
below its floor fails the job.  Published-only checks are listed in the job
summary and never fail it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
MIN_SCORE = 0
MAX_SCORE = 10
NOT_APPLICABLE = -1
# Initial floors were measured in the policy's recorded Scorecard run. Changes
# must also be compared with the trusted previous policy via --previous-floors.
MINIMUM_GATED_FLOORS = {
    "Dangerous-Workflow": 10,
    "Token-Permissions": 10,
    "Pinned-Dependencies": 9,
    "Vulnerabilities": 0,
    "Binary-Artifacts": 8,
    "SAST": 9,
}


class GateError(ValueError):
    """Raised when the policy or the scorecard evidence is unusable."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GateError(f"JSON object contains duplicate key {key}")
        result[key] = value
    return result


def _is_score(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (value == NOT_APPLICABLE or MIN_SCORE <= value <= MAX_SCORE)
    )


def load_floors(path: Path) -> tuple[dict[str, int], list[str]]:
    """Return the gated floors and the published-only check names."""

    try:
        policy = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("Scorecard floor policy is unreadable") from error
    if (
        not isinstance(policy, dict)
        or type(policy.get("schema_version")) is not int
        or policy["schema_version"] != SCHEMA_VERSION
    ):
        raise GateError("Scorecard floor policy schema_version must be 1")

    gated = policy.get("gated_checks")
    if not isinstance(gated, dict) or set(gated) != set(MINIMUM_GATED_FLOORS):
        raise GateError("Scorecard floor policy must define the six key gated_checks")
    for name, floor in gated.items():
        if not isinstance(name, str) or not _is_score(floor) or floor == NOT_APPLICABLE:
            raise GateError("Scorecard floors must be integers from 0 to 10")
        if floor < MINIMUM_GATED_FLOORS[name]:
            raise GateError(f"Scorecard {name} floor is below its initial minimum")

    published = policy.get("published_only_checks")
    if not isinstance(published, list) or not all(
        isinstance(name, str) and bool(name.strip()) for name in published
    ):
        raise GateError("published_only_checks must be a list of check names")
    if len(set(published)) != len(published):
        raise GateError("published_only_checks must not contain duplicates")
    if set(published) & set(gated):
        raise GateError("a check cannot be both gated and published-only")
    return dict(gated), list(published)


def load_scores(path: Path, expected_commit: str) -> dict[str, int]:
    """Return check scores only when the native result matches the event commit."""

    if not isinstance(expected_commit, str) or not re.fullmatch(
        r"[0-9a-f]{40}", expected_commit
    ):
        raise GateError("Expected Scorecard commit must be a full lowercase SHA")

    try:
        result = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("Scorecard JSON result is unreadable") from error
    if not isinstance(result, dict) or not isinstance(result.get("checks"), list):
        raise GateError("Scorecard JSON result must contain a checks list")
    repo = result.get("repo")
    if not isinstance(repo, dict) or repo.get("commit") != expected_commit:
        raise GateError("Scorecard JSON result commit does not match the event commit")

    scores: dict[str, int] = {}
    for check in result["checks"]:
        if not isinstance(check, dict):
            raise GateError("Scorecard check entries must be objects")
        name = check.get("name")
        score = check.get("score")
        if not isinstance(name, str) or not name:
            raise GateError("Scorecard check entries must carry a name")
        if not isinstance(score, int) or not _is_score(score):
            raise GateError(f"Scorecard check {name} has an invalid score")
        if name in scores:
            raise GateError(f"Scorecard check {name} appears more than once")
        scores[name] = score
    return scores


def evaluate(
    floors: dict[str, int],
    published: list[str],
    scores: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Return (failure messages, summary lines) for the gate decision."""

    failures: list[str] = []
    summary = [
        "### OpenSSF Scorecard floors",
        "",
        "| Check | Score | Floor | Gate |",
        "| --- | ---: | ---: | --- |",
    ]
    for name in sorted(floors):
        floor = floors[name]
        score = scores.get(name)
        if score is None or score == NOT_APPLICABLE:
            failures.append(f"{name} has no applicable score; the gate is unknown")
            shown = "n/a"
        elif score < floor:
            failures.append(f"{name} scored {score}, below its floor of {floor}")
            shown = str(score)
        else:
            shown = str(score)
        summary.append(f"| {name} | {shown} | {floor} | gated |")
    for name in sorted(published):
        shown = str(scores[name]) if name in scores else "n/a"
        summary.append(f"| {name} | {shown} | - | published only |")
    return failures, summary


def _write_summary(summary_path: Path | None, lines: list[str]) -> None:
    if summary_path is None:
        return
    with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def run_gate(
    floors_path: Path,
    result_path: Path,
    summary_path: Path | None,
    expected_commit: str,
) -> int:
    try:
        floors, published = load_floors(floors_path)
        scores = load_scores(result_path, expected_commit)
    except GateError as error:
        print(f"::error::{error}; the scan result is unknown.", file=sys.stderr)
        return 1

    failures, summary = evaluate(floors, published, scores)
    _write_summary(summary_path, summary)
    if failures:
        for failure in failures:
            print(f"::error::Scorecard {failure}.", file=sys.stderr)
        return 1
    print("Scorecard gated checks meet their recorded floors.")
    return 0


def validate_result_source(result_path: Path, expected_commit: str) -> int:
    """Validate the native result before a separate SARIF report is published."""

    try:
        load_scores(result_path, expected_commit)
    except GateError as error:
        print(f"::error::{error}; the scan result is unknown.", file=sys.stderr)
        return 1
    print("Scorecard JSON result matches the event commit.")
    return 0


def run_ratchet(floors_path: Path, previous_path: Path) -> int:
    """Reject floor reductions against the policy from a trusted base commit."""

    try:
        current, _ = load_floors(floors_path)
        previous, _ = load_floors(previous_path)
    except GateError as error:
        print(
            f"::error::{error}; the Scorecard floor ratchet is unknown.",
            file=sys.stderr,
        )
        return 1

    failures = [
        f"{name} floor decreased from {previous[name]} to {current[name]}"
        for name in sorted(previous)
        if current[name] < previous[name]
    ]
    for failure in failures:
        print(f"::error::Scorecard {failure}.", file=sys.stderr)
    if failures:
        return 1
    print("Scorecard floors have not decreased from the previous policy.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("floors", type=Path, help="quality/scorecard-floors.json")
    parser.add_argument(
        "result", type=Path, nargs="?", help="Scorecard native JSON result"
    )
    parser.add_argument(
        "--previous-floors",
        type=Path,
        help="trusted previous policy for the floor ratchet",
    )
    parser.add_argument("--summary-file", type=Path, default=None)
    parser.add_argument(
        "--expected-commit", help="full event commit SHA for scan evidence"
    )
    parser.add_argument("--validate-source-only", action="store_true")
    arguments = parser.parse_args(argv)
    if (arguments.result is None) == (arguments.previous_floors is None):
        parser.error("provide exactly one result or --previous-floors")
    if arguments.previous_floors is not None:
        if (
            arguments.summary_file is not None
            or arguments.expected_commit is not None
            or arguments.validate_source_only
        ):
            parser.error("scan result options cannot be used when checking the ratchet")
        return run_ratchet(arguments.floors, arguments.previous_floors)
    if arguments.expected_commit is None:
        parser.error("--expected-commit is required when checking a scan result")
    if arguments.validate_source_only:
        if arguments.summary_file is not None:
            parser.error("--summary-file cannot be used with --validate-source-only")
        return validate_result_source(arguments.result, arguments.expected_commit)
    return run_gate(
        arguments.floors,
        arguments.result,
        arguments.summary_file,
        arguments.expected_commit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
