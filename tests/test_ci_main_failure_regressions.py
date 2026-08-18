"""Regression contracts for failures observed on the protected main branch."""

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "contract-validation.yml"
)


def test_openapi_drift_gate_only_compares_generated_contract_artifacts() -> None:
    """Unrelated lockfile changes must not be reported as OpenAPI drift."""

    workflow = yaml.safe_load(CONTRACT_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["openapi-typescript-drift"]["steps"]
    drift_step = next(
        step
        for step in steps
        if step.get("name") == "Check for schema-drift / uncommitted changes"
    )
    script = drift_step["run"]

    assert "git diff --exit-code ||" not in script
    assert "git diff --exit-code -- \\" in script
    for generated_path in (
        "frontend/openapi.json",
        "frontend/src/api/generated/",
        "frontend/src/tests/mocks/generated/",
    ):
        assert generated_path in script
