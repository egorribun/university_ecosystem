from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DAST_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "dast.yml"
TARGET_EXPRESSION = "${{ inputs.target_url || secrets.DAST_TARGET_URL }}"
EMPTY_TARGET_ERROR = (
    "No target URL configured. Set DAST_TARGET_URL secret or pass target_url input."
)
TRUSTED_REF_ERROR = "DAST scans must run from the protected main ref."


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML parses the YAML 1.1 key ``on`` as boolean True."""

    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _assert_fail_closed_target_preflight(preflight_script: str) -> None:
    """Assert that missing targets fail before a scan can receive one."""

    shell_lines = [
        line.strip()
        for line in preflight_script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert shell_lines == [
        'echo "::add-mask::$TARGET_URL"',
        'if [ -z "$TARGET_URL" ]; then',
        f'echo "::error::{EMPTY_TARGET_ERROR}"',
        "exit 1",
        "fi",
    ]


def test_dast_active_scans_reject_pr_controlled_workflow_sources() -> None:
    """Changing a PR label must never expose the configured scan target."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert "pull_request" not in triggers
    assert "pull_request_target" not in triggers

    trusted_ref = workflow["jobs"]["verify-trusted-ref"]
    assert trusted_ref["permissions"] == {"contents": "read"}
    validation_step = trusted_ref["steps"][0]
    assert validation_step["env"] == {"WORKFLOW_REF": "${{ github.ref }}"}
    assert 'if [ "$WORKFLOW_REF" != "refs/heads/main" ]; then' in validation_step["run"]
    assert f'echo "::error::{TRUSTED_REF_ERROR}"' in validation_step["run"]
    assert "exit 1" in validation_step["run"]

    for job_name in ("nuclei", "zap"):
        job = workflow["jobs"][job_name]
        assert job["needs"] == "verify-trusted-ref"
        assert job["if"] == "${{ needs.verify-trusted-ref.result == 'success' }}"
        checkout = next(
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "main"


def test_target_preflight_blocks_an_empty_target_before_active_scans() -> None:
    """Both scanners mask and reject absent configured targets before scanning."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    scan_steps = {
        "nuclei": ("Validate Nuclei target URL", "Run Nuclei scan"),
        "zap": ("Validate ZAP target URL", "ZAP Full Scan"),
    }
    for job_name, (preflight_name, scan_name) in scan_steps.items():
        steps = workflow["jobs"][job_name]["steps"]
        preflight_index, preflight = next(
            (index, step)
            for index, step in enumerate(steps)
            if step.get("name") == preflight_name
        )
        scan_index = next(
            index for index, step in enumerate(steps) if step.get("name") == scan_name
        )
        assert preflight_index < scan_index
        assert preflight["env"] == {"TARGET_URL": TARGET_EXPRESSION}
        assert preflight.get("continue-on-error", False) is False
        _assert_fail_closed_target_preflight(preflight["run"])


def test_nuclei_nonzero_exit_remains_terminal_after_artifact_uploads() -> None:
    """Network/configuration failures must not be converted into a green DAST run."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    scan_index, scan = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "Run Nuclei scan"
    )
    assert scan.get("continue-on-error", False) is False
    assert "|| true" not in scan["run"]
    assert "nuclei \\" in scan["run"]

    artifact_steps = [
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name")
        in {"Upload results to GitHub Security", "Upload raw JSON findings"}
    ]
    assert len(artifact_steps) == 2
    assert all(
        scan_index < index and step["if"] == "always()"
        for index, step in artifact_steps
    )


def test_zap_preflight_contract_rejects_exit_after_the_empty_target_branch() -> None:
    """A configured target must not inherit the empty-target failure exit."""

    escaped_failure_exit = "\n".join(
        (
            'echo "::add-mask::$TARGET_URL"',
            'if [ -z "$TARGET_URL" ]; then',
            f'  echo "::error::{EMPTY_TARGET_ERROR}"',
            "fi",
            "exit 1",
        )
    )

    with pytest.raises(AssertionError):
        _assert_fail_closed_target_preflight(escaped_failure_exit)


def test_zap_action_keeps_the_authorized_target_and_scan_configuration() -> None:
    """Trusted scheduled/manual scans retain the full active ZAP configuration."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    zap_action = next(
        step
        for step in workflow["jobs"]["zap"]["steps"]
        if step.get("name") == "ZAP Full Scan"
    )

    assert zap_action == {
        "name": "ZAP Full Scan",
        "uses": "zaproxy/action-full-scan@3c58388149901b9a03b7718852c5ba889646c27c",
        "env": {"TARGET_URL": TARGET_EXPRESSION},
        "with": {
            "target": TARGET_EXPRESSION,
            "rules_file_name": ".zap/rules.tsv",
            "cmd_options": "-a -j -T 60",
            "artifact_name": "zap-results-${{ github.run_id }}",
        },
    }
