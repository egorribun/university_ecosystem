"""AUD-244 focused contract for checkout token lifetime in read-only jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"

READ_ONLY_CHECKOUT_JOBS = (
    ("build-orchestrated-linux.yml", "build-validation"),
    ("cargo-deny.yml", "cargo-deny-crates"),
    ("contract-tests.yml", "consumer"),
    ("contract-tests.yml", "message-provider-verify"),
    ("contract-tests.yml", "pact-provider-verify"),
    ("db-perf-gate.yml", "explain-check"),
    ("generate-openapi.yml", "generate"),
    ("go-lint.yml", "go-sbom"),
    ("nightly-full-gate.yml", "container-integration-cells"),
    ("nightly-full-gate.yml", "load-and-chaos"),
    ("nightly-full-gate.yml", "kyverno-test"),
    ("nightly-full-gate.yml", "miri"),
    ("python-fuzz.yml", "fuzz"),
    ("renovate-config-validation.yml", "renovate-validation"),
    ("reusable-cache-deps.yml", "cache"),
    ("reusable-setup-node.yml", "setup"),
    ("reusable-setup-python.yml", "setup"),
    ("unauthenticated-routes-smoke.yml", "unauthed-smoke"),
    ("visual-audit.yml", "visual-audit"),
)


@pytest.mark.parametrize(
    ("workflow_name", "job_name"),
    READ_ONLY_CHECKOUT_JOBS,
    ids=[f"{workflow}:{job}" for workflow, job in READ_ONLY_CHECKOUT_JOBS],
)
def test_read_only_job_does_not_persist_checkout_credentials(
    workflow_name: str, job_name: str
) -> None:
    """Untrusted later steps must not inherit checkout's GitHub token."""
    workflow: dict[str, Any] = yaml.safe_load(
        (WORKFLOW_ROOT / workflow_name).read_text(encoding="utf-8")
    )
    steps = workflow["jobs"][job_name]["steps"]
    checkouts = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]

    assert len(checkouts) == 1
    assert checkouts[0].get("with", {}).get("persist-credentials") is False
