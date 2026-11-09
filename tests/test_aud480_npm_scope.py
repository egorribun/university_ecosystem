"""Portable contract for the dedicated AUD-480 npm audit proof."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/reusable-security-audit.yml"
PROOF = "tests/aud480_npm_scope_proof.py"


def test_npm_scope_proof_runs_after_tool_setup_and_before_the_blocking_audit() -> None:
    job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["npm-audit"]
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    proof = steps[names.index("Verify npm audit scope with a local registry")]

    assert names.index("Set up Node.js") < names.index("Install dependencies")
    assert names.index("Install dependencies") < names.index(proof["name"])
    assert names.index(proof["name"]) < names.index(
        "Block moderate and low npm advisories"
    )
    assert proof["working-directory"] == "."
    assert proof["shell"] == "bash"
    assert "continue-on-error" not in proof
    assert PROOF in proof["run"]
    assert (ROOT / PROOF).is_file()
