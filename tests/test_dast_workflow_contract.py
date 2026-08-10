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
PR_AUTHORIZATION_GUARD = (
    "${{ github.event_name != 'pull_request' || "
    "github.event.label.name == 'run-dast' }}"
)


def _assert_fail_closed_empty_target_branch(preflight_script: str) -> None:
    """Assert that the empty-target branch returns a non-zero status."""

    shell_lines = [
        line.strip() for line in preflight_script.splitlines() if line.strip()
    ]
    assert shell_lines == [
        'if [ -z "$TARGET_URL" ]; then',
        f'echo "::error::{EMPTY_TARGET_ERROR}"',
        "exit 1",
        "fi",
    ]


def test_zap_preflight_contract_rejects_exit_after_the_empty_target_branch() -> None:
    """A configured target must not inherit the empty-target failure exit."""

    escaped_failure_exit = "\n".join(
        (
            'if [ -z "$TARGET_URL" ]; then',
            f'  echo "::error::{EMPTY_TARGET_ERROR}"',
            "fi",
            "exit 1",
        )
    )

    with pytest.raises(AssertionError):
        _assert_fail_closed_empty_target_branch(escaped_failure_exit)


def test_zap_preflight_blocks_an_empty_target_before_the_active_scan() -> None:
    """ZAP must fail closed before its action can receive an absent target."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    zap_steps = workflow["jobs"]["zap"]["steps"]
    zap_action_index = next(
        index
        for index, step in enumerate(zap_steps)
        if step.get("name") == "ZAP Full Scan"
    )
    preflights = [
        (index, step)
        for index, step in enumerate(zap_steps)
        if step.get("name") == "Validate ZAP target URL"
    ]

    assert preflights, "ZAP must validate its target before the active scan action"
    assert len(preflights) == 1

    preflight_index, preflight = preflights[0]
    preflight_script = preflight["run"]

    assert preflight_index < zap_action_index
    assert preflight["env"] == {"TARGET_URL": TARGET_EXPRESSION}
    assert (
        "continue-on-error" not in preflight or preflight["continue-on-error"] is False
    )
    _assert_fail_closed_empty_target_branch(preflight_script)
    assert "::add-mask::" not in preflight_script

    output_lines = [
        line.strip()
        for line in preflight_script.splitlines()
        if line.strip().startswith(("echo ", "printf "))
    ]
    assert all("$TARGET_URL" not in line for line in output_lines)


def test_zap_action_keeps_the_authorized_target_and_scan_configuration() -> None:
    """A configured target continues through the existing authorized ZAP action."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    zap_job = workflow["jobs"]["zap"]
    zap_action = next(
        step for step in zap_job["steps"] if step.get("name") == "ZAP Full Scan"
    )

    assert zap_job["if"] == PR_AUTHORIZATION_GUARD
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
