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
    assert triggers["workflow_dispatch"]["inputs"]["frozen_rc_sha"]["required"] is True
    assert triggers["workflow_dispatch"]["inputs"]["frozen_rc_sha"]["type"] == "string"
    schedules = triggers["schedule"]
    assert len(schedules) == 1
    assert re.fullmatch(
        r"(?:[0-5]?\d)\s+(?:[01]?\d|2[0-3])\s+\*\s+\*\s+\*",
        schedules[0]["cron"],
    ), "full acceptance must run once each night"
    assert "default branch" in source.lower()

    assert workflow["permissions"] == {"contents": "read"}
    concurrency = workflow["concurrency"]
    assert (
        concurrency["group"]
        == "live-acceptance-${{ github.event.pull_request.number || github.ref }}"
    )
    assert (
        concurrency["cancel-in-progress"]
        == "${{ github.event_name == 'pull_request' }}"
    ), "only a superseded PR smoke may cancel an in-flight acceptance"
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
    event_checkout = next(
        step for step in steps if step.get("uses", "").startswith("actions/checkout@")
    )
    assert event_checkout["with"]["ref"] == "${{ github.sha }}"
    assert event_checkout["with"]["persist-credentials"] is False
    verify_checkout_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Verify the checked-out event commit"
    )
    verify_checkout = steps[verify_checkout_index]
    assert verify_checkout["id"] == "verify-event-commit"
    assert verify_checkout["env"]["EXPECTED_EVENT_SHA"] == "${{ github.sha }}"
    assert "git rev-parse HEAD" in verify_checkout["run"]
    assert '"$actual_sha" != "$EXPECTED_EVENT_SHA"' in verify_checkout["run"]
    assert "checked_out_sha=$actual_sha" in verify_checkout["run"]
    assert steps.index(event_checkout) + 1 == verify_checkout_index

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
    assert "--stack core" in steps[up_index]["run"]
    assert "--in-place" in steps[up_index]["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in steps[up_index]["run"]
    assert (
        steps[up_index]["env"]["STAND_REF"]
        == "${{ steps.verify-event-commit.outputs.checked_out_sha }}"
    )
    assert npm_install_index < contract_index < browser_setup_index < up_index
    e2e_index = next(
        index
        for index, step in enumerate(steps)
        if "live_stand.py e2e" in step.get("run", "")
    )
    assert steps[e2e_index]["id"] == "core-e2e"
    stop_index = next(
        index
        for index, step in enumerate(steps)
        if "live_stand.py stop" in step.get("run", "")
    )
    assert steps[stop_index]["id"] == "stop-stand"
    assert up_index < e2e_index < stop_index
    assert "--in-place" in steps[e2e_index]["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in steps[e2e_index]["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in steps[stop_index]["run"]
    assert steps[up_index - 1]["name"] == "Select unique owned Core state directory"
    assert "always()" in steps[stop_index].get("if", "")
    assert all("live_stand.py teardown" not in step.get("run", "") for step in steps)
    assert "github.event_name == 'pull_request'" in source
    assert "--mode" in steps[e2e_index]["run"]
    assert "secrets." not in source
    assert "test:e2e:live:contract" in steps[contract_index]["run"]

    receipt_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Write the metadata-only Core receipt"
    )
    receipt = steps[receipt_index]
    assert receipt["if"] == "${{ always() }}"
    assert (
        receipt["env"]["VERIFIED_SHA"]
        == "${{ steps.verify-event-commit.outputs.checked_out_sha }}"
    )
    assert receipt["env"]["LIVE_MODE"] == "${{ env.LIVE_E2E_MODE }}"
    assert receipt["env"]["CHECKOUT_OUTCOME"] == (
        "${{ steps.verify-event-commit.outcome }}"
    )
    assert receipt["env"]["STAND_START_OUTCOME"] == "${{ steps.start-stand.outcome }}"
    assert receipt["env"]["E2E_OUTCOME"] == "${{ steps.core-e2e.outcome }}"
    assert receipt["env"]["STAND_STOP_OUTCOME"] == "${{ steps.stop-stand.outcome }}"
    for safe_field in (
        '"kind": "owned-core-live-acceptance"',
        '"source_sha": source_sha',
        '"workflow_ref": os.environ["GITHUB_WORKFLOW_REF"]',
        '"event": os.environ["GITHUB_EVENT_NAME"]',
        '"run_id": int(os.environ["GITHUB_RUN_ID"])',
        '"run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"])',
        '"stack": "core"',
        '"mode": mode',
        '"outcomes": outcomes',
    ):
        assert safe_field in receipt["run"]
    assert "os.environ.copy" not in receipt["run"]
    assert "os.environ.items" not in receipt["run"]
    assert "stdout" not in receipt["run"] and "stderr" not in receipt["run"]
    assert "LIVE_E2E_MODE" in receipt["run"] or "LIVE_MODE" in receipt["env"]
    receipt_upload = steps[receipt_index + 1]
    assert receipt_upload["name"] == "Upload the metadata-only Core receipt"
    assert receipt_upload["if"] == "${{ always() }}"
    assert receipt_upload["with"]["path"] == "core-live-acceptance-receipt.json"
    assert receipt_upload["with"]["if-no-files-found"] == "error"
    assert receipt_upload["with"]["name"] == (
        "core-live-receipt-${{ github.sha }}-${{ github.run_id }}-"
        "${{ github.run_attempt }}"
    )
    assert receipt_upload["with"]["retention-days"] == 90
    assert stop_index < receipt_index < steps.index(receipt_upload)

    jobs = workflow["jobs"]
    validation = jobs["validate-frozen-rc"]
    validation_script = "\n".join(step.get("run", "") for step in validation["steps"])
    assert '"refs/heads/main"' in validation_script
    assert "^[0-9a-f]{40}$" in validation_script
    frozen = jobs["frozen-rc-full-smoke"]
    assert frozen["needs"] == "validate-frozen-rc"
    frozen_checkout = next(
        step
        for step in frozen["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert frozen_checkout["with"]["ref"] == "${{ inputs.frozen_rc_sha }}"
    frozen_checkout_index = frozen["steps"].index(frozen_checkout)
    verify_checkout = frozen["steps"][frozen_checkout_index + 1]
    assert verify_checkout["id"] == "verify-frozen-rc"
    assert "git rev-parse HEAD" in verify_checkout["run"]
    assert '"$actual_sha" != "$EXPECTED_FROZEN_RC_SHA"' in verify_checkout["run"]
    assert "checked_out_sha=$actual_sha" in verify_checkout["run"]
    assert "GITHUB_STEP_SUMMARY" in verify_checkout["run"]
    frozen_up = next(
        step for step in frozen["steps"] if "live_stand.py up" in step.get("run", "")
    )
    frozen_e2e = next(
        step for step in frozen["steps"] if "live_stand.py e2e" in step.get("run", "")
    )
    assert "--stack full" in frozen_up["run"]
    assert (
        frozen_up["env"]["FROZEN_RC_VERIFIED_SHA"]
        == "${{ steps.verify-frozen-rc.outputs.checked_out_sha }}"
    )
    assert '"$FROZEN_RC_VERIFIED_SHA"' in frozen_up["run"]
    assert "--mode full" in frozen_e2e["run"]
    assert frozen_e2e["id"] == "frozen-rc-e2e"
    assert "--stack core" not in frozen_up["run"]

    receipt_index = next(
        index
        for index, step in enumerate(frozen["steps"])
        if step.get("name") == "Write the metadata-only frozen-RC receipt"
    )
    receipt = frozen["steps"][receipt_index]
    assert receipt["if"] == "${{ always() }}"
    assert (
        receipt["env"]["VERIFIED_SHA"]
        == "${{ steps.verify-frozen-rc.outputs.checked_out_sha }}"
    )
    for safe_field in (
        '"source_sha": source_sha',
        '"workflow_ref": os.environ["GITHUB_WORKFLOW_REF"]',
        '"run_id": int(os.environ["GITHUB_RUN_ID"])',
        '"run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"])',
        '"outcomes": outcomes',
    ):
        assert safe_field in receipt["run"]
    assert "os.environ.copy" not in receipt["run"]
    assert "stdout" not in receipt["run"] and "stderr" not in receipt["run"]
    receipt_upload = frozen["steps"][receipt_index + 1]
    assert receipt_upload["name"] == "Upload the metadata-only frozen-RC receipt"
    assert receipt_upload["with"]["path"] == "frozen-rc-live-receipt.json"
    assert receipt_upload["with"]["if-no-files-found"] == "error"
    assert "${{ inputs.frozen_rc_sha }}" in receipt_upload["with"]["name"]
    assert "${{ github.run_id }}" in receipt_upload["with"]["name"]


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
