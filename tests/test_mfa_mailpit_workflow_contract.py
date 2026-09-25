"""Required local-only SMTP acceptance contract for the backend CI lane."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"


def _integration_job() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow["jobs"]["integration-tests"]


def test_postgres_integration_lane_has_pinned_loopback_mailpit_sink() -> None:
    job = _integration_job()
    assert job["if"] == "${{ inputs.run-integration-tests }}"
    mailpit = job["services"]["mailpit"]
    assert re.fullmatch(
        r"ghcr\.io/axllent/mailpit:v1\.31\.1@sha256:[0-9a-f]{64}",
        mailpit["image"],
    )
    assert mailpit["ports"] == ["127.0.0.1:8025:8025", "127.0.0.1:1025:1025"]
    assert "volumes" not in mailpit
    assert "credentials" not in mailpit


def test_mailpit_acceptance_is_required_not_an_implicit_skip() -> None:
    job = _integration_job()
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    ready = next(step for step in steps if step.get("name") == "Wait for Mailpit")
    acceptance = next(
        step for step in steps if step.get("name") == "Verify email MFA outbox delivery"
    )
    assert names.index("Run Alembic migrations") < names.index("Wait for Mailpit")
    assert names.index("Wait for Mailpit") < names.index(
        "Verify email MFA outbox delivery"
    )
    assert ready["timeout-minutes"] == 2
    assert "/readyz" in ready["run"]
    assert "smtplib.SMTP" in ready["run"]
    assert "range(30)" in ready["run"]
    assert "continue-on-error" not in ready
    assert acceptance["env"] == {
        "MFA_TEST_MAILPIT_API": "http://127.0.0.1:8025",
        "MFA_TEST_SMTP_PORT": "1025",
    }
    assert "tests/integration/test_mfa_mailpit_outbox.py" in acceptance["run"]
    assert "--junitxml=" in acceptance["run"]
    assert "skipped" in acceptance["run"]
    assert "tests" in acceptance["run"]
    assert "continue-on-error" not in acceptance
    assert "if" not in acceptance


def test_pr_and_nightly_callers_enable_the_required_integration_lane() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    nightly = (ROOT / ".github" / "workflows" / "nightly-full-gate.yml").read_text(
        encoding="utf-8"
    )
    assert "run-integration: true" in ci
    assert "run-integration-tests: ${{ matrix.run-integration }}" in ci
    assert "run-integration-tests: true" in nightly
