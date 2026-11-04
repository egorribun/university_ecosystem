"""CI, supply-chain and scanner contracts for AUD-245, 346, 378, 380, 384, 429, 480 and 483.

Each test pins a behaviour of a workflow or scanner policy file that the audit found
unproven. A green result here shows the repository configuration, not a hosted run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"


def _load_workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


# AUD-380 ---------------------------------------------------------------------


def test_semgrep_policy_does_not_claim_a_hosted_ci_job() -> None:
    text = (REPOSITORY_ROOT / ".semgrep.yml").read_text(encoding="utf-8")

    assert "The CI job runs" not in text
    assert "enforced in CI via the 'semgrep' job" not in text
    assert "semgrep-docker" in text
    assert "NO hosted Semgrep CI job" in text


def test_no_workflow_defines_a_semgrep_job() -> None:
    offenders: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name in (workflow or {}).get("jobs", {}):
            if "semgrep" in job_name.lower():
                offenders.append(f"{path.name}:{job_name}")

    assert offenders == [], "a semgrep job exists; update .semgrep.yml accordingly"


# AUD-378 ---------------------------------------------------------------------


def test_slsa_attestation_verification_retries_boundedly_and_fails_closed() -> None:
    job = _load_workflow("ci.yml")["jobs"]["provenance-check"]
    step = _step(job, "Verify SLSA provenance attestation of slsa-verifier")
    run = step["run"]

    assert "continue-on-error" not in step
    assert "|| true" not in run
    assert "for attempt in 1 2 3; do" in run
    assert "timeout --kill-after=15s 120s /tmp/slsa-verifier verify-artifact" in run
    assert "--source-tag v2.7.1" in run
    assert 'if [[ "$verified" -ne 1 ]]; then' in run
    assert "exit 1" in run
    # Three bounded attempts (120s plus 15s kill grace each) with 20s and 40s
    # backoff must fit inside the catalogued 10-minute job budget with headroom.
    attempts_and_backoff_seconds = 3 * (120 + 15) + 20 + 40
    assert job["timeout-minutes"] * 60 >= attempts_and_backoff_seconds + 120


# AUD-346 ---------------------------------------------------------------------


def test_nightly_chaos_dry_run_probes_no_target_and_serves_none() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["chaos-loadtest-orchestrator"]
    names = [step.get("name") for step in job["steps"]]
    runs = [str(step.get("run", "")) for step in job["steps"]]

    assert not any("health target" in str(name).lower() for name in names)
    assert not any("http.server" in run for run in runs)
    assert not any("8000" in run or "127.0.0.1:8000" in run for run in runs)
    dry_run = _step(job, "Run chaos loadtest dry-runs")
    assert "continue-on-error" not in dry_run
    invocations = [
        line for line in dry_run["run"].splitlines() if "run_chaos_loadtest.py" in line
    ]
    assert invocations and all("--dry-run" in line for line in invocations)
    assert all("--target-url" not in line for line in invocations)


# AUD-384 ---------------------------------------------------------------------


def test_slack_notification_configuration_precedes_output_guard() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["notify-failure"]
    names = [step.get("name") for step in job["steps"]]
    detect = _step(job, "Detect optional Slack notification configuration")
    send = _step(job, "Send optional Slack notification")

    assert names.index(
        "Detect optional Slack notification configuration"
    ) < names.index("Send optional Slack notification")
    assert detect["id"] == "slack_config"
    assert detect["env"]["SLACK_WEBHOOK_URL"] == "${{ secrets.SLACK_WEBHOOK_URL }}"
    assert 'if [[ -n "$SLACK_WEBHOOK_URL" ]]; then' in detect["run"]
    assert 'echo "configured=true" >> "$GITHUB_OUTPUT"' in detect["run"]
    assert 'echo "configured=false" >> "$GITHUB_OUTPUT"' in detect["run"]
    assert send["if"] == (
        "${{ !cancelled() && steps.trusted_source.outcome == 'success' "
        "&& steps.slack_config.outputs.configured == 'true' }}"
    )
    assert detect["if"] == (
        "${{ !cancelled() && steps.trusted_source.outcome == 'success' }}"
    )
    assert "continue-on-error" not in detect


def test_slack_notification_retains_trusted_main_and_failure_admission() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["notify-failure"]
    verify = _step(job, "Verify trusted main source")
    detect = _step(job, "Detect optional Slack notification configuration")
    assert verify["id"] == "trusted_source"

    assert job["if"] == (
        "${{ github.ref == 'refs/heads/main' && always() "
        "&& contains(needs.*.result, 'failure') }}"
    )
    assert job["steps"].index(verify) < job["steps"].index(detect)
    assert '"$EVENT_SHA" != "$trusted_sha"' in verify["run"]
    assert '"$WORKFLOW_SHA" != "$trusted_sha"' in verify["run"]
    assert "exit 1" in verify["run"]
    assert "continue-on-error" not in verify


def test_configured_slack_delivery_remains_fail_closed() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["notify-failure"]
    send = _step(job, "Send optional Slack notification")

    assert send["env"]["SLACK_WEBHOOK_URL"] == "${{ secrets.SLACK_WEBHOOK_URL }}"
    assert "continue-on-error" not in job
    assert "continue-on-error" not in send
    assert (
        "curl --fail-with-body --silent --show-error --connect-timeout 10 "
        "--max-time 30 --request POST"
    ) in send["run"]
    assert '"$SLACK_WEBHOOK_URL"' in send["run"]
    assert "|| true" not in send["run"]


# AUD-480 ---------------------------------------------------------------------


def test_npm_gate_blocks_moderate_and_low_without_allowlist_or_omission() -> None:
    job = _load_workflow("reusable-security-audit.yml")["jobs"]["npm-audit"]
    gate = _step(job, "Block moderate and low npm advisories")

    assert "continue-on-error" not in gate
    assert gate["run"].strip().splitlines()[-1].strip() == "npm audit --audit-level=low"
    assert "--omit" not in gate["run"]
    assert "allowlist" not in gate["run"]
    assert "audit_dependencies" not in gate["run"]


def test_npm_high_gate_with_allowlist_remains_blocking() -> None:
    job = _load_workflow("reusable-security-audit.yml")["jobs"]["npm-audit"]
    names = [step.get("name") for step in job["steps"]]
    allowlist_gate = _step(job, "Run npm audit with allowlist")

    assert "continue-on-error" not in allowlist_gate
    assert names.index("Run npm audit with allowlist") < names.index(
        "Block moderate and low npm advisories"
    )


# AUD-429 wiring --------------------------------------------------------------


def test_e2e_run_enables_realtime_specs_against_the_started_backend() -> None:
    workflow = _load_workflow("reusable-e2e-tests.yml")
    job = next(iter(workflow["jobs"].values()))
    step = _step(job, "Run E2E tests")

    assert step["env"]["REALTIME_E2E"] == "true"
    assert step["env"]["VITE_BACKEND_ORIGIN"] == "http://127.0.0.1:8000"
    assert "continue-on-error" not in step


def test_e2e_run_step_follows_the_backend_readiness_gate() -> None:
    workflow = _load_workflow("reusable-e2e-tests.yml")
    job = workflow["jobs"]["e2e"]
    names = [step.get("name") for step in job["steps"]]

    assert names.index("Wait for backend") < names.index("Run E2E tests")


def test_sbom_pr_inventory_remains_read_only_and_validated() -> None:
    job = _load_workflow("sbom.yml")["jobs"]["vuln-gate-pr"]
    validate = _step(job, "Validate OSV scanner result (pull request inventory)")

    assert job["permissions"] == {"contents": "read"}
    assert "::error::OSV scanner exited 0 but reported" in validate["run"]
    assert all("upload" not in str(step.get("uses", "")) for step in job["steps"])
