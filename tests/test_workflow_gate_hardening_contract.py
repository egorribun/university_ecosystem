"""Workflow contracts for the CI gate hardening of AUD-244, AUD-381, AUD-384 and AUD-483."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

PERSIST_CREDENTIAL_FILES = (
    "auto-merge-patches.yml",
    "chromatic.yml",
    "contract-validation.yml",
    "dast.yml",
    "go-lint.yml",
    "lhci-linux.yml",
    "quality-promotion-check.yml",
    "reusable-full-backend-mutation.yml",
    "reusable-helm-dependencies.yml",
    "sbom.yml",
    "sonar.yml",
    "trufflehog.yml",
)


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _names(job: dict[str, Any]) -> list[str]:
    return [step.get("name", "") for step in job["steps"]]


def test_zizmor_configuration_disables_no_audit() -> None:
    config = yaml.safe_load((ROOT / "zizmor.yml").read_text(encoding="utf-8"))

    assert config == {"rules": {}}


def test_dependabot_auto_merge_gates_on_immutable_pr_author_id() -> None:
    job = _load("auto-merge-patches.yml")["jobs"]["auto-merge"]

    assert job["if"] == "github.event.pull_request.user.id == 49699333"


def test_deploy_and_lhci_default_to_read_only_repository_contents() -> None:
    deploy = _load("deploy.yml")
    lhci = _load("lhci-linux.yml")

    assert deploy["permissions"] == {"contents": "read"}
    assert deploy["jobs"]["validate"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert lhci["permissions"] == {"contents": "read"}


def test_nightly_slack_notification_reads_a_step_output_in_its_condition() -> None:
    job = _load("nightly-full-gate.yml")["jobs"]["notify-failure"]
    detect = next(step for step in job["steps"] if step.get("id") == "slack_config")
    send = _step(job, "Send optional Slack notification")

    assert set(detect["env"]) == {"SLACK_WEBHOOK_URL"}
    assert send["if"] == "${{ steps.slack_config.outputs.configured == 'true' }}"
    assert "env." not in send["if"]
    assert "secrets." not in send["if"]


def test_dast_nuclei_fails_on_high_or_critical_only_after_publication() -> None:
    job = _load("dast.yml")["jobs"]["nuclei"]
    names = _names(job)
    gate = _step(job, "Fail on high or critical Nuclei findings")
    run = gate["run"]

    assert names.index("Upload raw JSON findings") < names.index(gate["name"])
    assert '.info.severity == "high" or .info.severity == "critical"' in run
    assert "exit 1" in run
    assert "[[ ! -f nuclei-results.json ]]" in run  # missing export fails closed


def test_scorecard_fails_on_high_severity_after_sarif_upload() -> None:
    job = _load("scorecard.yml")["jobs"]["analysis"]
    names = _names(job)
    gate = _step(job, "Fail on high-severity Scorecard findings")

    assert names.index("Upload SARIF results to GitHub Security tab") < names.index(
        gate["name"]
    )
    assert "security-severity" in gate["run"]
    assert ">= 7.0" in gate["run"]
    assert "sys.exit(1)" in gate["run"]


def test_sqlmap_writes_result_logs_and_fails_on_confirmed_injection() -> None:
    job = _load("sqlmap.yml")["jobs"]["sqlmap"]
    scan = _step(job, "Run SQLMap Scan on API")["run"]
    gate = _step(job, "Fail on confirmed SQL injection")
    upload = _step(job, "Upload SQLMap result logs")

    assert "--output-dir=sqlmap-output" in scan
    assert gate["if"] == "${{ always() }}"
    assert "identified the following injection point" in gate["run"]
    assert "exit 1" in gate["run"]
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["path"] == "sqlmap-output/"


def test_pull_request_vulnerability_gate_runs_read_only_osv_inventory() -> None:
    job = _load("sbom.yml")["jobs"]["vuln-gate-pr"]
    names = _names(job)
    scan = _step(job, "Scan Go modules for vulnerabilities (pull request inventory)")
    validate = _step(job, "Validate OSV scanner result (pull request inventory)")

    assert "Install osv-scanner (pull request inventory)" in names
    assert job["permissions"] == {"contents": "read"}
    assert "scan source --recursive --format sarif" in scan["run"]
    assert "::error::OSV scanner exited 0 but reported" in validate["run"]
    assert not any("upload" in str(step.get("uses", "")) for step in job["steps"])


def test_hardened_workflows_do_not_persist_checkout_credentials() -> None:
    for workflow_name in PERSIST_CREDENTIAL_FILES:
        workflow = _load(workflow_name)
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                if not str(step.get("uses", "")).startswith("actions/checkout@"):
                    continue
                persist = step.get("with", {}).get("persist-credentials")
                assert persist is False, f"{workflow_name}:{job_name}"
