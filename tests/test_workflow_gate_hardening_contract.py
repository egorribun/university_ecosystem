"""Workflow contracts for the CI gate hardening of AUD-244, AUD-381, AUD-384 and AUD-483."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
pytest_plugins = ("pytester",)

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


def _nuclei_export(severity: str) -> str:
    """Representative native JSON export, not JSONL or scanner emulation."""
    return json.dumps(
        [
            {
                "template-id": "workflow-contract-fixture",
                "info": {
                    "name": "Synthetic workflow contract finding",
                    "author": ["workflow-contract"],
                    "tags": ["workflow-contract"],
                    "severity": severity,
                },
                "type": "http",
                "host": "https://example.invalid",
                "matched-at": "https://example.invalid/",
                "timestamp": "2026-10-31T00:00:00Z",
                "matcher-status": True,
            }
        ]
    )


@pytest.fixture
def nuclei_gate(pytester, monkeypatch: pytest.MonkeyPatch):
    job = _load("dast.yml")["jobs"]["nuclei"]
    scan = _step(job, "Run Nuclei scan")["run"]
    gate = _step(job, "Fail on high or critical Nuclei findings")
    script = gate["run"]

    # A producer switch to JSONL requires an explicit fixture-contract review.
    assert "-json-export nuclei-results.json" in scan
    assert gate["shell"] == "bash"
    assert "${{" not in script, "Actions expressions require runner substitution"

    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash, "Real Bash is required to execute the Nuclei gate"
    monkeypatch.chdir(pytester.path)
    monkeypatch.delenv("BASH_ENV", raising=False)

    # Missing jq is a fixture/environment failure, never product RED evidence.
    probe = pytester.run(
        bash,
        "--noprofile",
        "--norc",
        "-e",
        "-o",
        "pipefail",
        "-c",
        "jq --version",
        timeout=20,
    )
    assert probe.ret == 0, (
        "Real jq must be available inside Bash before testing the Nuclei gate:\n"
        + probe.stdout.str()
        + "\n"
        + probe.stderr.str()
    )
    assert probe.stdout.str().strip().startswith("jq-")

    script_path = pytester.path / "actual-nuclei-gate.sh"
    script_path.write_text(script, encoding="utf-8", newline="\n")
    export_path = pytester.path / "nuclei-results.json"

    def run(export: str | None):
        export_path.unlink(missing_ok=True)
        if export is not None:
            export_path.write_text(export, encoding="utf-8", newline="\n")
        return pytester.run(
            bash,
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            script_path.as_posix(),
            timeout=20,
        )

    return run


@pytest.mark.parametrize(
    ("export", "expected_success", "blocking_count"),
    [
        pytest.param("[]", True, None, id="native-empty-array"),
        pytest.param(_nuclei_export("medium"), True, None, id="native-medium"),
        pytest.param(_nuclei_export("high"), False, 1, id="native-high"),
        pytest.param(_nuclei_export("critical"), False, 1, id="native-critical"),
        pytest.param(None, False, None, id="missing-export"),
        pytest.param("", False, None, id="zero-byte-export"),
        pytest.param("[", False, None, id="malformed-json"),
        pytest.param(
            '{"info":{"severity":"medium"}}',
            False,
            None,
            id="wrong-top-level-object",
        ),
    ],
)
def test_dast_nuclei_gate_consumes_native_json_export(
    nuclei_gate,
    export: str | None,
    expected_success: bool,
    blocking_count: int | None,
) -> None:
    result = nuclei_gate(export)
    stdout = result.stdout.str()
    stderr = result.stderr.str()
    diagnostic = f"exit={result.ret}\nstdout:\n{stdout}\nstderr:\n{stderr}"

    assert (result.ret == 0) is expected_success, diagnostic

    clean_message = "Nuclei reported no high or critical findings."
    if expected_success:
        assert clean_message in stdout, diagnostic
    else:
        assert clean_message not in stdout + stderr, diagnostic

    if blocking_count is not None:
        # A jq type error must not satisfy the high/critical negative control.
        assert result.ret == 1, diagnostic
        assert (
            f"Nuclei reported {blocking_count} high or critical" in stderr
        ), diagnostic


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
