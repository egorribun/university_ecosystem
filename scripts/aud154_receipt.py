"""Source-bound, allowlisted final Playwright receipt for AUD-154 only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts import fast_preflight

CASE_TITLES = {
    "aud154-sent-confirmation": (
        "a message is delivered, edited, and tombstoned in the other authenticated session"
    ),
    "aud154-enter-sent-confirmation": (
        "shows sent confirmation after the server accepts the message"
    ),
}
SOURCE_PATHS = (
    "frontend/tests/e2e-live/messenger-realtime.live.spec.ts",
    "frontend/src/components/messenger/ChatWindow.tsx",
    "frontend/tests/e2e-live/fixtures.ts",
    "frontend/playwright.live.config.ts",
    "frontend/scripts/live-aud154-reporter.mjs",
    "scripts/live_stand.py",
    "scripts/aud154_receipt.py",
    ".github/workflows/reusable-live-realtime-visual.yml",
)
_STATUSES = {"passed", "failed", "timedOut", "skipped", "interrupted"}
_OUTCOMES = {"expected", "unexpected", "flaky", "skipped"}
_KEYS = {
    "schema",
    "case_id",
    "project",
    "final_status",
    "expected_status",
    "outcome",
    "attempts",
    "retry",
    "skipped",
}
_FAILURE = "AUD-154 source or receipt validation failed"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_FAILURE)
        result[key] = value
    return result


def _valid_record(record: Any) -> bool:
    if not isinstance(record, dict) or set(record) != _KEYS:
        return False
    if (
        type(record["schema"]) is not int
        or record["schema"] != 1
        or not isinstance(record["case_id"], str)
        or record["case_id"] not in CASE_TITLES
        or record["project"] not in ("desktop", "mobile")
        or type(record["retry"]) is not int
        or record["retry"] not in (0, 1)
        or type(record["skipped"]) is not bool
    ):
        return False
    for key, domain in (
        ("final_status", _STATUSES),
        ("expected_status", _STATUSES),
        ("outcome", _OUTCOMES),
    ):
        if not isinstance(record[key], str) or record[key] not in domain:
            return False
    attempts = record["attempts"]
    return (
        isinstance(attempts, list)
        and len(attempts) == record["retry"] + 1
        and all(isinstance(value, str) and value in _STATUSES for value in attempts)
        and attempts[-1] == record["final_status"]
        and record["skipped"] == ("skipped" in attempts)
    )


def project_case_records(
    output: str, *, retained: bool = False
) -> list[dict[str, Any]]:
    """Reject the whole named projection on malformed, duplicate or partial rows."""
    prefix = "live E2E AUD154 " if retained else "UE_LIVE_AUD154_V1 "
    records: list[dict[str, Any]] = []
    for line in output.split("\n")[:-1]:
        if prefix not in line:
            continue
        if not line.startswith(prefix) or len(line) > 768 or not line.isascii():
            return []
        try:
            record = json.loads(line[len(prefix) :], object_pairs_hook=_unique_object)
        except (ValueError, TypeError):
            return []
        if not _valid_record(record) or any(
            (item["case_id"], item["project"]) == (record["case_id"], record["project"])
            for item in records
        ):
            return []
        records.append(record)
    if prefix in output.split("\n")[-1]:
        return []
    return records


def _git(root: Path, *arguments: str) -> str:
    result = fast_preflight.run_check(
        fast_preflight.CheckSpec(
            "aud154-source", ("git", "--no-optional-locks", *arguments)
        ),
        repo_root=root,
        timeout_seconds=30,
        include_output=True,
    )
    if result.status != "passed" or result.exit_code != 0:
        raise ValueError(_FAILURE)
    return result.stdout.strip()


def source_snapshot(root: Path, environment: Mapping[str, str]) -> dict[str, Any]:
    """Require committed clean source and bind the bytes actually used by the job."""
    sha = environment.get("GITHUB_SHA", "")
    run_id = environment.get("GITHUB_RUN_ID", "")
    attempt = environment.get("GITHUB_RUN_ATTEMPT", "")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", sha)
        or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
        or not re.fullmatch(r"[1-9][0-9]{0,5}", attempt)
        or _git(root, "rev-parse", "HEAD") != sha
        or _git(root, "status", "--porcelain", "--untracked-files=no")
    ):
        raise ValueError(_FAILURE)
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ValueError(_FAILURE)
    bindings = {}
    for name in SOURCE_PATHS:
        path = root / name
        if not stat.S_ISREG(path.lstat().st_mode) or path.resolve() != path.absolute():
            raise ValueError(_FAILURE)
        data = path.read_bytes()
        try:
            completed = subprocess.run(
                ("git", "hash-object", "--stdin"),
                cwd=root,
                input=data,
                capture_output=True,
                check=True,
                timeout=30,
            )
            blob = completed.stdout.decode("ascii").strip()
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise ValueError(_FAILURE) from None
        if _git(root, "rev-parse", f"HEAD:{name}") != blob:
            raise ValueError(_FAILURE)
        bindings[name] = {"blob": blob, "sha256": hashlib.sha256(data).hexdigest()}
    return {
        "tested_commit": sha,
        "source_tree": tree,
        "run_id": int(run_id),
        "run_attempt": int(attempt),
        "bindings": bindings,
    }


def build_receipt(
    output: str,
    before: dict[str, Any],
    *,
    root: Path,
    environment: Mapping[str, str],
    exit_code: str,
) -> dict[str, Any]:
    after = source_snapshot(root, environment)
    if json.dumps(before, sort_keys=True) != json.dumps(
        after, sort_keys=True
    ) or not re.fullmatch(r"0|[1-9][0-9]{0,4}", exit_code):
        raise ValueError(_FAILURE)
    records = project_case_records(output, retained=True)
    counts = [
        line for line in output.split("\n") if line.startswith("live E2E counts ")
    ]
    outcomes = [
        line for line in output.split("\n") if line.startswith("live E2E outcome=")
    ]
    accepted = (
        exit_code == "0"
        and counts == ["live E2E counts passed=18"]
        and outcomes == ["live E2E outcome=passed exit_code=0"]
        and {(item["case_id"], item["project"]) for item in records}
        == {
            (case_id, project)
            for case_id in CASE_TITLES
            for project in ("desktop", "mobile")
        }
        and all(
            item
            == {
                "schema": 1,
                "case_id": item["case_id"],
                "project": item["project"],
                "final_status": "passed",
                "expected_status": "passed",
                "outcome": "expected",
                "attempts": ["passed"],
                "retry": 0,
                "skipped": False,
            }
            for item in records
        )
    )
    return {
        "schema": "ue-aud154-named-case-receipt-v2",
        "finding": "AUD-154",
        "evidence_scope": "current-live-button-and-enter-cases-only",
        "original_criterion_satisfied": False,
        "original_case_title": "shows delivery confirmation after message is sent",
        "expected_projects": ["desktop", "mobile"],
        "case_titles": CASE_TITLES,
        "suite": "live messenger delivery",
        "source": SOURCE_PATHS[0],
        "accepted": accepted,
        "process_exit_code": int(exit_code),
        "cases": sorted(records, key=lambda item: (item["case_id"], item["project"])),
        **after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("snapshot", "receipt"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--exit-code")
    args = parser.parse_args()
    try:
        root = Path.cwd().resolve()
        if args.operation == "snapshot":
            result = source_snapshot(root, os.environ)
        else:
            if args.before is None or args.input is None or args.exit_code is None:
                raise ValueError(_FAILURE)
            before = json.loads(
                args.before.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
            result = build_receipt(
                args.input.read_text(encoding="utf-8"),
                before,
                root=root,
                environment=os.environ,
                exit_code=args.exit_code,
            )
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        return 0 if result.get("accepted", True) else 1
    except (OSError, ValueError, TypeError):
        parser.exit(1, _FAILURE + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
