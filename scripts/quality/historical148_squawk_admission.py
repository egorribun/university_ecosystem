"""Owner-activated finite admission for historical revision 148642dd1207.

The 2026-10-31 owner decision admits exactly the 37 diagnostic Squawk findings in
quality/historical148-squawk-policy.json: 13 for the ordinary live parent-to-148
scratch render and 24 for the populated instrumented expanded DDL control. Matching
is exact by scenario SQL digest, rule and location. Any new, changed, missing,
duplicate or extra finding fails closed. Raw Squawk exits must be the recorded
failures and are reported, never converted into scanner success.

This module only reads files that the CI step already produced with the verified
Squawk binary. It executes nothing. The migration is bound by the Git object id that
the workflow computes with `git hash-object -- <path>` over the working-tree file and
passes as an argument; this module compares it with the policy and computes no digest
of its own. An admission is not permission for any other migration, proof that a
target database is empty, or deployment acceptance. The pure recognizer in
validate_historical148_squawk.py stays free of file access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

POLICY_SCHEMA = "ue-historical148-policy-v1"
ACTIVE_STATUS = "owner-activated-finite"
OWNER = "egorribun"
DECISION_DATE = "2026-10-31"
SCOPE = "new-empty-mvp-only"
EXPIRES_AT = "2026-11-13T00:00:00Z"
EXPIRES_INSTANT = datetime(2026, 11, 13, tzinfo=UTC)
PRODUCER_JOB = "alembic-migrations"
MIGRATION_PATH = "alembic/versions/148642dd1207_fix_missing_tables.py"
MIGRATION_REVISION = "148642dd1207"
MIGRATION_PARENT = "f7aa476e968a"
SCANNER_VERSION = "squawk 2.67.0"
SCENARIO_NAMES = ("ordinary-parent-live", "expanded-populated-diagnostic")
EXPECTED_COUNTS = (13, 24)
RAW_EXIT = 1
POLICY_LIMIT = 32768
SQL_LIMIT = 65536
OUTPUT_LIMIT = 131072


class AdmissionError(ValueError):
    """Every condition that must fail the Alembic job closed."""


class ScenarioEvidence(NamedTuple):
    """One rendered SQL input and the recorded outcome of its two Squawk runs.

    The raw exit comes from the human-readable gate; the JSON exit and the stderr
    file come from the diagnostic JSON run over the same SQL path.
    """

    sql_path: str
    raw_exit: int
    json_path: str
    json_exit: int
    stderr_path: str


def _reject_constant(_name: str) -> None:
    raise ValueError("non-finite JSON number")


def _reject_float(_text: str) -> None:
    raise ValueError("fractional JSON number")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _strict_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise AdmissionError(f"{label} is malformed") from error


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(path: Path, limit: int, *, minimum: int = 1) -> bytes:
    absolute = path.absolute()
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise AdmissionError("symlink input is forbidden")
    if not absolute.is_file():
        raise AdmissionError("input must be a regular file")
    with absolute.open("rb") as source:
        data = source.read(limit + 1)
    if not minimum <= len(data) <= limit:
        raise AdmissionError("input is empty or exceeds its byte limit")
    return data


def _validate_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise AdmissionError("policy root is not an object")
    if policy.get("schema") != POLICY_SCHEMA:
        raise AdmissionError("policy schema is invalid")
    if policy.get("status") != ACTIVE_STATUS:
        raise AdmissionError("policy is not owner-activated")
    if policy.get("owner") != OWNER:
        raise AdmissionError("policy owner is invalid")
    if policy.get("execution_scope") != SCOPE:
        raise AdmissionError("policy scope is invalid")
    if policy.get("expires_at") != EXPIRES_AT:
        raise AdmissionError("policy expiry is invalid")
    activation = policy.get("activation")
    if not (
        isinstance(activation, dict)
        and activation.get("decision_date") == DECISION_DATE
        and activation.get("owner") == OWNER
        and activation.get("expires_at") == EXPIRES_AT
    ):
        raise AdmissionError("activation record does not match the owner decision")
    migration = policy.get("migration")
    if migration != {
        "path": MIGRATION_PATH,
        "revision": MIGRATION_REVISION,
        "parent": MIGRATION_PARENT,
    }:
        raise AdmissionError("migration pin is invalid")
    provenance = policy.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("producer_job") != PRODUCER_JOB
    ):
        raise AdmissionError("policy producer job is invalid")
    scanner = policy.get("scanner")
    if not (
        isinstance(scanner, dict)
        and scanner.get("version") == SCANNER_VERSION
        and isinstance(scanner.get("binary_sha256"), str)
        and isinstance(scanner.get("args"), list)
    ):
        raise AdmissionError("scanner pin is invalid")
    source_blobs = policy.get("source_blobs")
    if not (
        isinstance(source_blobs, dict)
        and isinstance(source_blobs.get(MIGRATION_PATH), str)
    ):
        raise AdmissionError("migration source pin is missing")
    scenarios = policy.get("scenarios")
    names = (
        [item.get("scenario") if isinstance(item, dict) else None for item in scenarios]
        if isinstance(scenarios, list)
        else []
    )
    if names != list(SCENARIO_NAMES):
        raise AdmissionError("scenario inventory is invalid")
    return policy


def _admit_scenario(
    policy_scenario: dict[str, Any],
    expected_count: int,
    evidence: ScenarioEvidence,
) -> int:
    name = policy_scenario["scenario"]
    if (
        type(evidence.raw_exit) is not int
        or evidence.raw_exit != RAW_EXIT
        or policy_scenario.get("raw_exit") != RAW_EXIT
    ):
        raise AdmissionError("raw Squawk exit is not the recorded failure")
    data = _read_regular(Path(evidence.sql_path), SQL_LIMIT)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AdmissionError("SQL input is not UTF-8") from error
    if len(data) != policy_scenario.get("sql_bytes") or (
        _sha256(data) != policy_scenario.get("sql_sha256")
    ):
        raise AdmissionError(f"{name} SQL digest does not match the policy")
    findings = policy_scenario.get("findings")
    if not isinstance(findings, list) or len(findings) != expected_count:
        raise AdmissionError(f"{name} policy inventory count is invalid")
    if type(evidence.json_exit) is not int or evidence.json_exit != RAW_EXIT:
        raise AdmissionError("JSON scan exit is not the recorded failure")
    if _read_regular(Path(evidence.stderr_path), OUTPUT_LIMIT, minimum=0):
        raise AdmissionError("scanner wrote diagnostics to stderr")
    rows = _strict_json(
        _read_regular(Path(evidence.json_path), OUTPUT_LIMIT), "scanner output"
    )
    if not isinstance(rows, list):
        raise AdmissionError("scanner output is not a list")
    live: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise AdmissionError("scanner row is not an object")
        if row.get("file") != evidence.sql_path:
            raise AdmissionError("warning location is not the scanned SQL")
        live[
            _canonical({key: value for key, value in row.items() if key != "file"})
        ] += 1
    if live != Counter(_canonical(finding) for finding in findings):
        raise AdmissionError(f"{name} warning inventory differs from the policy")
    return len(rows)


def admit(
    policy_bytes: bytes,
    *,
    migration_blob: str,
    scanner_sha256: str,
    scanner_version: str,
    scanner_args: tuple[str, ...],
    ordinary: ScenarioEvidence,
    expanded: ScenarioEvidence,
) -> str:
    """Return an admission message only for the exact recorded inventory.

    The expiry is read from the real UTC clock here. No caller supplies a clock.
    """
    if not 0 < len(policy_bytes) <= POLICY_LIMIT:
        raise AdmissionError("policy is empty or exceeds its byte limit")
    policy = _validate_policy(_strict_json(policy_bytes, "policy"))
    if datetime.now(UTC) >= EXPIRES_INSTANT:
        raise AdmissionError("policy has expired")
    if tuple(scanner_args) != tuple(policy["scanner"]["args"]):
        raise AdmissionError("scanner arguments do not match the policy")
    if migration_blob != policy["source_blobs"][MIGRATION_PATH]:
        raise AdmissionError(
            "migration source is not the unchanged historical revision"
        )
    if scanner_sha256 != policy["scanner"]["binary_sha256"]:
        raise AdmissionError("scanner binary digest does not match the policy")
    if scanner_version != SCANNER_VERSION:
        raise AdmissionError("scanner version does not match the policy")
    ordinary_count = _admit_scenario(
        policy["scenarios"][0], EXPECTED_COUNTS[0], ordinary
    )
    expanded_count = _admit_scenario(
        policy["scenarios"][1], EXPECTED_COUNTS[1], expanded
    )
    return (
        "AUD148 historical admission: exact owner-activated inventory matched "
        f"({ordinary_count} ordinary + {expanded_count} expanded warnings); "
        f"raw Squawk exits {ordinary.raw_exit}/{expanded.raw_exit} retained; "
        f"policy expires {EXPIRES_AT}; not scanner success or migration permission"
    )


def _evidence(options: argparse.Namespace, prefix: str) -> ScenarioEvidence:
    return ScenarioEvidence(
        sql_path=getattr(options, f"{prefix}_sql"),
        raw_exit=getattr(options, f"{prefix}_raw_exit"),
        json_path=getattr(options, f"{prefix}_json"),
        json_exit=getattr(options, f"{prefix}_json_exit"),
        stderr_path=getattr(options, f"{prefix}_stderr"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Admit the exact owner-activated historical-148 Squawk inventory."
    )
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--migration-blob", required=True)
    parser.add_argument("--scanner-sha256", required=True)
    parser.add_argument("--scanner-version", required=True)
    parser.add_argument("--exclude", action="append", default=[], dest="excluded_rules")
    for prefix in ("ordinary", "expanded"):
        parser.add_argument(f"--{prefix}-sql", required=True)
        parser.add_argument(f"--{prefix}-raw-exit", type=int, required=True)
        parser.add_argument(f"--{prefix}-json", required=True)
        parser.add_argument(f"--{prefix}-json-exit", type=int, required=True)
        parser.add_argument(f"--{prefix}-stderr", required=True)
    options = parser.parse_args(argv)
    if os.environ.get("GITHUB_JOB") != PRODUCER_JOB:
        print("AUD148 historical admission rejected: producer job is invalid")
        return 1
    scanner_args = tuple(
        value for rule in options.excluded_rules for value in ("--exclude", rule)
    )
    try:
        message = admit(
            _read_regular(options.policy, POLICY_LIMIT),
            migration_blob=options.migration_blob,
            scanner_sha256=options.scanner_sha256,
            scanner_version=options.scanner_version,
            scanner_args=scanner_args,
            ordinary=_evidence(options, "ordinary"),
            expanded=_evidence(options, "expanded"),
        )
    except AdmissionError as error:
        print(f"AUD148 historical admission rejected: {error}")
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
