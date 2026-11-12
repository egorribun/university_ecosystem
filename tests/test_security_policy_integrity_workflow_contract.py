"""Guard the intentional pull_request_target use in security-policy-integrity.

The workflow runs with base-branch trust and read-only API access so that it
can inspect a pull request's changed-file list without executing pull-request
code. These contracts keep that property from eroding: no checkout of the
candidate, no pull-request head references in executable or `with:` inputs,
no write permissions and no secrets beyond the automatic GITHUB_TOKEN.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "security-policy-integrity.yml"
READ_ONLY = {"contents": "read", "pull-requests": "read"}
HEAD_REFERENCE_PATTERN = re.compile(
    r"github\.event\.pull_request\.head\b|github\.head_ref\b|\bGITHUB_HEAD_REF\b"
)
EXPRESSION_PATTERN = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(_workflow_text())
    assert isinstance(workflow, dict)
    return workflow


def _jobs(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict) and jobs
    return list(jobs.values())


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps = [step for job in _jobs(workflow) for step in job["steps"]]
    assert steps
    return steps


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _walk_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _walk_strings(item)]
    return []


def _walk_values(value: Any) -> list[Any]:
    found: list[Any] = [value]
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(key)
            found.extend(_walk_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_values(item))
    return found


def _trusted_base_violations(workflow: dict[str, Any]) -> list[str]:
    """Return every reason the workflow has left its reviewed trust boundary."""
    violations: list[str] = []

    for step in _steps(workflow):
        uses = str(step.get("uses", ""))
        if uses.lower().startswith("actions/checkout"):
            violations.append(f"checkout step: {step.get('name', uses)}")

        for field in ("run", "with"):
            if field not in step:
                continue
            for text in _walk_strings(step[field]):
                if HEAD_REFERENCE_PATTERN.search(text):
                    violations.append(
                        f"pull-request head reference in {field}: {step.get('name')}"
                    )

    permissions_blocks = [workflow.get("permissions")]
    permissions_blocks.extend(job.get("permissions") for job in _jobs(workflow))
    for block in permissions_blocks:
        if block != READ_ONLY:
            violations.append(f"permissions are not exactly read-only: {block!r}")
    for value in _walk_values(workflow):
        if isinstance(value, str) and value.strip().lower() in {
            "write",
            "write-all",
        }:
            violations.append(f"write permission present: {value}")

    for text in _walk_strings(workflow):
        for expression in EXPRESSION_PATTERN.findall(text):
            remainder = expression.replace("secrets.GITHUB_TOKEN", "")
            if re.search(r"\bsecrets\b", remainder):
                violations.append(f"non-GITHUB_TOKEN secret reference: {expression}")
    return violations


def test_security_policy_integrity_keeps_pull_request_target_trigger() -> None:
    workflow = _workflow()
    # PyYAML parses the bare `on:` key as boolean True.
    triggers = workflow[True]
    assert set(triggers) == {"pull_request_target"}


def test_security_policy_integrity_has_no_checkout_of_candidate_code() -> None:
    workflow = _workflow()
    checkouts = [
        step
        for step in _steps(workflow)
        if str(step.get("uses", "")).lower().startswith("actions/checkout")
    ]
    assert checkouts == []


def test_security_policy_integrity_never_references_pull_request_head_in_run_or_with() -> (
    None
):
    workflow = _workflow()
    for step in _steps(workflow):
        for field in ("run", "with"):
            for text in _walk_strings(step.get(field, {})):
                assert not HEAD_REFERENCE_PATTERN.search(text), (
                    step.get("name"),
                    field,
                )


def test_security_policy_integrity_is_read_only_at_every_level() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == READ_ONLY
    for job in _jobs(workflow):
        assert job["permissions"] == READ_ONLY
    assert not [value for value in _walk_values(workflow) if value == "write"]
    assert not [
        value
        for value in _walk_values(workflow)
        if isinstance(value, str) and value.lower() == "write-all"
    ]


def test_security_policy_integrity_references_only_github_token_secret() -> None:
    workflow = _workflow()
    expressions = [
        expression
        for text in _walk_strings(workflow)
        for expression in EXPRESSION_PATTERN.findall(text)
    ]
    assert expressions, "the trusted-base checker must read the event context"
    for expression in expressions:
        remainder = expression.replace("secrets.GITHUB_TOKEN", "")
        assert not re.search(r"\bsecrets\b", remainder), expression
    # Secrets are only reachable through ${{ }} expressions, which the loop
    # above covers across every run, env and with value in the workflow.


def test_current_workflow_has_no_trusted_base_violations() -> None:
    assert _trusted_base_violations(_workflow()) == []


@pytest.mark.parametrize(
    ("label", "mutate"),
    (
        (
            "checkout",
            lambda w: w["jobs"]["security-policy-integrity"]["steps"].insert(
                0, {"uses": "actions/checkout@v7"}
            ),
        ),
        (
            "head sha in run",
            lambda w: w["jobs"]["security-policy-integrity"]["steps"].append(
                {"run": 'echo "${{ github.event.pull_request.head.sha }}"'}
            ),
        ),
        (
            "head ref in with",
            lambda w: w["jobs"]["security-policy-integrity"]["steps"].append(
                {
                    "uses": "owner/action@v1",
                    "with": {"ref": "${{ github.event.pull_request.head.ref }}"},
                }
            ),
        ),
        (
            "job write permission",
            lambda w: w["jobs"]["security-policy-integrity"]["permissions"].update(
                {"pull-requests": "write"}
            ),
        ),
        (
            "workflow write permission",
            lambda w: w.update({"permissions": {"contents": "write"}}),
        ),
        (
            "extra secret",
            lambda w: w["jobs"]["security-policy-integrity"]["steps"].append(
                {"run": "echo ${{ secrets.DEPLOY_KEY }}"}
            ),
        ),
        (
            "secret toJSON",
            lambda w: w["jobs"]["security-policy-integrity"]["steps"].append(
                {"run": "echo ${{ toJSON(secrets) }}"}
            ),
        ),
    ),
)
def test_guard_rejects_each_trusted_base_violation(label: str, mutate: Any) -> None:
    workflow = _workflow()
    mutate(workflow)
    assert _trusted_base_violations(workflow), label
