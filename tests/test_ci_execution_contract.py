"""Repository-wide CI execution-budget and stale-run cancellation contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"
MAX_JOB_TIMEOUT_MINUTES = 360


def _load_workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), path.name
    return loaded


def _triggers(workflow: dict[str, Any]) -> object:
    # PyYAML 1.1 interprets the unquoted GitHub Actions key ``on`` as ``True``.
    return workflow.get("on", workflow.get(True, {}))


def test_every_runner_job_has_a_bounded_timeout() -> None:
    missing: list[str] = []
    invalid: list[str] = []

    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = _load_workflow(workflow_path).get("jobs", {})
        assert isinstance(jobs, dict), workflow_path.name
        for job_name, job in jobs.items():
            if not isinstance(job, dict) or "runs-on" not in job:
                continue
            timeout = job.get("timeout-minutes")
            if timeout is None:
                missing.append(f"{workflow_path.name}:{job_name}")
            elif not isinstance(timeout, int) or not (
                1 <= timeout <= MAX_JOB_TIMEOUT_MINUTES
            ):
                invalid.append(f"{workflow_path.name}:{job_name}={timeout!r}")

    assert not missing, "runner jobs without timeout-minutes: " + ", ".join(missing)
    assert not invalid, "runner jobs with invalid timeout-minutes: " + ", ".join(
        invalid
    )


def test_push_and_pull_request_workflows_cancel_stale_runs() -> None:
    missing: list[str] = []

    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _load_workflow(workflow_path)
        triggers = _triggers(workflow)
        if isinstance(triggers, str):
            trigger_names = {triggers}
        elif isinstance(triggers, dict):
            trigger_names = set(triggers)
        else:
            trigger_names = set()
        if not trigger_names.intersection({"push", "pull_request"}):
            continue
        concurrency = workflow.get("concurrency")
        if not isinstance(concurrency, dict):
            missing.append(workflow_path.name)
            continue
        if "group" not in concurrency or "cancel-in-progress" not in concurrency:
            missing.append(workflow_path.name)

    assert not missing, (
        "push/PR workflows without stale-run cancellation: " + ", ".join(missing)
    )
