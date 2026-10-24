"""Static safety contract for the owned Docker live-acceptance workflow."""

from __future__ import annotations

import json
import os
import re
import runpy
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "live-acceptance.yml"


def _workflow() -> tuple[str, dict[str, object]]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(source)
    if "on" not in parsed and True in parsed:
        parsed["on"] = parsed.pop(True)
    return source, parsed


def test_live_stand_module_help_resolves_package_without_pythonpath(
    monkeypatch, capsys
) -> None:
    child_environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        if key in os.environ
    }
    if os.name == "posix":
        from scripts import owned_nats_process as process
        from scripts.owned_nats_outage import Deadline

        result = process.run_private_process(
            process.PrivateProcessRequest(
                argv=(sys.executable, "-m", "scripts.live_stand", "--help"),
                cwd=str(ROOT),
                env=child_environment,
                stdout_limit=32 * 1024,
                stderr_limit=32 * 1024,
                input_limit=0,
            ),
            deadline=Deadline.after(10, clock=time.monotonic),
        )
        assert result.outcome is process.ProcessOutcome.EXITED
        assert result.returncode == 0
        assert result.local_cleanup is process.LocalCleanup.CONFIRMED
        help_output = result.stdout
        error_output = result.stderr
    else:
        inherited_pythonpath = {
            str(Path(entry).resolve())
            for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep)
            if entry
        }
        monkeypatch.delenv("PYTHONPATH", raising=False)
        isolated_path = [str(ROOT)]
        for entry in sys.path:
            if not entry:
                continue
            resolved = str(Path(entry).resolve())
            if resolved not in inherited_pythonpath and resolved != isolated_path[0]:
                isolated_path.append(entry)
        monkeypatch.setattr(sys, "path", isolated_path)
        monkeypatch.setattr(sys, "argv", ["scripts.live_stand", "--help"])
        for module_name in ("scripts.live_stand", "scripts.fast_preflight", "scripts"):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

        with pytest.raises(SystemExit) as result:
            runpy.run_module("scripts.live_stand", run_name="__main__", alter_sys=True)

        assert result.value.code == 0
        help_output = capsys.readouterr().out.encode("utf-8")
        error_output = b""

    assert len(help_output) <= 32 * 1024
    assert len(error_output) <= 32 * 1024
    help_text = help_output.decode("utf-8", errors="replace").lower()
    assert "usage:" in help_text
    assert "up" in help_text and "e2e" in help_text and "stop" in help_text


def test_workflow_runs_pr_smoke_and_nightly_manual_full_with_safe_cleanup() -> None:
    source, workflow = _workflow()
    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    assert triggers["workflow_dispatch"] in (None, {}), (
        "manual dispatch must not accept runtime parameters"
    )
    assert "inputs.frozen_rc_sha" not in source
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
    assert concurrency["cancel-in-progress"] is False, (
        "superseding commits must not automatically cancel active owned runs"
    )
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
        if "python -m scripts.live_stand up" in step.get("run", "")
    )
    assert "--stack core" in steps[up_index]["run"]
    assert "--in-place" in steps[up_index]["run"]
    assert '--ref "$STAND_REF"' in steps[up_index]["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in steps[up_index]["run"]
    assert (
        steps[up_index]["env"]["STAND_REF"]
        == "${{ steps.verify-event-commit.outputs.checked_out_sha }}"
    )
    assert npm_install_index < contract_index < browser_setup_index < up_index
    e2e_index = next(
        index
        for index, step in enumerate(steps)
        if "python -m scripts.live_stand e2e" in step.get("run", "")
    )
    assert steps[e2e_index]["id"] == "core-e2e"
    stop_index = next(
        index
        for index, step in enumerate(steps)
        if "python -m scripts.live_stand stop" in step.get("run", "")
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
    assert validation["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
    assert validation["outputs"] == {
        "source_sha": "${{ steps.resolve-frozen-rc.outputs.source_sha }}"
    }
    validation_steps = validation["steps"]
    assert validation_steps[0]["env"]["WORKFLOW_REF"] == "${{ github.ref }}"
    assert '"$WORKFLOW_REF" != "refs/heads/main"' in validation_steps[0]["run"]
    assert "exit 1" in validation_steps[0]["run"]
    validation_checkout = validation_steps[1]
    assert validation_checkout["uses"].startswith("actions/checkout@")
    assert validation_checkout["with"]["ref"] == "${{ github.sha }}"
    assert validation_checkout["with"]["persist-credentials"] is False
    verify_manifest_source = validation_steps[2]
    assert verify_manifest_source["env"]["EXPECTED_WORKFLOW_SHA"] == "${{ github.sha }}"
    assert "git rev-parse HEAD" in verify_manifest_source["run"]
    assert '"$actual_sha" != "$EXPECTED_WORKFLOW_SHA"' in verify_manifest_source["run"]
    resolve_manifest = validation_steps[3]
    assert resolve_manifest["id"] == "resolve-frozen-rc"
    assert (
        "python3 scripts/quality/resolve_frozen_rc_manifest.py"
        in resolve_manifest["run"]
    )
    assert "--manifest quality/frozen-rc.json" in resolve_manifest["run"]
    assert "source_sha=$source_sha" in resolve_manifest["run"]
    assert "GITHUB_OUTPUT" in resolve_manifest["run"]
    frozen = jobs["frozen-rc-full-smoke"]
    assert frozen["if"] == (
        "${{ github.event_name == 'workflow_dispatch' && "
        "github.ref == 'refs/heads/main' && "
        "needs.validate-frozen-rc.result == 'success' }}"
    )
    assert frozen["needs"] == "validate-frozen-rc"
    assert frozen.get("cache-mode") == "none", (
        "manifest-selected frozen-RC code must have no default-branch cache access"
    )
    frozen_uv = next(
        step
        for step in frozen["steps"]
        if step.get("uses", "").startswith("astral-sh/setup-uv@")
    )
    assert frozen_uv["with"].get("enable-cache") is False, (
        "manifest-selected frozen-RC code must not restore or save a shared uv cache"
    )
    frozen_node = next(
        step
        for step in frozen["steps"]
        if step.get("uses", "").startswith("actions/setup-node@")
    )
    assert "cache" not in frozen_node["with"]
    assert "cache-dependency-path" not in frozen_node["with"]
    assert frozen_node["with"]["package-manager-cache"] is False

    core_uv = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("astral-sh/setup-uv@")
    )
    assert core_uv["with"].get("enable-cache") is True
    core_node = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-node@")
    )
    assert core_node["with"].get("cache") == "npm"
    assert "package-manager-cache" not in core_node["with"]

    frozen_checkout = next(
        step
        for step in frozen["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert frozen_checkout["with"]["ref"] == (
        "${{ needs.validate-frozen-rc.outputs.source_sha }}"
    )
    assert frozen_checkout["with"]["persist-credentials"] is False
    frozen_checkout_index = frozen["steps"].index(frozen_checkout)
    assert frozen_checkout_index == 0
    verify_checkout = frozen["steps"][frozen_checkout_index + 1]
    assert verify_checkout["id"] == "verify-frozen-rc"
    assert verify_checkout["env"]["EXPECTED_FROZEN_RC_SHA"] == (
        "${{ needs.validate-frozen-rc.outputs.source_sha }}"
    )
    assert "git rev-parse HEAD" in verify_checkout["run"]
    assert '"$actual_sha" != "$EXPECTED_FROZEN_RC_SHA"' in verify_checkout["run"]
    assert "checked_out_sha=$actual_sha" in verify_checkout["run"]
    assert "GITHUB_STEP_SUMMARY" in verify_checkout["run"]
    frozen_up = next(
        step
        for step in frozen["steps"]
        if "python -m scripts.live_stand up" in step.get("run", "")
    )
    frozen_e2e = next(
        step
        for step in frozen["steps"]
        if "python -m scripts.live_stand e2e" in step.get("run", "")
    )
    assert "--stack full" in frozen_up["run"]
    assert (
        frozen_up["env"]["FROZEN_RC_VERIFIED_SHA"]
        == "${{ steps.verify-frozen-rc.outputs.checked_out_sha }}"
    )
    assert '--ref "$FROZEN_RC_VERIFIED_SHA"' in frozen_up["run"]
    assert "--mode full" in frozen_e2e["run"]
    assert frozen_e2e["id"] == "frozen-rc-e2e"
    assert "--stack core" not in frozen_up["run"]
    assert frozen_up["id"] == "start-frozen-rc"
    frozen_stop = next(
        step
        for step in frozen["steps"]
        if "python -m scripts.live_stand stop" in step.get("run", "")
    )
    assert not re.search(r"\bpython scripts/live_stand\.py (?:up|e2e|stop)\b", source)
    assert "PYTHONPATH" not in source
    assert frozen_stop["id"] == "stop-frozen-rc"
    assert frozen_stop["if"] == (
        "${{ always() && steps.start-frozen-rc.outcome != 'skipped' }}"
    )
    for owned_step in (frozen_up, frozen_e2e, frozen_stop):
        assert "--in-place" in owned_step["run"]
        assert '--state-dir "$LIVE_STATE_DIR"' in owned_step["run"]
        assert "teardown" not in owned_step["run"]
    frozen_steps = frozen["steps"]
    assert frozen_steps.index(verify_checkout) < frozen_steps.index(frozen_up)
    state_selection = frozen_steps[frozen_steps.index(frozen_up) - 1]
    assert state_selection["name"] == "Select unique owned frozen-RC state directory"
    assert "run-%s-%s-frozen-rc-full" in state_selection["run"]
    assert '"$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT"' in state_selection["run"]
    assert "GITHUB_ENV" in state_selection["run"]
    assert all(
        "live_stand.py teardown" not in step.get("run", "") for step in frozen_steps
    )
    assert (
        frozen_steps.index(frozen_up)
        < frozen_steps.index(frozen_e2e)
        < frozen_steps.index(frozen_stop)
    )

    receipt_index = next(
        index
        for index, step in enumerate(frozen["steps"])
        if step.get("name") == "Write the metadata-only frozen-RC receipt"
    )
    receipt = frozen["steps"][receipt_index]
    assert receipt["if"] == "${{ always() }}"
    assert receipt["env"] == {
        "VERIFIED_SHA": "${{ steps.verify-frozen-rc.outputs.checked_out_sha }}",
        "E2E_OUTCOME": "${{ steps.frozen-rc-e2e.outcome }}",
        "STAND_START_OUTCOME": "${{ steps.start-frozen-rc.outcome }}",
        "STAND_STOP_OUTCOME": "${{ steps.stop-frozen-rc.outcome }}",
    }
    assert frozen_steps.index(frozen_stop) < receipt_index
    assert (
        receipt["env"]["VERIFIED_SHA"]
        == "${{ steps.verify-frozen-rc.outputs.checked_out_sha }}"
    )
    for safe_field in (
        '"schema": "ue-live-acceptance-receipt-v1"',
        '"kind": "frozen-rc-full-smoke"',
        '"event": os.environ["GITHUB_EVENT_NAME"]',
        '"stack": "full"',
        '"source_sha": source_sha',
        '"workflow_ref": os.environ["GITHUB_WORKFLOW_REF"]',
        '"run_id": int(os.environ["GITHUB_RUN_ID"])',
        '"run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"])',
        '"outcomes": outcomes',
    ):
        assert safe_field in receipt["run"]
    assert "os.environ.copy" not in receipt["run"]
    assert "os.environ.items" not in receipt["run"]
    assert "stdout" not in receipt["run"] and "stderr" not in receipt["run"]
    receipt_upload = frozen["steps"][receipt_index + 1]
    assert receipt_upload["name"] == "Upload the metadata-only frozen-RC receipt"
    assert receipt_upload["if"] == "${{ always() }}"
    assert receipt_upload["with"]["retention-days"] == 90
    assert "${{ github.run_attempt }}" in receipt_upload["with"]["name"]
    assert receipt_upload["with"]["path"] == "frozen-rc-live-receipt.json"
    assert receipt_upload["with"]["if-no-files-found"] == "error"
    assert (
        "${{ steps.verify-frozen-rc.outputs.checked_out_sha }}"
        in receipt_upload["with"]["name"]
    )
    assert "${{ github.run_id }}" in receipt_upload["with"]["name"]


def test_nats_outage_is_gated_and_receipted_as_metadata_only() -> None:
    _source, workflow = _workflow()
    job = workflow["jobs"]["live-acceptance"]
    steps = job["steps"]

    outage_indices = [
        index for index, step in enumerate(steps) if step.get("id") == "nats-outage"
    ]
    assert len(outage_indices) == 1, (
        "the Core live job must contain exactly one owned NATS outage step"
    )

    outage_index = outage_indices[0]
    outage = steps[outage_index]
    core_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "core-e2e"
    )
    stop_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "stop-stand"
    )

    assert outage_index == core_index + 1
    assert outage_index < stop_index
    assert outage["if"] == (
        "${{ github.event_name == 'pull_request' && "
        "github.event.pull_request.head.repo.full_name == "
        "'egorribun/university_ecosystem' && "
        "github.event.pull_request.head.ref == 'egorribun' && "
        "steps.core-e2e.outcome == 'success' }}"
    )
    assert "python -m scripts.live_stand nats-outage" in outage["run"]
    assert "scripts/live_stand.py nats-outage" not in outage["run"]
    assert "--in-place" in outage["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in outage["run"]
    assert outage.get("timeout-minutes") == 10

    stop = steps[stop_index]
    assert "always()" in stop.get("if", "")
    assert '--state-dir "$LIVE_STATE_DIR"' in stop["run"]

    receipt = next(
        step
        for step in steps
        if step.get("name") == "Write the metadata-only Core receipt"
    )
    assert receipt["if"] == "${{ always() }}"
    assert receipt["env"]["NATS_OUTAGE_OUTCOME"] == "${{ steps.nats-outage.outcome }}"
    assert '"nats_outage": os.environ.get("NATS_OUTAGE_OUTCOME", "")' in receipt["run"]
    assert '"schema": "ue-live-acceptance-receipt-v1"' in receipt["run"]
    assert '"kind": "owned-core-live-acceptance"' in receipt["run"]
    assert (
        'allowed_outcomes = {"success", "failure", "cancelled", "skipped"}'
        in receipt["run"]
    )
    assert (
        "if any(value not in allowed_outcomes for value in outcomes.values())"
        in receipt["run"]
    )
    assert "os.environ.copy" not in receipt["run"]
    assert "os.environ.items" not in receipt["run"]
    assert "stdout" not in receipt["run"] and "stderr" not in receipt["run"]


def test_live_stand_nats_outage_dispatches_once_and_redacts_failures(
    monkeypatch, capsys, tmp_path
) -> None:
    from scripts import live_stand, owned_nats_outage_cli
    from scripts.owned_nats_coordinator import OutageOutcome, OutageResult, OutageStage

    state_dir = str(tmp_path / "ue-live-acceptance" / "run-test-core")
    configured: list[object] = []
    monkeypatch.setattr(
        live_stand, "_configure_state_mode", lambda args: configured.append(args)
    )
    calls: list[tuple[object, object]] = []

    def accept(state: object, *, in_place: object) -> OutageResult:
        calls.append((state, in_place))
        return OutageResult(OutageOutcome.ACCEPTED, OutageStage.COMPLETE)

    monkeypatch.setattr(owned_nats_outage_cli, "run_owned_nats_outage", accept)
    argv = ["nats-outage", "--in-place", "--state-dir", state_dir]
    assert live_stand.main(argv) == 0
    assert calls == [(state_dir, True)]
    assert len(configured) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    def fail_with_private_detail(state: object, *, in_place: object) -> OutageResult:
        calls.append((state, in_place))
        raise RuntimeError("private nonce owner credential detail")

    monkeypatch.setattr(
        owned_nats_outage_cli,
        "run_owned_nats_outage",
        fail_with_private_detail,
    )
    assert live_stand.main(argv) == 2
    assert calls == [(state_dir, True), (state_dir, True)]
    error = capsys.readouterr().err
    assert error == "live_stand: owned NATS acceptance failed reason=runner_exception\n"
    assert "private nonce" not in error
    assert "credential" not in error


def test_live_stand_nats_outage_requires_owned_in_place_state_before_dispatch(
    monkeypatch, capsys
) -> None:
    from scripts import live_stand, owned_nats_outage_cli

    calls: list[tuple[object, object]] = []
    monkeypatch.setattr(live_stand, "_configure_state_mode", lambda _args: None)
    monkeypatch.setattr(
        owned_nats_outage_cli,
        "run_owned_nats_outage",
        lambda state, *, in_place: calls.append((state, in_place)),
    )

    assert live_stand.main(["nats-outage"]) == 2
    assert calls == []
    assert (
        "owned NATS outage requires --in-place and --state-dir"
        in capsys.readouterr().err
    )


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


def test_live_contract_command_runs_real_playwright_deadline_adapter() -> None:
    frontend = ROOT / "frontend"
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    command = package["scripts"]["test:e2e:live:contract"]
    assert command.endswith(
        " && cross-env SKIP_WEBSERVER=true playwright test "
        "tests/e2e/playwright-deadline-adapter.runtime.spec.ts "
        "--project=chromium --workers=1 --retries=0"
    )
    assert (
        frontend / "tests/e2e/playwright-deadline-adapter.runtime.spec.ts"
    ).is_file()


def test_browser_dependency_smoke_is_pr_only_bounded_and_precedes_docker() -> None:
    _, workflow = _workflow()
    steps = workflow["jobs"]["live-acceptance"]["steps"]
    smoke_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("id") == "browser-dependency-smoke"
    )
    browser_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Install locked Chromium and Linux browser dependencies"
    )
    state_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Select unique owned Core state directory"
    )
    smoke = steps[smoke_index]
    assert browser_index < smoke_index < state_index
    assert smoke["if"] == "${{ github.event_name == 'pull_request' }}"
    assert smoke["working-directory"] == "frontend"
    assert smoke["timeout-minutes"] == 3
    assert smoke["run"] == "node scripts/browser-dependency-smoke.mjs"
    assert smoke["env"] == {
        "SOURCE_SHA": "${{ github.sha }}",
        "SMOKE_RUN_ID": "${{ github.run_id }}",
        "SMOKE_RUN_ATTEMPT": "${{ github.run_attempt }}",
    }
    assert not smoke.get("continue-on-error", False)
    upload = steps[smoke_index + 1]
    assert upload["if"] == "${{ success() && github.event_name == 'pull_request' }}"
    assert upload["uses"] == "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    artifact = (
        "browser-dependency-smoke-${{ github.run_id }}-"
        "${{ github.run_attempt }}-${{ github.sha }}"
    )
    assert upload["with"] == {
        "name": artifact,
        "path": "${{ runner.temp }}/" + artifact + ".json",
        "if-no-files-found": "error",
        "overwrite": False,
        "retention-days": 7,
    }
    assert not upload.get("continue-on-error", False)
    for name, job in workflow["jobs"].items():
        if name != "live-acceptance":
            assert all(
                "browser-dependency-smoke" not in step.get("run", "")
                for step in job.get("steps", [])
            )
