from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import sys
import tomllib
from copy import deepcopy
from pathlib import Path
from shutil import which

import pytest
import yaml

from scripts.quality.capture_isolated_benchmarks import GO_IMAGE as BENCHMARK_GO_IMAGE
from scripts.quality.filter_checkov_sarif import filter_suppressed_results


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if parent.name == "mutants":
            continue
        if (parent / "pyproject.toml").exists() and (
            parent / "native" / "rust_ext" / ".cargo" / "audit.toml"
        ).exists():
            return parent
    for parent in [current, *current.parents]:
        if parent.name == "mutants":
            continue
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[1]


def _assert_helm_dependency_helper_invocation(
    script: str, *, skip_refresh: bool = False
) -> None:
    """Require workflows to use the bounded, fail-closed Helm helper."""

    assert "python3 scripts/ci/helm_dependency_build.py" in script
    assert "charts/university-ecosystem" in script
    assert "redis-20.13.4.tgz" in script
    assert "nats-8.5.4.tgz" in script
    assert "helm dependency build" not in script
    if skip_refresh:
        assert "--skip-refresh" in script
    else:
        assert "--skip-refresh" not in script


REPOSITORY_ROOT = _find_repo_root()
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
SQLMAP_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "sqlmap.yml"
LHCI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "lhci-linux.yml"
SQLMAP_OPENAPI_URL = "http://127.0.0.1:8000/api/openapi.json"
SQLMAP_OPENAPI_BASE_URL = "http://127.0.0.1:8000"
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
GO_LINT_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "go-lint.yml"
BUILD_ORCHESTRATED_LINUX_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "build-orchestrated-linux.yml"
)
SECURITY_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-security-audit.yml"
)
CHECKOV_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "checkov.yml"
PACT_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "contract-tests.yml"
PR_RUN_CANCELLATION_WORKFLOWS = (
    "benchmark.yml",
    "cargo-deny.yml",
    "checkov.yml",
    "codeql.yml",
    "db-perf-gate.yml",
    "dependency-review.yml",
    "generate-openapi.yml",
    "gitleaks.yml",
    "go-fuzz.yml",
    "go-lint.yml",
    "nilaway.yml",
    "python-fuzz.yml",
    "renovate-config-validation.yml",
    "rust-fuzz.yml",
    "semantic-pr.yml",
    "sqlmap.yml",
    "trufflehog.yml",
    "zizmor.yml",
)
QUALITY_HISTORY_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "quality-history.yml"
)
NIGHTLY_FULL_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "nightly-full-gate.yml"
)
FULL_BACKEND_MUTATION_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-full-backend-mutation.yml"
)
SBOM_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "sbom.yml"
DEPENDENCY_AUDIT_VALIDATOR_PATH = (
    REPOSITORY_ROOT / "scripts" / "check_dependency_audit_report.py"
)
OSV_BATCH_AUDIT_PATH = REPOSITORY_ROOT / "scripts" / "osv_batch_audit.py"
RUST_AUDIT_CONFIG_PATH = (
    REPOSITORY_ROOT / "native" / "rust_ext" / ".cargo" / "audit.toml"
)
QUALITY_PROMOTION_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "quality-promotion-check.yml"
)
DAST_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "dast.yml"
MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "manual-mutation-evidence.yml"
)
MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "manual-performance-evidence.yml"
)
QUALITY_CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"
MUTMUT_GATE_PATH = REPOSITORY_ROOT / "scripts" / "mutmut_ci_gate.py"
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
        "Rust Native Optimizer Regression Gate",
    }
)
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
        "Go Tests (services/gateway) / Test Go Service (services/gateway)",
        "Go Tests (services/ws-hub) / Test Go Service (services/ws-hub)",
        "Go Tests (services/file-processor) / Test Go Service (services/file-processor)",
        "Go Tests (services/cmd/uni-cli) / Test Go Service (services/cmd/uni-cli)",
        "Go Tests (services/pkg/logging) / Test Go Service (services/pkg/logging)",
        "Go Tests (services/pkg/spiffe) / Test Go Service (services/pkg/spiffe)",
        "Go Tests (services/pkg/spicedb) / Test Go Service (services/pkg/spicedb)",
        "Rust - cargo test (x3 crates) + wasm-pack + coverage",
        "Rust Lint & Format",
        "Alembic Migrations",
        "DB Migration Gate (Postgres)",
        "Helm Lint & Validate",
        "Contract Tests",
        "OpenAPI Backward Compatibility Check",
        "Verify OpenAPI Types",
        "Security Audit / Python Dependency Audit",
        "Security Audit / Node.js Dependency Audit",
        "Security Audit / Go Vulnerability Scan",
        "Security Audit / detect-secrets Baseline Integrity",
        "Trivy Image Scan",
        "Dockerfile Lint",
        "Lint GitHub Actions Workflows",
        "Kyverno policy tests",
        "Run Go Benchmarks",
        "WS-Hub Go Benchmark Regression Gate",
        "Rust Native Optimizer Regression Gate",
        "Run cargo fuzz",
    }
)
RUST_FUZZ_MANUAL_CONTEXT_EXPRESSION = (
    "${{ (github.event_name == 'pull_request' || github.event_name == 'push') && "
    "'Run cargo fuzz' || 'Extended Rust fuzz evidence' }}"
)
RUST_FUZZ_CONTEXT_BY_EVENT = {
    "pull_request": "Run cargo fuzz",
    "push": "Run cargo fuzz",
    "schedule": "Extended Rust fuzz evidence",
    "workflow_dispatch": "Extended Rust fuzz evidence",
}


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML 5/6 parses the YAML 1.1 key ``on`` as boolean True."""

    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def _job_context_for_event(
    workflow_path: Path, job_id: str, job_name: str, event_name: str
) -> str:
    """Resolve the one audited event-conditional job name before collision checks."""

    if workflow_path.name == "rust-fuzz.yml" and job_id == "fuzz":
        assert job_name == RUST_FUZZ_MANUAL_CONTEXT_EXPRESSION
        return RUST_FUZZ_CONTEXT_BY_EVENT[event_name]
    return job_name


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


def test_pr_branch_push_does_not_duplicate_contract_workflows() -> None:
    """Push validation is reserved for main; PRs use the pull_request event."""

    renovate = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "renovate-config-validation.yml"
        ).read_text(encoding="utf-8")
    )
    contract = yaml.safe_load(PACT_WORKFLOW_PATH.read_text(encoding="utf-8"))

    for workflow in (renovate, contract):
        triggers = _workflow_triggers(workflow)
        push = triggers.get("push")
        assert isinstance(push, dict)
        assert push.get("branches") == ["main"]
        assert "pull_request" in triggers


def test_pr_workflows_cancel_superseded_runs_without_cancelling_main() -> None:
    """Stale PR runs must release scarce hosted runners for the newest SHA."""

    expected_group = (
        "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
    )
    expected_cancel = "${{ github.event_name == 'pull_request' }}"
    for filename in PR_RUN_CANCELLATION_WORKFLOWS:
        workflow = yaml.safe_load(
            (REPOSITORY_ROOT / ".github" / "workflows" / filename).read_text(
                encoding="utf-8"
            )
        )
        concurrency = workflow.get("concurrency")
        assert isinstance(concurrency, dict), filename
        assert concurrency.get("group") == expected_group, filename
        assert concurrency.get("cancel-in-progress") == expected_cancel, filename


def test_sbom_cancels_superseded_pr_and_main_push_runs_only() -> None:
    """SBOM must release stale PR runners without cancelling manual evidence."""

    workflow = yaml.safe_load(SBOM_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    concurrency = workflow.get("concurrency")
    assert concurrency == {
        "group": "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
        "cancel-in-progress": "${{ github.event_name == 'pull_request' || github.event_name == 'push' }}",
    }


def test_dockerfile_lint_excludes_companion_dockerignore_files() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    hadolint_step = next(
        step
        for step in workflow["jobs"]["dockerfile-lint"]["steps"]
        if step.get("name") == "Run Hadolint"
    )

    assert '! -name "*.dockerignore"' in hadolint_step["run"]


def test_rust_codecov_reports_are_staged_for_trusted_upload() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    rust_job = workflow["jobs"]["rust-tests"]
    coverage_gate = workflow["jobs"]["coverage-policy-gate"]
    staging_step = next(
        step
        for step in coverage_gate["steps"]
        if step.get("name") == "Stage trusted Codecov reports"
    )
    trusted_uploads = {
        step.get("with", {}).get("flags"): step
        for step in workflow["jobs"]["codecov-upload"]["steps"]
        if str(step.get("uses", "")).startswith("codecov/codecov-action@")
    }

    report_commands = {
        "rust-native": "cargo llvm-cov report --codecov",
        "rust-wasm-sanitizer": "cargo llvm-cov report --codecov",
        "rust-crypto": "cargo llvm-cov report --codecov",
    }
    for component, command in report_commands.items():
        report_path = f"artifacts/coverage/rust/{component}/codecov.json"
        coverage_step = next(
            step
            for step in rust_job["steps"]
            if f"{component}/llvm.json" in step.get("run", "")
        )
        coverage_script = coverage_step["run"]
        # Rust coverage commands are lockfile-bound.  Normalize the flag here
        # so this artifact-shape contract remains focused on report routing;
        # the dedicated lockfile contract below asserts the flag itself.
        normalized_script = coverage_script.replace(" --locked", "")
        assert command in normalized_script
        assert f"--output-path ../../{report_path}" in coverage_script
        report_line = next(
            line.strip()
            for line in coverage_script.splitlines()
            if line.strip().startswith("cargo llvm-cov report") and report_path in line
        )
        assert report_line.replace(" --locked", "") == (
            f"{command} --output-path ../../{report_path}"
        )
        assert (
            coverage_script.index(f"{component}/llvm.json")
            < coverage_script.index(report_path)
            < coverage_script.index(f"{component}/branch-llvm.json")
        )
        assert (
            f"cp {report_path} artifacts/coverage/codecov/{component}.json"
            in staging_step["run"]
        )
        assert trusted_uploads[component]["with"]["files"] == (
            f"artifacts/coverage/codecov/{component}.json"
        )

    assert not any(
        str(step.get("uses", "")).startswith("codecov/codecov-action@")
        for step in rust_job["steps"]
    )


@pytest.fixture
def downloaded_coverage_shape(tmp_path: Path) -> str:
    """Stage producer file layouts, then execute the consumer's real shape checks.

    Run 37120306322's digest-verified ZIPs confirmed that the three Rust
    diagnostic reports retain their component directories on download.
    Provenance bytes are verified separately by the provenance test suite;
    this fixture exercises the shell boundary before those identity checks.
    """

    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    frontend = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    rust_job = workflow["jobs"]["rust-tests"]
    rust_upload = _step_named(rust_job, "Upload Rust coverage artifacts")
    codecov_upload = _step_named(rust_job, "Upload Rust Codecov diagnostic artifacts")
    frontend_upload = _step_named(
        frontend["jobs"]["unit-tests"], "Upload coverage artifacts"
    )
    contract = json.loads(QUALITY_CONTRACT_PATH.read_text(encoding="utf-8"))
    rust_components = {
        report["component"]
        for report in contract["coverage_reports"]
        if report["format"] == "llvm-cov-json"
    }
    assert rust_components == {"rust-native", "rust-wasm-sanitizer", "rust-crypto"}
    assert set(codecov_upload["with"]["path"].splitlines()) == {
        f"artifacts/coverage/rust/{component}/codecov.json"
        for component in rust_components
    }

    paths = [
        f"artifacts/coverage/python/shards/.coverage.shard-{shard}"
        for shard in range(4)
    ]
    for upload in (frontend_upload, rust_upload, codecov_upload):
        paths.extend(upload["with"]["path"].splitlines())
    for producer in workflow["jobs"]["go-tests"]["strategy"]["matrix"]["include"]:
        report = Path(producer["coverage-canonical-path"])
        paths.extend((str(report), str(report.with_name("coverage-provenance.json"))))
    for relative_path in paths:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("producer report\n", encoding="utf-8")

    verify = _step_named(
        workflow["jobs"]["coverage-policy-gate"], "Verify downloaded coverage artifacts"
    )
    shape_checks, separator, _ = verify["run"].partition("verify_producer() {")
    assert separator, "the artifact shape checks must precede provenance verification"
    return shape_checks


def _run_coverage_shape_checks(
    script: str, root: Path
) -> subprocess.CompletedProcess[str]:
    candidates = [
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path(which("bash") or ""),
    ]
    bash = next(
        (str(candidate) for candidate in candidates if candidate.is_file()), None
    )
    assert bash is not None, "the workflow's Bash shell is required"
    return subprocess.run(  # noqa: S603 -- execute the repository-owned workflow step
        [bash, "-e", "-o", "pipefail", "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_downloaded_coverage_shape_accepts_the_complete_producer_inventory(
    downloaded_coverage_shape: str, tmp_path: Path
) -> None:
    result = _run_coverage_shape_checks(downloaded_coverage_shape, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "component", ["rust-native", "rust-wasm-sanitizer", "rust-crypto"]
)
@pytest.mark.parametrize("damage", ["missing", "empty", "misplaced"])
def test_downloaded_coverage_shape_rejects_invalid_required_rust_diagnostics(
    downloaded_coverage_shape: str, tmp_path: Path, component: str, damage: str
) -> None:
    report = tmp_path / "artifacts/coverage/rust" / component / "codecov.json"
    if damage == "missing":
        report.unlink()
    elif damage == "empty":
        report.write_text("", encoding="utf-8")
    else:
        # Preserve the count while substituting an unrecognized component.
        replacement = report.parent.parent / "unexpected" / report.name
        replacement.parent.mkdir()
        report.rename(replacement)

    result = _run_coverage_shape_checks(downloaded_coverage_shape, tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode != 0, "invalid required Rust diagnostic was accepted"
    assert (
        f"::error::Missing or empty required Rust Codecov report: "
        f"artifacts/coverage/rust/{component}/codecov.json"
    ) in output


@pytest.mark.parametrize("extra_directory", ["unexpected", "rust-native/nested"])
def test_downloaded_coverage_shape_rejects_extra_rust_diagnostics(
    downloaded_coverage_shape: str, tmp_path: Path, extra_directory: str
) -> None:
    extra = tmp_path / "artifacts/coverage/rust" / extra_directory / "codecov.json"
    extra.parent.mkdir(parents=True)
    extra.write_text("unexpected report\n", encoding="utf-8")

    result = _run_coverage_shape_checks(downloaded_coverage_shape, tmp_path)
    assert (
        "::error::Rust Codecov report inventory does not match the required components"
        in result.stdout + result.stderr
    )
    assert result.returncode != 0, "extra Rust diagnostic was accepted"


def test_rust_coverage_job_does_not_restore_stale_llvm_build_artifacts() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    rust_job = workflow["jobs"]["rust-tests"]

    cache_step = next(
        step
        for step in rust_job["steps"]
        if step.get("name") == "Cache Cargo registry + target dirs (coverage-safe)"
    )
    assert "cargo-rust-tests-v2-" in cache_step["with"]["key"]
    assert "Cargo.lock" in cache_step["with"]["key"]
    assert all(
        "cargo-rust-tests-v2-" in restore_key
        for restore_key in cache_step["with"]["restore-keys"].splitlines()
        if restore_key.strip()
    )

    components = {
        "rust-native": "rust_ext — native unit tests + coverage (--no-default-features)",
        "rust-wasm-sanitizer": "wasm-sanitizer — native unit tests + coverage",
        "rust-crypto": "rust-crypto — native KAT tests + coverage",
    }
    for component, step_name in components.items():
        coverage_step = next(
            step for step in rust_job["steps"] if step.get("name") == step_name
        )
        assert coverage_step["env"]["CARGO_TARGET_DIR"] == (
            "${{ runner.temp }}/llvm-cov/" + component
        )
        assert coverage_step["env"]["NIGHTLY_CARGO_TARGET_DIR"] == (
            "${{ runner.temp }}/llvm-cov/" + component + "-nightly"
        )
        coverage_script = coverage_step["run"]
        stable_clean = "cargo llvm-cov clean"
        stable_report = f"{component}/llvm.json"
        codecov_report = f"{component}/codecov.json"
        nightly_target = 'export CARGO_TARGET_DIR="$nightly_target_dir"'
        nightly_clean = "cargo +nightly llvm-cov clean"
        nightly_report = f"{component}/branch-llvm.json"
        assert stable_clean in coverage_script
        assert nightly_clean in coverage_script
        assert 'nightly_target_dir="${NIGHTLY_CARGO_TARGET_DIR:?}"' in coverage_script
        assert nightly_target in coverage_script
        assert (
            coverage_script.index(stable_clean)
            < coverage_script.index(stable_report)
            < coverage_script.index(codecov_report)
            < coverage_script.index(nightly_target)
            < coverage_script.index(nightly_clean)
            < coverage_script.index(nightly_report)
        )


def test_rust_dependency_commands_are_lockfile_bound_and_coverage_tool_pinned() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))

    lint_run = _run_text(workflow["jobs"]["rust-lint"])
    clippy_lines = [
        line.strip()
        for line in lint_run.splitlines()
        if line.strip().startswith("cargo clippy ")
    ]
    udeps_lines = [
        line.strip()
        for line in lint_run.splitlines()
        if line.strip().startswith("cargo +nightly udeps ")
    ]
    assert len(clippy_lines) == 3
    assert len(udeps_lines) == 3
    assert all("--locked" in line for line in [*clippy_lines, *udeps_lines])

    rust_tests = workflow["jobs"]["rust-tests"]
    install = next(
        step
        for step in rust_tests["steps"]
        if step.get("name") == "Install cargo-llvm-cov"
    )
    assert install["with"]["tool"] == "cargo-llvm-cov@0.9.1"
    coverage_commands = [
        line.strip()
        for line in _run_text(rust_tests).splitlines()
        if line.strip().startswith(("cargo llvm-cov ", "cargo +nightly llvm-cov "))
        and " clean" not in line
        and " --version" not in line
    ]
    assert coverage_commands
    assert all("--locked" in line for line in coverage_commands)


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
    finalizer_step = steps[0]
    run_script = finalizer_step.get("run", "")
    finalizer_env = str(finalizer_step.get("env", {}))
    expected_result_check = f"${{{{ needs.{policy_job_name}.result }}}}"
    # The finalizer may carry the expression through a job-level environment
    # variable before evaluating it in a shell array.  Keep the trust-boundary
    # assertion strict while accepting either equivalent representation.
    assert (
        expected_result_check in run_script
        or expected_result_check in finalizer_env
        or (f"{policy_job_name}|$" in run_script)
    ), f"ci-success must assert the result of {policy_job_name}"

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

    inventory_commands = "\n".join(
        str(step.get("run", ""))
        for step in inventory_job.get("steps", [])
        if isinstance(step, dict)
    )
    for command in (
        "uv run python scripts/quality/generate_test_inventory.py",
        "uv run python scripts/quality/audit_model_defaults.py",
        "uv run python scripts/quality/validate_ci_check_catalog.py",
        "uv run python scripts/quality/check_orphans_and_anti_patterns.py",
        "uv run python verify_harness.py --repo-only",
    ):
        assert command in inventory_commands, (
            "quality-inventory-check must run every Python helper through the "
            f"locked uv environment: missing {command!r}"
        )
    assert "npm --prefix frontend ci --no-audit --no-fund" in inventory_commands

    # The inventory helper imports SQLAlchemy models, which loads application
    # settings.  Keep the workflow-level secret intentionally empty, but give
    # this unprivileged metadata-only job a fresh process-scoped key so the
    # fail-closed settings validator can run without consuming a repository
    # secret or relying on a checked-in default.
    inventory_step_text = "\n".join(
        str(step.get("run", ""))
        for step in inventory_job.get("steps", [])
        if isinstance(step, dict)
    )
    assert "SECRET_KEY=$(openssl rand -hex 32)" in inventory_step_text
    assert '>> "$GITHUB_ENV"' in inventory_step_text

    inventory_uploads = [
        step
        for step in inventory_job.get("steps", [])
        if "upload-artifact" in str(step.get("uses", ""))
    ]
    assert len(inventory_uploads) == 1, (
        "quality-inventory-check must publish exactly one model-default inventory artifact"
    )
    inventory_upload = inventory_uploads[0].get("with", {})
    assert (
        inventory_upload.get("name")
        == "model-default-inventory-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}"
    )
    assert (
        inventory_upload.get("path") == "artifacts/quality/model-default-inventory.json"
    )
    assert inventory_upload.get("if-no-files-found") == "error"

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
    assert "--retry-connrefused" in kyverno_text
    assert "--retry-all-errors" not in kyverno_text
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


def test_release_download_retries_are_transient_only() -> None:
    """Never retry deterministic HTTP/product errors as if they were flakes."""

    workflow_paths = (
        REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "nightly-full-gate.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-e2e-tests.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml",
    )
    for workflow_path in workflow_paths:
        text = workflow_path.read_text(encoding="utf-8")
        assert "--retry-all-errors" not in text, workflow_path
        assert "--retry-connrefused" in text, workflow_path


def test_ci_success_publishes_current_run_health_artifact() -> None:
    """The existing finalizer must publish one current-run health projection."""

    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    ci_success = workflow["jobs"]["ci-success"]
    assert ci_success["permissions"] == {"actions": "read", "contents": "read"}
    steps = ci_success["steps"]
    checkout = next(
        step
        for step in steps
        if step.get("name") == "Checkout source for CI health report"
    )
    assert checkout["uses"] == CHECKOUT_ACTION_PIN
    assert checkout["with"] == {
        "ref": "${{ github.sha }}",
        "fetch-depth": 1,
        "persist-credentials": False,
    }
    analyzer = next(
        step
        for step in steps
        if step.get("name") == "Generate current-run CI timing ledger"
    )
    analyzer_run = analyzer["run"]
    assert "--diagnostic-lower-bound" in analyzer_run
    assert "${GITHUB_RUN_ID}" in analyzer_run
    assert "--concurrency-cap 20" in analyzer_run
    renderer = next(
        step
        for step in steps
        if step.get("name") == "Render compact current-run CI health report"
    )
    assert "render_ci_health_report.py" in renderer["run"]
    upload = next(
        step
        for step in steps
        if step.get("name") == "Upload current-run CI health report"
    )
    assert upload["uses"] == UPLOAD_ARTIFACT_ACTION_PIN
    assert upload["with"] == {
        "name": "ci-health-${{ github.run_id }}-${{ github.run_attempt }}",
        "path": "artifacts/quality/ci-health-report.*",
        "if-no-files-found": "error",
        "retention-days": 14,
    }


def test_lhci_is_outside_blocking_ci_after_q4_migration() -> None:
    """Blocking CI must not depend on a disabled Lighthouse artifact producer."""

    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert "performance-gate" not in jobs
    assert "performance-gate" not in jobs["ci-success"]["needs"]
    assert jobs["frontend-tests"]["with"]["run-lighthouse"] is False
    finalizer = jobs["ci-success"]["steps"][0]["run"]
    assert "performance-gate" not in finalizer
    assert "performance_expected_result" not in finalizer

    lhci = yaml.safe_load(LHCI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    trigger = lhci.get("on", lhci.get(True))
    assert "schedule" in trigger
    assert "workflow_dispatch" in trigger
    assert "pull_request" not in trigger
    assert "push" not in trigger
    assert "github.ref == 'refs/heads/main'" in lhci["jobs"]["lhci"]["if"]


def test_kyverno_matrix_covers_every_policy_with_positive_and_negative_cases() -> None:
    policies = {
        document["metadata"]["name"]
        for document in yaml.safe_load_all(
            KYVERNO_POLICY_PATH.read_text(encoding="utf-8")
        )
        if isinstance(document, dict)
        and document.get("apiVersion") == "policies.kyverno.io/v1"
        and document.get("kind") == "ValidatingPolicy"
        and isinstance(document.get("metadata"), dict)
    }
    suites = {
        path.name
        for path in KYVERNO_TEST_ROOT.iterdir()
        if path.is_dir() and (path / "kyverno-test.yaml").is_file()
    }

    assert policies, "Kyverno policy file must declare at least one ValidatingPolicy"
    assert suites == policies, (
        "Every ValidatingPolicy must have exactly one executable test suite; "
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
    # These two schemas currently have no independently replayable provider:
    # the callback sender is not implemented in file-processor, and the
    # files.process producer is not exposed as a backend provider handler.
    # Keep them in the consumer-side CI contract suite, but do not let the
    # cross-process artifact job publish an unverified/orphan Pact file.
    assert "test_file_processor_contract.py" not in consumer_text
    assert "test_files_process_contract.py" not in consumer_text
    consumer_only_ci = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "uv run pytest tests/contracts/" in consumer_only_ci
    assert '-k "not integration"' in consumer_only_ci
    assert (
        "--ignore=tests/contracts/test_file_processor_contract.py"
        not in consumer_only_ci
    )
    assert (
        "--ignore=tests/contracts/test_files_process_contract.py"
        not in consumer_only_ci
    )
    assert "test_nats_message_contract.py" in consumer_text
    assert "ws-hub-university-backend.json" in artifact_path
    assert "gateway-university-backend.json" in artifact_path
    assert "university-backend-file-processor.json" in artifact_path
    assert "file-processor-university-backend.json" not in artifact_path

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


def test_unreplayed_pacts_remain_consumer_only() -> None:
    """Unreplayed schemas must not create artifacts consumed as provider pacts."""

    for filename in (
        "test_file_processor_contract.py",
        "test_files_process_contract.py",
        "test_optimizer_grpc_contract.py",
    ):
        source = (REPOSITORY_ROOT / "tests" / "contracts" / filename).read_text(
            encoding="utf-8"
        )
        assert ".write_file(" not in source

    workflow = yaml.safe_load(PACT_WORKFLOW_PATH.read_text(encoding="utf-8"))
    consumer = workflow["jobs"]["consumer"]
    artifact_path = str(consumer["steps"][-1]["with"]["path"])
    assert "file-processor-university-backend.json" not in artifact_path
    assert "university-backend-optimizer-service.json" not in artifact_path
    assert "university-backend-file-processor.json" in artifact_path
    assert not (
        REPOSITORY_ROOT
        / "tests/contracts/pacts/university-backend-optimizer-service.json"
    ).exists()


def test_pact_privileged_install_preserves_configured_go_toolchain() -> None:
    """The Pact installer must not fall back to the runner's system Go under sudo.

    ``actions/setup-go`` prepends the selected toolchain to ``PATH``.  A plain
    ``sudo go`` invocation uses sudo's secure_path instead, which can launch an
    older system Go and trigger an unbounded toolchain download.  The workflow
    therefore has to pass the configured PATH and local toolchain mode
    explicitly into the privileged command.
    """

    workflow = yaml.safe_load(PACT_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["message-provider-verify"]["steps"]
    setup_go = next(step for step in steps if step.get("name") == "Set up Go")
    install = next(
        step for step in steps if step.get("name") == "Install Pact FFI library"
    )

    assert setup_go["with"]["go-version"] == "1.26.9"
    assert setup_go["with"]["cache"] is True
    command = str(install["run"])
    assert "sudo env" in command
    assert 'PATH="$PATH"' in command
    assert "GOTOOLCHAIN=local" in command
    assert "sudo go run" not in command


def test_cross_browser_e2e_is_nightly_while_live_pr_smoke_remains() -> None:
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = nightly["jobs"]
    browser = jobs["browser-matrix"]

    assert "e2e-tests-cross-browser" not in ci["jobs"]
    assert "e2e-tests-cross-browser" not in ci["jobs"]["ci-success"]["needs"]
    assert ci["jobs"]["frontend-tests"]["with"]["run-lighthouse"] is False
    chromium = [
        entry
        for entry in browser["strategy"]["matrix"]["include"]
        if entry["browser"] == "chromium"
    ]
    assert [entry["shard-index"] for entry in chromium] == [1, 2, 3, 4]
    assert all(entry["shard-total"] == 4 for entry in chromium)
    assert {entry["browser"] for entry in browser["strategy"]["matrix"]["include"]} == {
        "chromium",
        "firefox",
        "webkit",
        "mobile-webkit",
    }
    assert browser["if"] == "${{ github.ref == 'refs/heads/main' }}"
    live_path = REPOSITORY_ROOT / ".github" / "workflows" / "live-acceptance.yml"
    live = yaml.safe_load(live_path.read_text(encoding="utf-8"))
    assert "pull_request" in _workflow_triggers(live)


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
        "trivy-revocation-config.sarif": "trivy-revocation-config",
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
    assert image_scan["env"]["TRIVY_DB_REPOSITORY"] == "ghcr.io/aquasecurity/trivy-db:2"

    image_scan_steps = [
        step
        for step in ci_workflow["jobs"]["docker-security-scan"]["steps"]
        if step.get("uses", "").startswith("aquasecurity/trivy-action@")
    ]
    assert len(image_scan_steps) == 1
    assert image_scan_steps[0]["id"] == "trivy_scan"
    assert "continue-on-error" not in image_scan_steps[0]
    image_step_names = [
        step.get("name", "")
        for step in ci_workflow["jobs"]["docker-security-scan"]["steps"]
    ]
    assert not any("retry" in name.lower() for name in image_step_names)
    assert not any("first trivy" in name.lower() for name in image_step_names)
    assert not any("re-assert trivy" in name.lower() for name in image_step_names)


def test_reusable_trivy_materializes_and_validates_each_helm_chart() -> None:
    security_workflow = yaml.safe_load(
        SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    steps = security_workflow["jobs"]["docker-security"]["steps"]

    helm_setup = next(step for step in steps if step.get("name") == "Set up Helm")
    assert helm_setup["uses"] == (
        "azure/setup-helm@9bc31f4ebc9c6b171d7bfbaa5d006ae7abdb4310"
    )
    assert helm_setup["with"]["version"] == "3.17.0"

    dependency_build = next(
        step
        for step in steps
        if step.get("name") == "Build Helm dependencies for Trivy"
    )
    dependency_script = dependency_build["run"]
    _assert_helm_dependency_helper_invocation(dependency_script)

    preflight = next(
        step
        for step in steps
        if step.get("name") == "Validate Helm charts before Trivy configuration scan"
    )
    preflight_script = preflight["run"]
    assert "charts/revocation-store" in preflight_script
    assert "charts/university-ecosystem" in preflight_script
    assert "--helm-values security/trivy-revocation-values.yaml" in preflight_script
    assert "Skipping chart" in preflight_script
    assert "pipefail" in preflight_script

    configuration = next(
        step
        for step in steps
        if step.get("name") == "Run Trivy configuration scanner (IaC)"
    )
    assert configuration["with"]["trivy-config"] == (
        "security/trivy-university-config.yaml"
    )
    assert configuration["with"]["skip-dirs"] == "charts/revocation-store"

    revocation = next(
        step
        for step in steps
        if step.get("name") == "Run Trivy revocation-store configuration scanner"
    )
    assert revocation["id"] == "trivy_revocation"
    assert revocation["continue-on-error"] is True
    assert revocation["with"]["scan-ref"] == "charts/revocation-store"
    assert revocation["with"]["trivy-config"] == (
        "security/trivy-revocation-config.yaml"
    )
    assert revocation["with"]["exit-code"] == "1"

    assert yaml.safe_load(
        (REPOSITORY_ROOT / "security" / "trivy-revocation-config.yaml").read_text(
            encoding="utf-8"
        )
    )["misconfiguration"]["helm"]["values"] == ["security/trivy-revocation-values.yaml"]
    scan_values = yaml.safe_load(
        (REPOSITORY_ROOT / "security" / "trivy-revocation-values.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert scan_values["applicationReleaseName"] == "trivy-scan"
    assert scan_values["redis"]["fullnameOverride"] == "trivy-scan-revocation-redis"
    assert scan_values["redis"]["image"]["digest"].startswith("sha256:")
    assert scan_values["redis"]["metrics"]["image"]["digest"].startswith("sha256:")
    assert all(
        not isinstance(value, str) or "password" not in value.lower()
        for value in scan_values["redis"].values()
        if not isinstance(value, dict)
    )
    university_config = yaml.safe_load(
        (REPOSITORY_ROOT / "security" / "trivy-university-config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert university_config["misconfiguration"]["helm"]["set"] == [
        "applicationSecrets.existingSecret=trivy-scan-application"
    ]


def test_reusable_trivy_install_isolated_from_hosted_apt_mirror_drift() -> None:
    """Trivy must be checksum-bound and independent of hosted apt mirrors."""

    security_workflow = yaml.safe_load(
        SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    install = next(
        step
        for step in security_workflow["jobs"]["docker-security"]["steps"]
        if step.get("name") == "Install checksum-pinned Trivy"
    )
    script = str(install["run"])

    assert (
        install["env"]
        == {
            "TRIVY_VERSION": "0.73.0",
            "TRIVY_ARCHIVE_SHA256": (
                "2edd39da482bb4e9831962487b68f68e3928ec3137794757f54d00383d79547b"  # pragma: allowlist secret -- public Trivy release checksum
            ),
        }
    )
    assert "--proto '=https'" in script
    assert "--tlsv1.2" in script
    assert (
        "https://github.com/aquasecurity/trivy/releases/download/"
        "v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
    ) in script
    assert "sha256sum --check --strict" in script
    assert "apt-get" not in script
    assert "aquasecurity.github.io/trivy-repo" not in script
    assert "wget" not in script

    lines = [line.strip() for line in script.splitlines()]
    checksum_index = next(
        index
        for index, line in enumerate(lines)
        if "sha256sum --check --strict" in line
    )
    extract_index = next(
        index for index, line in enumerate(lines) if line.startswith("tar --extract")
    )
    install_index = next(
        index for index, line in enumerate(lines) if line.startswith("sudo install")
    )
    assert checksum_index < extract_index < install_index


def test_iac_scan_exceptions_use_supported_scoped_syntax() -> None:
    """Keep documented IaC exceptions active instead of silently ignored."""

    exception_files = (
        REPOSITORY_ROOT / ".github" / "workflows" / "lhci-linux.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "dast.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "build-orchestrated-linux.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "visual-audit.yml",
        REPOSITORY_ROOT / "Dockerfile.test",
        REPOSITORY_ROOT / "Dockerfile.protogen",
        REPOSITORY_ROOT / "k8s" / "backend" / "deployment.yaml",
        REPOSITORY_ROOT / "k8s" / "frontend" / "deployment.yaml",
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
    ]


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


def test_e2e_coverage_is_chromium_opt_in_and_staged_for_codecov() -> None:
    e2e_workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    call = _workflow_triggers(e2e_workflow)["workflow_call"]
    inputs = call["inputs"]
    assert inputs["collect-coverage"]["default"] is False
    assert "CODECOV_TOKEN" not in call.get("secrets", {})

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

    artifact_step = next(
        step for step in steps if step.get("name") == "Upload E2E coverage artifact"
    )
    assert "inputs.collect-coverage" in artifact_step["if"]
    assert "inputs.browser == 'chromium'" in artifact_step["if"]
    assert artifact_step["with"]["path"] == "frontend/coverage/e2e/"
    assert not any(
        str(step.get("uses", "")).startswith("codecov/codecov-action@")
        for step in steps
    )
    assert e2e_workflow["permissions"] == {"contents": "read"}
    assert e2e_workflow["jobs"]["e2e"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }

    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    staging = next(
        step
        for step in ci_workflow["jobs"]["coverage-policy-gate"]["steps"]
        if step.get("name") == "Stage trusted Codecov reports"
    )
    assert "frontend/coverage/lcov.info" in staging["run"]
    assert "artifacts/coverage/codecov/frontend.lcov" in staging["run"]

    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    browser = nightly["jobs"]["browser-matrix"]
    assert browser["with"]["collect-coverage"] == "${{ matrix.browser == 'chromium' }}"
    assert "e2e-tests" not in ci_workflow["jobs"]


def test_codecov_oidc_permissions_are_scoped_to_trusted_upload_job() -> None:
    """Only the trusted main-branch uploader receives an OIDC token."""

    reusable_workflows = (
        (BACKEND_WORKFLOW_PATH, "unit-tests"),
        (FRONTEND_WORKFLOW_PATH, "unit-tests"),
        (E2E_WORKFLOW_PATH, "e2e"),
        (GO_WORKFLOW_PATH, "test"),
    )
    for workflow_path, upload_job_name in reusable_workflows:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        call = _workflow_triggers(workflow)["workflow_call"]
        assert workflow["permissions"] == {"contents": "read"}
        assert "CODECOV_TOKEN" not in call.get("secrets", {})
        expected_permissions = {"contents": "read"}
        if workflow_path == E2E_WORKFLOW_PATH:
            expected_permissions["actions"] = "read"
        assert workflow["jobs"][upload_job_name]["permissions"] == expected_permissions
        assert not any(
            str(step.get("uses", "")).startswith("codecov/codecov-action@")
            for step in workflow["jobs"][upload_job_name]["steps"]
        )

    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert nightly["permissions"] == {"contents": "read"}
    assert "CODECOV_TOKEN" not in NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8")
    for job_name in ("backend-full", "backend-integration"):
        assert nightly["jobs"][job_name]["permissions"] == {"contents": "read"}
    assert nightly["jobs"]["browser-matrix"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }

    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    trusted = ci["jobs"]["codecov-upload"]
    assert trusted["permissions"] == {"contents": "read", "id-token": "write"}
    assert "github.ref == 'refs/heads/main'" in trusted["if"]
    uploads = [
        step
        for step in trusted["steps"]
        if str(step.get("uses", "")).startswith("codecov/codecov-action@")
    ]
    expected_reports = {
        "python": "artifacts/coverage/codecov/python.xml",
        "frontend": "artifacts/coverage/codecov/frontend.lcov",
        "go-gateway": "artifacts/coverage/codecov/go-gateway.out",
        "go-ws-hub": "artifacts/coverage/codecov/go-ws-hub.out",
        "go-file-processor": "artifacts/coverage/codecov/go-file-processor.out",
        "go-shared": "artifacts/coverage/codecov/go-shared.out",
        "rust-native": "artifacts/coverage/codecov/rust-native.json",
        "rust-wasm-sanitizer": ("artifacts/coverage/codecov/rust-wasm-sanitizer.json"),
        "rust-crypto": "artifacts/coverage/codecov/rust-crypto.json",
    }
    assert len(uploads) == len(expected_reports)
    assert {step["with"]["flags"] for step in uploads} == set(expected_reports)
    for upload in uploads:
        settings = upload["with"]
        flag = settings["flags"]
        assert settings["files"] == expected_reports[flag]
        assert settings["use_oidc"] is True
        assert settings["disable_search"] is True
        assert settings["fail_ci_if_error"] is True
        assert settings["name"] == f"trusted-main-{flag}-${{{{ github.sha }}}}"


def test_sbom_go_gate_uses_symbol_aware_reachable_vulnerability_analysis() -> None:
    """Keep full OSV reporting while blocking every reachable Go vulnerability."""

    workflow = yaml.safe_load(SBOM_WORKFLOW_PATH.read_text(encoding="utf-8"))
    report_job = workflow["jobs"]["sbom-go"]
    report_script = "\n".join(str(step.get("run", "")) for step in report_job["steps"])
    assert "osv-scanner scan --recursive --format sarif" in report_script
    assert any(
        str(step.get("uses", "")).startswith("github/codeql-action/upload-sarif@")
        for step in report_job["steps"]
    )

    gate_steps = workflow["jobs"]["vuln-gate"]["steps"]
    install = next(
        step for step in gate_steps if step.get("name") == "Install govulncheck"
    )
    assert install["run"] == "go install golang.org/x/vuln/cmd/govulncheck@v1.7.0"

    scan = next(
        step
        for step in gate_steps
        if step.get("name") == "Go — govulncheck reachable vulnerability gate"
    )
    scan_script = scan["run"]
    expected_packages = (
        "./services/gateway/...",
        "./services/ws-hub/...",
        "./services/file-processor/...",
        "./services/cmd/uni-cli/...",
        "./services/pkg/logging/...",
        "./services/pkg/spiffe/...",
        "./services/pkg/spicedb/...",
    )
    assert scan_script.strip().startswith("govulncheck \\")
    assert all(package in scan_script for package in expected_packages)
    assert "osv-scanner" not in scan_script
    assert "max_cvss" not in scan_script
    assert "score < 0" not in scan_script

    reusable_audit = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-security-audit.yml"
    ).read_text(encoding="utf-8")
    assert "go install golang.org/x/vuln/cmd/govulncheck@v1.7.0" in reusable_audit
    assert "govulncheck@v1.5.0" not in reusable_audit


def test_dependency_audit_scanners_and_rust_policy_are_exactly_pinned() -> None:
    """Keep scanner behavior and RustSec severity policy reproducible."""

    project = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    security_dependencies = project["dependency-groups"]["security"]
    assert "pip-audit==2.10.1" in security_dependencies
    assert not any(
        dependency.startswith("pip-audit") and dependency != "pip-audit==2.10.1"
        for dependency in security_dependencies
    )
    dev_dependencies = project["dependency-groups"]["dev"]
    assert "pip-audit==2.10.1" in dev_dependencies
    assert not any(
        dependency.startswith("pip-audit") and dependency != "pip-audit==2.10.1"
        for dependency in dev_dependencies
    )
    uv_overrides = project["tool"]["uv"]["override-dependencies"]
    assert "pip>=26.2.0" in uv_overrides

    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8"))
    pip_audit_packages = [
        package for package in lock["package"] if package.get("name") == "pip-audit"
    ]
    assert [package["version"] for package in pip_audit_packages] == ["2.10.1"]
    pip_packages = [
        package for package in lock["package"] if package.get("name") == "pip"
    ]
    assert [package["version"] for package in pip_packages] == ["26.2.1"]

    sbom_text = SBOM_WORKFLOW_PATH.read_text(encoding="utf-8")
    install_command = "cargo install cargo-audit --version 0.22.2 --locked"
    assert sbom_text.count(install_command) == 3
    assert "cargo install cargo-audit --version 0.21.2" not in sbom_text

    audit_config = tomllib.loads(RUST_AUDIT_CONFIG_PATH.read_text(encoding="utf-8"))
    assert audit_config["advisories"] == {
        "ignore": [],
        "severity_threshold": "high",
    }
    assert DEPENDENCY_AUDIT_VALIDATOR_PATH.is_file()
    assert OSV_BATCH_AUDIT_PATH.is_file()


def test_pytest_asyncio_import_is_clean_under_python314_deprecation_errors() -> None:
    """Keep the Python 3.14 test runner free of import-time deprecation errors."""

    result = subprocess.run(  # noqa: S603 -- trusted interpreter, fixed import probe
        [
            sys.executable,
            "-W",
            "error::DeprecationWarning",
            "-c",
            "import pytest_asyncio",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_sbom_python_and_rust_audits_capture_then_validate_reports() -> None:
    """Require report validation to distinguish findings from scanner failures."""

    workflow = yaml.safe_load(SBOM_WORKFLOW_PATH.read_text(encoding="utf-8"))
    gate = workflow["jobs"]["vuln-gate"]
    # Keep the main-CI check context from existing run history stable even when
    # the implementation enforces a stricter policy.
    assert gate["name"] == "Vulnerability gate (CRITICAL/HIGH)"
    # A cold gate compiles cargo-audit and runs Python, Go, and Rust network
    # scanners sequentially; fifteen minutes is too close to observed cold time.
    assert gate["timeout-minutes"] >= 30
    gate_steps = gate["steps"]
    gate_step_names = {step.get("name") for step in gate_steps}
    python_name = "Python — known-vulnerability allowlist gate"
    rust_name = "Rust — high/critical/unknown vulnerability gate"
    assert python_name in gate_step_names
    assert rust_name in gate_step_names

    python_script = next(
        step["run"] for step in gate_steps if step.get("name") == python_name
    )
    assert (
        "uv run --frozen --no-sync python scripts/osv_batch_audit.py" in python_script
    )
    assert "--requirement /tmp/requirements.txt" in python_script
    assert "--timeout 30" in python_script
    assert "--attempts 4" in python_script
    assert "--batch-size 100" in python_script
    assert "--output /tmp/pip-audit.json" in python_script
    assert "pip_audit_status=$?" in python_script
    assert "set +e" in python_script and "set -e" in python_script
    assert python_script.index("set +e") < python_script.index("pip_audit_status=$?")
    assert python_script.index("pip_audit_status=$?") < python_script.index("set -e")
    assert (
        "uv run --frozen --no-sync python scripts/check_dependency_audit_report.py pip"
    ) in python_script
    assert "--allowlist security/audit-allowlist.yaml" in python_script

    rust_script = next(
        step["run"] for step in gate_steps if step.get("name") == rust_name
    )
    assert 'cargo audit "${cargo_audit_fetch_args[@]}"' in rust_script
    assert '--file "../../$lockfile"' in rust_script
    assert '--json > "/tmp/rust-audit-reports/$report_name"' in rust_script
    assert "cargo_audit_status=$?" in rust_script
    assert "set +e" in rust_script and "set -e" in rust_script
    assert "scripts/check_dependency_audit_report.py cargo" in rust_script
    assert "--report-only" not in rust_script

    report_steps = workflow["jobs"]["sbom-rust"]["steps"]
    report_script = next(
        step["run"]
        for step in report_steps
        if step.get("name") == "Run cargo-audit report and validate output"
    )
    assert "cargo_audit_status=$?" in report_script
    assert "scripts/check_dependency_audit_report.py cargo" in report_script
    assert "--report-only" in report_script

    relevant_scripts = (python_script, rust_script, report_script)
    for script in relevant_scripts:
        assert "|| true" not in script
        assert "2>/dev/null" not in script
        assert "--ignore-vuln-file" not in script
        assert "uvx pip-audit" not in script
        assert "float(cvss)" not in script


def test_sbom_rust_audit_covers_every_tracked_lockfile() -> None:
    """Every Rust lockfile, including fuzz targets, must be audited fail-closed."""

    workflow = yaml.safe_load(SBOM_WORKFLOW_PATH.read_text(encoding="utf-8"))
    git_executable = which("git")
    assert git_executable is not None, "Git is required for repository contracts"
    tracked_result = subprocess.run(  # noqa: S603 -- resolved Git, fixed operation
        [git_executable, "ls-files", "-z", "--", "*Cargo.lock"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_lockfiles = {path for path in tracked_result.stdout.split("\0") if path}
    configured_lockfiles = {
        path.strip()
        for path in workflow["env"]["RUST_AUDIT_LOCKFILES"].splitlines()
        if path.strip()
    }

    assert configured_lockfiles == tracked_lockfiles
    assert any("/fuzz/" in path for path in configured_lockfiles)

    report_script = next(
        step["run"]
        for step in workflow["jobs"]["sbom-rust"]["steps"]
        if step.get("name") == "Run cargo-audit report and validate output"
    )
    gate_script = next(
        step["run"]
        for step in workflow["jobs"]["vuln-gate"]["steps"]
        if step.get("name") == "Rust — high/critical/unknown vulnerability gate"
    )
    for script in (report_script, gate_script):
        assert "while IFS= read -r lockfile" in script
        assert 'done <<< "$RUST_AUDIT_LOCKFILES"' in script
        assert 'cargo audit "${cargo_audit_fetch_args[@]}"' in script
        assert '--file "../../$lockfile"' in script
        assert 'report_name="${lockfile//\\//__}.json"' in script
        assert 'if [[ ! -f "../../$lockfile" ]]' in script
        assert "audit_count=$((audit_count + 1))" in script
        assert "if (( audit_count == 0 ))" in script

    artifact_step = next(
        step
        for step in workflow["jobs"]["sbom-rust"]["steps"]
        if step.get("name") == "Upload Rust audit artifact"
    )
    assert artifact_step["with"]["path"] == "rust-audit-reports/"


def test_reusable_python_audit_uses_the_same_fail_closed_validator() -> None:
    """Do not leave the duplicate active Python audit path fail-open."""

    workflow = yaml.safe_load(SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["pip-audit"]["steps"]
    step_name = "Run Python known-vulnerability allowlist gate"
    assert step_name in {step.get("name") for step in steps}
    script = next(step["run"] for step in steps if step.get("name") == step_name)
    assert "uv run --frozen --no-sync python scripts/osv_batch_audit.py" in script
    assert "--requirement /tmp/requirements.txt" in script
    assert "--timeout 30" in script
    assert "--attempts 4" in script
    assert "--batch-size 100" in script
    assert "--output /tmp/pip-audit.json" in script
    assert "pip_audit_status=$?" in script
    assert "set +e" in script and "set -e" in script
    assert (
        "uv run --frozen --no-sync python scripts/check_dependency_audit_report.py pip"
    ) in script
    assert "--allowlist security/audit-allowlist.yaml" in script
    for unsafe in ("|| true", "2>/dev/null", "--ignore-vuln-file", "uvx pip-audit"):
        assert unsafe not in script

    npm_helper = (REPOSITORY_ROOT / "scripts" / "audit_dependencies.py").read_text(
        encoding="utf-8"
    )
    assert "collect_pip_advisories" not in npm_helper
    assert 'parser.add_argument("--pip"' not in npm_helper
    assert 'parser.add_argument("--npm"' in npm_helper


@pytest.mark.parametrize(
    "workflow_path,job_name",
    (
        (SBOM_WORKFLOW_PATH, "vuln-gate"),
        (SECURITY_WORKFLOW_PATH, "pip-audit"),
    ),
)
def test_python_audit_exports_exclude_local_workspace_editables(
    workflow_path: Path, job_name: str
) -> None:
    """pip-audit must receive third-party pins resolvable outside the checkout."""

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    export_step = next(
        step
        for step in workflow["jobs"][job_name]["steps"]
        if step.get("name") == "Export Python requirements"
    )
    assert (
        "uv export --frozen --no-hashes --no-dev --no-emit-workspace"
        in export_step["run"]
    )


def test_cargo_audit_validator_has_no_runtime_pyyaml_dependency() -> None:
    """The Rust SBOM job invokes cargo validation before uv/PyYAML setup."""

    validator_module = ast.parse(
        DEPENDENCY_AUDIT_VALIDATOR_PATH.read_text(encoding="utf-8")
    )
    top_level_imports = {
        alias.name
        for statement in validator_module.body
        if isinstance(statement, ast.Import)
        for alias in statement.names
    }
    top_level_imports.update(
        statement.module
        for statement in validator_module.body
        if isinstance(statement, ast.ImportFrom) and statement.module is not None
    )
    assert "yaml" not in top_level_imports


def test_active_go_toolchain_pins_use_current_security_patch() -> None:
    """Executable Go surfaces use a pinned security-patched toolchain.

    The bounded fuzz workflows intentionally use Go 1.27.2 because it carries
    the upstream fix for the fuzz deadline race; all other Go surfaces remain
    on the repository-wide 1.26.9 security patch.
    """

    expected_version = "1.26.9"
    manifest_expected_version = "1.26.4"
    manifests = (
        "go.mod",
        "go.work",
        "gen/go/go.mod",
        "services/cmd/uni-cli/go.mod",
        "services/file-processor/go.mod",
        "services/gateway/go.mod",
        "services/pkg/logging/go.mod",
        "services/pkg/spiffe/go.mod",
        "services/ws-hub/go.mod",
    )
    for relative_path in manifests:
        directives = [
            line.split(maxsplit=1)[1]
            for line in (REPOSITORY_ROOT / relative_path)
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith("go ")
        ]
        assert directives == [manifest_expected_version], relative_path

    literal_version_workflows = (
        "benchmark.yml",
        "ci.yml",
        "go-fuzz.yml",
        "go-lint.yml",
        "manual-performance-evidence.yml",
        "nilaway.yml",
        "reusable-cache-deps.yml",
        "reusable-go-integration-tests.yml",
        "reusable-go-tests.yml",
        "reusable-security-audit.yml",
        "contract-tests.yml",
    )
    for workflow_name in literal_version_workflows:
        workflow_text = (
            REPOSITORY_ROOT / ".github" / "workflows" / workflow_name
        ).read_text(encoding="utf-8")
        assert '"1.26.4"' not in workflow_text, workflow_name
        assert '"1.26.5"' not in workflow_text, workflow_name
        if workflow_name == "go-fuzz.yml":
            assert '"1.26.9"' not in workflow_text, workflow_name
            assert '"1.27.2"' in workflow_text, workflow_name
        else:
            assert f'"{expected_version}"' in workflow_text, workflow_name

    assert BENCHMARK_GO_IMAGE == (
        "docker.io/library/golang:1.26.9-bookworm@"
        "sha256:d9c68c2c51161e12fd77e4c6320687c9cd86e1af1e3ad6e6cd63ff970641453c"
    )


def test_pr_executed_go_jobs_never_persist_the_workflow_token() -> None:
    """PR-controlled Go tooling must not receive a persisted Git credential."""

    jobs = (
        ("ci.yml", "go-fuzz"),
        ("go-fuzz.yml", "fuzz"),
        ("nilaway.yml", "nilaway"),
        ("reusable-go-integration-tests.yml", "integration"),
    )
    for workflow_name, job_name in jobs:
        workflow = yaml.safe_load(
            (REPOSITORY_ROOT / ".github" / "workflows" / workflow_name).read_text(
                encoding="utf-8"
            )
        )
        checkout = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["persist-credentials"] is False, (
            workflow_name,
            job_name,
        )


def test_go_service_container_example_uses_canonical_immutable_toolchain() -> None:
    """The documented race-test container must match audited CI provenance."""

    services_agents = (REPOSITORY_ROOT / "services" / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert BENCHMARK_GO_IMAGE in services_agents
    assert "golang:1.26.4-bookworm" not in services_agents


def test_go_integration_workflow_validates_service_input_before_shell_use() -> None:
    workflow_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-go-integration-tests.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["integration"]

    assert job["env"]["SERVICE_DIRECTORY"] == "${{ inputs.service-directory }}"
    scripts = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "${{ inputs.service-directory }}" not in scripts

    validation = next(
        step for step in job["steps"] if step.get("id") == "validate-service"
    )
    for service in (
        "services/gateway",
        "services/file-processor",
        "services/ws-hub",
    ):
        assert service in validation["run"]

    upload = next(
        step
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )
    assert "inputs.service-directory" not in upload["with"]["path"]
    assert "steps.validate-service.outcome == 'success'" in upload["if"]


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


def test_frontend_build_memory_budget_keeps_native_headroom_bounded() -> None:
    workflow = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    env = workflow["jobs"]["build"]["env"]

    # RSS includes Rolldown's native worker pool in addition to V8's bounded
    # heap, so the process ceiling must retain finite native-memory headroom.
    assert env["FRONTEND_BUILD_MAX_RSS_MB"] == "2048"
    assert env["FRONTEND_BUILD_MAX_OLD_SPACE_MB"] == "1536"


def test_linux_build_reproducibility_gate_canonicalizes_known_metadata() -> None:
    workflow = yaml.safe_load(
        BUILD_ORCHESTRATED_LINUX_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    run = next(
        step["run"]
        for step in workflow["jobs"]["build-validation"]["steps"]
        if step.get("name") == "Run build-orchestrated.mjs × N"
    )

    assert "SHELL_STABLE_HASH=$(sed -E" in run
    assert 'nonce="__CSP_NONCE__"' in run
    assert "match-updated-at" in run
    assert "SW_STABLE_HASH=$(sed -E" in run
    assert "_shell\\.html" in run
    assert '"url":"_shell.html"' in run
    assert '"url":"offline.html"' in run
    assert '"${SHELL_STABLE_HASHES[$i]}"' in run
    assert '"${SW_STABLE_HASHES[$i]}"' in run
    assert "grep -q 'nonce=\"__CSP_NONCE__\"'" in run


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


def test_e2e_playwright_install_retries_and_ignores_stale_chrome_apt_source() -> None:
    workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    install_step = next(
        step
        for step in workflow["jobs"]["e2e"]["steps"]
        if step.get("name") == "Install Playwright"
    )
    assert install_step["run"].strip() == (
        'bash ../scripts/ci/install-playwright-with-deps.sh "$BROWSER"'
    )

    helper = (
        REPOSITORY_ROOT / "scripts" / "ci" / "install-playwright-with-deps.sh"
    ).read_text(encoding="utf-8")

    assert "google-chrome.list" in helper
    assert "google-chrome.sources" in helper
    assert "for attempt in 1 2 3" in helper
    assert 'npx playwright install --with-deps "${browsers[@]}"' in helper
    assert 'npx playwright install-deps --dry-run "${browsers[@]}"' in helper
    assert 'npx playwright install "${browsers[@]}"' in helper
    assert "PLAYWRIGHT_SKIP_SYSTEM_DEPS must be 0/false or 1/true" in helper
    assert "system dependency probe failed" in helper
    assert "Playwright installation failed after 3 attempts" in helper

    assert install_step["env"]["PLAYWRIGHT_SKIP_SYSTEM_DEPS"] == "1"


def test_e2e_playwright_browser_cache_is_lock_bound_and_narrow() -> None:
    workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["e2e"]["steps"]
    restore_step = next(
        step for step in steps if step.get("name") == "Restore Playwright browser cache"
    )
    save_step = next(
        step for step in steps if step.get("name") == "Save Playwright browser cache"
    )

    # Public actions/cache commit identifier, not credential material.
    expected_cache_action = (
        "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"  # pragma: allowlist secret
    )
    assert restore_step["uses"] == "actions/cache/restore@" + expected_cache_action
    assert save_step["uses"] == "actions/cache/save@" + expected_cache_action
    assert restore_step["with"]["path"] == "~/.cache/ms-playwright"
    assert save_step["with"]["path"] == "~/.cache/ms-playwright"

    cache_key = restore_step["with"]["key"]
    assert cache_key == save_step["with"]["key"]
    assert cache_key.startswith("playwright-browsers-v1-")
    assert "${{ runner.os }}" in cache_key
    assert "inputs.browser == 'mobile-webkit' && 'webkit' || inputs.browser" in (
        cache_key
    )
    assert "hashFiles('frontend/package-lock.json')" in cache_key
    assert "node_modules" not in cache_key
    assert "frontend/playwright-report" not in cache_key
    assert "steps.restore_playwright_browser_cache.outputs.cache-hit" in save_step["if"]


def test_all_linux_playwright_bootstraps_use_the_resilient_helper() -> None:
    helper = REPOSITORY_ROOT / "scripts" / "ci" / "install-playwright-with-deps.sh"
    assert helper.is_file()
    helper_text = helper.read_text(encoding="utf-8")
    for workflow_path in (
        E2E_WORKFLOW_PATH,
        REPOSITORY_ROOT / ".github" / "workflows" / "unauthenticated-routes-smoke.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "admin-smoke-monitoring.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "visual-audit.yml",
    ):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        install_steps = [
            step
            for job in workflow.get("jobs", {}).values()
            if isinstance(job, dict)
            for step in job.get("steps", [])
            if isinstance(step, dict)
            and (
                "playwright install --with-deps" in str(step.get("run", ""))
                or "install-playwright-with-deps.sh" in str(step.get("run", ""))
            )
        ]
        assert install_steps, f"{workflow_path.name} has no Playwright bootstrap"
        assert all(
            "install-playwright-with-deps.sh" in str(step["run"])
            for step in install_steps
        )

    assert "set -euo pipefail" in helper_text
    assert "Acquire::Retries" not in helper_text
    assert "exit 1" in helper_text

    # The hosted reusable E2E lane is the only caller opting out of the apt
    # bootstrap. Local and standalone smoke/audit workflows must retain the
    # helper's default full dependency installation.
    e2e_workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    e2e_install = next(
        step
        for step in e2e_workflow["jobs"]["e2e"]["steps"]
        if step.get("name") == "Install Playwright"
    )
    assert e2e_install["env"]["PLAYWRIGHT_SKIP_SYSTEM_DEPS"] == "1"
    for workflow_path in (
        REPOSITORY_ROOT / ".github" / "workflows" / "unauthenticated-routes-smoke.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "admin-smoke-monitoring.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "visual-audit.yml",
    ):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if "install-playwright-with-deps.sh" in str(step.get("run", "")):
                    assert "PLAYWRIGHT_SKIP_SYSTEM_DEPS" not in step.get("env", {})


def test_cross_browser_navigation_retries_only_transient_abort_errors() -> None:
    source = (
        REPOSITORY_ROOT / "frontend" / "tests" / "e2e" / "utils" / "navigation.ts"
    ).read_text(encoding="utf-8")

    assert "NS_BINDING_ABORTED" in source
    assert "net::ERR_ABORTED" in source
    assert "MAX_ATTEMPTS = 3" in source
    assert "waitForTimeout(250 * attempt)" in source
    assert "if (!TRANSIENT_NAVIGATION_ERROR.test(message)" in source


def test_go_coverage_artifacts_are_staged_for_trusted_codecov_upload() -> None:
    workflow = yaml.safe_load(GO_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["test"]["steps"]
    upload = next(
        step for step in steps if step.get("name") == "Upload coverage artifacts"
    )
    assert "coverage.out" in upload["with"]["path"]
    assert upload["with"]["name"] == "${{ steps.artifact-name.outputs.name }}"
    artifact_name = next(
        step for step in steps if step.get("name") == "Generate artifact name"
    )
    assert (
        "go-coverage-$SANITIZED-attempt-${{ github.run_attempt }}"
        in artifact_name["run"]
    )

    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    go_matrix = ci["jobs"]["go-tests"]["strategy"]["matrix"]["include"]
    assert {entry["coverage-threshold"] for entry in go_matrix} == {100}
    staging = next(
        step
        for step in ci["jobs"]["coverage-policy-gate"]["steps"]
        if step.get("name") == "Stage trusted Codecov reports"
    )
    for report in (
        "go-gateway.out",
        "go-ws-hub.out",
        "go-file-processor.out",
        "go-shared.out",
    ):
        assert f"artifacts/coverage/codecov/{report}" in staging["run"]


def test_go_integration_is_blocking_while_full_chaos_stays_nightly() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    nightly_workflow = yaml.safe_load(
        NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    blocking_script = workflow["jobs"]["ci-success"]["steps"][0]["run"]

    for job_name in (
        "go-integration-ws-hub",
        "go-integration-file-processor",
        "go-integration-gateway",
    ):
        assert f"needs.{job_name}.result" in blocking_script

    # Full load/chaos remains in the intentionally longer nightly workflow.
    assert "chaos-tests" not in workflow["jobs"]
    assert "chaos-loadtest-orchestrator" not in workflow["jobs"]
    assert "load-and-chaos" not in workflow["jobs"]
    assert "Load and Chaos Resilience Tests" not in CI_WORKFLOW_PATH.read_text(
        encoding="utf-8"
    )
    assert {"chaos-tests", "chaos-loadtest-orchestrator", "load-and-chaos"} <= set(
        nightly_workflow["jobs"]
    )
    assert nightly_workflow["jobs"]["load-and-chaos"]["name"] == (
        "Load and chaos resilience"
    )
    assert nightly_workflow["jobs"]["load-and-chaos"]["timeout-minutes"] == 45


def test_blocking_ci_contains_no_mutation_evidence_execution() -> None:
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = ci["jobs"]
    ci_success = jobs["ci-success"]
    gate = _step_named(ci_success, "Check all jobs passed")["run"].lower()

    assert not any("mutation" in job_id or "stryker" in job_id for job_id in jobs)
    assert not any(
        "mutation" in need or "stryker" in need for need in ci_success["needs"]
    )
    assert not any(
        token in gate
        for token in ("mutation", "stryker", "schemathesis", "chaos", "cross-browser")
    )
    assert {
        "coverage-policy-gate",
        "security-audit",
        "provenance-check",
        "openapi-verify",
    } <= set(ci_success["needs"])
    assert jobs["frontend-tests"]["with"]["run-lighthouse"] is False


def test_backend_mutation_evidence_remains_nightly_and_manual() -> None:
    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    nightly_triggers = _workflow_triggers(nightly)
    assert {"schedule", "workflow_dispatch"} <= set(nightly_triggers)
    caller = nightly["jobs"]["mutation-tests-full"]
    assert (
        caller["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert caller["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"

    full = yaml.safe_load(
        FULL_BACKEND_MUTATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    full_jobs = full["jobs"]
    plan = full_jobs["mutation-tests-full-plan"]
    mutation = full_jobs["mutation-tests-full"]
    aggregate = full_jobs["mutation-tests-full-aggregate"]
    assert mutation["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert mutation["strategy"]["max-parallel"] == 8
    assert plan["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
    ]
    plan_step = _step_named(plan, "Plan and budget every exact full mutation shard")
    assert "scripts/plan_mutmut_shards.py" in plan_step["run"]
    assert "--num-shards 128" in plan_step["run"]
    assert "--max-timeout-seconds 20970" in plan_step["run"]
    aggregate_step = _step_named(aggregate, "Merge and gate full mutation evidence")
    assert "--expected-shards 128" in aggregate_step["run"]
    assert "scripts/check_mutation_score.py --min-score 100" in aggregate_step["run"]

    manual = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    assert "workflow_dispatch" in _workflow_triggers(manual)
    manual_jobs = manual["jobs"]
    assert manual_jobs["manual-mutation-stats"]["strategy"]["matrix"][
        "stats_shard"
    ] == list(range(8))
    assert manual_jobs["manual-mutation-tests"]["strategy"]["matrix"]["shard"] == list(
        range(1, 129)
    )
    assert manual_jobs["manual-mutation-tests"]["needs"] == "manual-mutation-stats"


def test_manual_incremental_mutation_keeps_deadline_and_exact_artifact_proof() -> None:
    manual = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    jobs = manual["jobs"]
    mutation = jobs["manual-mutation-tests"]
    assert mutation["timeout-minutes"] == 360
    assert mutation["strategy"]["max-parallel"] == 20
    deadline = _step_named(mutation, "Record mutmut job deadline")["run"]
    assert "MUTMUT_JOB_DEADLINE_EPOCH" in deadline
    run = _step_named(
        mutation, "Run manual incremental mutmut (blocking, stats-derived budget)"
    )["run"]
    for invariant in (
        "scripts/plan_mutmut_shards.py",
        "--num-shards 128",
        "--max-timeout-seconds 20970",
        "--prepare-exact-execution",
        "--verify-exact-execution",
        "scripts/mutmut_ci_gate.py",
    ):
        assert invariant in run
    assert "MUTMUT_JOB_DEADLINE_EPOCH" in str(
        mutation.get("env", {})
    ) or "Record mutmut job deadline" in str(mutation["steps"])
    assert (
        _step_named(mutation, "Validate manual mutation evidence artifact")[
            "run"
        ].count("test -s")
        >= 3
    )
    for job_id in ("manual-mutation-stats", "manual-mutation-tests"):
        checkout = next(
            step
            for step in jobs[job_id]["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["persist-credentials"] is False


def test_pr_code_execution_never_receives_repository_ci_secret() -> None:
    workflow_text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)

    assert workflow["env"]["SECRET_KEY"] == ""
    assert "secrets.CI_TEST_SECRET_KEY" not in workflow_text


def test_reusable_node_cache_never_restores_stale_node_modules() -> None:
    """Dependency cache must contain only the lock-bound npm download store.

    Restoring ``node_modules`` from a broad prefix can silently combine an
    older executable tree with the current lockfile.  The reusable cache
    workflow therefore caches only ``~/.npm`` and always runs ``npm ci``.
    """

    workflow_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-cache-deps.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["cache"]["steps"]
    cache_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Cache Node.js dependencies"
    )
    cache_paths = str(cache_step["with"]["path"])
    assert "frontend/node_modules" not in cache_paths
    assert "~/.npm" in cache_paths
    assert "hashFiles('frontend/package-lock.json')" in cache_step["with"]["key"]
    assert "restore-keys" not in cache_step["with"]

    install_step = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Install Node.js dependencies"
    )
    assert "if" not in install_step
    assert install_step["run"] == "npm ci --no-audit --no-fund"


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
    assert dispatch["inputs"]["backend_scope"] == {
        "description": "Choose the default incremental backend evidence or full backend evidence.",
        "required": True,
        "type": "choice",
        "default": "incremental",
        "options": ["incremental", "full"],
    }
    assert dispatch["inputs"]["mutation_base_sha"] == {
        "description": "Required strict-ancestor SHA for incremental backend evidence; ignored in full mode.",
        "required": False,
        "type": "string",
    }
    assert (
        jobs["manual-mutation-stats"]["if"]
        == "${{ inputs.backend_scope == 'incremental' }}"
    )
    assert (
        jobs["manual-mutation-tests"]["if"]
        == "${{ inputs.backend_scope == 'incremental' }}"
    )
    full_call = jobs["manual-full-backend-mutation"]
    assert full_call["if"] == "${{ inputs.backend_scope == 'full' }}"
    assert full_call["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    assert full_call["with"]["source_sha"] == "${{ github.sha }}"
    assert full_call["with"]["helm_artifact_name"] == (
        "${{ needs.manual-full-helm-dependencies.outputs.artifact_name }}"
    )
    assert jobs["manual-full-helm-dependencies"]["uses"] == (
        "./.github/workflows/reusable-helm-dependencies.yml"
    )
    assert jobs["manual-full-backend-scope-guard"]["if"] == (
        "${{ inputs.backend_scope == 'full' }}"
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["group"] == (
        "manual-mutation-evidence-${{ github.ref }}"
    )
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert all(
        isinstance(job.get("name"), str) and job["name"].startswith("Manual ")
        for job in jobs.values()
    )
    assert {job["name"] for job in jobs.values()}.isdisjoint(REQUIRED_CI_CONTEXTS)

    stats_job = jobs["manual-mutation-stats"]
    stats_upload = next(
        step
        for step in stats_job["steps"]
        if step.get("name") == "Upload manual mutmut stats shard"
    )
    assert stats_upload["with"]["name"] == (
        "manual-mutmut-stats-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ matrix.stats_shard }}"
    )

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

    manual_mutation_job = jobs["manual-mutation-tests"]
    assert manual_mutation_job["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert manual_mutation_job["strategy"]["max-parallel"] == 20
    assert manual_mutation_job["timeout-minutes"] == 360
    manual_mutation_text = "\n".join(
        step.get("run", "")
        for step in manual_mutation_job["steps"]
        if isinstance(step, dict)
    )
    assert "--num-shards 128" in manual_mutation_text
    assert "scripts/mutmut_shard_budget.py" in manual_mutation_text
    assert "--max-timeout-seconds 20970" in manual_mutation_text
    assert "--metadata-startup-reserve-seconds 120" in manual_mutation_text
    assert '--prepare-exact-execution "$MUTMUT_EVIDENCE_DIR/execution-plan.json"' in (
        manual_mutation_text
    )
    assert '--verify-exact-execution "$MUTMUT_EVIDENCE_DIR/execution-plan.json"' in (
        manual_mutation_text
    )
    manual_upload = next(
        step
        for step in manual_mutation_job["steps"]
        if step.get("name") == "Upload manual mutation evidence"
    )
    assert manual_upload["with"]["name"] == (
        "manual-mutation-evidence-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ matrix.shard }}"
    )
    assert "mutants/mutmut-exact-evidence/" in manual_upload["with"]["path"]

    stats_download = next(
        step
        for step in manual_mutation_job["steps"]
        if step.get("name") == "Download manual mutmut stats shards"
    )
    assert stats_download["with"]["pattern"] == (
        "manual-mutmut-stats-${{ github.run_id }}-${{ github.run_attempt }}-*"
    )
    assert "if-no-artifact-found" not in stats_download["with"]
    require_stats = next(
        step
        for step in manual_mutation_job["steps"]
        if step.get("name") == "Require all manual mutmut stats shards"
    )
    assert "expected=8" in require_stats["run"]
    assert "find mutmut-stats -type f -name 'mutmut-stats.json'" in require_stats["run"]
    assert "seq 0 7" in require_stats["run"]


def test_mutation_execution_deadlines_and_evidence_are_owned_by_scheduled_lanes() -> (
    None
):
    manual = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    manual_job = manual["jobs"]["manual-mutation-tests"]
    nightly = yaml.safe_load(
        FULL_BACKEND_MUTATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    nightly_job = nightly["jobs"]["mutation-tests-full"]

    assert (
        "mutation-tests-incremental"
        not in yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]
    )
    assert manual_job["timeout-minutes"] == 360
    assert (
        "MUTMUT_JOB_DEADLINE_EPOCH"
        in _step_named(manual_job, "Record mutmut job deadline")["run"]
    )
    manual_run = _step_named(
        manual_job, "Run manual incremental mutmut (blocking, stats-derived budget)"
    )["run"]
    assert "execution-proof.json" in manual_run
    assert "scripts/mutmut_ci_gate.py" in manual_run
    nightly_run = _step_named(nightly_job, "Plan and run exact full mutation shard")[
        "run"
    ]
    assert "--verify-exact-execution" in nightly_run
    assert "mutmut-full-plan" in nightly_run
    assert "Validate full mutation shard evidence artifact" in str(nightly_job["steps"])


def test_dispatchable_mutation_evidence_is_not_a_required_ci_context() -> None:
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    manual = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    assert "workflow_dispatch" in _workflow_triggers(manual)
    assert not any("mutation" in job_id or "stryker" in job_id for job_id in ci["jobs"])
    assert "manual-frontend-mutation-aggregate" in manual["jobs"]
    assert "manual-mutation-tests" in manual["jobs"]


def test_nightly_full_gate_contains_the_long_running_quality_suites() -> None:
    workflow = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert triggers["schedule"][0]["cron"] == "0 1 * * *"
    jobs = workflow["jobs"]

    # Nightly remains a main-only caller. The mutation implementation is
    # shared with the explicitly scoped manual full-evidence route.
    helm_call = jobs["nightly-helm-dependencies"]
    assert (
        helm_call["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert helm_call["uses"] == "./.github/workflows/reusable-helm-dependencies.yml"
    assert helm_call["with"]["source_sha"] == "${{ github.sha }}"
    mutation_call = jobs["mutation-tests-full"]
    assert (
        mutation_call["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert mutation_call["needs"] == "nightly-helm-dependencies"
    assert mutation_call["uses"] == (
        "./.github/workflows/reusable-full-backend-mutation.yml"
    )
    assert mutation_call["with"]["source_sha"] == "${{ github.sha }}"
    assert mutation_call["with"]["helm_artifact_name"] == (
        "${{ needs.nightly-helm-dependencies.outputs.artifact_name }}"
    )
    full_workflow = yaml.safe_load(
        FULL_BACKEND_MUTATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    full_jobs = full_workflow["jobs"]
    assert {
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
        "mutation-tests-full-aggregate",
    } <= set(full_jobs)
    mutation_steps = full_jobs["mutation-tests-full-aggregate"]["steps"]
    export_step = next(
        step
        for step in mutation_steps
        if step.get("name") == "Merge and gate full mutation evidence"
    )
    assert "scripts/merge_mutmut_cicd_stats.py" in export_step["run"]
    assert "--expected-shards 128" in export_step["run"]
    assert "scripts/check_mutation_score.py --min-score 100" in export_step["run"]
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
    assert "test_s3_storage_integration.py" in cell_text
    assert "test_spicedb_integration.py" in cell_text
    browser_entries = jobs["browser-matrix"]["strategy"]["matrix"]["include"]
    assert {entry["browser"] for entry in browser_entries} == {
        "chromium",
        "firefox",
        "webkit",
        "mobile-webkit",
    }
    assert [
        entry["shard-index"]
        for entry in browser_entries
        if entry["browser"] == "chromium"
    ] == [1, 2, 3, 4]
    assert all(
        entry["shard-total"] == 4
        for entry in browser_entries
        if entry["browser"] == "chromium"
    )
    assert "always()" in jobs["notify-failure"]["if"]
    assert "mutation-tests-full" in jobs["notify-failure"]["needs"]
    assert "mutation-tests-full-stats" not in jobs["notify-failure"]["needs"]
    assert "mutation-tests-full-plan" not in jobs["notify-failure"]["needs"]
    assert "frontend-mutation-tests-full" in jobs["notify-failure"]["needs"]
    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["notify-failure"]["permissions"] == {
        "contents": "read",
        "issues": "write",
    }
    assert jobs["notify-failure"]["timeout-minutes"] == 5
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
    assert "Start the chaos dependency closure" in chaos_steps
    assert "docker-compose.ci-loadtest.yml" in chaos_steps
    assert "54321/test_ecosystem" in chaos_steps
    assert "Tear down full chaos compose stack" in chaos_steps


def test_nightly_chaos_starts_only_its_declared_compose_dependency_closure() -> None:
    """Keep the nightly chaos runner bounded to services the suite exercises.

    Compose follows ``depends_on`` recursively for targeted services.  Derive
    that graph from the same four layered manifests used by the workflow and
    pin the roots/closure so a future test or dependency change cannot silently
    start the 27-service production-like stack (or omit a required dependency).
    Optional ToxiProxy/real-MinIO chaos remains disabled in this workflow, as it
    has no corresponding service or endpoint configuration here.
    """

    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = nightly["jobs"]["load-and-chaos"]
    start_step = _provenance_step(job, "Start the chaos dependency closure")
    run_text = str(start_step["run"])
    assert (
        'docker compose "${CF[@]}" up -d --build backend gateway ws-hub outbox-worker'
    ) in run_text

    dependency_map: dict[str, set[str]] = {}
    for relative_path in (
        "docker-compose.yml",
        "docker-compose.infra.yml",
        "docker-compose.go.yml",
        "docker-compose.ci-loadtest.yml",
    ):
        compose = yaml.safe_load(
            (REPOSITORY_ROOT / relative_path)
            .read_text(encoding="utf-8")
            .replace("!override", "")
        )
        for service_name, service in compose["services"].items():
            depends_on = service.get("depends_on") or {}
            dependency_names = (
                depends_on.keys() if isinstance(depends_on, dict) else depends_on
            )
            dependency_map.setdefault(service_name, set()).update(dependency_names)

    roots = {"backend", "gateway", "ws-hub", "outbox-worker"}
    expected_closure = {
        "backend",
        "gateway",
        "ws-hub",
        "outbox-worker",
        "migrations",
        "minio-init",
        "nats",
        "revocation-valkey",
        "valkey",
        "postgres",
        "minio",
    }
    closure: set[str] = set()
    pending = list(roots)
    while pending:
        service_name = pending.pop()
        if service_name in closure:
            continue
        assert service_name in dependency_map, service_name
        closure.add(service_name)
        pending.extend(dependency_map[service_name])

    assert closure == expected_closure
    assert roots <= closure

    run_env = next(
        step.get("env", {})
        for step in job["steps"]
        if step.get("name") == "Run chaos and resilience tests"
    )
    assert "TOXIPROXY_URL" not in run_env
    assert "MINIO_PROXY_ENDPOINT" not in run_env
    assert "MINIO_DIRECT_ENDPOINT" not in run_env


def test_go_service_dockerfiles_package_local_spiffe_replacement() -> None:
    for service in ("gateway", "ws-hub", "file-processor"):
        dockerfile = (REPOSITORY_ROOT / "services" / service / "Dockerfile").read_text(
            encoding="utf-8"
        )
        assert "COPY services/pkg/spiffe ./services/pkg/spiffe" in dockerfile
        assert "COPY services/pkg/logging ./services/pkg/logging" in dockerfile


def test_go_fuzz_workflow_executes_all_service_fuzz_targets() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "go-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert workflow["jobs"]["fuzz"]["timeout-minutes"] == 15
    setup_go = next(
        step
        for step in workflow["jobs"]["fuzz"]["steps"]
        if step.get("name") == "Set up Go"
    )
    assert setup_go["with"]["go-version"] == "1.27.2"
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
    # Go 1.27.2 includes the upstream fix for golang/go#75804, so retain the
    # full bounded smoke budget without relying on retries or ignored failures.
    assert all("-fuzztime=20s" in command for command in fuzz_commands)
    assert all("-parallel=1" in command for command in fuzz_commands)


def test_ci_ws_hub_fuzz_uses_deadline_margin() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["go-fuzz"]
    setup_go = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-go@")
    )
    assert setup_go["with"]["go-version"] == "1.27.2"
    text = "\n".join(
        step.get("run", "") for step in job["steps"] if isinstance(step, dict)
    )
    fuzz_commands = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("go test") and "-fuzz=" in line
    ]
    assert len(fuzz_commands) == 2
    assert all("-fuzztime=20s" in command for command in fuzz_commands)
    assert all("-parallel=1" in command for command in fuzz_commands)
    assert all("-timeout=3m" in command for command in fuzz_commands)


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


def test_cargo_deny_scans_all_release_rust_crates_in_parallel() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "cargo-deny.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    matrix_job = jobs["cargo-deny-crates"]
    assert matrix_job["name"] == "Cargo Deny (${{ matrix.name }})"
    assert matrix_job["strategy"]["fail-fast"] is False
    assert matrix_job["strategy"]["max-parallel"] == 4
    entries = matrix_job["strategy"]["matrix"]["include"]
    assert {entry["manifest-path"] for entry in entries} == {
        "native/rust_ext/Cargo.toml",
        "frontend/wasm-sanitizer/Cargo.toml",
        "frontend/rust-crypto/Cargo.toml",
    }
    assert all(entry["name"] for entry in entries)
    assert {entry["config-path"] for entry in entries} == {"native/rust_ext/deny.toml"}

    deny_step = next(
        step for step in matrix_job["steps"] if step.get("name") == "Run Cargo Deny"
    )
    assert deny_step["with"]["manifest-path"] == "${{ matrix.manifest-path }}"
    assert deny_step["with"]["command"] == "check"
    assert (
        deny_step["with"]["arguments"]
        == "--config ${{ matrix.config-path }} --all-features"
    )

    aggregate = jobs["cargo-deny"]
    assert aggregate["name"] == "Cargo Deny Scan"
    assert aggregate["needs"] == ["cargo-deny-crates"]
    assert aggregate["if"] == "${{ always() }}"
    aggregate_run = aggregate["steps"][0]["run"]
    assert "needs.cargo-deny-crates.result" in aggregate_run
    assert '!= "success"' in aggregate_run


def test_rust_fuzz_matrix_covers_every_fuzz_workspace() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "rust-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    matrix = workflow["jobs"]["fuzz-additional-rust-crates"]["strategy"]["matrix"]
    entries = matrix["include"]

    by_directory = {entry["directory"]: entry for entry in entries}
    assert set(by_directory) == {
        "frontend/wasm-sanitizer/fuzz",
        "frontend/rust-crypto/fuzz",
    }
    assert "crates/" not in workflow_path.read_text(encoding="utf-8")


def test_rust_fuzz_required_context_runs_when_its_workflow_changes() -> None:
    """A workflow-only PR change must exercise the required fuzz context."""

    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "rust-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    for event_name in ("push", "pull_request"):
        event = triggers[event_name]
        assert isinstance(event, dict)
        assert ".github/workflows/rust-fuzz.yml" in event["paths"]


def test_rust_fuzz_keeps_the_required_pr_context_out_of_manual_and_scheduled_runs() -> (
    None
):
    """The extended fuzz duration must not mint a required PR status context."""

    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "rust-fuzz.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    fuzz_job = workflow["jobs"]["fuzz"]

    assert "Run cargo fuzz" in REQUIRED_CI_CONTEXTS
    assert "workflow_dispatch" in _workflow_triggers(workflow)
    assert fuzz_job["name"] == RUST_FUZZ_MANUAL_CONTEXT_EXPRESSION
    assert (
        _job_context_for_event(workflow_path, "fuzz", fuzz_job["name"], "pull_request")
        == "Run cargo fuzz"
    )
    assert (
        _job_context_for_event(
            workflow_path, "fuzz", fuzz_job["name"], "workflow_dispatch"
        )
        == "Extended Rust fuzz evidence"
    )
    assert "Extended Rust fuzz evidence" not in REQUIRED_CI_CONTEXTS

    fuzz_step = next(
        step for step in fuzz_job["steps"] if step.get("name") == "Run fuzz targets"
    )
    assert (
        'if [ "${EVENT_NAME}" = "schedule" ] || [ "${EVENT_NAME}" = "workflow_dispatch" ]; then'
        in fuzz_step["run"]
    )
    assert "DURATION=300" in fuzz_step["run"]
    assert "DURATION=60" in fuzz_step["run"]


def test_incremental_mutation_gate_is_blocking_and_fails_on_timeout() -> None:
    manual_workflow = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    jobs = manual_workflow["jobs"]
    mutation_job = jobs["manual-mutation-tests"]
    assert mutation_job["timeout-minutes"] == 360
    deadline_step = mutation_job["steps"][0]
    assert deadline_step["name"] == "Record mutmut job deadline"
    assert (
        'MUTMUT_JOB_DEADLINE_EPOCH="$((MUTMUT_JOB_STARTED_EPOCH + 21600))"'
        in deadline_step["run"]
    )
    mutation_text = "\n".join(
        step.get("run", "") for step in mutation_job["steps"] if isinstance(step, dict)
    )
    assert "exceeded its stats-derived budget" in mutation_text
    assert "--max-timeout-seconds 20970" in mutation_text
    assert "MUTMUT_TIMEOUT_KILL_GRACE_SECONDS=30" in mutation_text
    assert "Skipping score verification" not in mutation_text
    assert (
        "mutation-tests-incremental"
        not in yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]
    )
    export_index = mutation_text.index("scripts/export_mutmut_shard_stats.py")
    gate_index = mutation_text.index("scripts/mutmut_ci_gate.py")
    assert export_index < gate_index
    assert "--selected-file /tmp/mutmut-shard.txt" in mutation_text
    assert (
        '--prepare-exact-execution "$MUTMUT_EVIDENCE_DIR/execution-plan.json"'
        in mutation_text
    )
    assert (
        '--verify-exact-execution "$MUTMUT_EVIDENCE_DIR/execution-plan.json"'
        in mutation_text
    )
    assert '"$MUTMUT_EVIDENCE_DIR/execution-proof.json"' in mutation_text
    assert "--output mutants/mutmut-cicd-stats.json" in mutation_text
    assert "uv run mutmut export-cicd-stats" not in mutation_text
    assert "test -s mutants/mutmut-cicd-stats.json" in mutation_text


def test_blocking_mutation_jobs_are_not_mislabeled_as_advisory() -> None:
    ci_text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "advisory mutation" not in ci_text.lower()
    assert "mutation: $mut" not in ci_text
    assert "stryker: $stryker" not in ci_text


def test_full_mutation_gate_uses_the_fail_closed_exporter() -> None:
    full_workflow = yaml.safe_load(
        FULL_BACKEND_MUTATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    mutation_job = full_workflow["jobs"]["mutation-tests-full-aggregate"]
    mutation_text = "\n".join(
        step.get("run", "") for step in mutation_job["steps"] if isinstance(step, dict)
    )

    export_index = mutation_text.index("scripts/merge_mutmut_cicd_stats.py")
    gate_index = mutation_text.index("scripts/check_mutation_score.py")
    assert export_index < gate_index
    assert "--expected-shards 128" in mutation_text
    assert "uv run mutmut export-cicd-stats" not in mutation_text
    assert "test -s mutants/mutmut-cicd-stats.json" in mutation_text


def test_full_mutation_gate_isolates_stats_and_clean_pytest_invocations() -> None:
    """Keep sharded stats isolated and the clean baseline fresh."""

    full_workflow = yaml.safe_load(
        FULL_BACKEND_MUTATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    jobs = full_workflow["jobs"]
    stats_job = jobs["mutation-tests-full-stats"]
    plan_job = jobs["mutation-tests-full-plan"]
    plan_steps = plan_job["steps"]
    mutation_job = jobs["mutation-tests-full"]
    mutation_steps = mutation_job["steps"]
    assert mutation_job["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-plan",
    ]
    assert plan_job["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
    ]
    assert mutation_job["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert jobs["mutation-tests-full"]["strategy"]["max-parallel"] == 8
    assert stats_job["strategy"]["matrix"]["stats_shard"] == list(range(8))
    stats_steps = stats_job["steps"]
    stats_helm = next(step for step in stats_steps if step.get("name") == "Set up Helm")
    stats_dependencies = next(
        step
        for step in stats_steps
        if step.get("name") == "Resolve Helm chart dependencies"
    )
    stats_step = next(
        step
        for step in stats_steps
        if step.get("name") == "Collect full mutmut stats shard"
    )
    upload_step = next(
        step
        for step in stats_steps
        if step.get("name") == "Upload full mutmut stats shard"
    )
    run_step_index = next(
        index
        for index, step in enumerate(mutation_steps)
        if step.get("name") == "Plan and run exact full mutation shard"
    )
    download_step = next(
        step
        for step in plan_steps
        if step.get("name") == "Download full mutmut stats shards"
    )
    merge_step = next(
        step
        for step in plan_steps
        if step.get("name") == "Merge full mutmut stats shards"
    )
    preflight_step = next(
        step
        for step in plan_steps
        if step.get("name") == "Plan and budget every exact full mutation shard"
    )
    stats_script = stats_step["run"]
    run_script = mutation_steps[run_step_index]["run"]

    assert stats_helm["uses"].startswith("azure/setup-helm@")
    assert stats_helm["with"] == {"version": "v3.17.0"}
    _assert_helm_dependency_helper_invocation(
        stats_dependencies["run"], skip_refresh=True
    )
    assert stats_steps.index(stats_dependencies) < stats_steps.index(stats_step)

    mutation_helm = next(
        step for step in mutation_steps if step.get("name") == "Set up Helm"
    )
    mutation_dependencies = next(
        step
        for step in mutation_steps
        if step.get("name") == "Resolve Helm chart dependencies"
    )
    assert mutation_helm["uses"].startswith("azure/setup-helm@")
    assert mutation_helm["with"] == {"version": "v3.17.0"}
    _assert_helm_dependency_helper_invocation(
        mutation_dependencies["run"], skip_refresh=True
    )
    assert mutation_steps.index(mutation_dependencies) < run_step_index

    generation_job = jobs["mutation-tests-full-generation-base"]
    generation_steps = generation_job["steps"]
    generation_step = next(
        step
        for step in generation_steps
        if step.get("name") == "Generate reusable mutmut source and metadata"
    )
    generation_script = generation_step["run"]
    generation_upload = next(
        step
        for step in generation_steps
        if step.get("name") == "Upload full mutmut generation base"
    )
    assert generation_job["needs"] == "verify-full-mutation-provenance"
    assert stats_job["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-generation-base",
    ]
    assert "rm -rf mutants" in generation_script
    assert "--prepare-only" in generation_script
    assert "test -s mutants/mutmut-generation.json" in generation_script
    assert "mutants/" in generation_upload["with"]["path"]
    assert "rm -rf mutants" not in stats_script
    assert "--reuse-generated-universe" in stats_script
    assert "test ! -e mutants/mutmut-stats.json" in stats_script
    stats_step_names = [
        step.get("name") for step in stats_steps if isinstance(step, dict)
    ]
    assert stats_step_names.index(
        "Download selected same-run mutmut generation base"
    ) < stats_step_names.index("Verify selected full mutmut generation payload")
    assert stats_step_names.index(
        "Verify selected full mutmut generation payload"
    ) < stats_step_names.index("Select retry-safe full mutmut generation base")
    assert stats_step_names.index(
        "Select retry-safe full mutmut generation base"
    ) < stats_step_names.index("Collect full mutmut stats shard")
    assert "scripts/mutmut_stats_shard.py" in stats_script
    assert '--shard-id "${{ matrix.stats_shard }}"' in stats_script
    assert "--num-shards 8" in stats_script
    assert "--max-children 2" in stats_script
    assert upload_step["with"]["name"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-stats-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ matrix.stats_shard }}"
    )
    assert download_step["with"]["pattern"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-stats-${{ github.run_id }}-${{ github.run_attempt }}-*"
    )
    assert "if-no-artifact-found" not in download_step["with"]
    require_stats = next(
        step
        for step in plan_steps
        if step.get("name") == "Require all full mutmut stats shards"
    )
    assert "expected=8" in require_stats["run"]
    assert "find mutmut-stats -type f -name 'mutmut-stats.json'" in require_stats["run"]
    assert "seq 0 7" in require_stats["run"]
    plan_upload = next(
        step
        for step in plan_steps
        if step.get("name") == "Upload preflighted full mutation plan"
    )
    assert plan_upload["with"]["name"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-plan-${{ github.run_id }}-${{ github.run_attempt }}"
    )
    plan_download = next(
        step
        for step in mutation_steps
        if step.get("name") == "Download preflighted full mutation plan"
    )
    assert plan_download["with"]["name"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-plan-${{ github.run_id }}-${{ github.run_attempt }}"
    )
    assert "if-no-artifact-found" not in plan_download["with"]
    shard_upload = next(
        step
        for step in mutation_steps
        if step.get("name") == "Upload full mutation shard evidence"
    )
    assert shard_upload["with"]["name"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-shard-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ matrix.shard }}"
    )
    assert "scripts/merge_mutmut_stats.py" in merge_step["run"]
    assert "--input-root mutmut-stats" in merge_step["run"]
    assert "--output-directory mutants/mutmut-full-plan" in preflight_step["run"]
    assert "for shard in $(seq 1 128)" in preflight_step["run"]
    assert "scripts/mutmut_shard_budget.py" in preflight_step["run"]
    assert "scripts/plan_mutmut_shards.py" in run_script
    assert "--num-shards 128" in run_script
    assert "cmp --silent" in run_script
    assert (
        "scripts/run_mutmut_with_stats.py --reuse-generated-universe --max-children 8"
    ) in run_script
    assert "scripts/run_mutmut_with_stats.py --max-children 2" in run_script
    assert "uv run mutmut run" not in run_script
    assert "scripts/mutmut_stats_shard.py" not in run_script
    aggregate_job = jobs["mutation-tests-full-aggregate"]
    assert aggregate_job["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full",
    ]
    aggregate_text = "\n".join(
        step.get("run", "") for step in aggregate_job["steps"] if isinstance(step, dict)
    )
    aggregate_download = next(
        step
        for step in aggregate_job["steps"]
        if step.get("name") == "Download full mutation shard evidence"
    )
    assert aggregate_download["with"]["pattern"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-shard-${{ github.run_id }}-${{ github.run_attempt }}-*"
    )
    assert "if-no-artifact-found" not in aggregate_download["with"]
    require_shards = next(
        step
        for step in aggregate_job["steps"]
        if step.get("name") == "Require all full mutmut execution shards"
    )
    assert "expected=128" in require_shards["run"]
    assert (
        "find mutmut-shards -type f -name 'mutmut-cicd-stats.json'"
        in require_shards["run"]
    )
    assert "seq 1 128" in require_shards["run"]
    assert (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}"
        in require_shards["run"]
    )
    assert "${RUN_ID}-${RUN_ATTEMPT}-${shard}" in require_shards["run"]
    aggregate_upload = next(
        step
        for step in aggregate_job["steps"]
        if step.get("name") == "Upload aggregate mutation evidence"
    )
    assert aggregate_upload["with"]["name"] == (
        "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}-mutmut-${{ github.run_id }}-${{ github.run_attempt }}"
    )
    assert "scripts/merge_mutmut_cicd_stats.py" in aggregate_text
    assert "--expected-shards 128" in aggregate_text


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


def test_scheduled_lhci_linux_keeps_threshold_and_route_privacy_checks() -> None:
    workflow = yaml.safe_load(LHCI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["lhci"]
    run = next(step for step in job["steps"] if step.get("name") == "Run Lighthouse CI")
    assert run["run"] == "npm run lhci"

    runner = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"lhci assert"' in runner
    assert "assertLhciRoutePolicy" in runner

    lighthouse_config = LIGHTHOUSE_CONFIG_PATH.read_text(encoding="utf-8")
    assert (
        '"categories:performance": ["error", { minScore: 0.95 }]' in lighthouse_config
    )
    assert (
        '"categories:accessibility": ["error", { minScore: 0.95 }]' in lighthouse_config
    )


def test_lighthouse_config_uses_supported_budget_path_and_audit() -> None:
    lighthouse_config = LIGHTHOUSE_CONFIG_PATH.read_text(encoding="utf-8")

    assert "budgetPath:" in lighthouse_config
    assert "budgetsPath:" not in lighthouse_config
    assert "budgets:" not in lighthouse_config
    assert "assertMatrix:" in lighthouse_config
    assert '"total-blocking-time": [' in lighthouse_config
    assert (
        '"categories:performance": ["error", { minScore: 0.95 }]' in lighthouse_config
    )
    assert (
        '"categories:accessibility": ["error", { minScore: 0.95 }]' in lighthouse_config
    )
    assert re.search(r'"largest-contentful-paint":\s*\[\s*"error"', lighthouse_config)
    assert re.search(r'"total-blocking-time":\s*\[\s*"error"', lighthouse_config)
    assert "publicSeoUrlPattern" in lighthouse_config
    assert "INP is a field metric" in lighthouse_config
    assert "--disable-gpu" not in lighthouse_config


def test_lhci_collection_uses_lighthouse_budget_path_inside_settings() -> None:
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'budgetPath: path.resolve(frontendRoot, "../budget.json")' in lhci_script
    assert "budgetsPath:" not in lhci_script
    assert '"categories:performance": ["error", { minScore: 0.95 }]' in lhci_script
    assert '"categories:accessibility": ["error", { minScore: 0.95 }]' in lhci_script
    assert "INP is a field metric" in lhci_script
    assert "--disable-gpu" not in lhci_script


def test_lhci_collection_scores_the_real_404_document_without_rewriting_status() -> (
    None
):
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignoreStatusCode: true" in lhci_script


def test_bundle_analysis_uses_portable_fail_closed_analyzer_and_real_report() -> None:
    workflow = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    analysis_job = workflow["jobs"]["bundle-analysis"]
    test_step = next(
        step
        for step in analysis_job["steps"]
        if step.get("name") == "Test bundle analyzer"
    )
    analyze_step = next(
        step
        for step in analysis_job["steps"]
        if step.get("name") == "Analyze bundle size"
    )

    assert test_step["run"] == "node --test scripts/check-bundle-budget.test.mjs"
    assert analyze_step["run"] == "node scripts/check-bundle-budget.mjs"
    assert not analyze_step.get("continue-on-error", False)
    assert "echo '{}'" not in FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_lhci_command_runner_uses_shell_free_platform_resolution() -> None:
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")
    command_script = (LHCI_SCRIPT_PATH.parent / "lhci-command.mjs").read_text(
        encoding="utf-8"
    )

    assert "shell: false" in lhci_script
    assert "shell: true" not in lhci_script
    assert "buildSafeCommandInvocation" in lhci_script
    assert '"npm-cli.js"' in command_script
    assert "args: [cliPath, ...args]" in command_script
    assert '"exec", "--yes",' in lhci_script


def test_lhci_system_dependency_bootstrap_is_explicitly_skippable() -> None:
    lhci_script = LHCI_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "LHCI_SKIP_SYSTEM_DEPS" in lhci_script
    assert "playwright install-deps chromium" in lhci_script


def test_lhci_ci_uses_route_specific_ssr_preview_without_lowering_budgets() -> None:
    workflow = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    lighthouse_shards = workflow["jobs"]["lighthouse-shards"]
    assert lighthouse_shards["env"]["LHCI_USE_SSR_PREVIEW"] == "1"

    mode_script = (LHCI_SCRIPT_PATH.parent / "lhci-preview-mode.mjs").read_text(
        encoding="utf-8"
    )
    assert (
        'return { kind: "ssr", base: `http://127.0.0.1:${port}`, port }' in mode_script
    )
    assert 'return "node scripts/server-prod.mjs"' in mode_script
    assert 'return "server-prod: listening"' in mode_script
    ssr_response_script = (LHCI_SCRIPT_PATH.parent / "lhci-ssr-response.mjs").read_text(
        encoding="utf-8"
    )
    assert "stripLhciEntryScript" in ssr_response_script
    assert "pathForLhciPreview" in LHCI_SCRIPT_PATH.read_text(encoding="utf-8")
    assert (
        'collect.staticDistDir = path.resolve(frontendRoot, "dist", "client")'
        in LHCI_SCRIPT_PATH.read_text(encoding="utf-8")
    )


def test_chaos_job_provisions_real_s3_through_toxiproxy() -> None:
    nightly_workflow = yaml.safe_load(
        NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    chaos_job = nightly_workflow["jobs"]["chaos-tests"]
    minio_service = chaos_job["services"]["minio"]
    assert (
        minio_service["image"]
        == (
            "ghcr.io/chrislusf/seaweedfs:4.47@sha256:"
            "ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882"  # pragma: allowlist secret
        )
    )
    assert minio_service["command"] == "mini -dir=/data -s3.port=9000"
    assert minio_service["env"]["AWS_ACCESS_KEY_ID"] == "minioadmin"
    assert minio_service["env"]["S3_BUCKET"] == "quality-chaos"
    assert "9003:9003" in chaos_job["services"]["toxiproxy"]["ports"]

    configure_text = next(
        step["run"]
        for step in chaos_job["steps"]
        if step.get("name") == "Configure ToxiProxy proxies"
    )
    assert '"name":"minio"' in configure_text
    assert '"upstream":"minio:9000"' in configure_text
    assert "http://localhost:9000/status" in configure_text

    chaos_env = next(
        step["env"]
        for step in chaos_job["steps"]
        if step.get("name") == "Run chaos tests"
    )
    assert chaos_env["MINIO_PROXY_ENDPOINT"] == "http://localhost:9003"
    assert chaos_env["MINIO_DIRECT_ENDPOINT"] == "localhost:9000"
    assert chaos_env["STORAGE_S3_ENDPOINT_URL"] == "http://localhost:9003"
    assert (
        minio_service["env"]["AWS_SECRET_ACCESS_KEY"]
        == chaos_env["STORAGE_S3_SECRET_ACCESS_KEY"]
    )


def test_actionlint_documents_github_service_command_compatibility() -> None:
    config = yaml.safe_load(ACTIONLINT_CONFIG_PATH.read_text(encoding="utf-8"))
    paths = config["paths"]
    nightly_ignores = paths[".github/workflows/nightly-full-gate.yml"]["ignore"]

    assert ".github/workflows/ci.yml" not in paths
    assert 'unexpected key "command" for "services" section' in nightly_ignores
    assert (
        "docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax"
        in (ACTIONLINT_CONFIG_PATH.read_text(encoding="utf-8"))
    )


def test_stryker_duration_bounds_track_the_shard_job_cap() -> None:
    """Every duration bound in run-stryker.mjs must track the shard job cap.

    A shard cannot legitimately run longer than the job hosting it, so both
    bounds are derived from ``timeout-minutes`` rather than written out by
    hand.  Run 35545015344 and run 35547440861 each failed the whole frontend
    gate on a copy of that literal that had not been moved with the cap: the
    first rejected the configured ``STRYKER_SHARD_TIMEOUT_MS`` before any
    mutant ran, the second rejected shard 26/64's own 244-minute timing as
    malformed after it finally completed.  Pinning the derivation here means
    the next change to the cap fails locally instead of four hours into CI.
    """

    workflow = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    cap_minutes = workflow["jobs"]["frontend-mutation-shards"]["timeout-minutes"]
    cap_ms = cap_minutes * 60 * 1000

    script = (REPOSITORY_ROOT / "frontend" / "scripts" / "run-stryker.mjs").read_text(
        encoding="utf-8"
    )

    def literal(pattern: str) -> int:
        match = re.search(pattern, script)
        assert match, f"run-stryker.mjs no longer matches {pattern!r}"
        return int(match.group(1).replace("_", ""))

    historical_cost_bound = literal(
        r"const maximumHistoricalCostMs = ([0-9_]+)",
    )
    shard_timeout_bound = literal(
        r'"STRYKER_SHARD_TIMEOUT_MS",\s*[0-9_]+,\s*[0-9_]+,\s*([0-9_]+)',
    )

    assert historical_cost_bound == cap_ms
    assert shard_timeout_bound == cap_ms

    # The configured deadline must still sit strictly inside both the bound
    # and the cap, so an overrun is reported by the runner rather than by
    # GitHub cancelling the job.
    configured = int(
        workflow["jobs"]["frontend-mutation-shards"]["env"]["STRYKER_SHARD_TIMEOUT_MS"]
    )
    assert configured < shard_timeout_bound
    assert configured < cap_ms


def test_frontend_mutation_evidence_is_complete_on_nightly_and_manual_lanes() -> None:
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    manual = yaml.safe_load(
        MANUAL_MUTATION_EVIDENCE_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    ci_jobs = ci["jobs"]
    assert not any("mutation" in job_id or "stryker" in job_id for job_id in ci_jobs)
    assert not any(
        token
        in _step_named(ci_jobs["ci-success"], "Check all jobs passed")["run"].lower()
        for token in ("mutation", "stryker")
    )

    for workflow, prefix, max_parallel, aggregate_id, aggregate_name, roundtrip_id in (
        (
            nightly,
            "frontend-mutation",
            8,
            "frontend-mutation-tests-full",
            "Aggregate and verify nightly frontend mutation evidence",
            "frontend-mutation-roundtrip",
        ),
        (
            manual,
            "manual-frontend-mutation",
            20,
            "manual-frontend-mutation-aggregate",
            "Aggregate and verify manual frontend mutation evidence",
            "manual-frontend-mutation-roundtrip",
        ),
    ):
        jobs = workflow["jobs"]
        assert "workflow_dispatch" in _workflow_triggers(
            workflow
        ) or "schedule" in _workflow_triggers(workflow)
        shards_id = f"{prefix}-shards"
        shards = jobs[shards_id]
        assert shards["strategy"]["matrix"]["shard-index"] == list(range(64))
        assert shards["strategy"]["max-parallel"] == max_parallel
        aggregate = jobs[aggregate_id]
        assert shards_id in aggregate["needs"]
        assert (
            _step_named(aggregate, aggregate_name)["run"].count("test:mutation:verify")
            == 1
        )
        roundtrip = jobs[roundtrip_id]
        assert roundtrip["needs"] == aggregate_id
        assert any(
            "Re-verify downloaded" in step.get("name", "")
            for step in roundtrip["steps"]
        )

    assert (
        nightly["jobs"]["frontend-mutation-preflight"]["if"]
        == "${{ github.ref == 'refs/heads/main' }}"
    )
    assert (
        manual["jobs"]["manual-frontend-mutation-aggregate"]["name"]
        == "Manual Mutation Evidence (frontend Stryker 100%)"
    )
    assert (
        nightly["jobs"]["frontend-mutation-tests-full"]["name"]
        == "Full frontend mutation score (100%)"
    )


def test_former_frontend_mutation_required_context_is_not_a_required_gate() -> None:
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "frontend-mutation-required-context" not in ci["jobs"]
    assert "stryker-aggregate" not in ci["jobs"]["ci-success"]["needs"]
    catalog_text = json.dumps(
        json.loads(
            (REPOSITORY_ROOT / "quality/ci-check-catalog.json").read_text(
                encoding="utf-8"
            )
        )
    )
    assert "Incremental Mutation Tests (frontend)" not in catalog_text
    assert "Full frontend mutation score (100%)" in catalog_text
    assert "Manual Mutation Evidence (frontend Stryker 100%)" in catalog_text


def test_quality_promotion_workflow_uses_fail_closed_stabilization_checker() -> None:
    workflow = yaml.safe_load(
        QUALITY_PROMOTION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    triggers = _workflow_triggers(workflow)
    assert triggers == {"workflow_dispatch": {}}
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}

    text = QUALITY_PROMOTION_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "inputs." not in text
    assert "github.event.inputs" not in text
    assert "TARGET_BRANCH: main" in text
    assert 'REQUIRED_DAYS: "30"' in text
    assert "nightly-full-gate.yml/runs" in text
    assert "check_stabilization_window.py" in text
    assert "Fail when promotion is not yet eligible" in text

    canonical_job = workflow["jobs"]["verify-canonical-ref"]
    canonical_step = canonical_job["steps"][0]
    assert canonical_step["env"] == {"WORKFLOW_REF": "${{ github.ref }}"}
    assert '"$WORKFLOW_REF" != "refs/heads/main"' in canonical_step["run"]
    assert workflow["jobs"]["stabilization-window"]["needs"] == "verify-canonical-ref"

    checkout = workflow["jobs"]["stabilization-window"]["steps"][0]
    assert checkout["with"] == {"ref": "main", "fetch-depth": 1}


def test_dast_active_scans_do_not_accept_pr_label_authorization() -> None:
    """A PR label must never authorize a secret-bearing active DAST scan."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert "pull_request" not in triggers
    assert "pull_request_target" not in triggers

    for job_name in ("nuclei", "zap"):
        assert workflow["jobs"][job_name]["needs"] == "verify-trusted-ref"

    nuclei_setup = next(
        step
        for step in workflow["jobs"]["nuclei"]["steps"]
        if step.get("uses", "").startswith("projectdiscovery/nuclei-action@")
    )
    assert nuclei_setup["with"] == {"version": "v3.3.9", "install-only": True}


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
    *,
    candidate_capture_helper: bool = False,
) -> tuple[str, ...]:
    """Return the narrow trusted capture tail for one benchmark format."""

    assert capture_format in {"go", "rust"}
    rust_dockerfile_argument = (
        ' --rust-dockerfile "$BASE_RUST_DOCKERFILE"' if capture_format == "rust" else ""
    )
    capture_helper_variable = (
        "CAPTURE_HELPER" if candidate_capture_helper else "BASE_CAPTURE_HELPER"
    )
    selected_helper_output = (
        '  echo "selected_capture_helper=$CAPTURE_HELPER"\n'
        if candidate_capture_helper
        else ""
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
        + selected_helper_output
        + '  echo "python_bin=$PYTHON_BIN"\n'
        + '} >> "$GITHUB_OUTPUT"\n'
        + "\n"
        f'"$PYTHON_BIN" -I "${capture_helper_variable}" '
        f"--format {capture_format} "
        '--base-worktree "$BASE_WORKTREE" '
        '--candidate-worktree "$GITHUB_WORKSPACE" '
        '--artifact-root "$ARTIFACT_ROOT" '
        '--runner-temp "$RUNNER_TEMP" '
        '--base-revision "$BASE_SHA" '
        '--candidate-revision "$CANDIDATE_SHA"' + rust_dockerfile_argument
    )


def _expected_candidate_helper_selection_segment() -> tuple[str, ...]:
    """Keep helper activation tied to the explicit PR and main-push context."""

    return _canonical_shell_lines(
        'CAPTURE_HELPER_SELECTOR="$GITHUB_WORKSPACE/scripts/quality/benchmark_capture_activation.py"\n'
        'if ! test -f "$CAPTURE_HELPER_SELECTOR"; then\n'
        '  echo "Capture helper selector is absent" >&2\n'
        "  exit 2\n"
        "fi\n"
        'CAPTURE_HELPER="$(\n'
        '  EVENT_NAME="$EVENT_NAME" \\\n'
        '  REPOSITORY_NAME="$REPOSITORY_NAME_VALUE" \\\n'
        '  PR_NUMBER="$PR_NUMBER_VALUE" \\\n'
        '  PR_HEAD_REPOSITORY="$PR_HEAD_REPOSITORY_VALUE" \\\n'
        '  PR_HEAD_REF="$PR_HEAD_REF_VALUE" \\\n'
        '  PR_BASE_REF="$PR_BASE_REF_VALUE" \\\n'
        '  PUSH_REF="$PUSH_REF_VALUE" \\\n'
        '  PUSH_BASE_REF="$PUSH_BASE_REF" \\\n'
        '  BASE_SHA="$BASE_SHA" \\\n'
        '  SOURCE_HEAD_SHA="$SOURCE_HEAD_SHA" \\\n'
        '  CANDIDATE_SHA="$CANDIDATE_SHA" \\\n'
        '  BASE_WORKTREE="$BASE_WORKTREE" \\\n'
        '  BASE_CAPTURE_HELPER="$BASE_CAPTURE_HELPER" \\\n'
        '  "$PYTHON_BIN" -I "$CAPTURE_HELPER_SELECTOR"\n'
        ')"\n'
        'if [[ -z "$CAPTURE_HELPER" ]]; then\n'
        '  echo "Selected capture helper is unavailable" >&2\n'
        "  exit 2\n"
        "fi\n"
        'if ! test -f "$CAPTURE_HELPER"; then\n'
        '  echo "Selected capture helper is unavailable" >&2\n'
        "  exit 2\n"
        "fi"
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
    revision_environment = (
        {
            "MANUAL_BASE_SHA": "${{ inputs.base_sha }}",
            "MANUAL_CANDIDATE_SHA": "${{ github.sha }}",
            "MANUAL_SOURCE_HEAD_SHA": "${{ github.sha }}",
            "MANUAL_BASE_REF": "${{ github.ref_name }}",
        }
        if is_manual
        else {
            "EVENT_NAME": "${{ github.event_name }}",
            "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
            "PR_CANDIDATE_SHA": "${{ github.sha }}",
            "PR_SOURCE_HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
            "PR_BASE_REF": "${{ github.event.pull_request.base.ref }}",
            "PUSH_BASE_SHA": "${{ github.event.before }}",
            "PUSH_CANDIDATE_SHA": "${{ github.sha }}",
            "PUSH_SOURCE_HEAD_SHA": "${{ github.sha }}",
            "PUSH_BASE_REF": "${{ github.ref_name }}",
        }
    )
    if not is_manual and not is_rust:
        revision_environment.update(
            {
                "PR_NUMBER_VALUE": "${{ github.event.pull_request.number }}",
                "PR_HEAD_REPOSITORY_VALUE": "${{ github.event.pull_request.head.repo.full_name }}",
                "PR_HEAD_REF_VALUE": "${{ github.event.pull_request.head.ref }}",
                "PR_BASE_REF_VALUE": "${{ github.event.pull_request.base.ref }}",
                "REPOSITORY_NAME_VALUE": "${{ github.repository }}",
            }
        )
        revision_environment["PUSH_REF_VALUE"] = "${{ github.ref }}"
    _assert_paired_capture_contract(
        job,
        capture_format="rust" if is_rust else "go",
        comparator_format="bencher" if is_rust else "go",
        revision_environment=revision_environment,
        candidate_capture_helper=not is_manual and not is_rust,
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
    capture_helper = (
        '"$PYTHON_BIN" -I "$CAPTURE_HELPER"'
        if "CAPTURE_HELPER_SELECTOR=" in str(capture["run"])
        else '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"'
    )

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
            str(capture["run"]), capture_helper
        )
    elif mutation == "comparison-conditional-wrapper":
        comparator["run"] = _wrap_standalone_invocation_in_if(
            str(comparator["run"]), '"$PYTHON_BIN" -I "$BASE_COMPARATOR"'
        )
    elif mutation == "capture-substitution-wrapper":
        capture["run"] = _wrap_standalone_invocation_in_substitution(
            str(capture["run"]), capture_helper
        )
    elif mutation == "capture-backtick-wrapper":
        capture["run"] = _wrap_standalone_invocation_in_backticks(
            str(capture["run"]), capture_helper
        )
    elif mutation.startswith("capture-outer-"):
        capture["run"] = _wrap_standalone_invocation_in_outer_context(
            str(capture["run"]),
            capture_helper,
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
    candidate_capture_helper: bool = False,
) -> None:
    """Assert the observable workflow contract for a fail-closed paired gate."""

    assert job["runs-on"] == "ubuntu-24.04"
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
    execution_contract_text = capture_text
    if candidate_capture_helper:
        selection_start = capture_text.index("CAPTURE_HELPER_SELECTOR=")
        selection_end = capture_text.index("\n\n{", selection_start)
        selection_segment = capture_text[selection_start:selection_end]
        assert _canonical_shell_lines(selection_segment) == (
            _expected_candidate_helper_selection_segment()
        )
        execution_contract_text = (
            capture_text[:selection_start] + capture_text[selection_end:]
        )
    _assert_critical_execution_segment(
        execution_contract_text,
        anchor='BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"',
        expected=_expected_capture_critical_execution_segment(
            capture_format, candidate_capture_helper=candidate_capture_helper
        ),
    )
    capture_helper_command = (
        '"$PYTHON_BIN" -I "$CAPTURE_HELPER"'
        if candidate_capture_helper
        else '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"'
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
        capture_helper_command,
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
    if candidate_capture_helper:
        assert (
            'CAPTURE_HELPER_SELECTOR="$GITHUB_WORKSPACE/scripts/quality/benchmark_capture_activation.py"'
            in normalized_capture_text
        )
        assert 'PUSH_REF="$PUSH_REF_VALUE"' in normalized_capture_text
        assert 'PUSH_BASE_REF="$PUSH_BASE_REF"' in normalized_capture_text
        assert '"$PYTHON_BIN" -I "$CAPTURE_HELPER_SELECTOR"' in normalized_capture_text
        assert 'if [[ -z "$CAPTURE_HELPER" ]]; then' in normalized_capture_text
        assert 'if ! test -f "$CAPTURE_HELPER"; then' in normalized_capture_text
        assert '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"' not in normalized_capture_text
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
    ) < capture_text.index(capture_helper_command)
    assert (
        capture_text.index(
            'BASE_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR" | awk \'{print $1}\')"'
        )
        < capture_text.index('echo "base_comparator_sha256=$BASE_COMPARATOR_SHA256"')
        < capture_text.index(capture_helper_command)
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


def _assert_paired_provenance_contract(
    job: dict[str, object], *, capture_id: str, is_pull_request_workflow: bool
) -> None:
    """Require revision provenance to be recorded and verified before comparison."""

    record = _step_named(job, "Record immutable benchmark provenance")
    assert record["shell"] == "bash"
    assert record.get("continue-on-error", False) is False
    record_text = str(record["run"])
    normalized_record_text = " ".join(record_text.replace("\\\n", " ").split())
    assert normalized_record_text.startswith("set -euo pipefail")
    for required_fragment in (
        'validate_sha "$BASE_SHA" "base SHA"',
        'validate_sha "$TESTED_COMMIT_SHA" "tested commit SHA"',
        'validate_sha "$SOURCE_HEAD_SHA" "source head SHA"',
        'if [[ ! "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]; then',
        'if [[ ! "$GITHUB_RUN_ATTEMPT" =~ ^[0-9]+$ ]]; then',
        'if [[ ! -d "$ARTIFACT_ROOT" ]]; then',
        "git rev-parse HEAD",
        'git rev-list --parents -n1 "$TESTED_COMMIT_SHA"',
        "tested_commit_parents",
        "jq -n",
        "provenance.json.tmp",
        'mv -- "$PROVENANCE_TMP" "$ARTIFACT_ROOT/provenance.json"',
    ):
        assert required_fragment in normalized_record_text
    record_env = record.get("env", {})
    assert isinstance(record_env, dict)
    assert record_env.get("EVENT_NAME") in {
        "workflow_dispatch",
        "${{ github.event_name }}",
    }

    comparator = _step_named(job, "Compare paired benchmark evidence")
    comparator_text = str(comparator["run"])
    normalized_comparator_text = " ".join(comparator_text.replace("\\\n", " ").split())
    assert (
        'BASE_COMPARATOR="${{ steps.' + capture_id + '.outputs.base_comparator }}"'
    ) in comparator_text
    assert "jq -e" in normalized_comparator_text
    assert '"$ARTIFACT_ROOT/provenance.json" >/dev/null' in normalized_comparator_text
    for required_fragment in (
        ".schema_version == 1",
        ".event == $event",
        ".run_id",
        ".run_attempt",
        ".base_ref == $base_ref",
        ".base_sha == $base_sha",
        ".source_head_sha == $source_head_sha",
        ".tested_commit_sha == $tested_commit_sha",
        'git rev-list --parents -n1 "$EXPECTED_TESTED_COMMIT_SHA"',
        "ACTUAL_PARENTS_JSON",
        ".tested_commit_parents == $expected_parents",
    ):
        assert required_fragment in normalized_comparator_text
    if is_pull_request_workflow:
        comparator_env = comparator.get("env", {})
        assert isinstance(comparator_env, dict)
        assert (
            comparator_env.get("PR_SOURCE_HEAD_SHA")
            == "${{ github.event.pull_request.head.sha }}"
        )
    else:
        assert ".source_head_sha == .tested_commit_sha" in normalized_comparator_text
    assert normalized_comparator_text.index("jq -e") < normalized_comparator_text.index(
        'ACTUAL_COMPARATOR_SHA256="$(sha256sum "$BASE_COMPARATOR"'
    )
    expected_jq_checks = (
        2 if capture_id == "capture_ws_hub" and is_pull_request_workflow else 1
    )
    assert comparator_text.count("jq -e") == expected_jq_checks
    if expected_jq_checks == 2:
        for required_fragment in (
            '"$ARTIFACT_ROOT/capture-helper-provenance.json" >/dev/null',
            '--arg origin "$HELPER_ORIGIN"',
            '--arg sha256 "$HELPER_SHA256"',
            '"$ARTIFACT_ROOT/provenance.json" >/dev/null',
        ):
            assert required_fragment in normalized_comparator_text

    capture = _step_named(
        job, "Resolve immutable revisions and capture paired evidence"
    )
    capture_text = " ".join(str(capture["run"]).replace("\\\n", " ").split())
    assert 'git rev-list --parents -n1 "$CANDIDATE_SHA"' in capture_text
    assert 'if [[ "$EVENT_NAME" == "pull_request" ]]; then' in capture_text or (
        not is_pull_request_workflow
    )
    if is_pull_request_workflow:
        for required_fragment in (
            'if ! git cat-file -e "$SOURCE_HEAD_SHA^{commit}"; then',
            'read -r COMMIT_ID PARENT_ONE PARENT_TWO EXTRA_PARENTS <<< "$PARENT_LINE"',
            'if [[ "$PARENT_ONE" != "$BASE_SHA" ]]; then',
            'if [[ "$PARENT_TWO" != "$SOURCE_HEAD_SHA" ]]; then',
            'if [[ -n "$EXTRA_PARENTS" ]]; then',
        ):
            assert required_fragment in capture_text
    else:
        assert 'git cat-file -e "$SOURCE_HEAD_SHA^{commit}"' in capture_text
        assert 'if [[ "$SOURCE_HEAD_SHA" != "$CANDIDATE_SHA" ]]; then' in capture_text


def test_paired_performance_provenance_is_current_and_fail_closed() -> None:
    """Both required and manual paired gates bind evidence to one run and SHA set."""

    for workflow_path, is_pull_request_workflow in (
        (REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml", True),
        (MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH, False),
    ):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        for job_id in ("ws-hub-regression", "rust-native-regression"):
            job = jobs[job_id]
            capture = _step_named(
                job, "Resolve immutable revisions and capture paired evidence"
            )
            _assert_paired_provenance_contract(
                job,
                capture_id=str(capture["id"]),
                is_pull_request_workflow=is_pull_request_workflow,
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
        "PR_SOURCE_HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
        "PR_BASE_REF": "${{ github.event.pull_request.base.ref }}",
        "PUSH_BASE_SHA": "${{ github.event.before }}",
        "PUSH_CANDIDATE_SHA": "${{ github.sha }}",
        "PUSH_SOURCE_HEAD_SHA": "${{ github.sha }}",
        "PUSH_BASE_REF": "${{ github.ref_name }}",
    }
    ws_revision_environment = {
        **shared_revision_environment,
        "PR_NUMBER_VALUE": "${{ github.event.pull_request.number }}",
        "PR_HEAD_REPOSITORY_VALUE": "${{ github.event.pull_request.head.repo.full_name }}",
        "PR_HEAD_REF_VALUE": "${{ github.event.pull_request.head.ref }}",
        "PR_BASE_REF_VALUE": "${{ github.event.pull_request.base.ref }}",
        "REPOSITORY_NAME_VALUE": "${{ github.repository }}",
        "PUSH_REF_VALUE": "${{ github.ref }}",
    }
    _assert_paired_capture_contract(
        jobs["ws-hub-regression"],
        capture_format="go",
        comparator_format="go",
        revision_environment=ws_revision_environment,
        base_worktree_leaf="performance-base-ws-hub",
        timeout_minutes=20,
        candidate_capture_helper=True,
    )
    _assert_paired_capture_contract(
        jobs["rust-native-regression"],
        capture_format="rust",
        comparator_format="bencher",
        revision_environment=shared_revision_environment,
        base_worktree_leaf="performance-base-rust-native",
        timeout_minutes=30,
    )


def test_benchmark_go_cache_covers_every_workspace_dependency_file() -> None:
    """Benchmark cache invalidation must include every Go module in the workspace."""

    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml").read_text(
            encoding="utf-8"
        )
    )
    setup_go = next(
        step
        for step in workflow["jobs"]["benchmark"]["steps"]
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/setup-go")
    )
    assert setup_go["with"]["cache"] is True
    assert setup_go["with"]["cache-dependency-path"].splitlines() == [
        "services/gateway/go.sum",
        "services/file-processor/go.sum",
        "services/ws-hub/go.sum",
        "services/cmd/uni-cli/go.sum",
        "services/pkg/spiffe/go.sum",
        "services/pkg/spicedb/go.mod",
        "services/pkg/logging/go.mod",
        "gen/go/go.sum",
        "go.sum",
    ]


def test_reusable_go_cache_covers_every_workspace_dependency_file() -> None:
    """Reusable Go callers must invalidate the shared cache for every module."""

    workflow = yaml.safe_load(GO_WORKFLOW_PATH.read_text(encoding="utf-8"))
    setup_go = next(
        step
        for step in workflow["jobs"]["test"]["steps"]
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/setup-go")
    )
    assert setup_go["with"]["cache"] is True
    assert setup_go["with"]["cache-dependency-path"].splitlines() == [
        "services/gateway/go.sum",
        "services/file-processor/go.sum",
        "services/ws-hub/go.sum",
        "services/cmd/uni-cli/go.sum",
        "services/pkg/spiffe/go.sum",
        "services/pkg/spicedb/go.mod",
        "services/pkg/logging/go.mod",
        "gen/go/go.sum",
        "go.sum",
    ]


def test_performance_history_is_main_only_and_advisory() -> None:
    """Historical charts cannot supply a PR decision or receive PR credentials."""

    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert jobs["benchmark"]["name"] == "Run Go Benchmarks"
    assert "rust-criterion" not in jobs

    for job_id in ("benchmark",):
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
    assert len(publisher_steps) == 1
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


def test_required_go_benchmark_job_is_not_mislabeled_as_advisory() -> None:
    """Keep workflow prose aligned with the live required status context."""

    workflow_text = (
        REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml"
    ).read_text(encoding="utf-8")
    assert "required by branch protection" in workflow_text
    assert "Capture advisory Go benchmark evidence" not in workflow_text
    assert "Upload advisory Go benchmark evidence" not in workflow_text


@pytest.mark.parametrize(
    "workflow_path",
    [
        REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
        MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
    ],
)
def test_performance_workflows_do_not_enforce_retired_gateway_hash_ring_budget(
    workflow_path: Path,
) -> None:
    """ADR-046 retired vector sharding and the root-package HashRing benchmark."""

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["benchmark"]["steps"]
    assert all(
        step.get("name") != "Enforce gateway HashRing lookup budget" for step in steps
    )
    commands = "\n".join(str(step.get("run", "")) for step in steps)
    assert "BenchmarkHashRingLookup" not in commands
    assert "gateway-hashring-budget.txt" not in commands


@pytest.mark.parametrize(
    ("workflow_path", "capture_step_name"),
    [
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "benchmark.yml",
            "Capture Go benchmark evidence",
        ),
        (
            MANUAL_PERFORMANCE_EVIDENCE_WORKFLOW_PATH,
            "Capture advisory Go benchmark evidence",
        ),
    ],
)
def test_performance_workflows_keep_active_go_benchmark_capture(
    workflow_path: Path,
    capture_step_name: str,
) -> None:
    """Retiring HashRing must preserve uninstrumented gateway and WS-Hub evidence."""

    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["benchmark"]
    assert job.get("continue-on-error", False) is False
    capture_step = _step_named(job, capture_step_name)
    assert capture_step == {
        "name": capture_step_name,
        "shell": "bash",
        "run": """\
set -euo pipefail
mkdir -p artifacts/performance/advisory/go
(
  cd services/gateway
  go test -bench=. -run=^$ ./...
) 2>&1 | tee artifacts/performance/advisory/go/gateway-bench.txt
(
  cd services/ws-hub
  go test -bench=. -run=^$ ./...
) 2>&1 | tee artifacts/performance/advisory/go/wshub-bench.txt
cat \\
  artifacts/performance/advisory/go/gateway-bench.txt \\
  artifacts/performance/advisory/go/wshub-bench.txt \\
  > artifacts/performance/advisory/go/benchmarks.txt
""",
    }
    command = capture_step["run"]
    _assert_fail_closed_shell_mode(command)
    _assert_no_shell_indirection_or_option_control(command)
    assert "-race" not in command
    assert "-cover" not in command


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
        "rust-native-regression": (
            "Manual Performance Evidence / Rust Native Optimizer Regression Gate"
        ),
    }
    assert {job_id: jobs[job_id]["name"] for job_id in expected_names} == expected_names
    assert set(expected_names.values()).isdisjoint(REQUIRED_PERFORMANCE_CONTEXTS)

    manual_revision_environment = {
        "MANUAL_BASE_SHA": "${{ inputs.base_sha }}",
        "MANUAL_CANDIDATE_SHA": "${{ github.sha }}",
        "MANUAL_SOURCE_HEAD_SHA": "${{ github.sha }}",
        "MANUAL_BASE_REF": "${{ github.ref_name }}",
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


def test_sqlmap_openapi_scan_is_pinned_local_and_bounded() -> None:
    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    sqlmap_job = workflow["jobs"]["sqlmap"]
    assert sqlmap_job.get("continue-on-error", False) is False
    assert sqlmap_job["timeout-minutes"] == 20

    steps = {step["name"]: step for step in sqlmap_job["steps"]}
    install = steps["Install SQLMap"]
    capability = steps["Verify SQLMap OpenAPI support"]
    readiness = steps["Start FastAPI Backend in Background"]
    scan = steps["Run SQLMap Scan on API"]

    assert install["run"].strip() == 'uv pip install "sqlmap==1.10.8"'
    assert "uv run sqlmap -hh" in capability["run"]
    assert 'grep -Fq -- "--openapi="' in capability["run"]
    assert "exit 1" in capability["run"]
    assert SQLMAP_OPENAPI_URL in readiness["run"]
    assert "http://127.0.0.1:8000/openapi.json" not in readiness["run"]
    assert "curl --fail --silent --show-error" in readiness["run"]
    assert "test -s" in readiness["run"]
    assert "for i in {1..30}; do" in readiness["run"]
    assert "exit 1" in readiness["run"]

    scan_script = scan["run"]
    assert f'--openapi="{SQLMAP_OPENAPI_URL}"' in scan_script
    assert f'--openapi-base="{SQLMAP_OPENAPI_BASE_URL}"' in scan_script
    for option in (
        "--batch",
        "--crawl=0",
        "--technique=BEU",
        "--risk=1",
        "--level=1",
        "--threads=2",
        "--timeout=5",
        "--retries=0",
    ):
        assert option in scan_script

    scan_arguments = shlex.split(scan_script.replace("\\\n", ""), comments=True)
    assert scan_arguments == [
        "uv",
        "run",
        "sqlmap",
        f"--openapi={SQLMAP_OPENAPI_URL}",
        f"--openapi-base={SQLMAP_OPENAPI_BASE_URL}",
        "--batch",
        "--crawl=0",
        "--technique=BEU",
        "--risk=1",
        "--level=1",
        "--threads=2",
        "--timeout=5",
        "--retries=0",
        "--flush-session",
    ]

    for step in (capability, readiness, scan):
        assert step.get("continue-on-error", False) is False
        assert "|| true" not in step["run"]


def _provenance_step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    matches = [
        step for step in steps if isinstance(step, dict) and step.get("name") == name
    ]
    assert len(matches) == 1, f"expected exactly one workflow step named {name!r}"
    return matches[0]


def _run_text(job: dict[str, object]) -> str:
    steps = job.get("steps")
    assert isinstance(steps, list)
    return "\n".join(
        str(step.get("run", "")) for step in steps if isinstance(step, dict)
    )


def _assert_current_run_download(step: dict[str, object]) -> None:
    uses = str(step.get("uses", ""))
    assert uses.startswith("actions/download-artifact@")
    options = step.get("with", {})
    assert isinstance(options, dict)
    assert "run-id" not in options
    assert "github-token" not in options
    assert "repository" not in options


def _assert_scoped_artifact_download(step: dict[str, object]) -> None:
    """Require an aggregate download to use a validated server-issued ID."""

    uses = str(step.get("uses", ""))
    assert uses.startswith("actions/download-artifact@")
    options = step.get("with", {})
    assert isinstance(options, dict)
    assert "artifact-ids" in options
    assert "steps.select_coverage_producers.outputs.selections" in str(
        options["artifact-ids"]
    )
    assert options.get("repository") == "${{ github.repository }}"
    assert options.get("run-id") == "${{ github.run_id }}"
    assert options.get("github-token") == "${{ github.token }}"
    assert options.get("merge-multiple") is False
    assert "name" not in options
    assert "pattern" not in options


def test_coverage_producers_publish_closed_v2_sidecars() -> None:
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    frontend = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    go = yaml.safe_load(GO_WORKFLOW_PATH.read_text(encoding="utf-8"))

    frontend_job = frontend["jobs"]["unit-tests"]
    frontend_steps = frontend_job["steps"]
    cleanup = _provenance_step(frontend_job, "Clean merged frontend coverage outputs")
    download = _provenance_step(frontend_job, "Download frontend coverage shards")
    assert frontend_steps.index(cleanup) < frontend_steps.index(download)
    _assert_current_run_download(download)
    provenance = _provenance_step(frontend_job, "Write frontend coverage provenance")
    provenance_run = str(provenance["run"])
    assert "scripts/quality/coverage_provenance.py write" in provenance_run
    assert (
        "frontend|lcov|frontend/coverage/lcov.info|frontend/coverage/lcov.info"
        in provenance_run
    )
    assert (
        "frontend|istanbul-json|frontend/coverage/coverage-final.json|frontend/coverage/coverage-final.json"
        in provenance_run
    )
    assert "test -s frontend/coverage/lcov.info" in provenance_run
    assert "test -s frontend/coverage/coverage-final.json" in provenance_run
    frontend_upload = _provenance_step(frontend_job, "Upload coverage artifacts")
    assert frontend_upload["with"]["if-no-files-found"] == "error"
    assert set(str(frontend_upload["with"]["path"]).splitlines()) == {
        "frontend/coverage/lcov.info",
        "frontend/coverage/coverage-final.json",
        "frontend/coverage/coverage-provenance.json",
    }

    go_job = go["jobs"]["test"]
    go_text = _run_text(go_job)
    assert "coverage-component" in _workflow_triggers(go)["workflow_call"]["inputs"]
    assert "Clean Go coverage outputs" in {
        str(step.get("name", "")) for step in go_job["steps"]
    }
    assert "scripts/quality/coverage_provenance.py write" in go_text
    assert "$COVERAGE_COMPONENT|go-coverprofile" in go_text
    go_upload = _provenance_step(go_job, "Upload coverage artifacts")
    assert go_upload["if"] == "${{ success() }}"
    assert go_upload["with"]["if-no-files-found"] == "error"
    assert "coverage-provenance.json" in str(go_upload["with"]["path"])
    assert go_upload["with"]["name"] == "${{ steps.artifact-name.outputs.name }}"

    rust_job = ci["jobs"]["rust-tests"]
    rust_steps = rust_job["steps"]
    rust_cleanup = _provenance_step(rust_job, "Clean Rust coverage outputs")
    rust_create = _provenance_step(rust_job, "Create coverage output directories")
    assert rust_steps.index(rust_cleanup) < rust_steps.index(rust_create)
    rust_provenance = _provenance_step(rust_job, "Write Rust coverage provenance")
    rust_run = str(rust_provenance["run"])
    assert '--artifact "rust-coverage-attempt-${RUN_ATTEMPT}"' in rust_run
    assert rust_run.count("|llvm-cov-json|") == 3
    assert rust_run.count("|llvm-cov-branch-json|") == 3
    assert (
        "test \"$(find artifacts/coverage/rust -name 'llvm.json' -type f | wc -l)\" -eq 3"
        in rust_run
    )
    assert (
        "test \"$(find artifacts/coverage/rust -name 'branch-llvm.json' -type f | wc -l)\" -eq 3"
        in rust_run
    )
    rust_upload = _provenance_step(rust_job, "Upload Rust coverage artifacts")
    assert rust_upload["with"]["if-no-files-found"] == "error"
    assert (
        rust_upload["with"]["name"] == "rust-coverage-attempt-${{ github.run_attempt }}"
    )
    assert "artifacts/coverage/rust/coverage-provenance.json" in str(
        rust_upload["with"]["path"]
    )


def test_coverage_aggregate_uses_scoped_current_run_artifacts_only() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["coverage-policy-gate"]
    steps = job["steps"]
    head_guard = _provenance_step(job, "Verify aggregate checkout SHA")
    cleanup = _provenance_step(job, "Clean aggregate coverage destinations")
    downloads = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/download-artifact@")
    ]
    assert downloads
    assert (
        steps.index(head_guard)
        < steps.index(cleanup)
        < min(steps.index(step) for step in downloads)
    )
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"' in str(head_guard["run"])
    assert head_guard["env"]["EXPECTED_SHA"] == "${{ github.sha }}"
    cleanup_run = str(cleanup["run"])
    assert "rm -rf -- artifacts/coverage/python/shards" in cleanup_run
    assert "rm -rf -- frontend/coverage" in cleanup_run
    assert "rm -rf -- artifacts/coverage/go" in cleanup_run
    assert "rm -rf -- artifacts/coverage/rust" in cleanup_run
    assert "rm -rf -- artifacts/coverage" not in {
        line.strip() for line in cleanup_run.splitlines()
    }
    selector_step = _provenance_step(
        job, "Select retry-safe same-run coverage producer artifacts"
    )
    assert selector_step["id"] == "select_coverage_producers"
    assert "scripts.quality.select_coverage_producer_artifacts" in str(
        selector_step["run"]
    )
    for download in downloads:
        _assert_scoped_artifact_download(download)

    verify = _provenance_step(job, "Verify downloaded coverage artifacts")
    verify_run = str(verify["run"])
    assert "coverage_provenance.py verify" in verify_run
    assert '--expected-sha "$EXPECTED_SHA"' in verify_run
    assert '--expected-run-id "$RUN_ID"' in verify_run
    assert '--expected-run-attempt "$producer_attempt"' in verify_run
    assert "SELECTIONS_JSON" in verify["env"]
    assert "selection_value" in verify_run
    backend_verify = _provenance_step(job, "Verify backend shard provenance")
    assert (
        "test \"$(find artifacts/coverage/python/shards -name '.coverage.shard-*' -type f | wc -l)\" -eq 4"
        in str(backend_verify["run"])
    )
    assert (
        "test \"$(find artifacts/coverage/python/shards -name 'pytest-shard-*.json' -type f | wc -l)\" -eq 4"
        in str(backend_verify["run"])
    )
    assert (
        'test "$(find artifacts/coverage/python/shards -type f | wc -l)" -eq 12'
        in str(backend_verify["run"])
    )
    assert (
        "test \"$(find artifacts/coverage/go/shared-inputs -name 'coverage.out' -type f | wc -l)\" -eq 4"
        in verify_run
    )


def test_coverage_api_selection_receipt_is_bound_before_canonical_merge() -> None:
    """Keep retry-selected producer evidence bound to the aggregate merge."""

    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["coverage-policy-gate"]
    steps = job["steps"]

    verify = _provenance_step(job, "Verify downloaded coverage artifacts")
    receipt = _provenance_step(job, "Write API-bound coverage selection receipt")
    merge = _provenance_step(job, "Merge canonical coverage provenance")
    assert steps.index(verify) < steps.index(receipt) < steps.index(merge)

    receipt_run = str(receipt["run"])
    assert "coverage_provenance.py write-api-receipt" in receipt_run
    assert "--output artifacts/coverage/provenance/api-selection.json" in receipt_run
    assert receipt_run.count("--selection ") == 5
    for expected_selection in (
        "frontend/coverage/coverage-provenance.json|unit-tests|$frontend_attempt|$frontend_id|$frontend_name|$frontend_digest",
        "artifacts/coverage/go/gateway/coverage-provenance.json|test|$gateway_attempt|$gateway_id|$gateway_name|$gateway_digest",
        "artifacts/coverage/go/ws-hub/coverage-provenance.json|test|$ws_hub_attempt|$ws_hub_id|$ws_hub_name|$ws_hub_digest",
        "artifacts/coverage/go/file-processor/coverage-provenance.json|test|$file_processor_attempt|$file_processor_id|$file_processor_name|$file_processor_digest",
        "artifacts/coverage/rust/coverage-provenance.json|rust-tests|$rust_attempt|$rust_id|$rust_name|$rust_digest",
    ):
        assert f'--selection "{expected_selection}"' in receipt_run

    merge_run = str(merge["run"])
    assert (
        "--retry-selection-receipt artifacts/coverage/provenance/api-selection.json"
        in merge_run
    )

    upload = _provenance_step(job, "Upload canonical quality evidence")
    upload_paths = str(upload["with"]["path"])
    assert "artifacts/coverage/provenance/api-selection.json" in upload_paths
    assert steps.index(merge) < steps.index(upload)


def test_quality_gate_supplies_all_v2_reports_and_current_run_identity() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["coverage-policy-gate"]
    normalize = _provenance_step(job, "Normalize coverage evidence")
    normalize_run = str(normalize["run"])

    assert normalize["env"]["SOURCE_HEAD_SHA"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )
    assert normalize["env"]["BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha || github.sha }}"
    )
    assert normalize["env"]["BASE_REF"] == (
        "${{ github.event.pull_request.base.ref || github.ref_name }}"
    )

    # The coverage gate installs the locked development environment with uv.
    # Running the normalizer through the runner's system Python bypasses that
    # environment (and its jsonschema dependency), making the gate fail before
    # it can validate the manifest. Keep the interpreter provenance-bound.
    assert (
        "uv run python scripts/quality/normalize_coverage_reports.py" in normalize_run
    )
    assert "python scripts/quality/normalize_coverage_reports.py" not in {
        line.strip() for line in normalize_run.splitlines()
    }

    for required in (
        '--repository-root "$GITHUB_WORKSPACE"',
        '--commit-sha "$EXPECTED_SHA"',
        '--source-head-sha "$SOURCE_HEAD_SHA"',
        '--base-sha "$BASE_SHA"',
        '--base-ref "$BASE_REF"',
        "--provenance-mode github-actions",
        '--workflow-run-id "$RUN_ID"',
        '--workflow-run-attempt "$RUN_ATTEMPT"',
        '--workflow-event "$WORKFLOW_EVENT"',
        '--workflow-repository "$WORKFLOW_REPOSITORY"',
        '--workflow-ref "$WORKFLOW_REF"',
        "--workflow-job coverage-policy-gate",
        "--python-xml coverage.xml",
        "--python-json artifacts/coverage/python/coverage.json",
        "--frontend-lcov frontend/coverage/lcov.info",
        "--frontend-json frontend/coverage/coverage-final.json",
    ):
        assert required in normalize_run
    assert normalize_run.count("--go-report ") == 4
    assert normalize_run.count("--rust-report ") == 3
    assert normalize_run.count("--rust-branch-report ") == 3
    assert "ignore-outside" not in normalize_run
    assert normalize_run.count("--tool-version ") >= 7

    combine = _provenance_step(job, "Combine Python shard coverage")
    combine_run = str(combine["run"])
    assert (
        "coverage_version=\"$(uv run python -c 'import coverage; print(coverage.__version__)')\""
        in combine_run
    )
    assert "coverage --version | awk" not in combine_run
    assert '[[ ! "$coverage_version" =~' in combine_run

    merge = _provenance_step(job, "Merge canonical coverage provenance")
    merge_run = str(merge["run"])
    assert "coverage_provenance.py merge" in merge_run
    assert merge_run.count("--metadata ") == 7
    assert "--contract quality/quality-contract.json" in merge_run
    assert "quality-evidence-${{ github.sha }}-attempt-${RUN_ATTEMPT}" in merge_run

    validator = _provenance_step(
        job, "Validate quality policy, mutation registry, and Tier0 manifest"
    )
    validator_run = str(validator["run"])
    assert "uv run python scripts/quality/validate_quality_contract.py" in validator_run
    assert "python scripts/quality/validate_quality_contract.py" not in {
        line.strip() for line in validator_run.splitlines()
    }
    for required in (
        "--schema quality/coverage-manifest.schema.json",
        '--artifact-root "$GITHUB_WORKSPACE"',
        '--expected-commit-sha "$EXPECTED_SHA"',
        '--expected-source-head-sha "$SOURCE_HEAD_SHA"',
        '--expected-tested-commit-sha "$EXPECTED_SHA"',
        '--expected-base-sha "$BASE_SHA"',
        '--expected-base-ref "$BASE_REF"',
        '--expected-workflow-run-id "$RUN_ID"',
        '--expected-workflow-run-attempt "$RUN_ATTEMPT"',
        '--expected-workflow-event "$WORKFLOW_EVENT"',
        '--expected-workflow-repository "$WORKFLOW_REPOSITORY"',
        '--expected-workflow-ref "$WORKFLOW_REF"',
        "--expected-workflow-job coverage-policy-gate",
    ):
        assert required in validator_run


def test_quality_evidence_bundle_is_hashed_after_validation_and_required() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["coverage-policy-gate"]
    steps = job["steps"]
    validator = _provenance_step(
        job, "Validate quality policy, mutation registry, and Tier0 manifest"
    )
    hash_step = _provenance_step(job, "Hash validated quality manifest")
    upload = _provenance_step(job, "Upload canonical quality evidence")
    assert steps.index(validator) < steps.index(hash_step) < steps.index(upload)
    hash_run = str(hash_step["run"])
    assert "sha256sum artifacts/coverage/quality-manifest.json" in hash_run
    assert "quality-manifest.json.sha256" in hash_run
    assert "sha256sum --check" in hash_run
    assert upload["with"]["name"] == (
        "quality-evidence-${{ github.sha }}-attempt-${{ github.run_attempt }}"
    )
    assert upload["with"]["if-no-files-found"] == "error"
    upload_paths = str(upload["with"]["path"])
    for required in (
        "coverage.xml",
        "artifacts/coverage/python/coverage.json",
        "frontend/coverage/lcov.info",
        "frontend/coverage/coverage-final.json",
        "artifacts/coverage/go/gateway/coverage.out",
        "artifacts/coverage/go/ws-hub/coverage.out",
        "artifacts/coverage/go/file-processor/coverage.out",
        "artifacts/coverage/go/shared/coverage.out",
        "artifacts/coverage/rust/",
        "artifacts/coverage/quality-manifest.json",
        "artifacts/coverage/quality-manifest.json.sha256",
        "artifacts/coverage/provenance/aggregate.json",
        "artifacts/coverage/provenance/api-selection.json",
    ):
        assert required in upload_paths

    for workflow_path in (
        BACKEND_WORKFLOW_PATH,
        FRONTEND_WORKFLOW_PATH,
        GO_WORKFLOW_PATH,
        CI_WORKFLOW_PATH,
    ):
        current = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job_config in current.get("jobs", {}).values():
            for step in job_config.get("steps", []):
                if not isinstance(step, dict):
                    continue
                if not str(step.get("uses", "")).startswith("actions/upload-artifact@"):
                    continue
                name = str(step.get("with", {}).get("name", "")).casefold()
                path = str(step.get("with", {}).get("path", "")).casefold()
                if any(
                    token in name + path
                    for token in ("coverage", "manifest", "provenance")
                ):
                    assert step["with"].get("if-no-files-found") == "error"


def test_release_and_deploy_require_the_same_sha_bound_quality_bundle() -> None:
    producer_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "build-release-images.yml"
    )
    release_path = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
    deploy_path = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
    for workflow_path in (producer_path, deploy_path):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        dispatch = _workflow_triggers(workflow)["workflow_dispatch"]
        inputs = dispatch["inputs"]
        assert inputs["release-sha"]["required"] is True
        assert inputs["quality-run-id"]["required"] is True
        gate = workflow["jobs"][
            "certify" if workflow_path == producer_path else "validate"
        ]
        text = _run_text(gate)
        assert "quality-evidence-$RELEASE_SHA-attempt-$run_attempt" in text
        assert "quality-manifest.json.sha256" in text
        assert "sha256sum --check" in text
        assert 'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"' in text
        assert "head_sha" in text and "conclusion" in text and "ci.yml" in text
        assert "gh run list" not in text
        assert "find " not in text

        download = _provenance_step(gate, "Download SHA-bound quality evidence")
        assert download["with"]["name"] == (
            "quality-evidence-${{ inputs.release-sha }}-attempt-"
            "${{ steps.quality-run.outputs.run-attempt }}"
        )
        assert download["with"]["run-id"] == "${{ inputs.quality-run-id }}"
        assert download["with"]["github-token"] == "${{ github.token }}"
        assert download["with"]["path"] == "."

        validate = _provenance_step(gate, "Validate SHA-bound quality evidence")
        validate_run = str(validate["run"])
        assert "validate_quality_contract.py" in validate_run
        assert '--expected-commit-sha "$RELEASE_SHA"' in validate_run
        assert '--expected-workflow-run-id "$QUALITY_RUN_ID"' in validate_run
        assert '--expected-workflow-run-attempt "$QUALITY_RUN_ATTEMPT"' in validate_run

    release = yaml.safe_load(release_path.read_text(encoding="utf-8"))
    assert "reusable-build-and-sign.yml" not in release_path.read_text(encoding="utf-8")
    assert release["jobs"]["publish"]["needs"] == ["resolve-images"]


def test_release_uses_actual_image_digest_provenance_after_build() -> None:
    obsolete = REPOSITORY_ROOT / ".github" / "workflows" / "slsa-provenance.yml"
    assert not obsolete.exists(), (
        "release-published provenance cannot run before release images exist"
    )

    reusable_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-build-and-sign.yml"
    )
    reusable = yaml.safe_load(reusable_path.read_text(encoding="utf-8"))
    steps = reusable["jobs"]["build"]["steps"]
    build = _provenance_step(
        reusable["jobs"]["build"], "Build local image for security scan"
    )
    provenance = _provenance_step(
        reusable["jobs"]["build"],
        "Attest build provenance for the published digest",
    )
    attest = _provenance_step(
        reusable["jobs"]["build"], "Attest SBOM for the built image"
    )
    sign = _provenance_step(reusable["jobs"]["build"], "Sign image (Keyless)")

    assert build["with"]["push"] is False
    assert build["with"]["load"] is True
    assert build["with"]["platforms"] == "linux/amd64"
    assert provenance["with"]["subject-digest"] == (
        "${{ steps.publish.outputs.digest }}"
    )
    assert provenance["with"]["push-to-registry"] is True
    assert str(attest["uses"]).startswith("actions/attest-sbom@")
    assert attest["with"]["subject-digest"] == "${{ steps.publish.outputs.digest }}"
    assert attest["with"]["sbom-path"] == "sbom.json"
    assert "github.sha" not in str(attest)
    assert steps.index(build) < steps.index(attest) < steps.index(sign)


def test_release_installs_checksum_pinned_trivy_before_registry_login() -> None:
    reusable_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-build-and-sign.yml"
    )
    reusable = yaml.safe_load(reusable_path.read_text(encoding="utf-8"))
    job = reusable["jobs"]["build"]
    steps = job["steps"]
    install = _provenance_step(job, "Install checksum-pinned Trivy")
    login = _provenance_step(job, "Login to GHCR after local security gates")
    scan = _provenance_step(job, "Scan local image before registry access (Trivy)")

    assert steps.index(install) < steps.index(login)
    assert install["env"]["TRIVY_VERSION"] == "0.73.0"
    assert re.fullmatch(r"[0-9a-f]{64}", install["env"]["TRIVY_ARCHIVE_SHA256"])
    install_run = str(install["run"])
    assert "releases/download/v${TRIVY_VERSION}/" in install_run
    assert "sha256sum --check" in install_run
    assert "apt-get" not in install_run
    assert "trivy-repo" not in install_run
    assert scan["with"]["skip-setup-trivy"] is True


def test_canonical_producer_builds_the_validated_source_sha() -> None:
    reusable_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-build-and-sign.yml"
    )
    reusable = yaml.safe_load(reusable_path.read_text(encoding="utf-8"))
    source_sha = _workflow_triggers(reusable)["workflow_call"]["inputs"]["source-sha"]
    assert source_sha["required"] is True
    job = reusable["jobs"]["build"]
    checkout = _provenance_step(job, "Checkout")
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    verify = _provenance_step(job, "Verify source checkout")
    verify_run = str(verify["run"])
    assert verify["env"]["SOURCE_SHA"] == "${{ inputs.source-sha }}"
    for fragment in (
        '[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$SOURCE_SHA" = "$GITHUB_SHA"',
        'test "$SOURCE_SHA" = "$GITHUB_WORKFLOW_SHA"',
        'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"',
        "git fetch origin refs/heads/main:refs/remotes/origin/main --depth=1",
        'test "$(git rev-parse origin/main)" = "$SOURCE_SHA"',
    ):
        assert fragment in verify_run
    assert job["steps"].index(verify) == job["steps"].index(checkout) + 1

    producer = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "build-release-images.yml"
        ).read_text(encoding="utf-8")
    )
    assert producer["jobs"]["build"]["with"]["source-sha"] == (
        "${{ inputs.release-sha }}"
    )

    for consumer_name in ("deploy.yml", "release.yml"):
        consumer = yaml.safe_load(
            (REPOSITORY_ROOT / ".github" / "workflows" / consumer_name).read_text(
                encoding="utf-8"
            )
        )
        assert "reusable-build-and-sign.yml" not in str(consumer)


def test_canonical_producer_matrix_uses_repository_root_docker_build_context() -> None:
    producer = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "build-release-images.yml"
        ).read_text(encoding="utf-8")
    )
    include = producer["jobs"]["build"]["strategy"]["matrix"]["include"]
    matrix = {entry["image_name"]: entry for entry in include}

    assert set(matrix) == {
        "backend",
        "caddy",
        "frontend",
        "ws-hub",
        "gateway",
        "file-processor",
    }
    # Every app Dockerfile copies repository-root inputs. In particular, each Go
    # service copies the shared root module, generated clients and shared SPIFFE
    # package before its own source, so a service-directory context cannot build.
    assert {entry["context"] for name, entry in matrix.items() if name != "caddy"} == {
        "."
    }
    assert matrix["caddy"] == {
        "image_name": "caddy",
        "file": "services/caddy/Dockerfile",
        "context": "services/caddy",
    }
    assert matrix["gateway"]["file"] == "services/gateway/Dockerfile"
    assert matrix["ws-hub"]["file"] == "services/ws-hub/Dockerfile"
    assert matrix["file-processor"]["file"] == ("services/file-processor/Dockerfile")

    assert producer["jobs"]["build"]["with"]["canonical_frontend"] == (
        "${{ matrix.image_name == 'frontend' }}"
    )

    reusable = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "reusable-build-and-sign.yml"
        ).read_text(encoding="utf-8")
    )
    build = _provenance_step(
        reusable["jobs"]["build"], "Build local image for security scan"
    )
    build_args = str(build["with"]["build-args"])
    assert "VITE_APP_RELEASE={0}" in build_args
    assert "VITE_ENABLE_WEB_VITALS=false" in build_args
    assert "VITE_CWV_TRUSTED_RUM=false" in build_args
    assert "VITE_WEB_VITALS_ENDPOINT=/api/v1/cwv" in build_args
    assert "VITE_ENABLE_WEB_VITALS=true" not in build_args
    assert "VITE_CWV_TRUSTED_RUM=true" not in build_args
    labels = str(build["with"]["labels"]).splitlines()
    assert labels == [
        "org.opencontainers.image.source=https://github.com/${{ github.repository }}",
        "org.opencontainers.image.revision=${{ inputs.source-sha }}",
    ]


def test_canonical_producer_publishes_only_the_immutable_sha_tag() -> None:
    producer = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "build-release-images.yml"
        ).read_text(encoding="utf-8")
    )

    build = producer["jobs"]["build"]
    assert build["permissions"] == {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
    }
    tags = str(build["with"]["tags"]).splitlines()
    assert tags == [
        "ghcr.io/${{ github.repository }}/${{ matrix.image_name }}:${{ inputs.release-sha }}"
    ]
    assert not any(tag.endswith(":latest") for tag in tags)

    release = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
    )
    publish = release["jobs"]["publish"]
    release_step = _provenance_step(publish, "Release")
    release_run = str(release_step["run"])
    assert "git fetch origin refs/heads/main:refs/remotes/origin/main --depth=1" in (
        release_run
    )
    assert 'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"' in release_run


def test_release_scans_local_image_before_any_registry_publication() -> None:
    reusable_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "reusable-build-and-sign.yml"
    )
    reusable = yaml.safe_load(reusable_path.read_text(encoding="utf-8"))
    job = reusable["jobs"]["build"]
    steps = job["steps"]
    build = _provenance_step(job, "Build local image for security scan")
    scan = _provenance_step(job, "Scan local image before registry access (Trivy)")
    sbom = _provenance_step(job, "Generate SBOM (CycloneDX)")
    login = _provenance_step(job, "Login to GHCR after local security gates")
    publish = _provenance_step(job, "Publish or reuse scanned immutable image")
    attest = _provenance_step(job, "Attest SBOM for the built image")
    sign = _provenance_step(job, "Sign image (Keyless)")
    verify = _provenance_step(job, "Verify final signature and attestation")

    assert build["with"]["push"] is False
    assert build["with"]["load"] is True
    assert scan["with"]["image-ref"] == "${{ steps.references.outputs.local_ref }}"
    assert "quarantine" not in reusable_path.read_text(encoding="utf-8").lower()
    assert steps.index(build) < steps.index(scan) < steps.index(sbom)
    assert steps.index(sbom) < steps.index(login)
    assert steps.index(login) < steps.index(publish) < steps.index(attest)
    assert steps.index(attest) < steps.index(sign) < steps.index(verify)
    publish_run = str(publish["run"])
    assert "publish_immutable_image.py" in publish_run
    assert '--final-ref "$FINAL_REF"' in publish_run
    assert '--local-ref "$LOCAL_REF"' in publish_run
    assert '--subject-name "$SUBJECT_NAME"' in publish_run
    assert "steps.publish.outputs.digest" in str(attest)


def test_release_keeps_global_serialization_for_immutable_tag_creation() -> None:
    release = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
    )

    assert release["concurrency"] == {
        "group": "release-main",
        "cancel-in-progress": False,
    }


def test_canonical_producer_aggregates_exact_digest_inventory() -> None:
    producer = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "build-release-images.yml"
        ).read_text(encoding="utf-8")
    )

    aggregate = producer["jobs"]["aggregate-image-provenance"]
    assert aggregate["needs"] == ["certify", "build"]
    select_cohort = _provenance_step(
        aggregate, "Select retry-safe release artifact cohort"
    )
    download_images = _provenance_step(
        aggregate, "Download selected verified image digest evidence"
    )
    download_certification = _provenance_step(
        aggregate, "Download selected signed certification"
    )
    verify_certification = _provenance_step(
        aggregate, "Verify selected signed certification"
    )
    aggregate_inventory = _provenance_step(
        aggregate, "Aggregate selected release image inventory"
    )
    install_cosign = _provenance_step(aggregate, "Install cosign")
    registry_login = _provenance_step(
        aggregate, "Login to GHCR for private image verification"
    )
    reverify = _provenance_step(aggregate, "Reverify every immutable image subject")
    aggregate_steps = aggregate["steps"]
    assert aggregate_steps.index(select_cohort) < aggregate_steps.index(download_images)
    assert aggregate_steps.index(download_images) < aggregate_steps.index(
        download_certification
    )
    assert aggregate_steps.index(download_certification) < aggregate_steps.index(
        verify_certification
    )
    assert aggregate_steps.index(verify_certification) < aggregate_steps.index(
        aggregate_inventory
    )
    assert aggregate_steps.index(aggregate_inventory) < aggregate_steps.index(
        install_cosign
    )
    assert aggregate_steps.index(install_cosign) < aggregate_steps.index(registry_login)
    assert aggregate_steps.index(registry_login) < aggregate_steps.index(reverify)
    select_cohort_run = str(select_cohort["run"])
    assert "--select-release-cohort" in select_cohort_run
    assert "--consumer-run-attempt" in select_cohort_run
    assert "selected-release-artifact-cohort.json" in select_cohort_run
    assert download_images["with"]["artifact-ids"] == (
        "${{ steps.select-artifact-cohort.outputs.image-artifact-ids }}"
    )
    assert download_certification["with"]["artifact-ids"] == (
        "${{ steps.select-artifact-cohort.outputs.certification-artifact-id }}"
    )
    assert (
        "--cohort artifacts/image-evidence-provenance/selected-release-artifact-cohort.json"
        in str(aggregate_inventory["run"])
    )
    assert str(registry_login["uses"]).startswith("docker/login-action@")
    assert registry_login["with"] == {
        "registry": "ghcr.io",
        "username": "${{ github.actor }}",
        "password": "${{ github.token }}",
    }
    steps_after_login = aggregate_steps[aggregate_steps.index(registry_login) + 1 :]
    assert [step["name"] for step in steps_after_login] == [
        "Reverify every immutable image subject",
        "Attest canonical image digest manifest",
        "Upload canonical image provenance",
    ]
    aggregate_text = _run_text(aggregate)
    assert "aggregate_release_image_evidence.py" in aggregate_text
    assert "cosign verify" in aggregate_text
    assert "gh attestation verify" in aggregate_text
    assert "sha256sum --check" in aggregate_text
    assert any(
        str(step.get("uses", "")).startswith("actions/attest-build-provenance@")
        for step in aggregate["steps"]
    )
    assert any(
        str(step.get("uses", "")).startswith("actions/upload-artifact@")
        and step.get("with", {}).get("name")
        == "release-image-provenance-${{ inputs.release-sha }}-attempt-${{ github.run_attempt }}"
        for step in aggregate["steps"]
    )

    release = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
    )
    publish = release["jobs"]["publish"]
    assert publish["needs"] == ["resolve-images"]
    publish_text = _run_text(publish)
    assert "release-image-manifest.json.sha256" in publish_text
    assert "gh attestation verify" in publish_text


def test_deploy_never_checks_out_untrusted_release_input() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )
    )

    for job_name in ("validate", "deploy", "rollback"):
        steps = workflow["jobs"][job_name]["steps"]
        checkout_index = next(
            index
            for index, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        checkout = steps[checkout_index]
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        assert checkout["with"]["persist-credentials"] is False
        assert "inputs.release-sha" not in str(checkout)

        verify = steps[checkout_index + 1]
        assert verify["name"].startswith("Verify trusted release checkout")
        assert verify["env"]["RELEASE_SHA"] == "${{ inputs.release-sha }}"
        run = str(verify["run"])
        assert '[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]' in run
        assert 'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"' in run
        assert (
            "git fetch origin refs/heads/main:refs/remotes/origin/main --depth=1" in run
        )
        assert 'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"' in run


def test_deploy_reverifies_trusted_sha_immediately_before_oidc() -> None:
    """OIDC must be requested only after a fresh immutable-source proof.

    The initial checkout proof is separated from the privileged deployment
    step by tool setup and contract validation.  A later checkout/ref race or
    workflow-context mismatch must therefore fail closed at the trust-boundary
    immediately before AWS receives an OIDC token.
    """
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = workflow["jobs"]["deploy"]["steps"]
    oidc_index = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith(
            "aws-actions/configure-aws-credentials@"
        )
    )
    assert oidc_index > 0
    verify = steps[oidc_index - 1]
    assert verify["name"] == "Reverify trusted release source before OIDC"
    assert verify["env"] == {
        "RELEASE_SHA": "${{ inputs.release-sha }}",
        "GITHUB_REF": "${{ github.ref }}",
        "GITHUB_SHA": "${{ github.sha }}",
        "GITHUB_WORKFLOW_SHA": "${{ github.workflow_sha }}",
    }
    run = str(verify["run"])
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in run
    assert 'test "$GITHUB_SHA" = "$RELEASE_SHA"' in run
    assert 'test "$GITHUB_WORKFLOW_SHA" = "$RELEASE_SHA"' in run
    assert 'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"' in run
    assert 'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"' in run


def test_contract_drift_serializes_openapi_deterministically() -> None:
    workflow = yaml.safe_load(
        CONTRACT_VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    step = _provenance_step(
        workflow["jobs"]["openapi-typescript-drift"],
        "Generate current OpenAPI spec",
    )

    assert "json.dumps(spec, indent=2, sort_keys=True) + '\\n'" in str(step["run"])


def test_hosted_browser_smokes_bound_frontend_build_memory() -> None:
    workflow_jobs = (
        ("unauthenticated-routes-smoke.yml", "unauthed-smoke"),
        ("admin-smoke-monitoring.yml", "admin-smoke"),
        ("visual-audit.yml", "visual-audit"),
    )

    for workflow_name, job_name in workflow_jobs:
        workflow = yaml.safe_load(
            (REPOSITORY_ROOT / ".github" / "workflows" / workflow_name).read_text(
                encoding="utf-8"
            )
        )
        build = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if str(step.get("name", "")).startswith("Build frontend")
        )
        assert build["env"]["FRONTEND_BUILD_MAX_RSS_MB"] == "2048"
        assert build["env"]["FRONTEND_BUILD_MAX_OLD_SPACE_MB"] == "1536"


def test_frontend_provenance_version_queries_are_shell_safe() -> None:
    source = FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8")
    safe_query = (
        'vitest_version="$(node -p '
        '\'require("./frontend/node_modules/vitest/package.json").version\')"'
    )

    assert source.count(safe_query) == 2
    assert 'node -p \\"require(' not in source


def test_backend_shards_publish_and_aggregate_current_attempt_lineage() -> None:
    backend = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    unit_job = backend["jobs"]["unit-tests"]
    provenance = _provenance_step(unit_job, "Write backend shard coverage provenance")
    provenance_run = str(provenance["run"])
    assert "coverage_provenance.py write" in provenance_run
    assert "coverage-provenance-shard-$SHARD_ID.json" in provenance_run
    assert provenance["env"]["ARTIFACT_NAME"].endswith(
        "-attempt-${{ github.run_attempt }}"
    )
    assert "python-shard|coverage-py-data" in provenance_run
    assert "python-shard|pytest-node-manifest" in provenance_run
    upload = _provenance_step(unit_job, "Upload raw coverage data for aggregation")
    assert upload["with"]["name"].endswith("-attempt-${{ github.run_attempt }}")
    assert set(str(upload["with"]["path"]).splitlines()) == {
        "artifacts/coverage/python/producer/.coverage.shard-${{ inputs.shard-id }}",
        "artifacts/coverage/python/producer/pytest-shard-${{ inputs.shard-id }}.json",
        "artifacts/coverage/python/producer/coverage-provenance-shard-${{ inputs.shard-id }}.json",
    }

    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    aggregate = ci["jobs"]["coverage-policy-gate"]
    download = _provenance_step(aggregate, "Download Python shard coverage data")
    _assert_scoped_artifact_download(download)
    verify = _provenance_step(aggregate, "Verify backend shard provenance")
    verify_run = str(verify["run"])
    assert "for shard in 0 1 2 3" in verify_run
    assert "coverage_provenance.py verify" in verify_run
    assert "--expected-job unit-tests" in verify_run
    assert '--expected-artifact "$artifact"' in verify_run
    assert '--expected-run-attempt "$producer_attempt"' in verify_run
    assert "selection_value" in verify_run
    assert "coverage-provenance-shard-${shard}.json" in verify_run
    assert (
        "find artifacts/coverage/python/shards -name '.coverage.shard-*'" in verify_run
    )


def test_frontend_shards_are_verified_before_coverage_merge() -> None:
    frontend = yaml.safe_load(FRONTEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    shard_job = frontend["jobs"]["unit-tests-shard"]
    provenance = _provenance_step(shard_job, "Write frontend shard provenance")
    provenance_run = str(provenance["run"])
    assert "coverage_provenance.py write" in provenance_run
    assert "frontend-shard|istanbul-json" in provenance_run
    assert provenance["env"]["ARTIFACT_NAME"] == (
        "frontend-coverage-shard-${{ matrix.shard }}-attempt-${{ github.run_attempt }}"
    )
    upload = _provenance_step(shard_job, "Upload frontend coverage shard")
    assert upload["with"]["name"].endswith("-attempt-${{ github.run_attempt }}")
    assert "coverage-provenance.json" in str(upload["with"]["path"])

    merge_job = frontend["jobs"]["unit-tests"]
    download = _provenance_step(merge_job, "Download frontend coverage shards")
    assert download["with"]["pattern"].endswith("-attempt-${{ github.run_attempt }}")
    verify = _provenance_step(merge_job, "Verify frontend shard provenance")
    verify_run = str(verify["run"])
    assert "for shard in 1 2 3 4" in verify_run
    assert "coverage_provenance.py verify" in verify_run
    assert "--expected-job unit-tests-shard" in verify_run
    assert '--expected-artifact "$artifact"' in verify_run
    merge = _provenance_step(merge_job, "Merge frontend coverage shards")
    assert merge_job["steps"].index(verify) < merge_job["steps"].index(merge)
    merged_upload = _provenance_step(merge_job, "Upload coverage artifacts")
    assert merged_upload["with"]["name"] == (
        "frontend-coverage-attempt-${{ github.run_attempt }}"
    )


def test_quality_history_revalidates_exact_sha_bound_run_evidence() -> None:
    workflow = yaml.safe_load(QUALITY_HISTORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["archive"]
    collect = _provenance_step(job, "Collect latest successful CI quality manifest")
    text = str(collect["run"])
    assert (
        "gh run list --workflow ci.yml --branch main --event push --status success"
        in text
    )
    for field in (
        "head_sha",
        "conclusion",
        "event",
        "head_branch",
        "path",
        "run_attempt",
    ):
        assert f".{field}" in text
    assert "actions/runs/$run_id" in text
    assert "actions/runs/$run_id/artifacts?per_page=100" in text
    assert "--paginate --slurp" in text
    assert "quality-evidence-$head_sha-attempt-$run_attempt" in text
    assert ".expired == false" in text
    assert "[.[].artifacts[]" in text
    assert "| length'" in text
    assert "git worktree add --detach" in text
    assert "validate_quality_contract.py" in text
    for required in (
        '--artifact-root "$evidence_root"',
        '--schema "$evidence_root/quality/coverage-manifest.schema.json"',
        '--expected-commit-sha "$head_sha"',
        '--expected-workflow-run-id "$run_id"',
        '--expected-workflow-run-attempt "$run_attempt"',
        "--expected-workflow-event push",
        '--expected-workflow-repository "$GITHUB_REPOSITORY"',
        '--expected-workflow-ref "$GITHUB_REPOSITORY/.github/workflows/ci.yml@refs/heads/main"',
        "--expected-workflow-job coverage-policy-gate",
    ):
        assert required in text


def test_rust_branch_reports_bind_the_nightly_rustc_version() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    rust_job = workflow["jobs"]["rust-tests"]
    provenance = _provenance_step(rust_job, "Write Rust coverage provenance")
    provenance_run = str(provenance["run"])
    assert "rustc +nightly --version" in provenance_run
    assert '--tool-version "rustc-nightly=$rustc_nightly_version"' in provenance_run
    normalize = _provenance_step(
        workflow["jobs"]["coverage-policy-gate"], "Normalize coverage evidence"
    )
    normalize_run = str(normalize["run"])
    assert 'rustc_nightly_version="$(read_tool rustc-nightly)"' in normalize_run
    assert '--tool-version "rustc-nightly=$rustc_nightly_version"' in normalize_run


def test_deploy_uses_build_digests_for_all_cluster_image_references() -> None:
    deploy_path = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
    workflow = yaml.safe_load(deploy_path.read_text(encoding="utf-8"))
    deploy = workflow["jobs"]["deploy"]
    helm = _provenance_step(deploy, "Deploy Helm release atomically")
    helm_run = (REPOSITORY_ROOT / ".github" / "scripts" / "deploy-helm.sh").read_text(
        encoding="utf-8"
    )
    assert "bash .github/scripts/deploy-helm.sh upgrade" in str(helm["run"])
    for setting in (
        "backend.image.digest=$BACKEND_IMAGE_DIGEST",
        "frontend.image.digest=$FRONTEND_IMAGE_DIGEST",
        "wsHub.image.digest=$WS_HUB_IMAGE_DIGEST",
        "gateway.image.digest=$GATEWAY_IMAGE_DIGEST",
        "fileProcessor.image.digest=$FILE_PROCESSOR_IMAGE_DIGEST",
        "outboxWorker.image.digest=$BACKEND_IMAGE_DIGEST",
    ):
        assert setting in helm_run
    assert "global.imageTag=$DEPLOY_VERSION" in helm_run
    assert not any(
        step.get("name") == "Deploy WS Hub image" for step in deploy["steps"]
    )
    verify = _provenance_step(deploy, "Verify Helm-managed rollouts")
    verify_run = str(verify["run"])
    assert "$image_prefix/backend@$BACKEND_IMAGE_DIGEST" in verify_run
    assert "$image_prefix/frontend@$FRONTEND_IMAGE_DIGEST" in verify_run
    assert "$image_prefix/ws-hub@$WS_HUB_IMAGE_DIGEST" in verify_run
    assert "$image_prefix/gateway@$GATEWAY_IMAGE_DIGEST" in verify_run
    assert "$image_prefix/file-processor@$FILE_PROCESSOR_IMAGE_DIGEST" in verify_run
    assert "$image_prefix/backend:$DEPLOY_VERSION" not in verify_run

    reusable = yaml.safe_load(
        (
            REPOSITORY_ROOT / ".github" / "workflows" / "reusable-build-and-sign.yml"
        ).read_text(encoding="utf-8")
    )
    readback = _provenance_step(reusable["jobs"]["build"], "Verify source checkout")
    assert 'test "$(git rev-parse HEAD)" = "$SOURCE_SHA"' in str(readback["run"])

    values = yaml.safe_load(
        (REPOSITORY_ROOT / "charts" / "university-ecosystem" / "values.yaml").read_text(
            encoding="utf-8"
        )
    )
    for component in (
        "backend",
        "frontend",
        "gateway",
        "fileProcessor",
        "outboxWorker",
    ):
        assert values[component]["image"]["digest"] == ""
    helpers = (
        REPOSITORY_ROOT
        / "charts"
        / "university-ecosystem"
        / "templates"
        / "_helpers.tpl"
    ).read_text(encoding="utf-8")
    assert 'define "university-ecosystem.image"' in helpers
    assert 'printf "%s/%s@%s"' in helpers


def test_nightly_chaos_database_is_explicitly_test_owned() -> None:
    workflow = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["load-and-chaos"]
    assert job["env"]["POSTGRES_DB"] == "test_ecosystem"
    assert str(job["env"]["DATABASE_URL"]).endswith("/test_ecosystem")

    prepare = _provenance_step(job, "Prepare full chaos compose environment")
    assert "localhost:54321/test_ecosystem" in str(prepare["run"])
    chaos = _provenance_step(job, "Run chaos and resilience tests")
    assert str(chaos["env"]["DATABASE_URL"]).endswith("/test_ecosystem")


def test_asan_pytest_disables_schemathesis_autoload_without_disabling_lsan() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "run_asan_tests.sh").read_text(
        encoding="utf-8"
    )
    invocation_start = script.index("  uv run pytest \\")
    invocation = script[invocation_start:].split("\n\n# echo", maxsplit=1)[0]
    environment = script[:invocation_start]

    assert "-p no:schemathesis" in invocation
    assert (
        'ASAN_OPTIONS="${ASAN_LOG_OPT}detect_leaks=1:detect_odr_violation=0:abort_on_error=1"'
        in environment
    )
    assert (
        'LSAN_OPTIONS="suppressions=${REPO_ROOT}/tests/lsan_suppressions.txt"'
        in environment
    )
    for smoke_test in (
        "tests/test_smoke_rust_audit.py",
        "tests/test_smoke_rust_partitions.py",
        "tests/test_property_based.py",
        "tests/test_smoke_pyo3_ext.py",
    ):
        assert smoke_test in invocation


def test_persistent_pytest_reset_jobs_use_explicit_narrow_opt_in() -> None:
    marker = "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"
    reusable = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert reusable["jobs"]["integration-tests"]["env"][marker] == "1"

    db_perf = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "db-perf-gate.yml").read_text(
            encoding="utf-8"
        )
    )
    pytest_step = _provenance_step(
        db_perf["jobs"]["explain-check"], "Run Pytest to capture query logs"
    )
    assert pytest_step["env"][marker] == "1"

    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    schemathesis = _provenance_step(
        nightly["jobs"]["schemathesis-api-tests-shard"],
        "Run Schemathesis conformance tests",
    )
    chaos = _provenance_step(nightly["jobs"]["chaos-tests"], "Run chaos tests")
    asan = _provenance_step(
        ci["jobs"]["rust-ffi-asan"], "Run FFI tests under ASan / LSan"
    )
    tsan = _provenance_step(ci["jobs"]["rust-ffi-tsan"], "Run FFI tests under TSan")
    assert schemathesis["env"][marker] == "1"
    assert schemathesis["env"]["REVOCATION_REDIS_URL"] == ("redis://localhost:6380/0")
    assert chaos["env"][marker] == "1"
    assert asan["env"][marker] == "1"
    assert tsan["env"][marker] == "1"

    nightly = yaml.safe_load(NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert nightly["jobs"]["container-integration-cells"]["env"][marker] == "1"
    nightly_chaos = _provenance_step(
        nightly["jobs"]["load-and-chaos"], "Run chaos and resilience tests"
    )
    assert nightly_chaos["env"][marker] == "1"

    assert CI_WORKFLOW_PATH.read_text(encoding="utf-8").count(marker) == 2
    assert NIGHTLY_FULL_WORKFLOW_PATH.read_text(encoding="utf-8").count(marker) == 5
    assert BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8").count(marker) == 1
    db_perf_path = REPOSITORY_ROOT / ".github" / "workflows" / "db-perf-gate.yml"
    assert db_perf_path.read_text(encoding="utf-8").count(marker) == 1

    contract_tests = REPOSITORY_ROOT / ".github" / "workflows" / "contract-tests.yml"
    assert marker not in contract_tests.read_text(encoding="utf-8")

    deploy = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
    assert marker not in deploy.read_text(encoding="utf-8")


def test_local_infra_sandbox_scopes_database_reset_opt_in_to_pytest() -> None:
    marker = "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"
    script = (REPOSITORY_ROOT / "scripts" / "run-test-sandbox.ps1").read_text(
        encoding="utf-8"
    )
    backend = script.split('Invoke-Step "Backend pytest + coverage"', maxsplit=1)[1]
    backend = backend.split('if ($Filter -in @("all", "rust"))', maxsplit=1)[0]
    assert "$previousDatabaseResetOptIn = $env:" + marker in backend
    assert "if ($useInfra)" in backend
    assert "$env:" + marker + ' = "1"' in backend
    assert "uv run pytest tests/" in backend
    assert "finally" in backend
    assert "Remove-Item Env:\\" + marker in backend
    assert "$env:" + marker + " = $previousDatabaseResetOptIn" in backend


def test_frontend_npm_installs_require_node_24_and_npm_11() -> None:
    workflow_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml"))
    )
    package = json.loads(
        (REPOSITORY_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    npmrc = (REPOSITORY_ROOT / "frontend" / ".npmrc").read_text(encoding="utf-8")

    assert 'node-version: "22"' not in workflow_sources
    assert 'default: "20"' not in workflow_sources
    assert 'default: "22"' not in workflow_sources
    assert package["engines"] == {"node": ">=24.0.0", "npm": ">=11.0.0"}
    assert package["packageManager"] == "npm@11.17.0"
    assert "engine-strict=true" in npmrc.splitlines()
    assert "strict-allow-scripts=true" in npmrc.splitlines()
