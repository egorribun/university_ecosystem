"""Contract for allocating the hermetic NATS transport suite outside the backend preflight."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BACKEND_WORKFLOW = ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
TRANSPORT_TEST = ROOT / "tests" / "test_live_nats_transport.py"
TRANSPORT_SELECTOR = "tests/test_live_nats_transport.py"
FULL_BACKEND_REUSABLE_CONTRACT_SELECTOR = "tests/test_full_backend_reusable_contract.py"
HEALTH_ENDPOINT_SELECTORS = (
    "tests/test_health_endpoint.py::test_healthcheck_tiered_cache_reports_shared_layer_failure",
    "tests/test_health_endpoint.py::test_healthcheck_storage_probe_recovers_errors_and_caps_success_cache",
)
NATS_CHECKPOINT_SELECTORS = (
    "tests/test_owned_nats_outage_coordinator.py::test_invalid_broker_probe_has_distinct_finite_checkpoint",
    "tests/test_owned_nats_outage_cli.py::test_main_renders_broker_receipt_checkpoint_without_private_evidence",
)
CONSUMER_RUNNER = 'consumer_root="$cohort_root/consumer"'
POLICY_RUNNER = 'policy_root="$cohort_root/security-disposition"'


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
    policy_verification = _step(
        ci["jobs"]["contract-tests"]["steps"],
        "Verify exact security disposition contracts",
    )
    assert policy_verification["if"] == "${{ !cancelled() }}"
    policy_verification_run = policy_verification["run"]
    assert contract_run.split().count(TRANSPORT_SELECTOR) == 1
    assert contract_run.split().count(FULL_BACKEND_REUSABLE_CONTRACT_SELECTOR) == 1
    assert all(
        contract_run.split().count(selector) == 1
        for selector in HEALTH_ENDPOINT_SELECTORS
    )
    assert all(
        contract_run.split().count(selector) == 1
        for selector in NATS_CHECKPOINT_SELECTORS
    )
    assert ' -k "not integration"' in contract_run
    assert ci["jobs"]["contract-tests"]["timeout-minutes"] == 10
    assert contract_run.count('wait "$consumer_pid"') == 1
    assert contract_run.count('wait "$policy_pid"') == 1
    assert "consumer_status != 0 || policy_status != 0" in contract_run
    assert (
        "uv run --frozen --no-sync pytest tests/test_verify_secrets_baseline.py -v"
        in contract_run
    )
    assert contract_run.count("tests/test_verify_secrets_baseline.py") == 1
    assert (
        "exec uv run --frozen --no-sync pytest tests/test_verify_secrets_baseline.py"
        in contract_run
    )
    assert '--basetemp="$1"' in contract_run
    assert '--junitxml="$2"' in contract_run
    assert contract_run.count("setsid env") == 2
    assert CONSUMER_RUNNER in contract_run
    assert POLICY_RUNNER in contract_run
    assert (
        'cohort_root="$RUNNER_TEMP/contract-tests-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"'
        in contract_run
    )
    assert 'mkdir -p "$consumer_root/tmp" "$policy_root/tmp"' in contract_run
    assert "trap cleanup_contract_processes EXIT" in contract_run
    assert "trap 'exit 130' INT" in contract_run
    assert "trap 'exit 143' TERM" in contract_run
    assert "trap 'exit 129' HUP" in contract_run
    assert (
        'terminate_contract_process_groups "$consumer_pid" "$policy_pid"'
        in contract_run
    )
    assert 'kill -0 -- "-$process_pid"' in contract_run
    assert 'kill -TERM -- "-$process_pid"' in contract_run
    assert 'kill -KILL -- "-$process_pid"' in contract_run
    assert 'wait "$process_pid"' in contract_run
    assert "grace_tick < 20" in contract_run
    assert "sleep 0.1" in contract_run
    assert 'TMPDIR="$consumer_root/tmp"' in contract_run
    assert 'TMPDIR="$policy_root/tmp"' in contract_run
    assert '"$consumer_root/basetemp"' in contract_run
    assert '"$consumer_root/junit.xml"' in contract_run
    assert '"$policy_root/basetemp"' in contract_run
    assert '"$policy_root/junit.xml"' in contract_run
    assert 'tee "$3"' in contract_run
    assert '"$consumer_root/pytest.log"' in contract_run
    assert '"$policy_root/pytest.log"' in contract_run
    assert '"$policy_root/status"' in contract_run
    assert (
        '[[ ! -f "$policy_root/status" || ! -f "$policy_root/pytest.log" ]]'
        in policy_verification_run
    )
    assert 'cat "$policy_root/pytest.log"' in policy_verification_run
    assert 'policy_status="$(cat "$policy_root/status")"' in policy_verification_run
    assert 'if [[ "$policy_status" != "0" ]]' in policy_verification_run
    first_runner = contract_run.index("setsid env")
    consumer_runner = contract_run[
        first_runner : contract_run.index("consumer_pid=$!", first_runner)
    ]
    second_runner = contract_run.index("setsid env", first_runner + 1)
    policy_runner = contract_run[
        second_runner : contract_run.index("policy_pid=$!", second_runner)
    ]
    distinct_runner_paths = (consumer_runner, policy_runner)
    assert len(distinct_runner_paths) == 2
    for left, right in (
        ("consumer_root/tmp", "policy_root/tmp"),
        ("consumer_root/basetemp", "policy_root/basetemp"),
        ("consumer_root/junit.xml", "policy_root/junit.xml"),
        ("consumer_root/pytest.log", "policy_root/pytest.log"),
    ):
        assert left in distinct_runner_paths[0]
        assert right in distinct_runner_paths[1]
        assert left != right
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
