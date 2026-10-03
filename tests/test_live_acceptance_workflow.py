"""Static safety contract for the owned Docker live-acceptance workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "live-acceptance.yml"


def _workflow() -> tuple[str, dict[str, object]]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(source)
    if "on" not in parsed and True in parsed:
        parsed["on"] = parsed.pop(True)
    return source, parsed


def test_workflow_runs_pr_smoke_and_nightly_manual_full_with_safe_cleanup() -> None:
    source, workflow = _workflow()
    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    schedules = triggers["schedule"]
    assert len(schedules) == 1
    assert re.fullmatch(
        r"(?:[0-5]?\d)\s+(?:[01]?\d|2[0-3])\s+\*\s+\*\s+\*",
        schedules[0]["cron"],
    ), "full acceptance must run once each night"
    assert "default branch" in source.lower()

    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["live-acceptance"]
    assert (
        job["if"]
        == "${{ github.event_name == 'pull_request' || github.ref == 'refs/heads/main' }}"
    )
    assert (
        job["env"]["LIVE_E2E_MODE"]
        == "${{ github.event_name == 'pull_request' && 'smoke' || 'full' }}"
    )
    steps = job["steps"]
    npm_install_steps = [
        index for index, step in enumerate(steps) if "npm ci" in step.get("run", "")
    ]
    assert npm_install_steps, "CI must install the locked frontend dependencies"
    npm_install_index = npm_install_steps[0]
    browser_setup_steps = [
        index
        for index, step in enumerate(steps)
        if "playwright install --with-deps chromium" in step.get("run", "")
    ]
    assert browser_setup_steps, (
        "CI must install the locked Chromium browser and OS dependencies"
    )
    browser_setup_index = browser_setup_steps[0]
    assert steps[browser_setup_index].get("working-directory") == "frontend"
    assert "npm ci" not in steps[browser_setup_index].get("run", "")
    contract_steps = [
        index
        for index, step in enumerate(steps)
        if "npm run test:e2e:live:contract" in step.get("run", "")
    ]
    assert contract_steps, "live contracts must pass before starting Docker"
    contract_index = contract_steps[0]
    assert steps[contract_index].get("working-directory") == "frontend"
    up_index = next(
        index
        for index, step in enumerate(steps)
        if "live_stand.py up" in step.get("run", "")
    )
    assert npm_install_index < contract_index < browser_setup_index < up_index
    e2e_index = next(
        index
        for index, step in enumerate(steps)
        if "live_stand.py e2e" in step.get("run", "")
    )
    stop_index = next(
        index
        for index, step in enumerate(steps)
        if "live_stand.py stop" in step.get("run", "")
    )
    assert up_index < e2e_index < stop_index
    assert "always()" in steps[stop_index].get("if", "")
    assert all("live_stand.py teardown" not in step.get("run", "") for step in steps)
    assert "github.event_name == 'pull_request'" in source
    assert "--mode" in steps[e2e_index]["run"]
    assert "secrets." not in source
    assert "test:e2e:live:contract" in steps[contract_index]["run"]


def test_workflow_actions_are_immutable_and_only_read_repository_contents() -> None:
    source, workflow = _workflow()
    read_only_permissions = {"contents": "read"}
    assert workflow["permissions"] == read_only_permissions
    assert all(
        job.get("permissions", workflow["permissions"]) == read_only_permissions
        for job in workflow["jobs"].values()
    ), "no job may override the workflow's read-only permissions"
    uses = [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]
    assert uses
    assert all(re.search(r"@[0-9a-f]{40}(?:\s|$)", action) for action in uses)
    assert re.search(r"^permissions:\s*\n\s+contents:\s+read\s*$", source, re.M)


def test_live_contract_command_includes_every_live_contract_file() -> None:
    frontend = ROOT / "frontend"
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    command = package["scripts"]["test:e2e:live:contract"]
    contracts = {
        path.relative_to(frontend).as_posix()
        for pattern in (
            "tests/e2e-live/*.contract.test.mjs",
            "scripts/*live-contract.test.mjs",
        )
        for path in frontend.glob(pattern)
    }
    contracts.add("scripts/not-found-i18n.contract.test.mjs")
    assert contracts, "the live acceptance suite must have static contracts"
    missing = sorted(path for path in contracts if path not in command)
    assert not missing, f"live contract command omits: {missing}"
