"""Regression contracts for failures observed on the protected main branch."""

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "contract-validation.yml"
)
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


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


def test_primary_ci_openapi_gate_checks_every_generated_directory() -> None:
    """The primary gate must not silently check a non-existent legacy file."""

    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["openapi-verify"]["steps"]
    drift_step = next(
        step
        for step in steps
        if step.get("name") == "Verify generated API types are up to date"
    )
    script = drift_step["run"]

    assert "schema.ts" not in script
    for generated_path in (
        "frontend/openapi.json",
        "frontend/src/api/generated/",
        "frontend/src/tests/mocks/generated/",
    ):
        assert generated_path in script


def test_primary_ci_generates_canonical_tracked_openapi() -> None:
    """Every CI producer must serialize the tracked spec identically."""

    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    generator_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name")
        in {
            "Generate OpenAPI schema",
            "Generate OpenAPI spec from live FastAPI app",
        }
    ]

    assert len(generator_steps) == 2
    for step in generator_steps:
        script = step["run"]
        assert 'json.dumps(app.openapi(), indent=2, sort_keys=True) + "\\n"' in script
        assert 'encoding="utf-8"' in script
