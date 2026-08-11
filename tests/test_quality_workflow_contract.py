from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.quality.filter_checkov_sarif import filter_suppressed_results

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
ACTIONLINT_CONFIG_PATH = REPOSITORY_ROOT / ".github" / "actionlint.yaml"
LIGHTHOUSE_CONFIG_PATH = REPOSITORY_ROOT / ".lighthouserc.js"
LHCI_SCRIPT_PATH = REPOSITORY_ROOT / "frontend" / "scripts" / "run-lhci.mjs"
CONTRACT_VALIDATION_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "contract-validation.yml"
)
BACKEND_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
)
FRONTEND_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml"
)
E2E_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "reusable-e2e-tests.yml"
GO_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "reusable-go-tests.yml"
SECURITY_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-security-audit.yml"
)
CHECKOV_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "checkov.yml"
PACT_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "contract-tests.yml"
QUALITY_HISTORY_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "quality-history.yml"
)
NIGHTLY_FULL_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "nightly-full-gate.yml"
)
MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "manual-performance-evidence.yml"
)
CHECKOUT_ACTION_PIN = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_ACTION_PIN = (
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
)
UPLOAD_ARTIFACT_ACTION_PIN = (
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
)
CAPTURE_ALLOWED_CONDITIONAL_ORS = (
    'if [[ "$BASE_SHA" == "$ZERO_SHA" || "$CANDIDATE_SHA" == "$ZERO_SHA" ]]; then',
    'if [[ "$PYTHON_BIN" != /* || ! -x "$PYTHON_BIN" ]]; then',
)
COMPARISON_ALLOWED_CONDITIONAL_ORS = (
    'if [[ "$PYTHON_BIN" != /* || ! -x "$PYTHON_BIN" ]]; then',
)
FAIL_CLOSED_SHELL_DISABLE = re.compile(
    r"(?:^|[;\n])\s*set\s+\+(?:[a-z]*e[a-z]*|o\s+(?:errexit|pipefail))(?=\s|;|$)",
    re.IGNORECASE,
)
FORBIDDEN_SHELL_INDIRECTION_OR_OPTION_CONTROL = re.compile(
    r"`|\b(?:eval|builtin)\b|\bcommand\s+set\b|\bset\s+\+",
    re.IGNORECASE,
)
REQUIRED_PERFORMANCE_CONTEXTS = frozenset(
    {
        "Run Go Benchmarks",
        "WS-Hub Go Benchmark Regression Gate",
        "Rust Criterion Benchmarks (pyo3-sanitizer)",
        "Rust Native Optimizer Regression Gate",
    }
)
KYVERNO_POLICY_PATH = REPOSITORY_ROOT / "k8s" / "kyverno" / "cluster-policies.yaml"
KYVERNO_TEST_ROOT = REPOSITORY_ROOT / "k8s" / "kyverno" / "tests"


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML 5/6 parses the YAML 1.1 key ``on`` as boolean True."""

    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def test_ci_triggers_when_draft_pull_request_becomes_ready() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    pull_request = triggers.get("pull_request")

    assert isinstance(pull_request, dict)
    assert set(pull_request["types"]) >= {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    }


def test_required_openapi_compatibility_check_runs_for_every_pull_request() -> None:
    workflow = yaml.safe_load(
        CONTRACT_VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    triggers = _workflow_triggers(workflow)
    pull_request = triggers.get("pull_request")

    assert isinstance(pull_request, dict)
    assert "paths" not in pull_request, (
        "A required check must not be hidden behind a pull_request path filter"
    )
    assert set(pull_request["types"]) >= {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    }
    assert (
        workflow["jobs"]["openapi-diff"]["name"]
        == "OpenAPI Backward Compatibility Check"
    )


def test_quality_policy_gate_is_properly_wired_in_ci() -> None:
    assert CI_WORKFLOW_PATH.exists()

    with open(CI_WORKFLOW_PATH, encoding="utf-8") as file:
        workflow = yaml.safe_load(file)

    jobs = workflow.get("jobs", {})

    # We expect a job named 'coverage-policy-gate' or similar.
    # Let's search for a job that runs both validate_quality_contract.py and normalize_coverage_reports.py.
    policy_job_name = None
    policy_job = None

    for job_name, job_config in jobs.items():
        if job_name == "ci-success":
            continue

        steps = job_config.get("steps", [])
        has_validator = False
        has_normalizer = False

        for step in steps:
            run_cmd = step.get("run", "")
            if "validate_quality_contract.py" in run_cmd:
                has_validator = True
            if "normalize_coverage_reports.py" in run_cmd:
                has_normalizer = True

        if has_validator and has_normalizer:
            policy_job_name = job_name
            policy_job = job_config
            break

    assert policy_job_name is not None, (
        "Could not find a CI job that runs both the contract validator and coverage normalizer"
    )

    # Assert no continue-on-error at the job level
    assert policy_job.get("continue-on-error") is not True, (
        f"Job {policy_job_name} must not have continue-on-error enabled"
    )

    # Assert steps do not have continue-on-error
    for step in policy_job.get("steps", []):
        assert step.get("continue-on-error") is not True, (
            f"Steps in {policy_job_name} must not have continue-on-error enabled"
        )

    # Assert included in the needs of ci-success job
    ci_success = jobs.get("ci-success")
    assert ci_success is not None, "ci-success job is missing"

    needs = ci_success.get("needs", [])
    assert policy_job_name in needs, (
        f"{policy_job_name} must be in the needs list of ci-success"
    )

    # Assert included in the results array of ci-success step
    steps = ci_success.get("steps", [])
    assert len(steps) > 0
    run_script = steps[0].get("run", "")
    expected_result_check = f"${{{{ needs.{policy_job_name}.result }}}}"
    assert expected_result_check in run_script, (
        f"ci-success must assert the result of {policy_job_name}"
    )

    # Assert quality-manifest.json is uploaded as an artifact
    has_upload = False
    for step in policy_job.get("steps", []):
        uses = step.get("uses", "")
        if "upload-artifact" in uses:
            path = step.get("with", {}).get("path", "")
            if "quality-manifest.json" in path or "quality-manifest.json" in str(path):
                has_upload = True

    assert has_upload, (
        f"Job {policy_job_name} must upload quality-manifest.json as an artifact"
    )

    policy_commands = "\n".join(
        str(step.get("run", ""))
        for step in policy_job.get("steps", [])
        if isinstance(step, dict)
    )
    assert "--mutation-registry quality/mutation-exclusions.json" in policy_commands

    # ── Verify quality-inventory-check job ──
    inventory_job = jobs.get("quality-inventory-check")
    assert inventory_job is not None, "quality-inventory-check job is missing in ci.yml"

    # Assert no continue-on-error
    assert inventory_job.get("continue-on-error") is not True, (
        "quality-inventory-check must not have continue-on-error enabled"
    )
    for step in inventory_job.get("steps", []):
        assert step.get("continue-on-error") is not True, (
            "Steps in quality-inventory-check must not have continue-on-error enabled"
        )

    # Assert in needs of ci-success
    assert "quality-inventory-check" in needs, (
        "quality-inventory-check must be in the needs list of ci-success"
    )

    # Assert checked in results array
    expected_inventory_check = "${{ needs.quality-inventory-check.result }}"
    assert expected_inventory_check in run_script, (
        "ci-success must assert the result of quality-inventory-check"
    )

    kyverno_job = jobs.get("kyverno-test")
    assert kyverno_job is not None, "kyverno-test job is missing in ci.yml"
    kyverno_text = "\n".join(
        step.get("run", "")
        for step in kyverno_job.get("steps", [])
        if isinstance(step, dict)
    )
    assert "kyverno test k8s/kyverno/tests/ --require-tests" in kyverno_text
    assert "--retry-all-errors" in kyverno_text
    assert "--connect-timeout 20" in kyverno_text
    assert 'test -s "$archive_path"' in kyverno_text
    assert 'test -s "$checksum_path"' in kyverno_text
    assert 'expected_sha256="$(awk' in kyverno_text
    assert (
        'printf \'%s  %s\\n\' "$expected_sha256" "$archive_path" | sha256sum --check -'
        in kyverno_text
    )
    assert "kyverno-test" in needs
    assert "needs.kyverno-test.result" in run_script
    assert kyverno_job["timeout-minutes"] == 15


def test_kyverno_matrix_covers_every_policy_with_positive_and_negative_cases() -> None:
    policies = {
        document["metadata"]["name"]
        for document in yaml.safe_load_all(
            KYVERNO_POLICY_PATH.read_text(encoding="utf-8")
        )
        if isinstance(document, dict)
        and document.get("kind") == "ClusterPolicy"
        and isinstance(document.get("metadata"), dict)
    }
    suites = {
        path.name
        for path in KYVERNO_TEST_ROOT.iterdir()
        if path.is_dir() and (path / "kyverno-test.yaml").is_file()
    }

    assert policies, "Kyverno policy file must declare at least one ClusterPolicy"
    assert suites == policies, (
        "Every ClusterPolicy must have exactly one executable test suite; "
        f"missing={sorted(policies - suites)}, extra={sorted(suites - policies)}"
    )

    for policy_name in sorted(policies):
        suite_path = KYVERNO_TEST_ROOT / policy_name / "kyverno-test.yaml"
        suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
        assert suite["metadata"]["name"] == policy_name
        assert "../../cluster-policies.yaml" in suite["policies"]
        results = [
            result
            for result in suite.get("results", [])
            if result.get("policy") == policy_name
        ]
        assert any(result.get("result") == "pass" for result in results), (
            f"Kyverno suite {policy_name} needs a passing case"
        )
        assert any(result.get("result") == "fail" for result in results), (
            f"Kyverno suite {policy_name} needs a rejecting case"
        )


def test_pact_workflow_replays_every_cross_process_boundary() -> None:
    workflow = yaml.safe_load(PACT_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert {"consumer", "message-provider-verify", "pact-provider-verify"} <= set(jobs)
    assert jobs["message-provider-verify"]["needs"] == "consumer"
    assert jobs["pact-provider-verify"]["needs"] == "consumer"

    consumer_text = "\n".join(
        str(step.get("run", ""))
        for step in jobs["consumer"]["steps"]
        if isinstance(step, dict)
    )
    artifact_path = str(jobs["consumer"]["steps"][-1]["with"]["path"])
    assert "test_ws_hub_contract.py" in consumer_text
    assert "test_gateway_rest_contract.py" in consumer_text
    assert "test_file_processor_grpc_contract.py" in consumer_text
    assert "ws-hub-university-backend.json" in artifact_path
    assert "gateway-university-backend.json" in artifact_path
    assert "university-backend-file-processor.json" in artifact_path

    message_provider_text = "\n".join(
        str(step.get("run", ""))
        for step in jobs["message-provider-verify"]["steps"]
        if isinstance(step, dict)
    )
    http_provider_text = "\n".join(
        str(step.get("run", ""))
        for step in jobs["pact-provider-verify"]["steps"]
        if isinstance(step, dict)
    )
    assert "services/file-processor" in str(jobs["message-provider-verify"]["steps"])
    assert "go test -tags contract" in message_provider_text
    assert "scripts/quality/verify_pact_provider.py" in http_provider_text
    assert "uvicorn app.main:app" in http_provider_text


def test_cross_browser_e2e_is_advisory_during_stabilization() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    cross_browser = jobs["e2e-tests-cross-browser"]

    # Reusable-workflow callers cannot use continue-on-error directly. The
    # reusable job receives an explicit advisory input and applies the policy
    # at the executable job level.
    assert cross_browser.get("continue-on-error") is not True
    assert cross_browser["with"]["advisory"] is True
    assert cross_browser["strategy"]["matrix"]["browser"] == [
        "firefox",
        "webkit",
        "mobile-webkit",
    ]
    assert "e2e-tests-cross-browser" in jobs["ci-success"]["needs"]
    blocking_script = jobs["ci-success"]["steps"][0]["run"]
    assert "needs.e2e-tests-cross-browser.result" not in blocking_script


def test_trivy_job_id_matches_stable_code_scanning_configuration() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert "docker-security-scan" in jobs
    assert "docker-security" not in jobs
    assert "docker-security-scan" in jobs["ci-success"]["needs"]

    blocking_script = jobs["ci-success"]["steps"][0]["run"]
    assert "needs.docker-security-scan.result" in blocking_script
    assert "needs.docker-security.result" not in blocking_script


def test_trivy_sarif_categories_preserve_main_configuration_keys() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    image_upload = next(
        step
        for step in ci_workflow["jobs"]["docker-security-scan"]["steps"]
        if step.get("uses", "").startswith("github/codeql-action/upload-sarif@")
    )
    assert image_upload["with"]["category"] == (
        ".github/workflows/ci.yml:docker-security-scan"
    )

    security_workflow = yaml.safe_load(
        SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    security_uploads = [
        step
        for step in security_workflow["jobs"]["docker-security"]["steps"]
        if step.get("uses", "").startswith("github/codeql-action/upload-sarif@")
    ]
    categories_by_sarif = {
        step["with"]["sarif_file"]: step["with"]["category"]
        for step in security_uploads
    }
    assert categories_by_sarif == {
        "trivy-fs.sarif": ".github/workflows/ci.yml:docker-security",
        "trivy-config.sarif": "trivy-config",
    }

    trivy_steps = [
        step
        for step in security_workflow["jobs"]["docker-security"]["steps"]
        if step.get("uses", "").startswith("aquasecurity/trivy-action@")
    ]
    assert trivy_steps
    assert all(
        step["with"]["limit-severities-for-sarif"] is True
        for step in trivy_steps
        if step["with"].get("format") == "sarif"
    )

    image_scan = next(
        step
        for step in ci_workflow["jobs"]["docker-security-scan"]["steps"]
        if step.get("uses", "").startswith("aquasecurity/trivy-action@")
    )
    assert image_scan["with"]["limit-severities-for-sarif"] is True


def test_iac_scan_exceptions_use_supported_scoped_syntax() -> None:
    """Keep documented IaC exceptions active instead of silently ignored."""

    exception_files = (
        REPOSITORY_ROOT / ".github" / "workflows" / "lhci-linux.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "dast.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "build-orchestrated-linux.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "visual-audit.yml",
        REPOSITORY_ROOT / "Dockerfile.test",
        REPOSITORY_ROOT / "Dockerfile.protogen",
        REPOSITORY_ROOT / "infra" / "oss-fuzz" / "Dockerfile",
        REPOSITORY_ROOT / "k8s" / "backend" / "deployment.yaml",
        REPOSITORY_ROOT / "k8s" / "frontend" / "deployment.yaml",
        REPOSITORY_ROOT / "k8s" / "frontend" / "canary" / "deployment-stable.yaml",
    )
    assert all(
        "# checkov:skip" not in path.read_text(encoding="utf-8")
        for path in exception_files
    )

    security_workflow = yaml.safe_load(
        SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    config_scan = next(
        step
        for step in security_workflow["jobs"]["docker-security"]["steps"]
        if step.get("name") == "Run Trivy configuration scanner (IaC)"
    )
    assert config_scan["with"]["trivyignores"] == ".trivyignore.yaml"

    trivy_ignore = yaml.safe_load(
        (REPOSITORY_ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
    )
    assert [entry["id"] for entry in trivy_ignore["misconfigurations"]] == [
        "KSV-0012",
        "KSV-0104",
        "KSV-0023",
        "KSV-0001",
        "KSV-0118",
        "KSV-0014",
        "KSV-0047",
        "KSV-0017",
        "KSV-0009",
        "KSV-0010",
        "AVD-DS-0002",
    ]
    assert trivy_ignore["misconfigurations"][-1] == {
        "id": "AVD-DS-0002",
        "paths": ["infra/oss-fuzz/Dockerfile"],
        "statement": (
            "OSS-Fuzz controls this disposable builder image and requires its "
            "base-builder execution model; the image is never deployed or used as a "
            "runtime container."
        ),
    }


def test_checkov_sarif_filter_removes_only_source_backed_suppressions(tmp_path) -> None:
    suppressed = tmp_path / "suppressed.yml"
    suppressed.write_text(
        "workflow_dispatch: #checkov:skip=CKV_GHA_7:manual input is intentional\n",
        encoding="utf-8",
    )
    unsuppressed = tmp_path / "unsuppressed.yml"
    unsuppressed.write_text("workflow_dispatch:\n", encoding="utf-8")
    annotated = tmp_path / "annotated.yml"
    annotated.write_text(
        "checkov.io/skip1: CKV_K8S_43=the deployment pipeline pins the image\n",
        encoding="utf-8",
    )

    def result(path: str, rule_id: str = "CKV_GHA_7") -> dict[str, object]:
        return {
            "ruleId": rule_id,
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": path},
                        "region": {"startLine": 1, "endLine": 1},
                    }
                }
            ],
        }

    document: dict[str, object] = {
        "runs": [
            {
                "results": [
                    result("suppressed.yml"),
                    result("annotated.yml", "CKV_K8S_43"),
                    result("unsuppressed.yml"),
                ]
            }
        ]
    }

    assert filter_suppressed_results(document, tmp_path) == 2
    assert len(document["runs"][0]["results"]) == 1
    assert (
        document["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        == "unsuppressed.yml"
    )


def test_checkov_workflow_filters_sarif_before_upload() -> None:
    workflow = yaml.safe_load(CHECKOV_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["checkov"]["steps"]
    filter_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Remove inline-suppressed results from SARIF"
    )
    upload_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("github/codeql-action/upload-sarif@")
    )
    assert filter_index < upload_index
    assert steps[filter_index]["if"] == "always()"
    assert steps[filter_index]["run"] == (
        "python scripts/quality/filter_checkov_sarif.py results.sarif "
        "--output-path filtered-results.sarif"
    )
    assert steps[upload_index]["with"]["sarif_file"] == "filtered-results.sarif"


def test_e2e_coverage_is_chromium_opt_in_and_codecov_wired() -> None:
    e2e_workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    call = _workflow_triggers(e2e_workflow)["workflow_call"]
    inputs = call["inputs"]
    assert inputs["collect-coverage"]["default"] is False
    assert "CODECOV_TOKEN" in call["secrets"]

    steps = e2e_workflow["jobs"]["e2e"]["steps"]
    merge_step = next(
        step
        for step in steps
        if step.get("name") == "Merge Chromium JavaScript coverage"
    )
    assert "inputs.collect-coverage" in merge_step["if"]
    assert "inputs.browser == 'chromium'" in merge_step["if"]
    assert "merge-playwright-coverage.mjs" in merge_step["run"]
    merger_test_step = next(
        step for step in steps if step.get("name") == "Verify E2E coverage merger"
    )
    assert merger_test_step["run"] == "npm run test:e2e:coverage-tool"

    codecov_step = next(
        step for step in steps if step.get("name") == "Upload E2E coverage to Codecov"
    )
    assert "inputs.browser == 'chromium'" in codecov_step["if"]
    assert codecov_step["with"]["flags"] == "frontend"
    assert codecov_step["with"]["files"] == "./frontend/coverage/e2e/lcov.info"

    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert ci_workflow["jobs"]["e2e-tests"]["with"]["collect-coverage"] is True
    assert (
        "collect-coverage" not in ci_workflow["jobs"]["e2e-tests-cross-browser"]["with"]
    )


def test_e2e_postgres_healthcheck_uses_declared_credentials() -> None:
    workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    options = workflow["jobs"]["e2e"]["services"]["postgres"]["options"]

    assert "pg_isready -U test -d test_e2e" in options
    assert "--health-cmd pg_isready\n" not in options


def test_e2e_linux_build_memory_budget_keeps_both_limits_bounded() -> None:
    workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["e2e"]
    env = job["env"]

    assert env["FRONTEND_BUILD_MAX_RSS_MB"] == "2048"
    assert env["FRONTEND_BUILD_MAX_OLD_SPACE_MB"] == "1536"


def test_e2e_wasm_build_retries_transient_binaryen_downloads() -> None:
    workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["e2e"]
    assert job["env"]["SKIP_WASM_BUILD"] == "1"

    build_step = next(
        step for step in job["steps"] if step.get("name") == "Build WASM modules"
    )
    run = build_step["run"]
    assert build_step["env"]["SKIP_WASM_BUILD"] == "0"
    assert "for attempt in 1 2 3" in run
    assert "wasm-pack build rust-crypto --target web --release" in run
    assert "wasm-pack build wasm-sanitizer --target web --release" in run
    assert "sleep 10" in run
    assert "WASM build failed after 3 attempts" in run


def test_cross_browser_navigation_retries_only_transient_abort_errors() -> None:
    source = (
        REPOSITORY_ROOT / "frontend" / "tests" / "e2e" / "utils" / "navigation.ts"
    ).read_text(encoding="utf-8")

    assert "NS_BINDING_ABORTED" in source
    assert "net::ERR_ABORTED" in source
    assert "MAX_ATTEMPTS = 3" in source
    assert "waitForTimeout(250 * attempt)" in source
    assert "if (!TRANSIENT_NAVIGATION_ERROR.test(message)" in source


def test_go_codecov_flags_match_component_contract() -> None:
    workflow = yaml.safe_load(GO_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["test"]["steps"]
    resolver = next(
        step for step in steps if step.get("name") == "Resolve Codecov component flag"
    )
    resolver_script = resolver["run"]
    assert 'services/gateway) flag="go-gateway"' in resolver_script
    assert 'services/ws-hub) flag="go-ws-hub"' in resolver_script
    assert 'services/file-processor) flag="go-file-processor"' in resolver_script

    upload = next(
        step for step in steps if step.get("name") == "Upload coverage to Codecov"
    )
    assert "steps.codecov-flag.outputs.flag" in upload["if"]
    assert upload["with"]["flags"] == "${{ steps.codecov-flag.outputs.flag }}"


def test_advisory_integration_and_chaos_jobs_are_not_blocking() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    blocking_script = workflow["jobs"]["ci-success"]["steps"][0]["run"]

    for job_name in (
        "go-integration-ws-hub",
        "go-integration-file-processor",
        "go-integration-gateway",
        "load-and-chaos-tests",
    ):
        assert f"needs.{job_name}.result" not in blocking_script


def test_incremental_mutation_budget_matches_declared_gate() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["mutation-tests-incremental"]
    run_step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Run incremental mutmut (blocking, 25-minute budget)"
    )
    assert job["strategy"]["matrix"]["shard"] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
    ]
    assert "timeout --kill-after=30s 25m" in run_step["run"]
    job_text = "\n".join(
        step.get("run", "") for step in job["steps"] if isinstance(step, dict)
    )
    assert "grep -E '^app/.*\\.py$'" in job_text
    assert "matrix.shard" in job_text
    assert "scripts/plan_mutmut_shards.py" in job_text
    assert "--changed-files /tmp/changed_py.txt" in job_text
    assert "--num-shards 16" in job_text
    assert '"${MUTANT_NAMES[@]}"' in job_text
    assert "awk -v shard" not in job_text
    assert "grep '^app/core/tenant\\.py$'" not in job_text


def test_incremental_mutation_stats_are_sharded_and_merged_before_execution() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    stats_job = jobs["mutation-tests-stats"]
    mutation_job = jobs["mutation-tests-incremental"]

    assert stats_job["strategy"]["matrix"]["stats_shard"] == [0, 1, 2, 3]
    assert stats_job["timeout-minutes"] == 25
    assert "pre-commit-check" in stats_job["needs"]
    stats_text = "\n".join(
        step.get("run", "") for step in stats_job["steps"] if isinstance(step, dict)
    )
    assert "scripts/mutmut_stats_shard.py" in stats_text
    assert "--shard-id" in stats_text
    assert "--num-shards 4" in stats_text
    helper_text = (REPOSITORY_ROOT / "scripts/mutmut_stats_shard.py").read_text(
        encoding="utf-8"
    )
    assert "config = mutmut.config" in helper_text
    assert "mutmut_cli.config" not in helper_text

    assert "mutation-tests-stats" in mutation_job["needs"]
    mutation_text = "\n".join(
        step.get("run", "") for step in mutation_job["steps"] if isinstance(step, dict)
    )
    download_step = next(
        step
        for step in mutation_job["steps"]
        if step.get("uses", "").startswith("actions/download-artifact")
    )
    assert download_step["with"]["pattern"] == "mutmut-stats-*"
    assert "scripts/merge_mutmut_stats.py" in mutation_text
    assert "mutants/mutmut-stats.json" in mutation_text
    assert "mutation-tests-stats" in jobs["ci-success"]["needs"]
    assert "needs.mutation-tests-stats.result" in jobs["ci-success"]["steps"][0]["run"]


def test_quality_history_archives_manifests_and_renders_dashboard() -> None:
    workflow = yaml.safe_load(QUALITY_HISTORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert triggers["schedule"][0]["cron"] == "30 2 * * *"
    assert workflow["permissions"]["actions"] == "read"
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["permissions"]["pull-requests"] == "write"
    text = "\n".join(
        step.get("run", "")
        for step in workflow["jobs"]["archive"]["steps"]
        if isinstance(step, dict)
    )
    assert "gh run download" in text
    assert "artifacts/quality/history" in text
    assert "generate_dashboard.py" in text
    assert "git push --set-upstream origin" in text
    assert "gh pr create" in text


def test_miri_workflow_scopes_to_pure_rust_crate_targets() -> None:
    workflow = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["miri"]
    assert job["timeout-minutes"] == 60
    run_text = "\n".join(
        str(step.get("run", "")) for step in job["steps"] if isinstance(step, dict)
    )
    assert "cargo +nightly miri setup" in run_text
    assert "cargo +nightly miri test --locked" in run_text
    assert "--test-threads=1" in run_text
    assert "crates/pyo3-sanitizer/Cargo.toml" in run_text
    assert "frontend/rust-crypto/Cargo.toml" in run_text
    assert "components: miri" in NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8")

    pyo3_source = (REPOSITORY_ROOT / "crates/pyo3-sanitizer/src/lib.rs").read_text(
        encoding="utf-8"
    )
    for function_name in (
        "test_panic_boundary_catches_rust_panic",
        "test_panic_formatting_coverage",
        "test_pyo3_bindings_coverage",
    ):
        assert f"#[cfg(not(miri))]\n    #[test]\n    fn {function_name}" in pyo3_source


def test_backend_ci_uses_historical_duration_shards_and_aggregates_coverage() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    backend_job = ci_workflow["jobs"]["backend-tests"]
    matrix = backend_job["strategy"]["matrix"]["include"]
    assert [entry["shard"] for entry in matrix] == [0, 1, 2, 3]
    assert all(entry["python-version"] == "3.14" for entry in matrix)
    assert backend_job["with"]["shard-id"] == "${{ matrix.shard }}"
    assert backend_job["with"]["num-shards"] == 4

    policy_job = ci_workflow["jobs"]["coverage-policy-gate"]
    policy_text = "\n".join(
        step.get("run", "") for step in policy_job["steps"] if isinstance(step, dict)
    )
    download_steps = [
        step
        for step in policy_job["steps"]
        if step.get("uses", "").startswith("actions/download-artifact")
    ]
    python_download = next(
        step
        for step in download_steps
        if "backend-coverage-data" in str(step.get("with", {}))
    )
    assert python_download["with"]["merge-multiple"] is True
    assert "coverage combine" in policy_text
    assert "--python-xml coverage.xml" in policy_text
    assert (
        "--rust-report rust-crypto=artifacts/coverage/rust/rust-crypto/llvm.json"
        in policy_text
    )
    rust_tests_job = ci_workflow["jobs"]["rust-tests"]
    rust_crypto_step = next(
        step
        for step in rust_tests_job["steps"]
        if step.get("name", "").startswith("rust-crypto")
        and "coverage" in step.get("name", "")
    )
    assert "cargo llvm-cov --all-targets" in rust_crypto_step["run"]

    backend_workflow = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    inputs = _workflow_triggers(backend_workflow)["workflow_call"]["inputs"]
    assert inputs["run-unit-tests"]["default"] is True
    assert inputs["shard-id"]["default"] == -1
    assert inputs["num-shards"]["default"] == 1
    assert inputs["integration-shard-id"]["default"] == -1
    assert inputs["integration-num-shards"]["default"] == 1
    assert inputs["integration-test-pattern"]["default"] == "tests/integration/"
    run_step = next(
        step
        for step in backend_workflow["jobs"]["unit-tests"]["steps"]
        if step.get("name") == "Run pytest"
    )
    assert "--shard-id=${{ inputs.shard-id }}" in run_step["run"]
    assert "--num-shards=${{ inputs.num-shards }}" in run_step["run"]
    integration_run_step = next(
        step
        for step in backend_workflow["jobs"]["integration-tests"]["steps"]
        if step.get("name") == "Run integration tests"
    )
    assert "INTEGRATION_SHARD_ID" in integration_run_step["run"]
    assert "INTEGRATION_NUM_SHARDS" in integration_run_step["run"]
    assert "$env:INTEGRATION_TEST_PATTERN" in integration_run_step["run"]
    assert '"${{ inputs.integration-test-pattern }}"' not in integration_run_step["run"]
    assert integration_run_step["env"] == {
        "INTEGRATION_SHARD_ID": "${{ inputs.integration-shard-id }}",
        "INTEGRATION_NUM_SHARDS": "${{ inputs.integration-num-shards }}",
        "INTEGRATION_TEST_PATTERN": "${{ inputs.integration-test-pattern }}",
    }
    assert backend_workflow["jobs"]["integration-tests"]["timeout-minutes"] == 60
    integration_steps = backend_workflow["jobs"]["integration-tests"]["steps"]
    image_prep_step = next(
        step
        for step in integration_steps
        if step.get("name") == "Pre-pull testcontainer images with bounded retries"
    )
    image_prep_text = image_prep_step["run"]
    assert "nats:2.10-alpine" in image_prep_text
    assert "postgres:15-alpine" in image_prep_text
    assert "redis:7-alpine" in image_prep_text
    assert "pgvector/pgvector:pg17" in image_prep_text
    assert "docker image inspect" in image_prep_text
    assert "docker pull" in image_prep_text
    assert "$maxAttempts = 5" in image_prep_text
    assert "Start-Sleep" in image_prep_text
    assert (
        yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"][
            "backend-tests"
        ]["with"]["integration-test-pattern"]
        == "tests/integration/"
    )
    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert (
        nightly["jobs"]["backend-integration"]["with"]["integration-test-pattern"]
        == "tests/integration/"
    )


def test_reusable_quality_jobs_have_bounded_execution() -> None:
    backend = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert backend["jobs"]["unit-tests"]["timeout-minutes"] == 45
    assert backend["jobs"]["integration-tests"]["timeout-minutes"] == 60

    frontend = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert {
        name: frontend["jobs"][name]["timeout-minutes"]
        for name in (
            "unit-tests",
            "lint",
            "build",
            "bundle-analysis",
            "lighthouse-shards",
            "lighthouse",
        )
    } == {
        "unit-tests": 45,
        "lint": 30,
        "build": 45,
        "bundle-analysis": 15,
        "lighthouse-shards": 20,
        "lighthouse": 10,
    }

    lighthouse_shards = frontend["jobs"]["lighthouse-shards"]
    assert lighthouse_shards["strategy"]["fail-fast"] is False
    assert [
        entry["shard"] for entry in lighthouse_shards["strategy"]["matrix"]["include"]
    ] == [
        "core",
        "content",
        "realtime",
        "fallback",
    ]
    assert lighthouse_shards["env"]["LHCI_URLS"] == "${{ matrix.urls }}"
    assert lighthouse_shards["env"]["LHCI_SKIP_SYSTEM_DEPS"] == "1"
    shard_upload = next(
        step
        for step in lighthouse_shards["steps"]
        if step.get("name") == "Upload Lighthouse shard reports"
    )
    assert shard_upload["with"]["include-hidden-files"] is True
    assert shard_upload["with"]["name"] == "lighthouse-reports-${{ matrix.shard }}"

    lighthouse_aggregate = frontend["jobs"]["lighthouse"]
    assert lighthouse_aggregate["needs"] == "lighthouse-shards"
    assert "always()" in lighthouse_aggregate["if"]
    assert lighthouse_aggregate["name"] == "Lighthouse Audit"
    merge_text = "\n".join(
        step.get("run", "")
        for step in lighthouse_aggregate["steps"]
        if isinstance(step, dict)
    )
    assert "lhr-${counter}.json" in merge_text
    merged_upload = next(
        step
        for step in lighthouse_aggregate["steps"]
        if step.get("name") == "Upload merged Lighthouse reports"
    )
    assert merged_upload["with"]["name"] == "lighthouse-reports"
    assert merged_upload["with"]["include-hidden-files"] is True

    go = yaml.safe_load(GO_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert go["jobs"]["test"]["timeout-minutes"] == 60
    assert go["jobs"]["lint"]["timeout-minutes"] == 20
    go_lint_action = next(
        step
        for step in go["jobs"]["lint"]["steps"]
        if step.get("uses", "").startswith("golangci/golangci-lint-action@")
    )
    assert go_lint_action["with"]["verify"] is False

    security = yaml.safe_load(SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert {
        name: security["jobs"][name]["timeout-minutes"]
        for name in (
            "pip-audit",
            "npm-audit",
            "docker-security",
            "govulncheck",
            "sbom",
            "detect-secrets-baseline",
            "semgrep",
        )
    } == {
        "pip-audit": 20,
        "npm-audit": 25,
        "docker-security": 30,
        "govulncheck": 20,
        "sbom": 15,
        "detect-secrets-baseline": 15,
        "semgrep": 20,
    }

    semgrep_steps = security["jobs"]["semgrep"]["steps"]
    semgrep_run = next(
        step for step in semgrep_steps if step.get("name") == "Run Semgrep SAST"
    )
    semgrep_run_text = semgrep_run["run"]
    assert (
        "semgrep scan --config auto --baseline-commit origin/main" in semgrep_run_text
    )
    assert "--sarif --sarif-output=semgrep.sarif" in semgrep_run_text
    assert "SEMGREP_SCAN_STATUS" in semgrep_run_text
    assert any(
        step.get("name") == "Fail if Semgrep reported findings or scan errors"
        and step.get("if") == "always()"
        for step in semgrep_steps
    )
    semgrep_upload = next(
        step
        for step in semgrep_steps
        if step.get("name") == "Upload SARIF to GitHub Advanced Security"
    )
    assert "continue-on-error" not in semgrep_upload


def test_frontend_coverage_is_merged_after_all_vitest_shards() -> None:
    workflow = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    shard_job = workflow["jobs"]["unit-tests-shard"]
    aggregate_job = workflow["jobs"]["unit-tests"]

    assert shard_job["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]
    shard_text = "\n".join(str(step.get("run", "")) for step in shard_job["steps"])
    assert "npm run test:ci -- --shard=${{ matrix.shard }}/4" in shard_text
    shard_artifacts = "\n".join(
        str(step.get("with", {}).get("name", ""))
        for step in shard_job["steps"]
        if isinstance(step, dict)
    )
    assert "frontend-coverage-shard-${{ matrix.shard }}" in shard_artifacts
    assert aggregate_job["needs"] == "unit-tests-shard"
    assert aggregate_job["if"] == "${{ always() }}"

    aggregate_steps = aggregate_job["steps"]
    aggregate_checkout = next(
        step
        for step in aggregate_steps
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert aggregate_checkout["with"]["fetch-depth"] == 0
    merge_step = next(
        step
        for step in aggregate_steps
        if step.get("name") == "Merge frontend coverage shards"
    )
    assert (
        REPOSITORY_ROOT / "frontend" / "scripts" / "merge-vitest-coverage.mjs"
    ).is_file()
    assert "scripts/merge-vitest-coverage.mjs" in merge_step["run"]
    assert "--input=.coverage-shards" in merge_step["run"]
    assert "--output=coverage" in merge_step["run"]
    assert "--expected-shards=4" in merge_step["run"]
    assert any(
        step.get("with", {}).get("pattern") == "frontend-coverage-shard-*"
        for step in aggregate_steps
        if isinstance(step, dict)
    )
    assert any(
        step.get("with", {}).get("name") == "frontend-coverage"
        for step in aggregate_steps
        if isinstance(step, dict)
    )


def test_weekly_duration_refresh_is_a_reviewable_bot_pr() -> None:
    workflow_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "weekly-test-durations.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert _workflow_triggers(workflow)["schedule"][0]["cron"] == "0 4 * * 1"
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["permissions"]["pull-requests"] == "write"
    step_text = "\n".join(
        step.get("run", "")
        for step in workflow["jobs"]["refresh"]["steps"]
        if isinstance(step, dict)
    )
    assert "update_test_durations.py" in step_text
    assert "gh pr create" in step_text


def test_nightly_full_gate_contains_the_long_running_quality_suites() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "nightly-full-gate.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert triggers["schedule"][0]["cron"] == "0 1 * * *"
    jobs = workflow["jobs"]
    assert {
        "mutation-tests-full",
        "frontend-mutation-tests-full",
        "backend-full",
        "go-integration",
        "browser-matrix",
        "load-and-chaos",
        "kyverno-test",
        "miri",
        "notify-failure",
        "container-integration-cells",
    } <= set(jobs)
    mutation_steps = jobs["mutation-tests-full"]["steps"]
    export_step = next(
        step
        for step in mutation_steps
        if step.get("name") == "Export and gate mutation statistics"
    )
    assert "export-cicd-stats" in export_step["run"]
    assert jobs["go-integration"]["strategy"]["matrix"]["service-directory"] == [
        "services/gateway",
        "services/ws-hub",
        "services/file-processor",
    ]
    assert jobs["backend-integration"]["strategy"]["matrix"]["integration-shard"] == [
        0,
        1,
        2,
        3,
    ]
    assert jobs["backend-full"]["strategy"]["matrix"]["unit-shard"] == [0, 1, 2, 3]
    assert jobs["backend-full"]["with"]["run-unit-tests"] is True
    assert jobs["backend-full"]["with"]["num-shards"] == 4
    assert jobs["backend-integration"]["with"]["run-unit-tests"] is False
    assert jobs["backend-integration"]["with"]["integration-num-shards"] == 4
    assert "backend-integration" in jobs["notify-failure"]["needs"]
    cell_job = jobs["container-integration-cells"]
    assert cell_job["env"]["USE_TESTCONTAINERS_MINIO"] == "1"
    assert cell_job["env"]["USE_TESTCONTAINERS_SPICEDB"] == "1"
    cell_text = "\n".join(
        step.get("run", "") for step in cell_job["steps"] if isinstance(step, dict)
    )
    assert "test_minio_integration.py" in cell_text
    assert "test_spicedb_integration.py" in cell_text
    assert jobs["browser-matrix"]["strategy"]["matrix"]["browser"] == [
        "chromium",
        "firefox",
        "webkit",
        "mobile-webkit",
    ]
    assert "always()" in jobs["notify-failure"]["if"]
    assert "frontend-mutation-tests-full" in jobs["notify-failure"]["needs"]
    assert "issues" in workflow["permissions"]
    assert jobs["kyverno-test"]["timeout-minutes"] == 15
    assert jobs["miri"]["env"]["PROPTEST_DISABLE_FAILURE_PERSISTENCE"] == "1"
    assert jobs["miri"]["env"]["MIRIFLAGS"] == (
        "-Zmiri-tree-borrows -Zmiri-disable-isolation -Zmiri-isolation-error=warn"
    )
    chaos_job = jobs["load-and-chaos"]
    assert chaos_job["timeout-minutes"] == 45
    chaos_steps = "\n".join(
        f"{step.get('name', '')}\n{step.get('run', '')}"
        for step in chaos_job["steps"]
        if isinstance(step, dict)
    )
    assert "Prepare full chaos compose environment" in chaos_steps
    assert "Start the full chaos compose stack" in chaos_steps
    assert "docker-compose.ci-loadtest.yml" in chaos_steps
    assert "54321/ecosystem" in chaos_steps
    assert "Tear down full chaos compose stack" in chaos_steps
    pyo3_source = (
        REPOSITORY_ROOT / "crates" / "pyo3-sanitizer" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")
    assert "#[cfg(miri)]" in pyo3_source
    assert "failure_persistence: None" in pyo3_source


def test_go_service_dockerfiles_package_local_spiffe_replacement() -> None:
    for service in ("gateway", "ws-hub", "file-processor"):
        dockerfile = (REPOSITORY_ROOT / "services" / service / "Dockerfile").read_text(
            encoding="utf-8"
        )
        assert "COPY services/pkg/spiffe ./services/pkg/spiffe" in dockerfile


def test_go_fuzz_workflow_executes_all_service_fuzz_targets() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "go-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert workflow["jobs"]["fuzz"]["timeout-minutes"] == 15
    text = "\n".join(
        step.get("run", "")
        for step in workflow["jobs"]["fuzz"]["steps"]
        if isinstance(step, dict)
    )
    assert "FuzzEstimateQueryDepth" in text
    assert "FuzzJWTValidation" in text
    assert "FuzzParseMessage" in text
    assert "FuzzExtractAlgFromHeader" in text
    fuzz_commands = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("go test") and "-fuzz=" in line
    ]
    assert len(fuzz_commands) == 4
    assert all("-fuzztime=30s" in command for command in fuzz_commands)
    assert all("-parallel=1" in command for command in fuzz_commands)


def test_python_fuzz_workflow_is_bounded() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "python-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert workflow["jobs"]["fuzz"]["timeout-minutes"] == 15


def test_rust_fuzz_workflow_caches_every_declared_target_workspace() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "rust-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert workflow["jobs"]["fuzz"]["timeout-minutes"] == 30
    assert workflow["jobs"]["fuzz-additional-rust-crates"]["timeout-minutes"] == 30
    cache_step = next(
        step
        for step in workflow["jobs"]["fuzz"]["steps"]
        if step.get("uses", "").startswith("actions/cache")
    )
    cache_paths = str(cache_step["with"]["path"])
    cache_key = str(cache_step["with"]["key"])

    for workspace in (
        "native/rust_ext/target/",
        "frontend/wasm-sanitizer/fuzz/target/",
        "frontend/rust-crypto/fuzz/target/",
    ):
        assert workspace in cache_paths

    for manifest in (
        "native/rust_ext/Cargo.toml",
        "frontend/wasm-sanitizer/fuzz/Cargo.toml",
        "frontend/rust-crypto/fuzz/Cargo.toml",
    ):
        assert manifest in cache_key

    additional_cache = next(
        step
        for step in workflow["jobs"]["fuzz-additional-rust-crates"]["steps"]
        if step.get("uses", "").startswith("actions/cache")
    )
    assert "${{ matrix.directory }}/target/" in str(additional_cache["with"]["path"])
    additional_key = str(additional_cache["with"]["key"])
    assert "${{ matrix.name }}" in additional_key
    assert "matrix.parent_manifest" in additional_key
    assert "../Cargo.toml" not in additional_key


def test_incremental_mutation_gate_is_blocking_and_fails_on_timeout() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = ci_workflow["jobs"]
    mutation_job = jobs["mutation-tests-incremental"]
    assert mutation_job["timeout-minutes"] == 35
    assert "mutation-tests-incremental" in jobs["ci-success"]["needs"]
    mutation_text = "\n".join(
        step.get("run", "") for step in mutation_job["steps"] if isinstance(step, dict)
    )
    assert "exceeded its 25-minute budget" in mutation_text
    assert "Skipping score verification" not in mutation_text
    assert (
        "needs.mutation-tests-incremental.result"
        in jobs["ci-success"]["steps"][0]["run"]
    )
    export_index = mutation_text.index("mutmut export-cicd-stats")
    gate_index = mutation_text.index("scripts/mutmut_ci_gate.py")
    assert export_index < gate_index


def test_performance_gate_asserts_downloaded_lighthouse_without_rebuilding() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    performance_job = ci_workflow["jobs"]["performance-gate"]
    threshold_step = next(
        step
        for step in performance_job["steps"]
        if step.get("name") == "Enforce Lighthouse thresholds"
    )
    assert threshold_step["env"]["LHCI_SKIP_PREPARE"] == "1"
    threshold_command = threshold_step["run"]
    assert "--config=../.lighthouserc.js" in threshold_command
    assert "--preset=" not in threshold_command
    assert "--budgetsFile=" not in threshold_command


def test_lighthouse_config_uses_supported_budget_path_and_audit() -> None:
    lighthouse_config = LIGHTHOUSE_CONFIG_PATH.read_text(encoding="utf-8")

    assert "budgetPath:" in lighthouse_config
    assert "budgetsPath:" not in lighthouse_config
    assert "budgets:" not in lighthouse_config
    assert '"total-blocking-time": [' in lighthouse_config
    assert '"categories:performance": ["warn"' in lighthouse_config


def test_lhci_collection_uses_lighthouse_budget_path_inside_settings() -> None:
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'budgetPath: path.resolve(frontendRoot, "../../budget.json")' in lhci_script
    assert "budgetsPath:" not in lhci_script


def test_lhci_command_runner_uses_shell_free_platform_resolution() -> None:
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "shell: false" in lhci_script
    assert "shell: true" not in lhci_script
    assert '"/d", "/s", "/c", `${command}.cmd`' in lhci_script


def test_lhci_system_dependency_bootstrap_is_explicitly_skippable() -> None:
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "LHCI_SKIP_SYSTEM_DEPS" in lhci_script
    assert "playwright install-deps chromium" in lhci_script


def test_chaos_job_provisions_real_minio_through_toxiproxy() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    chaos_job = ci_workflow["jobs"]["chaos-tests"]
    minio_service = chaos_job["services"]["minio"]
    assert minio_service["image"].startswith("minio/minio:")
    assert minio_service["command"] == 'server /data --console-address ":9001"'
    assert "9003:9003" in chaos_job["services"]["toxiproxy"]["ports"]

    configure_text = next(
        step["run"]
        for step in chaos_job["steps"]
        if step.get("name") == "Configure ToxiProxy proxies"
    )
    assert '"name":"minio"' in configure_text
    assert '"upstream":"minio:9000"' in configure_text

    chaos_env = next(
        step["env"]
        for step in chaos_job["steps"]
        if step.get("name") == "Run chaos tests"
    )
    assert chaos_env["MINIO_PROXY_ENDPOINT"] == "http://localhost:9003"
    assert chaos_env["MINIO_DIRECT_ENDPOINT"] == "localhost:9000"
    assert chaos_env["STORAGE_S3_ENDPOINT_URL"] == "http://localhost:9003"


def test_actionlint_documents_github_service_command_compatibility() -> None:
    config = yaml.safe_load(ACTIONLINT_CONFIG_PATH.read_text(encoding="utf-8"))
    ignores = config["paths"][".github/workflows/ci.yml"]["ignore"]

    assert 'unexpected key "command" for "services" section' in ignores


def test_frontend_mutation_gate_is_blocking_and_reproducible() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = ci_workflow["jobs"]
    mutation_job = jobs["stryker-incremental"]
    mutation_condition = mutation_job["if"]
    assert "github.event_name == 'pull_request'" in mutation_condition
    assert "github.event_name == 'workflow_dispatch'" in mutation_condition
    assert "stryker-incremental" in jobs["ci-success"]["needs"]
    result_check = jobs["ci-success"]["steps"][0]["run"]
    assert "needs.stryker-incremental.result" in result_check

    frontend_workflow = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml"
        ).read_text(encoding="utf-8")
    )
    unit_steps = frontend_workflow["jobs"]["unit-tests"]["steps"]
    diff_step = next(
        step
        for step in unit_steps
        if step.get("name") == "Check differential frontend coverage"
    )
    assert "--fail-under=100" in diff_step["run"]
    codecov_step = next(
        step
        for step in unit_steps
        if step.get("name") == "Upload frontend coverage to Codecov"
    )
    assert codecov_step["with"]["flags"] == "frontend"


def _step_named(job: dict[str, object], name: str) -> dict[str, object]:
    return next(
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("name") == name
    )


def _assert_only_documented_conditional_ors(
    script: str, allowed_conditions: tuple[str, ...]
) -> None:
    """Permit only the audited conditional expressions, never shell fallbacks."""

    normalized_script = _normalize_shell_lexical_continuations(script)
    sanitized_script = normalized_script
    for condition in allowed_conditions:
        assert normalized_script.count(condition) == 1
        sanitized_script = sanitized_script.replace(condition, "")
    assert "||" not in sanitized_script


def _normalize_shell_lexical_continuations(script: str) -> str:
    """Make Bash backslash-newline token joins visible to contract assertions."""

    return script.replace("\\\r\n", "").replace("\\\n", "")


def _assert_fail_closed_shell_mode(script: str) -> None:
    """Prevent later shell-option changes from making a required command advisory."""

    assert script.splitlines()[0] == "set -euo pipefail"
    assert (
        FAIL_CLOSED_SHELL_DISABLE.search(_normalize_shell_lexical_continuations(script))
        is None
    )


def _canonical_shell_lines(script: str) -> tuple[str, ...]:
    """Canonicalize a small shell fragment without changing its command shape."""

    return tuple(
        " ".join(line.split())
        for line in _normalize_shell_lexical_continuations(script).splitlines()
        if line.strip()
    )


def _assert_critical_execution_segment(
    script: str, *, anchor: str, expected: tuple[str, ...]
) -> None:
    """Require the fail-closed hash-to-invocation tail to retain its exact shape."""

    assert script.count(anchor) == 1
    assert _canonical_shell_lines(script[script.index(anchor) :]) == expected


def _assert_no_shell_indirection_or_option_control(script: str) -> None:
    """Forbid unneeded constructs that can hide a required command's failure."""

    assert (
        FORBIDDEN_SHELL_INDIRECTION_OR_OPTION_CONTROL.search(
            _normalize_shell_lexical_continuations(script)
        )
        is None
    )


def _expected_capture_critical_execution_segment(
    capture_format: str,
) -> tuple[str, ...]:
    """Return the narrow trusted capture tail for one benchmark format."""

    assert capture_format in {"go", "rust"}
    rust_dockerfile_argument = (
        ' --rust-dockerfile "$BASE_RUST_DOCKERFILE"' if capture_format == "rust" else ""
    )
    return _canonical_shell_lines(
        'BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"\n'
        'if [[ ! "$BASE_COMPARATOR_SHA256" =~ ^[0-9a-f]{64}$ ]]; then\n'
        '  echo "Trusted base comparator hash is invalid" >&2\n'
        "  exit 2\n"
        "fi\n"
        "\n"
        "{\n"
        '  echo "base_sha=$BASE_SHA"\n'
        '  echo "candidate_sha=$CANDIDATE_SHA"\n'
        '  echo "base_worktree=$BASE_WORKTREE"\n'
        '  echo "base_comparator=$BASE_COMPARATOR"\n'
        '  echo "base_comparator_sha256=$BASE_COMPARATOR_SHA256"\n'
        '  echo "python_bin=$PYTHON_BIN"\n'
        '} >> "$GITHUB_OUTPUT"\n'
        "\n"
        '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER" '
        f"--format {capture_format} "
        '--base-worktree "$BASE_WORKTREE" '
        '--candidate-worktree "$GITHUB_WORKSPACE" '
        '--artifact-root "$ARTIFACT_ROOT" '
        '--runner-temp "$RUNNER_TEMP" '
        '--base-revision "$BASE_SHA" '
        '--candidate-revision "$CANDIDATE_SHA"' + rust_dockerfile_argument
    )


def _expected_comparator_critical_execution_segment(
    comparator_format: str, capture_id: str
) -> tuple[str, ...]:
    """Return the narrow trusted comparator tail for one benchmark format."""

    assert comparator_format in {"go", "bencher"}
    base_revision = "${{ steps." + capture_id + ".outputs.base_sha }}"
    candidate_revision = "${{ steps." + capture_id + ".outputs.candidate_sha }}"
    return _canonical_shell_lines(
        'ACTUAL_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"\n'
        'if [[ "$ACTUAL_COMPARATOR_SHA256" != "$EXPECTED_COMPARATOR_SHA256" ]]; then\n'
        '  echo "Trusted base comparator changed after capture" >&2\n'
        "  exit 2\n"
        "fi\n"
        '"$PYTHON_BIN" -I "$BASE_COMPARATOR" '
        f"--format {comparator_format} "
        '--base-dir "$ARTIFACT_ROOT/base" '
        '--candidate-dir "$ARTIFACT_ROOT/candidate" '
        "--expected-pairs 12 "
        f'--base-revision "{base_revision}" '
        f'--candidate-revision "{candidate_revision}" '
        '--toolchain-json "$ARTIFACT_ROOT/toolchain.json" '
        '--output "$ARTIFACT_ROOT/comparison.json"'
    )


def _covered_action_uses(job: dict[str, object], action_name: str) -> list[str]:
    """Return every use of one covered action, including malformed missing pins."""

    return [
        uses
        for step in job["steps"]
        if isinstance(step, dict)
        and (uses := str(step.get("uses", ""))).partition("@")[0].casefold()
        == action_name
    ]


def _assert_paired_gate_variant(
    workflow: dict[str, object], *, workflow_path: Path, job_id: str
) -> None:
    """Apply the shared paired-gate contract to one parsed workflow variant."""

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    assert workflow_path in {
        REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
        MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
    }
    assert job_id in {"ws-hub-regression", "rust-native-regression"}

    is_manual = workflow_path == MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH
    is_rust = job_id == "rust-native-regression"
    _assert_paired_capture_contract(
        job,
        capture_format="rust" if is_rust else "go",
        comparator_format="bencher" if is_rust else "go",
        revision_environment=(
            {
                "MANUAL_BASE_SHA": "${{ inputs.base_sha }}",
                "MANUAL_CANDIDATE_SHA": "${{ github.sha }}",
            }
            if is_manual
            else {
                "EVENT_NAME": "${{ github.event_name }}",
                "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
                "PR_CANDIDATE_SHA": "${{ github.sha }}",
                "PUSH_BASE_SHA": "${{ github.event.before }}",
                "PUSH_CANDIDATE_SHA": "${{ github.sha }}",
            }
        ),
        base_worktree_leaf=(
            "manual-performance-base-rust-native"
            if is_manual and is_rust
            else "manual-performance-base-ws-hub"
            if is_manual
            else "performance-base-rust-native"
            if is_rust
            else "performance-base-ws-hub"
        ),
        timeout_minutes=30 if is_rust else 20,
    )


def _wrap_standalone_invocation_in_if(script: str, invocation_prefix: str) -> str:
    """Turn the real multiline command into a Bash condition in memory."""

    command_start = script.index(invocation_prefix)
    command_block_start = script.rfind("\n", 0, command_start) + 1
    command_block_end = script.find("\n\n", command_start)
    if command_block_end == -1:
        command_block_end = len(script)
    command_block = script[command_block_start:command_block_end].strip()
    assert command_block.startswith(invocation_prefix)
    return (
        script[:command_block_start]
        + f"if {command_block}; then\n  :\nfi"
        + script[command_block_end:]
    )


def _wrap_standalone_invocation_in_substitution(
    script: str, invocation_prefix: str
) -> str:
    """Hide the real multiline command in a success-returning substitution."""

    command_start = script.index(invocation_prefix)
    command_block_start = script.rfind("\n", 0, command_start) + 1
    command_block_end = script.find("\n\n", command_start)
    if command_block_end == -1:
        command_block_end = len(script)
    command_block = script[command_block_start:command_block_end].strip()
    assert command_block.startswith(invocation_prefix)
    return (
        script[:command_block_start]
        + f': "$(\\\n  {command_block})'
        + script[command_block_end:]
    )


def _wrap_standalone_invocation_in_backticks(
    script: str, invocation_prefix: str
) -> str:
    """Hide the real multiline command in a success-returning legacy substitution."""

    command_start = script.index(invocation_prefix)
    command_block_start = script.rfind("\n", 0, command_start) + 1
    command_block_end = script.find("\n\n", command_start)
    if command_block_end == -1:
        command_block_end = len(script)
    command_block = script[command_block_start:command_block_end].strip()
    assert command_block.startswith(invocation_prefix)
    return (
        script[:command_block_start]
        + f": `\n  {command_block}`"
        + script[command_block_end:]
    )


def _wrap_standalone_invocation_in_outer_context(
    script: str, invocation_prefix: str, context: str
) -> str:
    """Put the direct command in an outer compound shell form with padding."""

    command_start = script.index(invocation_prefix)
    command_block_start = script.rfind("\n", 0, command_start) + 1
    command_block_end = script.find("\n\n", command_start)
    if command_block_end == -1:
        command_block_end = len(script)
    command_block = script[command_block_start:command_block_end].strip()
    assert command_block.startswith(invocation_prefix)
    contexts = {
        "if": ("if :; then\n  :\n", "  :\nfi"),
        "elif": ("if false; then\n  :\nelif :; then\n  :\n", "  :\nfi"),
        "negation": ("! {\n  :\n", "  :\n}"),
        "while": ("while :; do\n  :\n", "  break\ndone"),
        "until": ("until false; do\n  :\n", "  break\ndone"),
        "case": ("case 1 in\n  1)\n    :\n", "    :\n    ;;\nesac"),
    }
    assert context in contexts
    prefix, suffix = contexts[context]
    return (
        script[:command_block_start]
        + prefix
        + command_block
        + "\n\n"
        + suffix
        + script[command_block_end:]
    )


def _mutate_paired_gate(job: dict[str, object], mutation: str) -> None:
    """Introduce one real fail-open regression into an in-memory gate."""

    capture = _step_named(
        job, "Resolve immutable revisions and capture paired evidence"
    )
    comparator = _step_named(job, "Compare paired benchmark evidence")

    if mutation == "job-continue-on-error":
        job["continue-on-error"] = True
    elif mutation == "capture-continue-on-error":
        capture["continue-on-error"] = True
    elif mutation == "comparison-continue-on-error":
        comparator["continue-on-error"] = True
    elif mutation == "capture-error-swallowing":
        capture["run"] = f"{capture['run']}\ntrue || true\n"
    elif mutation == "comparison-error-swallowing":
        comparator["run"] = f"{comparator['run']}\ntrue || true\n"
    elif mutation == "capture-split-or-error-swallowing":
        capture["run"] = f"{capture['run']}\nfalse ||\n  true\n"
    elif mutation == "comparison-split-or-error-swallowing":
        comparator["run"] = f"{comparator['run']}\nfalse ||\n  true\n"
    elif mutation == "capture-lexical-split-or-error-swallowing":
        capture["run"] = f"{capture['run']}\nfalse |\\\n| true\n"
    elif mutation == "comparison-lexical-split-or-error-swallowing":
        comparator["run"] = f"{comparator['run']}\nfalse |\\\n| true\n"
    elif mutation == "capture-conditional-wrapper":
        capture["run"] = _wrap_standalone_invocation_in_if(
            str(capture["run"]), '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"'
        )
    elif mutation == "comparison-conditional-wrapper":
        comparator["run"] = _wrap_standalone_invocation_in_if(
            str(comparator["run"]), '"$PYTHON_BIN" -I "$BASE_COMPARATOR"'
        )
    elif mutation == "capture-substitution-wrapper":
        capture["run"] = _wrap_standalone_invocation_in_substitution(
            str(capture["run"]), '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"'
        )
    elif mutation == "capture-backtick-wrapper":
        capture["run"] = _wrap_standalone_invocation_in_backticks(
            str(capture["run"]), '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"'
        )
    elif mutation.startswith("capture-outer-"):
        capture["run"] = _wrap_standalone_invocation_in_outer_context(
            str(capture["run"]),
            '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"',
            mutation.removeprefix("capture-outer-").removesuffix("-wrapper"),
        )
    elif mutation.startswith("comparison-outer-"):
        comparator["run"] = _wrap_standalone_invocation_in_outer_context(
            str(comparator["run"]),
            '"$PYTHON_BIN" -I "$BASE_COMPARATOR"',
            mutation.removeprefix("comparison-outer-").removesuffix("-wrapper"),
        )
    elif mutation == "capture-disable-errexit":
        capture["run"] = str(capture["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\nset +e", 1
        )
    elif mutation == "capture-disable-errexit-option":
        capture["run"] = str(capture["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\nset +o errexit", 1
        )
    elif mutation == "comparison-disable-pipefail":
        comparator["run"] = str(comparator["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\nset +o pipefail", 1
        )
    elif mutation == "capture-builtin-disable-errexit":
        capture["run"] = str(capture["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\nbuiltin set +e", 1
        )
    elif mutation == "comparison-builtin-disable-pipefail":
        comparator["run"] = str(comparator["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\nbuiltin set +o pipefail", 1
        )
    elif mutation == "capture-eval-disable-errexit":
        capture["run"] = str(capture["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\neval 'set +e'", 1
        )
    elif mutation == "comparison-command-set-disable-errexit":
        comparator["run"] = str(comparator["run"]).replace(
            "set -euo pipefail", "set -euo pipefail\ncommand set +e", 1
        )
    elif mutation == "pre-capture-hash-order":
        capture_text = str(capture["run"])
        hash_start = capture_text.index(
            'BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"'
        )
        hash_end = capture_text.index("\n\n", hash_start) + 2
        hash_block = capture_text[hash_start:hash_end]
        capture["run"] = (
            capture_text[:hash_start] + capture_text[hash_end:] + hash_block
        )
    elif mutation == "checkout-pin":
        checkout = next(
            step
            for step in job["steps"]
            if isinstance(step, dict)
            and str(step.get("uses", "")).startswith("actions/checkout@")
        )
        checkout["uses"] = "actions/checkout@v7"
    elif mutation == "setup-python-pin":
        setup_python = _step_named(job, "Set up Python")
        setup_python["uses"] = "actions/setup-python@v7"
    elif mutation == "upload-pin":
        upload = _step_named(job, "Upload paired benchmark evidence")
        upload["uses"] = "actions/upload-artifact@v7"
    elif mutation == "upload-continue-on-error":
        upload = _step_named(job, "Upload paired benchmark evidence")
        upload["continue-on-error"] = True
    elif mutation.startswith("duplicate-unpinned-"):
        action_name = mutation.removeprefix("duplicate-unpinned-")
        action_pins = {
            "checkout": "actions/checkout@v7",
            "setup-python": "actions/setup-python@v7",
            "upload-artifact": "actions/upload-artifact@v7",
        }
        assert action_name in action_pins
        action_prefix = action_pins[action_name].split("@", maxsplit=1)[0] + "@"
        source_step = next(
            step
            for step in job["steps"]
            if isinstance(step, dict)
            and str(step.get("uses", "")).startswith(action_prefix)
        )
        duplicate_step = deepcopy(source_step)
        duplicate_step["uses"] = action_pins[action_name]
        cleanup = _step_named(job, "Remove immutable base worktree")
        steps = job["steps"]
        assert isinstance(steps, list)
        steps.insert(steps.index(cleanup), duplicate_step)
    elif mutation == "duplicate-case-variant-checkout":
        source_step = next(
            step
            for step in job["steps"]
            if isinstance(step, dict)
            and str(step.get("uses", "")).startswith("actions/checkout@")
        )
        duplicate_step = deepcopy(source_step)
        duplicate_step["uses"] = "Actions/checkout@v7"
        cleanup = _step_named(job, "Remove immutable base worktree")
        steps = job["steps"]
        assert isinstance(steps, list)
        steps.insert(steps.index(cleanup), duplicate_step)
    else:
        raise AssertionError(f"Unknown paired-gate mutation: {mutation}")


@pytest.mark.parametrize(
    ("workflow_path", "job_id", "mutation"),
    (
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "job-continue-on-error",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "capture-continue-on-error",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "comparison-continue-on-error",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-error-swallowing",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-error-swallowing",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "pre-capture-hash-order",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "pre-capture-hash-order",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "checkout-pin",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "setup-python-pin",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "upload-pin",
        ),
    ),
    ids=(
        "automatic-job-continue-on-error",
        "manual-capture-continue-on-error",
        "automatic-comparison-continue-on-error",
        "automatic-capture-error-swallowing",
        "manual-comparison-error-swallowing",
        "automatic-pre-capture-hash-order",
        "manual-pre-capture-hash-order",
        "automatic-checkout-tag",
        "manual-setup-python-tag",
        "manual-upload-tag",
    ),
)
def test_paired_performance_contract_rejects_fail_open_mutations(
    workflow_path: Path, job_id: str, mutation: str
) -> None:
    """The shared contract must reject fail-open changes in memory, before CI."""

    workflow = deepcopy(yaml.safe_load(workflow_path.read_text(encoding="utf-8")))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    _mutate_paired_gate(job, mutation)

    with pytest.raises(AssertionError):
        _assert_paired_gate_variant(
            workflow, workflow_path=workflow_path, job_id=job_id
        )


@pytest.mark.parametrize(
    ("workflow_path", "job_id", "mutation"),
    (
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-split-or-error-swallowing",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-split-or-error-swallowing",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "upload-continue-on-error",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "duplicate-unpinned-checkout",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "duplicate-unpinned-setup-python",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "duplicate-unpinned-upload-artifact",
        ),
    ),
    ids=(
        "automatic-capture-split-or-error-swallowing",
        "manual-comparison-split-or-error-swallowing",
        "manual-upload-continue-on-error",
        "automatic-duplicate-unpinned-checkout",
        "manual-duplicate-unpinned-setup-python",
        "automatic-duplicate-unpinned-upload-artifact",
    ),
)
def test_paired_performance_contract_rejects_evasion_mutations(
    workflow_path: Path, job_id: str, mutation: str
) -> None:
    """The shared contract must reject nonliteral fail-open evasions in memory."""

    workflow = deepcopy(yaml.safe_load(workflow_path.read_text(encoding="utf-8")))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    _mutate_paired_gate(job, mutation)

    with pytest.raises(AssertionError):
        _assert_paired_gate_variant(
            workflow, workflow_path=workflow_path, job_id=job_id
        )


@pytest.mark.parametrize(
    ("workflow_path", "job_id", "mutation"),
    (
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-lexical-split-or-error-swallowing",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-lexical-split-or-error-swallowing",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "duplicate-case-variant-checkout",
        ),
    ),
    ids=(
        "automatic-capture-lexical-split-or-error-swallowing",
        "manual-comparison-lexical-split-or-error-swallowing",
        "manual-case-variant-unpinned-checkout",
    ),
)
def test_paired_performance_contract_rejects_lexical_evasion_mutations(
    workflow_path: Path, job_id: str, mutation: str
) -> None:
    """Lexical spelling cannot bypass the fail-closed paired-gate contract."""

    workflow = deepcopy(yaml.safe_load(workflow_path.read_text(encoding="utf-8")))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    _mutate_paired_gate(job, mutation)

    with pytest.raises(AssertionError):
        _assert_paired_gate_variant(
            workflow, workflow_path=workflow_path, job_id=job_id
        )


@pytest.mark.parametrize(
    ("workflow_path", "job_id", "mutation"),
    (
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-conditional-wrapper",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-conditional-wrapper",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "capture-substitution-wrapper",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "capture-disable-errexit",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "capture-disable-errexit-option",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-disable-pipefail",
        ),
    ),
    ids=(
        "automatic-capture-conditional-wrapper",
        "manual-comparison-conditional-wrapper",
        "automatic-capture-substitution-wrapper",
        "automatic-capture-disable-errexit",
        "manual-capture-disable-errexit-option",
        "manual-comparison-disable-pipefail",
    ),
)
def test_paired_performance_contract_rejects_nonstandalone_invocation_mutations(
    workflow_path: Path, job_id: str, mutation: str
) -> None:
    """Immutable helper and comparator calls must remain independently blocking."""

    workflow = deepcopy(yaml.safe_load(workflow_path.read_text(encoding="utf-8")))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    _mutate_paired_gate(job, mutation)

    with pytest.raises(AssertionError):
        _assert_paired_gate_variant(
            workflow, workflow_path=workflow_path, job_id=job_id
        )


@pytest.mark.parametrize(
    ("workflow_path", "job_id", "mutation"),
    (
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-backtick-wrapper",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-outer-if-wrapper",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "capture-outer-elif-wrapper",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "comparison-outer-negation-wrapper",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-outer-while-wrapper",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-outer-until-wrapper",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "capture-outer-case-wrapper",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "ws-hub-regression",
            "capture-builtin-disable-errexit",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "rust-native-regression",
            "comparison-builtin-disable-pipefail",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "ws-hub-regression",
            "capture-eval-disable-errexit",
        ),
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "rust-native-regression",
            "comparison-command-set-disable-errexit",
        ),
    ),
    ids=(
        "automatic-capture-backtick-wrapper",
        "manual-comparison-outer-if-wrapper",
        "automatic-capture-outer-elif-wrapper",
        "manual-comparison-outer-negation-wrapper",
        "automatic-capture-outer-while-wrapper",
        "manual-comparison-outer-until-wrapper",
        "automatic-capture-outer-case-wrapper",
        "automatic-capture-builtin-disable-errexit",
        "manual-comparison-builtin-disable-pipefail",
        "manual-capture-eval-disable-errexit",
        "automatic-comparison-command-set-disable-errexit",
    ),
)
def test_paired_performance_contract_rejects_compound_shell_mutations(
    workflow_path: Path, job_id: str, mutation: str
) -> None:
    """No compound shell form may turn a required paired-gate command advisory."""

    workflow = deepcopy(yaml.safe_load(workflow_path.read_text(encoding="utf-8")))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    _mutate_paired_gate(job, mutation)

    with pytest.raises(AssertionError):
        _assert_paired_gate_variant(
            workflow, workflow_path=workflow_path, job_id=job_id
        )


def _assert_paired_capture_contract(
    job: dict[str, object],
    *,
    capture_format: str,
    comparator_format: str,
    revision_environment: dict[str, str],
    base_worktree_leaf: str,
    timeout_minutes: int,
) -> None:
    """Assert the observable workflow contract for a fail-closed paired gate."""

    assert job["runs-on"] == "ubuntu-latest"
    assert job["permissions"] == {"contents": "read"}
    assert job["timeout-minutes"] == timeout_minutes
    assert job.get("continue-on-error", False) is False
    for step in job["steps"]:
        assert isinstance(step, dict)
        assert step.get("continue-on-error", False) is False
    assert not any(
        "benchmark-action/github-action-benchmark" in str(step.get("uses", ""))
        for step in job["steps"]
        if isinstance(step, dict)
    )
    regression_job_text = "\n".join(
        str(step.get("run", "")) for step in job["steps"] if isinstance(step, dict)
    )
    for forbidden_fragment in (
        "go test",
        "cargo bench",
        "actions/setup-go",
        "dtolnay/rust-toolchain",
        "actions/cache",
        "for pair in",
        "run_base_then_candidate",
        "run_candidate_then_base",
    ):
        assert forbidden_fragment not in regression_job_text
    assert not any(
        forbidden_fragment in str(step.get("uses", ""))
        for step in job["steps"]
        if isinstance(step, dict)
        for forbidden_fragment in (
            "actions/setup-go",
            "dtolnay/rust-toolchain",
            "actions/cache",
        )
    )

    assert _covered_action_uses(job, "actions/checkout") == [CHECKOUT_ACTION_PIN]
    checkout = next(
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("uses") == CHECKOUT_ACTION_PIN
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False

    assert _covered_action_uses(job, "actions/setup-python") == [
        SETUP_PYTHON_ACTION_PIN
    ]
    setup_python = _step_named(job, "Set up Python")
    assert setup_python["uses"] == SETUP_PYTHON_ACTION_PIN

    capture = _step_named(
        job, "Resolve immutable revisions and capture paired evidence"
    )
    assert capture["shell"] == "bash"
    assert capture["env"] == revision_environment
    assert capture.get("continue-on-error", False) is False
    capture_text = str(capture["run"])
    normalized_capture_text = " ".join(capture_text.replace("\\\n", " ").split())
    assert normalized_capture_text.startswith("set -euo pipefail")
    _assert_fail_closed_shell_mode(capture_text)
    _assert_only_documented_conditional_ors(
        capture_text, CAPTURE_ALLOWED_CONDITIONAL_ORS
    )
    _assert_no_shell_indirection_or_option_control(capture_text)
    _assert_critical_execution_segment(
        capture_text,
        anchor='BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"',
        expected=_expected_capture_critical_execution_segment(capture_format),
    )
    for required_fragment in (
        "0000000000000000000000000000000000000000",
        'git fetch --no-tags origin "$BASE_SHA" "$CANDIDATE_SHA"',
        'git cat-file -e "$BASE_SHA^{commit}"',
        'git cat-file -e "$CANDIDATE_SHA^{commit}"',
        'if [[ "$BASE_SHA" == "$CANDIDATE_SHA" ]]; then',
        'git merge-base --is-ancestor "$BASE_SHA" "$CANDIDATE_SHA"',
        'if [[ "$(git rev-parse HEAD)" != "$CANDIDATE_SHA" ]]; then',
        f'BASE_WORKTREE="${{RUNNER_TEMP}}/{base_worktree_leaf}"',
        'if [[ -e "$BASE_WORKTREE" ]]; then',
        'git worktree add --detach "$BASE_WORKTREE" "$BASE_SHA"',
        'BASE_CAPTURE_HELPER="$BASE_WORKTREE/scripts/quality/capture_isolated_benchmarks.py"',
        'BASE_COMPARATOR="$BASE_WORKTREE/scripts/quality/compare_paired_benchmarks.py"',
        'if ! test -f "$BASE_CAPTURE_HELPER"; then',
        'if ! test -f "$BASE_COMPARATOR"; then',
        'PYTHON_BIN="$(command -v python)"',
        'if [[ "$PYTHON_BIN" != /* || ! -x "$PYTHON_BIN" ]]; then',
        'ARTIFACT_ROOT="${RUNNER_TEMP}/',
        'if [[ -e "$ARTIFACT_ROOT" ]]; then',
        'BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"',
        'if [[ ! "$BASE_COMPARATOR_SHA256" =~ ^[0-9a-f]{64}$ ]]; then',
        'echo "base_comparator=$BASE_COMPARATOR"',
        'echo "base_comparator_sha256=$BASE_COMPARATOR_SHA256"',
        'echo "artifact_root=$ARTIFACT_ROOT"',
        'echo "python_bin=$PYTHON_BIN"',
        '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"',
        f"--format {capture_format}",
        '--base-worktree "$BASE_WORKTREE"',
        '--candidate-worktree "$GITHUB_WORKSPACE"',
        '--artifact-root "$ARTIFACT_ROOT"',
        '--runner-temp "$RUNNER_TEMP"',
        '--base-revision "$BASE_SHA"',
        '--candidate-revision "$CANDIDATE_SHA"',
    ):
        assert " ".join(required_fragment.split()) in normalized_capture_text
    assert "trap " not in capture_text
    assert "$GITHUB_WORKSPACE/artifacts/performance" not in capture_text
    assert "scripts/quality/capture_isolated_benchmarks.py" not in capture_text.replace(
        "$BASE_WORKTREE/scripts/quality/capture_isolated_benchmarks.py", ""
    )
    if capture_format == "rust":
        assert (
            'BASE_RUST_DOCKERFILE="$BASE_WORKTREE/containers/quality/Dockerfile.performance-rust"'
            in normalized_capture_text
        )
        assert '--rust-dockerfile "$BASE_RUST_DOCKERFILE"' in normalized_capture_text
    else:
        assert "--rust-dockerfile" not in capture_text
    candidate_commit_validation = normalized_capture_text.index(
        'git cat-file -e "$CANDIDATE_SHA^{commit}"'
    )
    distinct_revision_validation = normalized_capture_text.index(
        'if [[ "$BASE_SHA" == "$CANDIDATE_SHA" ]]; then'
    )
    ancestor_validation = normalized_capture_text.index(
        'git merge-base --is-ancestor "$BASE_SHA" "$CANDIDATE_SHA"'
    )
    assert (
        candidate_commit_validation < distinct_revision_validation < ancestor_validation
    )
    assert capture_text.index(
        'echo "artifact_root=$ARTIFACT_ROOT"'
    ) < capture_text.index('git fetch --no-tags origin "$BASE_SHA" "$CANDIDATE_SHA"')
    assert capture_text.index(
        'echo "artifact_root=$ARTIFACT_ROOT"'
    ) < capture_text.index('"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"')
    assert (
        capture_text.index(
            'BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"'
        )
        < capture_text.index('echo "base_comparator_sha256=$BASE_COMPARATOR_SHA256"')
        < capture_text.index('"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"')
    )
    if "EVENT_NAME" in revision_environment:
        for required_fragment in (
            'pull_request) BASE_SHA="$PR_BASE_SHA" CANDIDATE_SHA="$PR_CANDIDATE_SHA"',
            'push) BASE_SHA="$PUSH_BASE_SHA" CANDIDATE_SHA="$PUSH_CANDIDATE_SHA"',
        ):
            assert required_fragment in normalized_capture_text
    else:
        assert 'BASE_SHA="$MANUAL_BASE_SHA" CANDIDATE_SHA="$MANUAL_CANDIDATE_SHA"' in (
            normalized_capture_text
        )

    comparator = _step_named(job, "Compare paired benchmark evidence")
    assert comparator["shell"] == "bash"
    assert comparator.get("continue-on-error", False) is False
    comparator_text = str(comparator["run"])
    capture_id = str(capture["id"])
    assert (
        'BASE_COMPARATOR="${{ steps.' + capture_id + '.outputs.base_comparator }}"'
    ) in comparator_text
    assert (
        'PYTHON_BIN="${{ steps.' + capture_id + '.outputs.python_bin }}"'
        in comparator_text
    )
    assert (
        'EXPECTED_COMPARATOR_SHA256="${{ steps.'
        + capture_id
        + '.outputs.base_comparator_sha256 }}"'
    ) in comparator_text
    assert 'ARTIFACT_ROOT="${{ steps.' + capture_id + '.outputs.artifact_root }}"' in (
        comparator_text
    )
    assert 'if [[ "$PYTHON_BIN" != /* || ! -x "$PYTHON_BIN" ]]; then' in comparator_text
    assert 'if ! test -f "$BASE_COMPARATOR"; then' in comparator_text
    assert (
        'ACTUAL_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"'
        in comparator_text
    )
    assert (
        'if [[ "$ACTUAL_COMPARATOR_SHA256" != "$EXPECTED_COMPARATOR_SHA256" ]]; then'
        in (comparator_text)
    )
    assert '"$PYTHON_BIN" -I "$BASE_COMPARATOR"' in comparator_text
    assert "set -euo pipefail" in comparator_text
    _assert_fail_closed_shell_mode(comparator_text)
    _assert_only_documented_conditional_ors(
        comparator_text, COMPARISON_ALLOWED_CONDITIONAL_ORS
    )
    _assert_no_shell_indirection_or_option_control(comparator_text)
    _assert_critical_execution_segment(
        comparator_text,
        anchor='ACTUAL_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"',
        expected=_expected_comparator_critical_execution_segment(
            comparator_format, capture_id
        ),
    )
    assert "python scripts/quality/compare_paired_benchmarks.py" not in comparator_text
    assert 'python "$BASE_COMPARATOR"' not in comparator_text
    assert "$GITHUB_WORKSPACE/scripts/quality/compare_paired_benchmarks.py" not in (
        comparator_text
    )
    for required_fragment in (
        f"--format {comparator_format}",
        '--base-dir "$ARTIFACT_ROOT/base"',
        '--candidate-dir "$ARTIFACT_ROOT/candidate"',
        "--expected-pairs 12",
        "--base-revision",
        "--candidate-revision",
        "--toolchain-json",
        "--output",
    ):
        assert required_fragment in comparator_text
    assert (
        comparator_text.index(
            'ACTUAL_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"'
        )
        < comparator_text.index(
            'if [[ "$ACTUAL_COMPARATOR_SHA256" != "$EXPECTED_COMPARATOR_SHA256" ]]; then'
        )
        < comparator_text.index('"$PYTHON_BIN" -I "$BASE_COMPARATOR"')
    )

    evidence_artifact = _step_named(job, "Upload paired benchmark evidence")
    assert _covered_action_uses(job, "actions/upload-artifact") == [
        UPLOAD_ARTIFACT_ACTION_PIN
    ]
    assert evidence_artifact["uses"] == UPLOAD_ARTIFACT_ACTION_PIN
    assert evidence_artifact["if"] == "always()"
    assert evidence_artifact["with"]["retention-days"] == 14
    assert evidence_artifact["with"]["path"] == (
        "${{ steps." + capture_id + ".outputs.artifact_root }}"
    )

    cleanup = _step_named(job, "Remove immutable base worktree")
    assert cleanup["if"] == "always()"
    assert cleanup["shell"] == "bash"
    assert cleanup.get("continue-on-error", False) is False
    cleanup_text = str(cleanup["run"])
    assert "set -euo pipefail" in cleanup_text
    assert f'BASE_WORKTREE="${{RUNNER_TEMP}}/{base_worktree_leaf}"' in cleanup_text
    assert 'git worktree remove --force "$BASE_WORKTREE" || true' in cleanup_text
    assert cleanup_text.count("|| true") == 1
    best_effort_steps = [
        step
        for step in job["steps"]
        if isinstance(step, dict) and "|| true" in str(step.get("run", ""))
    ]
    assert best_effort_steps == [cleanup]
    assert job["steps"][-1] is cleanup
    assert (
        job["steps"].index(cleanup)
        > job["steps"].index(evidence_artifact)
        > job["steps"].index(comparator)
    )


def test_performance_workflow_uses_same_run_immutable_paired_gates() -> None:
    """A required performance gate must compare immutable revisions in one VM."""

    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert "workflow_dispatch" not in triggers
    assert "paths" not in triggers["pull_request"]
    assert workflow["permissions"] == {"contents": "read"}

    jobs = workflow["jobs"]
    assert jobs["ws-hub-regression"]["name"] == ("WS-Hub Go Benchmark Regression Gate")
    assert jobs["rust-native-regression"]["name"] == (
        "Rust Native Optimizer Regression Gate"
    )

    shared_revision_environment = {
        "EVENT_NAME": "${{ github.event_name }}",
        "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "PR_CANDIDATE_SHA": "${{ github.sha }}",
        "PUSH_BASE_SHA": "${{ github.event.before }}",
        "PUSH_CANDIDATE_SHA": "${{ github.sha }}",
    }
    _assert_paired_capture_contract(
        jobs["ws-hub-regression"],
        capture_format="go",
        comparator_format="go",
        revision_environment=shared_revision_environment,
        base_worktree_leaf="performance-base-ws-hub",
        timeout_minutes=20,
    )
    _assert_paired_capture_contract(
        jobs["rust-native-regression"],
        capture_format="rust",
        comparator_format="bencher",
        revision_environment=shared_revision_environment,
        base_worktree_leaf="performance-base-rust-native",
        timeout_minutes=30,
    )


def test_performance_history_is_main_only_and_advisory() -> None:
    """Historical charts cannot supply a PR decision or receive PR credentials."""

    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert jobs["benchmark"]["name"] == "Run Go Benchmarks"
    assert (
        jobs["rust-criterion"]["name"] == "Rust Criterion Benchmarks (pyo3-sanitizer)"
    )

    for job_id in ("benchmark", "rust-criterion"):
        job = jobs[job_id]
        assert not any(
            "benchmark-action/github-action-benchmark" in str(step.get("uses", ""))
            for step in job["steps"]
            if isinstance(step, dict)
        )
        checkout = next(
            step
            for step in job["steps"]
            if isinstance(step, dict)
            and str(step.get("uses", "")).startswith("actions/checkout")
        )
        assert checkout["with"]["persist-credentials"] is False
        assert any(
            str(step.get("uses", "")).startswith("actions/upload-artifact")
            for step in job["steps"]
            if isinstance(step, dict)
        )

    publisher = jobs["publish-performance-history"]
    assert publisher["needs"] == [
        "benchmark",
        "ws-hub-regression",
        "rust-criterion",
        "rust-native-regression",
    ]
    assert publisher["if"] == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    )
    assert publisher["permissions"] == {"contents": "write"}
    publisher_steps = [
        step
        for step in publisher["steps"]
        if isinstance(step, dict)
        and "benchmark-action/github-action-benchmark" in str(step.get("uses", ""))
    ]
    assert len(publisher_steps) == 2
    for step in publisher_steps:
        assert step["with"]["auto-push"] is True
        assert step["with"]["comment-on-alert"] is False
        assert step["with"]["fail-on-alert"] is False

    assert [
        job_id
        for job_id, job in jobs.items()
        if job.get("permissions", {}).get("contents") == "write"
    ] == ["publish-performance-history"]

    combined_workflow_text = workflow_path.read_text(
        encoding="utf-8"
    ) + MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    for forbidden_fragment in (
        "pull_request_target",
        "self-hosted",
        "PERFORMANCE_BENCHMARK_RUNNER",
    ):
        assert forbidden_fragment not in combined_workflow_text
    for job in jobs.values():
        assert "${{" not in str(job["runs-on"])


def test_manual_performance_evidence_uses_distinct_read_only_paired_contexts() -> None:
    """Manual evidence has explicit revisions and cannot satisfy required PR checks."""

    workflow = yaml.safe_load(
        MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    assert workflow["name"] == "Manual Performance Evidence"
    triggers = _workflow_triggers(workflow)
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["base_sha"] == {
        "description": "Full immutable base commit SHA for same-run performance evidence",
        "required": True,
        "type": "string",
    }
    assert workflow["permissions"] == {"contents": "read"}

    jobs = workflow["jobs"]
    expected_names = {
        "benchmark": "Manual Performance Evidence / Run Go Benchmarks",
        "ws-hub-regression": (
            "Manual Performance Evidence / WS-Hub Go Benchmark Regression Gate"
        ),
        "rust-criterion": (
            "Manual Performance Evidence / Rust Criterion Benchmarks (pyo3-sanitizer)"
        ),
        "rust-native-regression": (
            "Manual Performance Evidence / Rust Native Optimizer Regression Gate"
        ),
    }
    assert {job_id: jobs[job_id]["name"] for job_id in expected_names} == expected_names
    assert set(expected_names.values()).isdisjoint(REQUIRED_PERFORMANCE_CONTEXTS)

    manual_revision_environment = {
        "MANUAL_BASE_SHA": "${{ inputs.base_sha }}",
        "MANUAL_CANDIDATE_SHA": "${{ github.sha }}",
    }
    _assert_paired_capture_contract(
        jobs["ws-hub-regression"],
        capture_format="go",
        comparator_format="go",
        revision_environment=manual_revision_environment,
        base_worktree_leaf="manual-performance-base-ws-hub",
        timeout_minutes=20,
    )
    _assert_paired_capture_contract(
        jobs["rust-native-regression"],
        capture_format="rust",
        comparator_format="bencher",
        revision_environment=manual_revision_environment,
        base_worktree_leaf="manual-performance-base-rust-native",
        timeout_minutes=30,
    )

    assert all(
        "benchmark-action/github-action-benchmark" not in str(step.get("uses", ""))
        for job in jobs.values()
        for step in job["steps"]
        if isinstance(step, dict)
    )
