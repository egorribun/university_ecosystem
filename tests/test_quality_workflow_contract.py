from __future__ import annotations

import json
from pathlib import Path

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
QUALITY_PROMOTION_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "quality-promotion-check.yml"
)
DAST_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "dast.yml"
MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "manual-mutation-evidence.yml"
)
QUALITY_CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"
MUTMUT_GATE_PATH = REPOSITORY_ROOT / "scripts" / "mutmut_ci_gate.py"
KYVERNO_POLICY_PATH = REPOSITORY_ROOT / "k8s" / "kyverno" / "cluster-policies.yaml"
KYVERNO_TEST_ROOT = REPOSITORY_ROOT / "k8s" / "kyverno" / "tests"
REQUIRED_CI_CONTEXTS = frozenset(
    {
        "CI Diagnostic",
        "Pre-commit & Linting (Read-only)",
        "CI Success",
        "Coverage & Quality Policy Gate",
        "Source/Test Inventory & Anti-Pattern Check",
        "Backend Tests (Python 3.14) / Unit Tests (All-Python 3.14)",
        "Backend Tests (Python 3.14) / Integration Tests (All-Python 3.14)",
        "Backend Type Check",
        "Frontend Tests / Lint & Format",
        "Frontend Tests / Unit Tests",
        "Frontend Tests / Production Build",
        "Frontend Tests / Bundle Analysis",
        "Frontend Tests / Lighthouse Audit",
        "Incremental Mutation Tests (frontend)",
        "Go Tests (services/gateway) / Test Go Service (services/gateway)",
        "Go Tests (services/ws-hub) / Test Go Service (services/ws-hub)",
        "Go Tests (services/file-processor) / Test Go Service (services/file-processor)",
        "Go Tests (services/cmd/uni-cli) / Test Go Service (services/cmd/uni-cli)",
        "Rust - cargo test (x3 crates) + wasm-pack + coverage",
        "Rust Lint & Format",
        "Alembic Migrations",
        "DB Migration Gate (Postgres)",
        "Helm Lint & Validate",
        "Contract Tests",
        "Schemathesis - API Schema Conformance",
        "OpenAPI Backward Compatibility Check",
        "Verify OpenAPI Types",
        "Security Audit / Semgrep SAST",
        "Security Audit / Python Dependency Audit",
        "Security Audit / Node.js Dependency Audit",
        "Security Audit / Go Vulnerability Scan",
        "Security Audit / detect-secrets Baseline Integrity",
        "Trivy Image Scan",
        "Dockerfile Lint",
        "Lint GitHub Actions Workflows",
        "Kyverno policy tests",
    }
)


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
    assert "This advisory job" not in run_step["run"]
    assert "This blocking job runs REAL mutation" in run_step["run"]
    assert "viable mutation score" in run_step["run"]
    job_text = "\n".join(
        step.get("run", "") for step in job["steps"] if isinstance(step, dict)
    )
    assert "grep -E '^app/.*\\.py$'" in job_text
    assert "matrix.shard" in job_text
    assert "scripts/plan_mutmut_shards.py" in job_text
    assert "--changed-files /tmp/changed_py.txt" in job_text
    assert "--changed-diff /tmp/changed_py.diff" in job_text
    assert "--num-shards 16" in job_text
    assert '"${MUTANT_NAMES[@]}"' in job_text
    assert "awk -v shard" not in job_text
    assert "grep '^app/core/tenant\\.py$'" not in job_text


def test_incremental_mutation_stats_are_sharded_and_merged_before_execution() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    stats_job = jobs["mutation-tests-stats"]
    mutation_job = jobs["mutation-tests-incremental"]

    assert "workflow_dispatch" not in _workflow_triggers(workflow)
    assert workflow["concurrency"]["group"] == "ci-matrix-${{ github.ref }}"
    assert jobs["ci-success"]["name"] == "CI Success"

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
    for job in (stats_job, mutation_job):
        mutation_scope = next(
            step
            for step in job["steps"]
            if step.get("name") == "Detect changed Python source"
        )
        scope_script = mutation_scope["run"]
        assert mutation_scope["env"]["PR_BASE_SHA"] == (
            "${{ github.event.pull_request.base.sha }}"
        )
        assert mutation_scope["env"]["EVENT_NAME"] == "${{ github.event_name }}"
        assert "scripts/resolve_mutation_base.py" in scope_script
        assert '--pr-base-sha "$PR_BASE_SHA"' in scope_script
        assert '--event-name "$EVENT_NAME"' in scope_script
        assert 'COMPARE_BASE="origin/main"' not in scope_script
        assert '"$COMPARE_BASE...HEAD"' in scope_script
        assert "origin/main...HEAD" not in scope_script
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


def test_manual_mutation_evidence_is_isolated_from_required_ci_contexts() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    ci_text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    # A manual workflow must never emit the required CI contexts.  GitHub
    # rulesets match check names across event types, so a workflow_dispatch
    # run with skipped PR-only work must not be able to satisfy protection.
    assert "workflow_dispatch" not in _workflow_triggers(ci_workflow)
    assert "github.event.inputs" not in ci_text
    assert ci_workflow["jobs"]["ci-success"]["name"] == "CI Success"

    assert set(_workflow_triggers(workflow)) == {"workflow_dispatch"}
    dispatch = _workflow_triggers(workflow)["workflow_dispatch"]
    assert isinstance(dispatch, dict)
    assert dispatch["inputs"]["mutation_base_sha"] == {
        "description": "Full strict-ancestor commit SHA used to scope manual mutation evidence",
        "required": True,
        "type": "string",
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["group"] == (
        "manual-mutation-evidence-${{ github.ref }}"
    )
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert all(
        isinstance(job.get("name"), str)
        and job["name"].startswith("Manual Mutation Evidence")
        for job in jobs.values()
    )
    assert {job["name"] for job in jobs.values()}.isdisjoint(REQUIRED_CI_CONTEXTS)

    for job_name in ("manual-mutation-stats", "manual-mutation-tests"):
        mutation_scope = next(
            step
            for step in jobs[job_name]["steps"]
            if step.get("name") == "Resolve manual mutation comparison base"
        )
        scope_script = mutation_scope["run"]
        assert mutation_scope["env"]["MANUAL_BASE_SHA"] == (
            "${{ inputs.mutation_base_sha }}"
        )
        assert "scripts/resolve_mutation_base.py" in scope_script
        assert '--event-name "workflow_dispatch"' in scope_script
        assert '--manual-base-sha "$MANUAL_BASE_SHA"' in scope_script


def test_dispatchable_workflows_never_emit_required_ci_contexts() -> None:
    workflow_root = REPOSITORY_ROOT / ".github" / "workflows"
    collisions: list[str] = []

    for workflow_path in sorted(workflow_root.glob("*.yml")):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        raw_triggers = workflow.get("on", workflow.get(True))
        if isinstance(raw_triggers, str):
            dispatchable = raw_triggers == "workflow_dispatch"
        elif isinstance(raw_triggers, list):
            dispatchable = "workflow_dispatch" in raw_triggers
        else:
            assert isinstance(raw_triggers, dict)
            dispatchable = "workflow_dispatch" in raw_triggers
        if not dispatchable:
            continue
        for job_id, job in workflow["jobs"].items():
            if not isinstance(job, dict):
                continue
            name = job.get("name", job_id)
            if not isinstance(name, str):
                collisions.append(f"{workflow_path.name}:{job_id}:non-string-name")
                continue
            for required_context in REQUIRED_CI_CONTEXTS:
                if required_context in name:
                    collisions.append(f"{workflow_path.name}:{job_id}:{name}")
                    break

    assert not collisions, (
        f"A workflow_dispatch run must not emit a required status context: {collisions}"
    )


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


def test_performance_workflow_has_blocking_native_and_ws_baselines() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True, {}))
    assert "workflow_dispatch" in triggers
    jobs = workflow["jobs"]
    assert jobs["benchmark"]["timeout-minutes"] == 20
    assert jobs["ws-hub-regression"]["timeout-minutes"] == 20
    assert jobs["rust-criterion"]["timeout-minutes"] == 30
    assert jobs["rust-native-regression"]["timeout-minutes"] == 30
    assert "rust-native-regression" in jobs
    native_text = "\n".join(
        step.get("run", "")
        for step in jobs["rust-native-regression"]["steps"]
        if isinstance(step, dict)
    )
    assert "native/rust_ext/Cargo.toml" in native_text
    native_store = next(
        step
        for step in jobs["rust-native-regression"]["steps"]
        if "benchmark-action/github-action-benchmark" in step.get("uses", "")
    )
    assert native_store["with"]["alert-threshold"] == "110%"
    assert native_store["with"]["fail-on-alert"] is True

    ws_run_text = "\n".join(
        step.get("run", "")
        for step in jobs["ws-hub-regression"]["steps"]
        if isinstance(step, dict)
    )
    assert "go test -bench=. -run=^$ -benchmem -count=5 -benchtime=1s" in ws_run_text

    ws_store = next(
        step
        for step in jobs["ws-hub-regression"]["steps"]
        if "benchmark-action/github-action-benchmark" in step.get("uses", "")
    )
    assert ws_store["with"]["benchmark-data-dir-path"] == "dev/bench/ws-hub-regression"
    assert ws_store["with"]["alert-threshold"] == "110%"
    assert ws_store["with"]["fail-on-alert"] is True


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
    assert "scripts/export_mutmut_shard_stats.py --all" in export_step["run"]
    assert "mutmut export-cicd-stats" not in export_step["run"]
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
    export_index = mutation_text.index("scripts/export_mutmut_shard_stats.py")
    gate_index = mutation_text.index("scripts/mutmut_ci_gate.py")
    assert export_index < gate_index
    assert "--selected-file /tmp/mutmut-shard.txt" in mutation_text
    assert "--output mutants/mutmut-cicd-stats.json" in mutation_text
    assert "uv run mutmut export-cicd-stats" not in mutation_text
    assert "test -s mutants/mutmut-cicd-stats.json" in mutation_text


def test_blocking_mutation_jobs_are_not_mislabeled_as_advisory() -> None:
    ci_text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "advisory mutation" not in ci_text.lower()
    assert "mutation: $mut" not in ci_text
    assert "stryker: $stryker" not in ci_text


def test_full_mutation_gate_uses_the_fail_closed_exporter() -> None:
    nightly_workflow = yaml.safe_load(
        NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    mutation_job = nightly_workflow["jobs"]["mutation-tests-full"]
    mutation_text = "\n".join(
        step.get("run", "") for step in mutation_job["steps"] if isinstance(step, dict)
    )

    export_index = mutation_text.index("scripts/export_mutmut_shard_stats.py")
    gate_index = mutation_text.index("scripts/check_mutation_score.py")
    assert export_index < gate_index
    assert "--all" in mutation_text
    assert "uv run mutmut export-cicd-stats" not in mutation_text
    assert "test -s mutants/mutmut-cicd-stats.json" in mutation_text


def test_pr_quality_gates_enforce_contract_policy_values() -> None:
    contract = json.loads(QUALITY_CONTRACT_PATH.read_text(encoding="utf-8"))
    policy = contract["policy"]
    patch_coverage = policy["patch_coverage"]
    viable_mutant_score = policy["viable_mutant_score"]
    assert patch_coverage == 100
    assert viable_mutant_score == 100

    backend_workflow = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    diff_coverage_step = next(
        step
        for step in backend_workflow["jobs"]["unit-tests"]["steps"]
        if step.get("name") == "Check differential coverage (diff-cover)"
    )
    assert "github.event_name == 'pull_request'" in diff_coverage_step["if"]
    assert "inputs.num-shards <= 1" in diff_coverage_step["if"]
    assert diff_coverage_step["env"]["COMPARE_BRANCH"] == "${{ github.base_ref }}"
    assert f"--fail-under={patch_coverage}" in diff_coverage_step["run"]
    assert "git fetch origin $compareBranch" in diff_coverage_step["run"]
    assert "origin/$compareBranch" in diff_coverage_step["run"]
    assert not diff_coverage_step.get("continue-on-error", False)

    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    aggregate_coverage_job = ci_workflow["jobs"]["coverage-policy-gate"]
    aggregate_diff_step = next(
        step
        for step in aggregate_coverage_job["steps"]
        if step.get("name") == "Enforce aggregate PR differential coverage"
    )
    aggregate_checkout_step = next(
        step
        for step in aggregate_coverage_job["steps"]
        if step.get("name") == "Checkout"
    )
    assert aggregate_checkout_step.get("with", {}).get("fetch-depth") == 0
    assert aggregate_diff_step["if"] == "${{ github.event_name == 'pull_request' }}"
    assert aggregate_diff_step["env"]["COMPARE_BRANCH"] == "${{ github.base_ref }}"
    assert f"--fail-under={patch_coverage}" in aggregate_diff_step["run"]
    assert 'git fetch origin "$COMPARE_BRANCH"' in aggregate_diff_step["run"]
    assert "origin/$COMPARE_BRANCH" in aggregate_diff_step["run"]
    assert not aggregate_diff_step.get("continue-on-error", False)

    combine_index = next(
        index
        for index, step in enumerate(aggregate_coverage_job["steps"])
        if step.get("name") == "Combine Python shard coverage"
    )
    aggregate_diff_index = next(
        index
        for index, step in enumerate(aggregate_coverage_job["steps"])
        if step is aggregate_diff_step
    )
    assert combine_index < aggregate_diff_index

    mutation_gate = MUTMUT_GATE_PATH.read_text(encoding="utf-8")
    assert 'main(["--min-score", "100"])' in mutation_gate


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
    manual_workflow = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    jobs = ci_workflow["jobs"]
    mutation_job = jobs["stryker-incremental"]
    mutation_condition = mutation_job["if"]
    assert "github.event_name == 'pull_request'" in mutation_condition
    assert "workflow_dispatch" not in mutation_condition
    assert "stryker-incremental" in jobs["ci-success"]["needs"]
    result_check = jobs["ci-success"]["steps"][0]["run"]
    assert "needs.stryker-incremental.result" in result_check

    manual_stryker = manual_workflow["jobs"]["manual-frontend-mutation-tests"]
    assert manual_stryker["name"] == "Manual Mutation Evidence (frontend Stryker)"
    manual_stryker_run = next(
        step["run"]
        for step in manual_stryker["steps"]
        if step.get("name") == "Run manual incremental Stryker gate"
    )
    assert "npm run test:mutation -- --incremental" in manual_stryker_run

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


def test_quality_promotion_workflow_uses_fail_closed_stabilization_checker() -> None:
    workflow = yaml.safe_load(
        QUALITY_PROMOTION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    triggers = _workflow_triggers(workflow)
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}

    text = QUALITY_PROMOTION_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "nightly-full-gate.yml/runs" in text
    assert "check_stabilization_window.py" in text
    assert "Fail when promotion is not yet eligible" in text


def test_dast_pr_trigger_requires_the_explicit_run_dast_label() -> None:
    """Active scans on pull requests require deliberate reviewer authorization."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    pull_request = _workflow_triggers(workflow)["pull_request"]
    assert pull_request["types"] == ["labeled"]

    required_guard = (
        "${{ github.event_name != 'pull_request' || "
        "github.event.label.name == 'run-dast' }}"
    )
    for job_name in ("nuclei", "zap"):
        assert workflow["jobs"][job_name]["if"] == required_guard

    nuclei_setup = next(
        step
        for step in workflow["jobs"]["nuclei"]["steps"]
        if step.get("uses", "").startswith("projectdiscovery/nuclei-action@")
    )
    assert nuclei_setup["with"] == {"version": "v3.3.9", "install-only": True}
