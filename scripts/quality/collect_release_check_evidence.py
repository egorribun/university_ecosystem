#!/usr/bin/env python3
"""Bind release check runs to their exact GitHub Actions workflow provenance."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def collect_evidence(
    pages: Any,
    policy: dict[str, Any],
    *,
    event: str,
    repository: str,
    commit_sha: str,
    fetch_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Return complete check evidence enriched from exact Actions run/job APIs."""
    if not _COMMIT_SHA.fullmatch(commit_sha):
        raise ValueError(
            "commit SHA must be exactly 40 lowercase hexadecimal characters"
        )
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("GitHub repository must be an owner/name pair")
    if not isinstance(pages, list) or not pages:
        raise ValueError("GitHub returned no check-run pages")
    if any(not isinstance(page, dict) for page in pages):
        raise ValueError("GitHub check-run pagination response is malformed")

    totals = {page.get("total_count") for page in pages}
    if len(totals) != 1 or not all(_positive_integer(total) for total in totals):
        raise ValueError("GitHub check-run total_count is missing or inconsistent")
    page_runs = [page.get("check_runs") for page in pages]
    if any(not isinstance(runs, list) for runs in page_runs):
        raise ValueError("GitHub check-run page has no check_runs array")
    check_runs = [item for runs in page_runs for item in runs]
    if any(not isinstance(item, dict) for item in check_runs):
        raise ValueError("GitHub check-run response contains a non-object run")
    expected_total = totals.pop()
    if len(check_runs) != expected_total:
        raise ValueError(
            f"check-run pagination was truncated: got {len(check_runs)}, "
            f"expected {expected_total}"
        )
    check_ids = [item.get("id") for item in check_runs]
    if any(not _positive_integer(check_id) for check_id in check_ids):
        raise ValueError("check-run pagination returned an invalid run ID")
    if len(check_ids) != len(set(check_ids)):
        raise ValueError("check-run pagination returned duplicate run IDs")
    if any(item.get("head_sha") != commit_sha for item in check_runs):
        raise ValueError("check-run evidence contains a foreign commit SHA")

    events = policy.get("events")
    if not isinstance(events, dict) or not isinstance(events.get(event), dict):
        raise ValueError(f"release check policy has no event named {event!r}")
    event_policy = events[event]
    requirements = event_policy.get("required_checks")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError(f"release check policy event {event!r} has no required checks")
    required_names = {
        requirement.get("name")
        for requirement in requirements
        if isinstance(requirement, dict) and isinstance(requirement.get("name"), str)
    }

    details_pattern = re.compile(
        rf"^https://github\.com/{re.escape(repository)}/actions/runs/"
        r"(?P<run_id>[1-9][0-9]*)/job/(?P<job_id>[1-9][0-9]*)$"
    )
    api_check_prefix = f"https://api.github.com/repos/{repository}/check-runs/"
    enriched: list[dict[str, Any]] = []
    for item in check_runs:
        result = dict(item)
        if item.get("name") not in required_names:
            enriched.append(result)
            continue
        app = item.get("app")
        if not isinstance(app, dict) or app.get("slug") != "github-actions":
            raise ValueError("required check is not owned by the GitHub Actions app")
        details_url = item.get("details_url")
        match = (
            details_pattern.fullmatch(details_url)
            if isinstance(details_url, str)
            else None
        )
        if match is None:
            raise ValueError("required check has no canonical GitHub Actions job URL")
        run_id = int(match.group("run_id"))
        job_id = int(match.group("job_id"))
        run = fetch_json(f"repos/{repository}/actions/runs/{run_id}")
        job = fetch_json(f"repos/{repository}/actions/jobs/{job_id}")
        expected_check_url = f"{api_check_prefix}{item['id']}"
        if (
            run.get("id") != run_id
            or job.get("id") != job_id
            or job.get("run_id") != run_id
            or job.get("check_run_url") != expected_check_url
        ):
            raise ValueError("GitHub Actions job is not bound to check run evidence")
        if job.get("head_sha") != commit_sha or job.get("run_attempt") != run.get(
            "run_attempt"
        ):
            raise ValueError("GitHub Actions job and workflow run provenance disagree")
        run_repository = run.get("repository")
        if not isinstance(run_repository, dict):
            raise ValueError("GitHub Actions workflow run has no repository provenance")
        result["workflow_run"] = {
            "id": run.get("id"),
            "path": run.get("path"),
            "event": run.get("event"),
            "head_branch": run.get("head_branch"),
            "head_sha": run.get("head_sha"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "run_attempt": run.get("run_attempt"),
            "repository": run_repository.get("full_name"),
            "job_id": job_id,
        }
        enriched.append(result)
    return {"commit_sha": commit_sha, "check_runs": enriched}


def _github_api_url(endpoint: str, repository: str) -> str:
    """Accept only the exact GitHub Actions API resources used by this collector."""
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("GitHub repository must be an owner/name pair")
    endpoint_pattern = re.compile(
        rf"^repos/{re.escape(repository)}/actions/(?:runs|jobs)/[1-9][0-9]*$"
    )
    if endpoint_pattern.fullmatch(endpoint) is None:
        raise ValueError(f"unsupported GitHub API endpoint {endpoint!r}")
    return f"https://api.github.com/{endpoint}"


def _github_fetcher(token: str, repository: str) -> Callable[[str], dict[str, Any]]:
    if not token:
        raise ValueError("GH_TOKEN is required for GitHub provenance collection")

    def fetch(endpoint: str) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 -- canonical HTTPS URL
            _github_api_url(endpoint, repository),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- URL is restricted to canonical api.github.com Actions endpoints
            value = json.load(response)
        if not isinstance(value, dict):
            raise ValueError(f"GitHub API endpoint {endpoint!r} returned a non-object")
        return value

    return fetch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    policy = _load_json(args.policy)
    if not isinstance(policy, dict):
        parser.error("release check policy must be an object")
    try:
        evidence = collect_evidence(
            _load_json(args.pages),
            policy,
            event=args.event,
            repository=args.repository,
            commit_sha=args.commit_sha,
            fetch_json=_github_fetcher(os.environ.get("GH_TOKEN", ""), args.repository),
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
