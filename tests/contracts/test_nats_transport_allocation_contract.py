"""Contract for allocating the hermetic NATS transport suite outside the backend preflight."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BACKEND_WORKFLOW = ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
TRANSPORT_TEST = ROOT / "tests" / "test_live_nats_transport.py"
TRANSPORT_SELECTOR = "tests/test_live_nats_transport.py"


def _step(steps: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(step for step in steps if step.get("name") == name)


def test_transport_suite_moves_to_contract_job_and_stays_in_full_backend_universe() -> (
    None
):
    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    reusable = yaml.safe_load(BACKEND_WORKFLOW.read_text(encoding="utf-8"))

    frozen_rc = _step(
        reusable["jobs"]["unit-tests"]["steps"],
        "Verify frozen-RC contracts and complete validator coverage",
    )
    assert TRANSPORT_SELECTOR not in frozen_rc["run"].split()

    contract_run = _step(
        ci["jobs"]["contract-tests"]["steps"], "Run contract tests (consumer-side)"
    )["run"]
    assert contract_run.split().count(TRANSPORT_SELECTOR) == 1
    assert ' -k "not integration"' in contract_run
    assert "integration" not in TRANSPORT_TEST.read_text(encoding="utf-8").lower()

    backend_call = ci["jobs"]["backend-tests"]["with"]
    assert backend_call["test-pattern"] == "tests/"
    assert backend_call["num-shards"] == 4
    assert backend_call["coverage-threshold"] == 0

    unit_steps = reusable["jobs"]["unit-tests"]["steps"]
    pytest_step = _step(unit_steps, "Run pytest")
    assert pytest_step["env"]["PYTEST_SHARD_MANIFEST"] == (
        "artifacts/coverage/python/pytest-shard-${{ inputs.shard-id }}.json"
    )
    assert "--cov=app" in pytest_step["run"]
    assert "--cov=alembic/versions" in pytest_step["run"]
    assert "--junitxml=pytest-report.xml" in pytest_step["run"]
    assert "--ignore=tests/test_schemathesis_api.py" in pytest_step["run"]
    assert "--ignore=tests/test_live_nats_transport.py" not in pytest_step["run"]

    provenance = _step(unit_steps, "Write backend shard coverage provenance")["run"]
    assert "pytest-node-manifest" in provenance
    assert "pytest-shard-$SHARD_ID.json" in provenance
    raw_upload = _step(unit_steps, "Upload raw coverage data for aggregation")["with"][
        "path"
    ]
    assert "pytest-shard-${{ inputs.shard-id }}.json" in raw_upload
    junit_upload = _step(unit_steps, "Upload pytest report")["with"]["path"]
    assert junit_upload == "pytest-report.xml"

    aggregate_steps = ci["jobs"]["coverage-policy-gate"]["steps"]
    names = [step.get("name") for step in aggregate_steps]
    assert names.index("Verify backend test-universe manifests") < names.index(
        "Combine Python shard coverage"
    )
