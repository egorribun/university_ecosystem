"""Collect a source-bound receipt for the ZAP SARIF producer output.

This private candidate validates a ZAP report and binds its digest to the
checked-out DAST workflow, rules file, event commit, and workflow run. It does
not set or apply a ZAP finding threshold; the current owner decision defines
thresholds for Nuclei and Scorecard, while ZAP threshold policy remains open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn

MAX_REPORT_BYTES = 128 * 1024 * 1024
VALID_LEVELS = frozenset({"error", "warning", "note", "none"})
WORKFLOW_PATH = Path(".github/workflows/dast.yml")
RULES_PATH = Path(".zap/rules.tsv")
SARIF_NAME = "zap-results.sarif"


class ReceiptError(ValueError):
    """Raised when source or report evidence cannot be bound safely."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("SARIF contains a duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> NoReturn:
    raise ReceiptError(f"SARIF contains invalid JSON constant {value}")


def _safe_repo_file(repo_root: Path, relative_path: Path) -> Path:
    root = repo_root.resolve(strict=True)
    candidate = repo_root / relative_path
    if candidate.is_symlink() or not candidate.is_file():
        raise ReceiptError("Required repository source file is unavailable")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ReceiptError("Required repository source escapes the checkout")
    return resolved


def _read_report(path: Path) -> bytes:
    if path.name != SARIF_NAME:
        raise ReceiptError("ZAP SARIF report has an unexpected artifact filename")
    if path.is_symlink() or not path.is_file():
        raise ReceiptError("ZAP SARIF report is missing or not a regular file")
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_REPORT_BYTES:
            raise ReceiptError("ZAP SARIF report size is outside the supported bound")
        payload = path.read_bytes()
    except OSError as error:
        raise ReceiptError("ZAP SARIF report cannot be read") from error
    if len(payload) != size:
        raise ReceiptError("ZAP SARIF report changed while it was being read")
    return payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_sha(repo_root: Path) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ReceiptError("Git executable is unavailable")
    try:
        result = subprocess.run(  # noqa: S603 - fixed Git verification; shell execution is disabled
            [git_executable, "rev-parse", "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReceiptError("Current DAST checkout SHA is unavailable") from error
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ReceiptError("Current DAST checkout SHA is invalid")
    return value


def _source_bytes_at_commit(repo_root: Path, commit: str, relative_path: Path) -> bytes:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ReceiptError("Git executable is unavailable")
    try:
        result = subprocess.run(  # noqa: S603 - fixed Git object read; no shell
            [
                git_executable,
                "--no-pager",
                "show",
                f"{commit}:{relative_path.as_posix()}",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReceiptError("Expected DAST source object is unavailable") from error
    if result.returncode != 0:
        raise ReceiptError("Expected DAST source object is unavailable")
    return result.stdout


def _positive_decimal(value: str, label: str) -> str:
    if re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise ReceiptError(f"{label} must be a positive decimal integer")
    return value


def _validate_sarif(payload: bytes) -> dict[str, Any]:
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptError("ZAP SARIF report is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or document.get("version") != "2.1.0":
        raise ReceiptError("ZAP SARIF report must use SARIF 2.1.0")
    runs = document.get("runs")
    if not isinstance(runs, list) or len(runs) != 1 or not isinstance(runs[0], dict):
        raise ReceiptError("ZAP SARIF report must contain exactly one run")
    run = runs[0]
    tool = run.get("tool")
    driver = tool.get("driver") if isinstance(tool, dict) else None
    tool_name = driver.get("name") if isinstance(driver, dict) else None
    if not isinstance(tool_name, str) or "zap" not in tool_name.casefold():
        raise ReceiptError("ZAP SARIF report has an unexpected tool identity")

    raw_results = run.get("results")
    if not isinstance(raw_results, list):
        raise ReceiptError("ZAP SARIF run does not contain a results list")
    raw_rules = driver.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ReceiptError("ZAP SARIF tool rules are invalid")
    rule_ids = {
        rule.get("id")
        for rule in raw_rules
        if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }

    level_counts: Counter[str] = Counter()
    for result in raw_results:
        if not isinstance(result, dict):
            raise ReceiptError("ZAP SARIF result entries must be objects")
        level = result.get("level", "warning")
        if not isinstance(level, str) or level not in VALID_LEVELS:
            raise ReceiptError("ZAP SARIF result has an invalid level")
        rule_id = result.get("ruleId")
        if rule_id is None:
            rule_index = result.get("ruleIndex")
            if (
                not isinstance(rule_index, int)
                or isinstance(rule_index, bool)
                or rule_index < 0
                or rule_index >= len(raw_rules)
            ):
                raise ReceiptError("ZAP SARIF result has no valid rule identity")
            rule = raw_rules[rule_index]
            rule_id = rule.get("id") if isinstance(rule, dict) else None
        if not isinstance(rule_id, str) or not rule_id:
            raise ReceiptError("ZAP SARIF result has an empty rule identity")
        if rule_ids and rule_id not in rule_ids:
            raise ReceiptError("ZAP SARIF result refers to an unknown rule")
        level_counts[level] += 1

    invocations = run.get("invocations")
    if invocations is not None:
        if not isinstance(invocations, list) or not all(
            isinstance(invocation, dict) for invocation in invocations
        ):
            raise ReceiptError("ZAP SARIF invocations are invalid")
        for invocation in invocations:
            successful = invocation.get("executionSuccessful")
            if successful is not None and not isinstance(successful, bool):
                raise ReceiptError("ZAP SARIF invocation status is invalid")
            if successful is False:
                raise ReceiptError("ZAP SARIF records an unsuccessful invocation")

    invocation_state = "not-recorded"
    if invocations:
        invocation_state = (
            "successful"
            if all(item.get("executionSuccessful") is True for item in invocations)
            else "partially-recorded"
        )
    return {
        "tool_name": tool_name,
        "version": document["version"],
        "result_count": len(raw_results),
        "levels": {level: level_counts[level] for level in sorted(VALID_LEVELS)},
        "invocation_state": invocation_state,
    }


def collect_receipt(
    *,
    repo_root: Path,
    expected_sha: str,
    run_id: str,
    run_attempt: str,
    artifact_name: str,
    scan_outcome: str,
    sarif_path: Path,
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        raise ReceiptError("Expected DAST event SHA is invalid")
    if scan_outcome != "success":
        raise ReceiptError("ZAP scan did not complete successfully")
    run_id = _positive_decimal(run_id, "GITHUB_RUN_ID")
    run_attempt = _positive_decimal(run_attempt, "GITHUB_RUN_ATTEMPT")
    expected_artifact_name = f"zap-results-{run_id}-attempt-{run_attempt}"
    if artifact_name != expected_artifact_name:
        raise ReceiptError("ZAP SARIF artifact name does not match this workflow run")

    repo_root = repo_root.resolve(strict=True)
    checkout_sha = _source_sha(repo_root)
    if checkout_sha != expected_sha:
        raise ReceiptError("ZAP report checkout SHA does not match the event SHA")

    workflow_path = _safe_repo_file(repo_root, WORKFLOW_PATH)
    rules_path = _safe_repo_file(repo_root, RULES_PATH)
    workflow_bytes = workflow_path.read_bytes()
    rules_bytes = rules_path.read_bytes()
    if (
        _source_bytes_at_commit(repo_root, expected_sha, WORKFLOW_PATH)
        != workflow_bytes
    ):
        raise ReceiptError("DAST workflow bytes do not match the event commit")
    if _source_bytes_at_commit(repo_root, expected_sha, RULES_PATH) != rules_bytes:
        raise ReceiptError("ZAP rules bytes do not match the event commit")
    report_candidate = (
        sarif_path if sarif_path.is_absolute() else repo_root / sarif_path
    )
    expected_report = repo_root / SARIF_NAME
    if report_candidate.is_symlink() or report_candidate.resolve() != expected_report:
        raise ReceiptError("ZAP SARIF report is not the expected checkout artifact")
    sarif_bytes = _read_report(report_candidate)
    sarif_metadata = _validate_sarif(sarif_bytes)

    return {
        "schema_version": 1,
        "workflow_run": {
            "id": run_id,
            "attempt": run_attempt,
            "artifact_name": artifact_name,
            "event_sha": expected_sha,
            "checkout_sha": checkout_sha,
        },
        "source": {
            "workflow_path": WORKFLOW_PATH.as_posix(),
            "workflow_sha256": _sha256(workflow_bytes),
            "zap_rules_path": RULES_PATH.as_posix(),
            "zap_rules_sha256": _sha256(rules_bytes),
        },
        "report": {
            "path": sarif_path.name,
            "sha256": _sha256(sarif_bytes),
            "size_bytes": len(sarif_bytes),
            **sarif_metadata,
        },
        "finding_threshold": "not_evaluated",
    }


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--scan-outcome", required=True)
    parser.add_argument("--sarif", type=Path, default=Path("zap-results.sarif"))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    try:
        receipt = collect_receipt(
            repo_root=arguments.repo_root,
            expected_sha=arguments.expected_sha,
            run_id=arguments.run_id,
            run_attempt=arguments.run_attempt,
            artifact_name=arguments.artifact_name,
            scan_outcome=arguments.scan_outcome,
            sarif_path=arguments.sarif,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        with arguments.output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except (OSError, ReceiptError) as error:
        print(
            f"::error::Could not validate ZAP SARIF provenance: {error}",
            file=sys.stderr,
        )
        return 1
    print("ZAP SARIF provenance receipt written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
