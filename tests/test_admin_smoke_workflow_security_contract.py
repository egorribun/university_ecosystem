from __future__ import annotations

import os
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW_FILE = (
    REPOSITORY_ROOT / ".github" / "workflows" / "admin-smoke-monitoring.yml"
)
WORKFLOW_FILE = Path(os.environ.get("AUD244_WORKFLOW_FILE", DEFAULT_WORKFLOW_FILE))


def test_admin_smoke_checkout_does_not_persist_checkout_credentials() -> None:
    workflow = yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["admin-smoke"]["steps"]
    checkouts = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]

    assert len(checkouts) == 1
    assert checkouts[0].get("with", {}).get("persist-credentials") is False
