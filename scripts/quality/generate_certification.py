#!/usr/bin/env python3
"""Create a content-addressed quality certification record for a release."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECK_POLICY_SCHEMA = (
    REPOSITORY_ROOT / "quality" / "release-required-checks.schema.json"
)
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_required_checks(
    evidence: dict[str, Any],
    policy: dict[str, Any],
    *,
    event: str,
    commit_sha: str,
) -> dict[str, dict[str, Any]]:
    """Return trusted release checks or fail closed on ambiguous evidence."""
    if not _COMMIT_SHA.fullmatch(commit_sha):
        raise ValueError(
            "commit SHA must be exactly 40 lowercase hexadecimal characters"
        )
    if evidence.get("commit_sha") != commit_sha:
        raise ValueError(
            "check evidence commit SHA does not match the release commit SHA"
        )

    events = policy.get("events")
    if not isinstance(events, dict) or event not in events:
        raise ValueError(f"release check policy has no event named {event!r}")
    event_policy = events[event]
    if not isinstance(event_policy, dict):
        raise ValueError(f"release check policy event {event!r} must be an object")
    github_event = event_policy.get("github_event")
    github_ref = event_policy.get("github_ref")
    github_repository = event_policy.get("github_repository")
    if not isinstance(github_event, str) or not github_event:
        raise ValueError(f"release check policy event {event!r} has no GitHub event")
    if not isinstance(github_ref, str) or not github_ref.startswith("refs/heads/"):
        raise ValueError(f"release check policy event {event!r} has no branch ref")
    expected_branch = github_ref.removeprefix("refs/heads/")
    if not expected_branch:
        raise ValueError(f"release check policy event {event!r} has an empty branch")
    if not isinstance(github_repository, str) or not github_repository:
        raise ValueError(
            f"release check policy event {event!r} has no GitHub repository"
        )

    requirements = event_policy.get("required_checks")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError(f"release check policy event {event!r} has no required checks")

    required_by_name: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise ValueError("each required check policy entry must be an object")
        name = requirement.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each required check policy entry must have a name")
        if name in required_by_name:
            raise ValueError(f"required check policy contains duplicate name {name!r}")
        workflow_path = requirement.get("workflow_path")
        if not isinstance(workflow_path, str) or not workflow_path.startswith(
            ".github/workflows/"
        ):
            raise ValueError(f"required check {name!r} has no workflow path")
        allowed = requirement.get("allowed_conclusions")
        if not isinstance(allowed, list) or not allowed:
            raise ValueError(f"required check {name!r} has no allowed conclusions")
        if "skipped" in allowed and not (
            requirement.get("safe_to_skip") is True
            and isinstance(requirement.get("skip_reason"), str)
            and requirement["skip_reason"].strip()
        ):
            raise ValueError(
                f"required check {name!r} skip is not explicitly documented as safe"
            )
        required_by_name[name] = requirement

    runs = evidence.get("check_runs")
    if not isinstance(runs, list):
        raise ValueError("check evidence check_runs must be an array")
    matching: dict[str, list[dict[str, Any]]] = {name: [] for name in required_by_name}
    for item in runs:
        if not isinstance(item, dict):
            raise ValueError("every check run must be an object")
        if item.get("head_sha") != commit_sha:
            raise ValueError("check evidence contains a run for a foreign commit SHA")
        name = item.get("name")
        if isinstance(name, str) and name in matching:
            matching[name].append(item)

    trusted: dict[str, dict[str, Any]] = {}
    for name, requirement in required_by_name.items():
        candidates = matching[name]
        if not candidates:
            raise ValueError(f"required check {name!r} is missing")
        if len(candidates) != 1:
            raise ValueError(
                f"required check {name!r} has duplicate ambiguous check runs"
            )
        item = candidates[0]
        status = item.get("status")
        if status != "completed":
            raise ValueError(f"required check {name!r} is not completed: {status!r}")
        conclusion = item.get("conclusion")
        allowed = requirement["allowed_conclusions"]
        if conclusion not in allowed:
            raise ValueError(
                f"required check {name!r} concluded {conclusion!r}; "
                f"allowed conclusions: {allowed!r}"
            )
        check_id = item.get("id")
        if not isinstance(check_id, int) or isinstance(check_id, bool) or check_id <= 0:
            raise ValueError(f"required check {name!r} has an invalid check-run id")
        details_url = item.get("details_url")
        if not isinstance(details_url, str) or not details_url:
            raise ValueError(f"required check {name!r} has no details URL")
        app = item.get("app")
        if not isinstance(app, dict) or app.get("slug") != "github-actions":
            raise ValueError(
                f"required check {name!r} is not owned by the GitHub Actions app"
            )
        workflow_run = item.get("workflow_run")
        if not isinstance(workflow_run, dict):
            raise ValueError(f"required check {name!r} has no workflow provenance")
        if workflow_run.get("path") != requirement["workflow_path"]:
            raise ValueError(f"required check {name!r} has the wrong workflow path")
        if workflow_run.get("event") != github_event:
            raise ValueError(f"required check {name!r} has the wrong workflow event")
        if workflow_run.get("head_branch") != expected_branch:
            raise ValueError(f"required check {name!r} has the wrong head branch")
        if workflow_run.get("head_sha") != commit_sha:
            raise ValueError(f"required check {name!r} has the wrong workflow head SHA")
        if workflow_run.get("repository") != github_repository:
            raise ValueError(
                f"required check {name!r} has the wrong workflow repository"
            )
        if workflow_run.get("status") != "completed":
            raise ValueError(f"required check {name!r} workflow is not completed")
        if workflow_run.get("conclusion") != "success":
            raise ValueError(f"required check {name!r} workflow did not succeed")
        if not _positive_integer(workflow_run.get("id")):
            raise ValueError(f"required check {name!r} has an invalid workflow run id")
        if not _positive_integer(workflow_run.get("run_attempt")):
            raise ValueError(
                f"required check {name!r} has an invalid workflow run attempt"
            )
        if not _positive_integer(workflow_run.get("job_id")):
            raise ValueError(f"required check {name!r} has an invalid workflow job id")
        trusted[name] = {
            "id": check_id,
            "status": status,
            "conclusion": conclusion,
            "details_url": details_url,
            "app_slug": "github-actions",
            "workflow_run": workflow_run,
        }
    return trusted


def build_record(
    *,
    commit_sha: str,
    contract_path: Path,
    report_paths: list[Path],
    check_results: dict[str, Any],
    known_limitations: list[str],
    check_policy_path: Path | None = None,
    check_event: str | None = None,
    signing_key: bytes | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    contract = _load_object(contract_path)
    record: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commit_sha": commit_sha,
        "required_checks": check_results,
        "contract_sha256": _sha256(contract_path),
        "report_hashes": {
            path.as_posix(): _sha256(path)
            for path in sorted(report_paths, key=lambda item: item.as_posix())
        },
        "exclusions": contract.get("exclusions", []),
        "quarantines": contract.get("quarantines", []),
        "known_limitations": known_limitations,
    }
    if check_policy_path is not None:
        record["check_policy_sha256"] = _sha256(check_policy_path)
    if check_event is not None:
        record["check_event"] = check_event
    unsigned = _canonical(record)
    record["record_sha256"] = hashlib.sha256(unsigned).hexdigest()
    if signing_key:
        record["hmac_sha256"] = hmac.new(
            signing_key, unsigned, hashlib.sha256
        ).hexdigest()
    return record


def verify_record_hmac(record: dict[str, Any], signing_key: bytes) -> None:
    """Fail closed unless both content hash and HMAC authenticate the record."""
    if not signing_key:
        raise ValueError("certification HMAC key must not be empty")
    stored_record_hash = record.get("record_sha256")
    stored_hmac = record.get("hmac_sha256")
    if not isinstance(stored_record_hash, str) or not isinstance(stored_hmac, str):
        raise ValueError("certification record has no HMAC authentication")
    unsigned = dict(record)
    unsigned.pop("record_sha256", None)
    unsigned.pop("hmac_sha256", None)
    payload = _canonical(unsigned)
    expected_record_hash = hashlib.sha256(payload).hexdigest()
    expected_hmac = hmac.new(signing_key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(stored_record_hash, expected_record_hash):
        raise ValueError(
            "certification record HMAC-authenticated content hash is invalid"
        )
    if not hmac.compare_digest(stored_hmac, expected_hmac):
        raise ValueError("certification record HMAC is invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPOSITORY_ROOT / "quality" / "quality-contract.json",
    )
    parser.add_argument("--report", type=Path, action="append", default=[])
    parser.add_argument(
        "--report-dir",
        type=Path,
        action="append",
        default=[],
        help="Directory containing additional report evidence to hash recursively",
    )
    parser.add_argument(
        "--checks",
        type=Path,
        required=True,
        help="JSON object mapping required check names to results",
    )
    parser.add_argument(
        "--check-policy",
        type=Path,
        required=True,
        help="Event-aware release-critical check policy",
    )
    parser.add_argument(
        "--check-policy-schema",
        type=Path,
        default=DEFAULT_CHECK_POLICY_SCHEMA,
    )
    parser.add_argument("--check-event", required=True)
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    check_evidence = _load_object(args.checks)
    check_policy = _load_object(args.check_policy)
    check_policy_schema = _load_object(args.check_policy_schema)
    policy_errors = sorted(
        Draft202012Validator(check_policy_schema).iter_errors(check_policy),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if policy_errors:
        parser.error(f"invalid release check policy: {policy_errors[0].message}")
    try:
        checks = validate_required_checks(
            check_evidence,
            check_policy,
            event=args.check_event,
            commit_sha=args.commit_sha,
        )
    except ValueError as error:
        parser.error(str(error))
    report_paths = list(args.report)
    for report_dir in args.report_dir:
        if not report_dir.is_dir():
            parser.error(f"report directory does not exist: {report_dir}")
        report_paths.extend(path for path in report_dir.rglob("*") if path.is_file())
    missing = [
        str(path)
        for path in [
            args.contract,
            args.check_policy,
            args.check_policy_schema,
            *report_paths,
        ]
        if not path.is_file()
    ]
    if missing:
        parser.error(f"missing evidence files: {', '.join(missing)}")
    key_text = os.environ.get("QUALITY_CERTIFICATION_KEY")
    record = build_record(
        commit_sha=args.commit_sha,
        contract_path=args.contract,
        report_paths=report_paths,
        check_results=checks,
        known_limitations=args.limitation,
        check_policy_path=args.check_policy,
        check_event=args.check_event,
        signing_key=key_text.encode("utf-8") if key_text else None,
    )
    if key_text:
        verify_record_hmac(record, key_text.encode("utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
