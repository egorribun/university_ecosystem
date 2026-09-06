"""Fail-closed contracts for active GitHub Actions workflows."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
PRE_COMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
LOCKED_PRE_COMMIT_VERSION = "4.6.0"

EXPECTED_EXTERNAL_IMAGES = {
    "pgvector/pgvector:pg17": (
        "pgvector/pgvector:pg17@sha256:"
        "cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"  # pragma: allowlist secret
    ),
    "redis:7-alpine": (
        "redis:7-alpine@sha256:"
        "e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"  # pragma: allowlist secret
    ),
    "nats:2.10.25-alpine": (
        "nats:2.10.25-alpine@sha256:"
        "3290c829aa05ddd4da12026783ccaff86f3fbc1f0551722908a934c293cd6228"  # pragma: allowlist secret
    ),
    "minio/minio:RELEASE.2025-09-07T16-13-09Z": (
        "minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:"
        "14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"  # pragma: allowlist secret
    ),
    "ghcr.io/shopify/toxiproxy:2.9.0": (
        "ghcr.io/shopify/toxiproxy:2.9.0@sha256:"
        "b44c283298cea49e2defaba1b3028783798346f2a926684e3a345fd8441af3b8"  # pragma: allowlist secret
    ),
    "semgrep/semgrep:1.113.0": (
        "semgrep/semgrep:1.113.0@sha256:"
        "136c094630123be54d7f832217fd0a217d148a8bfea08c7c366ce17f94cfdb22"  # pragma: allowlist secret
    ),
    "stoplight/spectral:6.15.0": (
        "stoplight/spectral:6.15.0@sha256:"
        "b3d5a530f83c4a72df69e682c5ac928bc9821b5ca3c42529e81d926c80fa50ab"  # pragma: allowlist secret
    ),
    "alpine/socat:1.8.0.3": (
        "alpine/socat:1.8.0.3@sha256:"
        "beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e"  # pragma: allowlist secret
    ),
    "postgres:15-alpine": (
        "postgres:15-alpine@sha256:"
        "fe0737ba566a2c5b2a28f34433c0a423261900ec17b9bf7ad115e1aae7e57f1b"  # pragma: allowlist secret
    ),
}

_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_SCRIPT_IMAGE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:"
    r"[a-z0-9.-]+(?:/[a-z0-9._-]+)+(?::[A-Za-z0-9._-]+)?"
    r"|(?:redis|nats|alpine|caddy|postgres|mysql|mongo|rabbitmq|ubuntu|debian|"
    r"node|python|golang|rust):[A-Za-z0-9._-]+"
    r")(?:@sha256:[0-9a-f]{64})?"
)
_DOCKER_RUN_OPTIONS_WITH_VALUE = {
    "--add-host",
    "--entrypoint",
    "--env",
    "--env-file",
    "--hostname",
    "--label",
    "--name",
    "--network",
    "--platform",
    "--publish",
    "--user",
    "--volume",
    "--workdir",
    "-e",
    "-h",
    "-l",
    "-p",
    "-u",
    "-v",
    "-w",
}


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _scalars(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _scalars(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _scalars(nested)


def _image_values(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"image", "container"} and isinstance(nested, str):
                yield nested
            yield from _image_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _image_values(nested)


def _docker_cli_images(script: str) -> Iterator[str]:
    flattened = script.replace("\\\n", " ")
    for match in re.finditer(r"\bdocker\s+(run|pull)\s+([^\n]+)", flattened):
        command, remainder = match.groups()
        tokens = shlex.split(remainder, comments=True, posix=True)
        if command == "pull":
            if tokens:
                yield tokens[0]
            continue

        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.startswith("-"):
                option = token.split("=", 1)[0]
                if "=" not in token and option in _DOCKER_RUN_OPTIONS_WITH_VALUE:
                    index += 2
                else:
                    index += 1
                continue
            yield token
            break


def _assert_pinned(ref: str, *, source: str) -> None:
    if "$" in ref:
        return
    assert _DIGEST.search(ref), f"unpinned static image {ref!r} in {source}"


def _configured_precommit_hook_ids() -> Counter[str]:
    """Return default-stage hook occurrences; identical ids may have variants."""

    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    hook_ids: Counter[str] = Counter()
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            stages = hook.get("stages")
            if stages == ["manual"]:
                continue
            hook_ids[hook["id"]] += 1
    return hook_ids


def _locked_pre_commit_version() -> str:
    """Read the exact runner version from the authoritative project lock."""

    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    versions = [
        package["version"]
        for package in lock["package"]
        if package["name"] == "pre-commit"
    ]
    assert versions == [LOCKED_PRE_COMMIT_VERSION]
    return versions[0]


def _workflow_precommit_hook_ids(job: dict[str, Any]) -> list[str]:
    """Extract explicit hook ids from the CI split without accepting all-files."""

    hook_ids: list[str] = []
    for step in job["steps"]:
        if "with" in step and "extra_args" in step["with"]:
            args = shlex.split(step["with"]["extra_args"])
            assert args and args[0] != "--all-files"
            hook_ids.append(args[0])
        if "run" in step:
            hook_ids.extend(
                re.findall(
                    r"(?:^|\n)\s*pre-commit run ([a-z0-9][a-z0-9-]*) --all-files",
                    step["run"],
                )
            )
    return hook_ids


def test_precommit_split_preserves_every_nonmanual_hook_and_fails_closed() -> None:
    workflow = _workflow(CI)
    jobs = workflow["jobs"]
    assert "pre-commit-autofix" not in jobs

    fast_job = jobs["pre-commit-check"]
    security_types_job = jobs["pre-commit-security-and-types"]
    for job in (fast_job, security_types_job):
        assert job["permissions"] == {"contents": "read"}
        assert "outputs" not in job
        assert "continue-on-error" not in job
        assert job["timeout-minutes"] == 15

    checkout = next(
        step
        for step in fast_job["steps"]
        if "actions/checkout@" in step.get("uses", "")
    )
    assert checkout["with"]["persist-credentials"] is False
    security_checkout = next(
        step
        for step in security_types_job["steps"]
        if "actions/checkout@" in step.get("uses", "")
    )
    assert security_checkout["with"]["persist-credentials"] is False

    assert "needs" not in security_types_job
    assert "if" not in security_types_job

    # The Docker-backed Semgrep hook remains a separate required security job.
    # All default-stage hooks other than it must be run exactly once by the
    # split. This prevents an accidental all-files fallback, duplicate work,
    # or a quiet drop of detect-secrets / mypy while allowing the fast subset
    # to unblock the rest of the CI graph.
    configured_hook_ids = _configured_precommit_hook_ids()
    expected_hook_ids = set(configured_hook_ids) - {"semgrep-docker"}
    actual_hook_ids = _workflow_precommit_hook_ids(fast_job) + (
        _workflow_precommit_hook_ids(security_types_job)
    )
    assert Counter(actual_hook_ids) == Counter(
        {hook_id: 1 for hook_id in expected_hook_ids}
    )

    # `pre-commit run ruff` selects every default-stage configuration with the
    # matching id. The config deliberately has two active Ruff variants, so
    # one selector is required and sufficient; adding a second selector would
    # run both variants twice.
    assert configured_hook_ids["ruff"] == 2
    assert actual_hook_ids.count("ruff") == 1

    # The pre-commit runner is an isolated, exact-pinned dependency group.  It
    # avoids synchronizing the complete application dev environment in each
    # lightweight job while still exporting every locked transitive wheel with
    # hashes.  Runtime verification makes a substituted executable fail closed
    # before any PR-controlled hook can execute.
    locked_pre_commit_version = _locked_pre_commit_version()
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert pyproject["dependency-groups"]["ci-precommit-runner"] == [
        f"pre-commit=={locked_pre_commit_version}"
    ]
    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    project_package = next(
        package
        for package in lock["package"]
        if package["name"] == "university-ecosystem"
    )
    assert project_package["dev-dependencies"]["ci-precommit-runner"] == [
        {"name": "pre-commit"}
    ]
    assert project_package["metadata"]["requires-dev"]["ci-precommit-runner"] == [
        {"name": "pre-commit", "specifier": f"=={locked_pre_commit_version}"}
    ]
    for job in (fast_job, security_types_job):
        assert any(
            step.get("uses", "").startswith("astral-sh/setup-uv@")
            for step in job["steps"]
        )
        installer = _step(job, "Install hash-verified pre-commit runner")
        install = installer["run"]
        assert "uv export --frozen" in install
        assert "--only-group ci-precommit-runner" in install
        assert "--no-emit-project" in install
        assert "--no-emit-workspace" in install
        assert "--format requirements-txt" in install
        assert '"$RUNNER_TEMP/ci-precommit.requirements.txt"' in install
        assert "--require-hashes" in install
        assert "--only-binary=:all:" in install
        assert "--no-deps" in install
        assert "--force-reinstall" in install
        assert '-r "$requirements_file"' in install
        assert "--no-hashes" not in install
        assert "tomllib.load" not in install
        assert '"pre-commit==$LOCKED_PRE_COMMIT_VERSION"' not in install
        assert (
            'test "$(pre-commit --version)" = '
            f'"pre-commit {locked_pre_commit_version}"' in install
        )

    security_hook = _step(security_types_job, "Run security and type pre-commit hooks")
    assert "detect-secrets" in security_hook["run"]
    assert "mypy" in security_hook["run"]
    assert "set -euo pipefail" in security_hook["run"]
    assert 'exit "$failed"' in security_hook["run"]
    # The two hooks are read-only with respect to the checkout (detect-secrets
    # only canonicalizes its baseline, while mypy writes an isolated cache),
    # so run them concurrently.  Keep explicit PID/wait handling so a failure
    # from either hook remains blocking instead of being lost in a background
    # shell process.
    assert (
        "pre-commit run detect-secrets --all-files --show-diff-on-failure &\n"
        in (security_hook["run"])
    )
    assert (
        "pre-commit run mypy --all-files --show-diff-on-failure &\n"
        in (security_hook["run"])
    )
    assert "detect_secrets_pid=$!" in security_hook["run"]
    assert "mypy_pid=$!" in security_hook["run"]
    assert 'wait "$detect_secrets_pid" || failed=1' in security_hook["run"]
    assert 'wait "$mypy_pid" || failed=1' in security_hook["run"]
    assert "continue-on-error" not in security_hook

    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    detect_secrets = next(
        hook
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook["id"] == "detect-secrets"
    )
    assert detect_secrets["entry"] == "python scripts/run_detect_secrets.py"
    assert detect_secrets["args"] == ["--baseline", ".secrets.baseline"]

    ci_success = jobs["ci-success"]
    assert "pre-commit-security-and-types" in ci_success["needs"]
    result_gate = _step(ci_success, "Check all jobs passed")["run"]
    assert (
        '"pre-commit-security-and-types|${{ needs.pre-commit-security-and-types.result }}"'
        in result_gate
    )


def test_semgrep_security_audit_starts_independently() -> None:
    workflow = _workflow(CI)
    jobs = workflow["jobs"]
    job = jobs["security-audit"]

    # The reusable security workflow contains the blocking, digest-pinned
    # Semgrep job. Removing this caller dependency lets that same job start
    # beside pre-commit, without introducing a duplicate scan or weakening
    # ci-success's existing security-audit requirement.
    assert "needs" not in job
    assert job["uses"] == "./.github/workflows/reusable-security-audit.yml"
    assert "security-audit" in jobs["ci-success"]["needs"]
    gate = jobs["ci-success"]["steps"][0]["run"]
    assert '"security-audit|${{ needs.security-audit.result }}"' in gate


def test_mutation_matrix_publishes_bounded_capacity_telemetry() -> None:
    """Keep the next allocation decision tied to fresh, observable evidence."""

    jobs = _workflow(CI)["jobs"]
    universe = jobs["mutation-tests-universe"]
    runners = jobs["mutation-tests-incremental"]
    stryker = jobs["stryker-shards"]

    assert universe["outputs"]["mutation_descriptor_count"] == (
        "${{ steps.mutation_matrix.outputs.descriptor_count }}"
    )
    matrix_step = _step(universe, "Build validated mutmut execution matrix")
    assert "descriptor_count=" in matrix_step["run"]
    assert '"$descriptor_count" -gt 64' in matrix_step["run"]
    assert "mutmut_shard_matrix.py groups" in matrix_step["run"]
    assert "--target-groups 64" in matrix_step["run"]
    assert "scripts/validate_mutmut_group_budgets.py" in matrix_step["run"]
    assert "--output-manifest /tmp/mutmut-group-budgets.json" in matrix_step["run"]
    assert "Preflight the exact execution budget" in matrix_step["run"]
    assert "--metadata-startup-reserve-seconds 120" in matrix_step["run"]
    assert "--max-timeout-seconds 20880" in matrix_step["run"]
    assert "21,600 - 630 - 90" in matrix_step["run"]
    assert "Mutation matrix capacity" in matrix_step["run"]
    assert (
        'if [ "${{ steps.mutation_scope.outputs.has_python }}" = "true" ]; then'
        in matrix_step["run"]
    )
    assert (
        'matrix_summary="Fully validated 128 logical assignments; up to 64 budget-validated physical groups"'
        in matrix_step["run"]
    )
    assert (
        'matrix_summary="No-Python sentinel: one explicit non-mutant descriptor '
        '(not a 128-assignment plan)"' in matrix_step["run"]
    )
    assert (
        'if [ "${{ steps.mutation_scope.outputs.has_python }}" = "false" ] '
        '&& [ "$descriptor_count" -ne 1 ]; then' in matrix_step["run"]
    )
    assert 'echo "- $matrix_summary"' in matrix_step["run"]
    assert 'echo "- $descriptor_summary"' in matrix_step["run"]
    assert "coverage phase barrier" in matrix_step["run"]
    assert 'echo "- Mutmut producer max concurrency: 12"' in matrix_step["run"]
    assert 'echo "- Stryker producer max concurrency: 8"' in matrix_step["run"]
    assert "global hosted-runner cap: 20" in matrix_step["run"]

    # After the coverage phase barrier, the two producer lanes consume the
    # complete repository-wide 20-runner budget (12 mutmut + 8 Stryker).
    for family, expected in ((runners, 12), (stryker, 8)):
        max_parallel = family["strategy"]["max-parallel"]
        assert isinstance(max_parallel, int)
        assert 1 <= max_parallel <= 20
        assert max_parallel == expected
    assert runners["strategy"]["matrix"] == (
        "${{ fromJSON(needs.mutation-tests-universe.outputs.mutation_matrix) }}"
    )


def test_precommit_cache_cannot_cross_into_privileged_workflows() -> None:
    """Cache only hook environments in unprivileged PR CI execution."""

    workflow = _workflow(CI)
    jobs = workflow["jobs"]
    cache_prefixes = ("pre-commit-fast-v2-", "pre-commit-security-types-v2-")

    ci_source = CI.read_text(encoding="utf-8")
    assert "pull_request_target:" not in ci_source
    assert "workflow_run:" not in ci_source

    for job_name, prefix in zip(
        ("pre-commit-check", "pre-commit-security-and-types"),
        cache_prefixes,
        strict=True,
    ):
        job = jobs[job_name]
        assert job["permissions"] == {"contents": "read"}
        # Hook definitions and local hook scripts are PR-controlled, so they
        # must not inherit the workflow-level CI test secret.
        assert job["env"] == {"SECRET_KEY": ""}
        cache_step = next(
            step
            for step in job["steps"]
            if step.get("with", {}).get("path") == "~/.cache/pre-commit"
        )
        assert cache_step["uses"].startswith("actions/cache@")
        assert cache_step["with"]["key"].startswith(prefix)
        assert (
            "hashFiles('.pre-commit-config.yaml', 'uv.lock')"
            in cache_step["with"]["key"]
        )
        assert "restore-keys" not in cache_step["with"]

    # GitHub scopes cache reads by branch (with default-branch fallback). Do
    # not let a future privileged workflow opt into either PR-cache namespace.
    for workflow_path in WORKFLOWS.glob("*.*ml"):
        if workflow_path == CI:
            continue
        source = workflow_path.read_text(encoding="utf-8")
        assert not any(prefix in source for prefix in cache_prefixes), workflow_path


def test_lighthouse_missing_artifact_fails_closed() -> None:
    job = _workflow(CI)["jobs"]["performance-gate"]
    selector = _step(job, "Select immutable same-run Lighthouse evidence candidate")
    download = _step(job, "Download selected Lighthouse results")
    enforce = _step(job, "Enforce Lighthouse thresholds")

    assert selector["id"] == "select_lighthouse_results"
    assert selector["env"] == {"GH_TOKEN": "${{ github.token }}"}
    selector_script = selector["run"]
    for invariant in (
        "set -euo pipefail",
        "scripts/quality/select_same_run_artifact_cli.py",
        '--artifact-prefix "lighthouse-reports-attempt-"',
        '--artifact-suffix ""',
        "--artifact-name-layout attempt",
        "--attempt-policy current-or-earlier",
    ):
        assert invariant in selector_script
    assert "if" not in download
    assert download["with"] == {
        "artifact-ids": "${{ steps.select_lighthouse_results.outputs.artifact_id }}",
        "repository": "${{ github.repository }}",
        "run-id": "${{ github.run_id }}",
        "github-token": "${{ github.token }}",
        "path": (
            "artifacts/lighthouse/candidates/"
            "${{ steps.select_lighthouse_results.outputs.artifact_name }}"
        ),
    }
    assert "continue-on-error" not in download
    assert "pattern" not in download["with"]
    lighthouse_runs = "\n".join(
        step.get("run", "") for step in job["steps"] if isinstance(step, dict)
    )
    assert "scripts/quality/select_lighthouse_artifacts_cli.py" in lighthouse_runs
    assert "--candidate-root" in lighthouse_runs
    assert "--destination-root" in lighthouse_runs
    enforce_if = enforce.get("if", "")
    assert enforce_if in ("", "always()") or "success()" in enforce_if


def test_helm_squawk_and_trivy_are_real_blocking_gates() -> None:
    jobs = _workflow(CI)["jobs"]

    helm = jobs["helm-validate"]
    dependency = _step(helm, "Helm dependency build")
    lint = _step(helm, "Helm lint — university-ecosystem chart")
    assert "continue-on-error" not in dependency
    assert "--strict" in lint["run"]
    assert "steps.helm-deps.outcome" not in lint["run"]

    squawk = _step(jobs["alembic-migrations"], "Lint Postgres Migrations (Squawk)")
    assert "set -euo pipefail" in squawk["run"]
    assert "squawk" in squawk["run"]
    assert "|| true" not in squawk["run"]

    trivy = jobs["docker-security-scan"]
    scan = _step(trivy, "Run Trivy vulnerability scanner")
    preserve = _step(trivy, "Preserve first Trivy scan evidence")
    retry = _step(
        trivy, "Retry Trivy vulnerability scanner after registry transient failure"
    )
    upload = _step(trivy, "Upload Trivy results to GitHub Security tab")
    reassert = _step(trivy, "Re-assert Trivy vulnerability gate")
    assert scan["with"]["exit-code"] == "1"
    assert scan["continue-on-error"] is True
    assert upload["continue-on-error"] is True
    assert upload["if"].startswith("always()")
    assert "hashFiles('trivy-results.sarif') != ''" in upload["if"]
    assert "steps.trivy_scan.outcome == 'failure'" in preserve["if"]
    assert "steps.trivy_scan.outcome == 'failure'" in retry["if"]
    assert reassert["if"] == "always()"
    assert "FIRST_OUTCOME" in reassert["env"]
    assert "RETRY_OUTCOME" in reassert["env"]
    assert "trivy-results-first.sarif" in reassert["run"]
    assert "jq -e" in reassert["run"]
    assert "exit 1" in reassert["run"]

    heads = _step(jobs["alembic-migrations"], "Check single migration head (MOD-22-05)")
    assert "set -euo pipefail" in heads["run"]
    assert "uv run alembic heads" in heads["run"]
    assert "|| true" not in heads["run"]


def test_python_coverage_scope_and_migration_gate_are_explicit() -> None:
    """Keep migration safety evidence separate from pytest-cov inventory.

    ``source_roots.python`` intentionally includes Alembic revisions so report
    identities stay canonical.  The backend producer measures only ``app``;
    the PostgreSQL migration job therefore remains the structural/round-trip
    gate for revisions instead of relying on a hidden normalizer exception.
    """
    contract = json.loads(
        (ROOT / "quality" / "quality-contract.json").read_text(encoding="utf-8")
    )
    assert contract["source_roots"]["python"] == ["app", "alembic/versions"]
    assert contract["coverage_scope"]["python"] == ["app"]

    workflow = _workflow(CI)
    migration_job = workflow["jobs"]["alembic-migrations"]
    migration_runs = "\n".join(
        step.get("run", "") for step in migration_job["steps"] if isinstance(step, dict)
    )
    assert "uv run alembic" in migration_runs
    assert "upgrade head" in migration_runs
    assert "downgrade" in migration_runs

    reusable = _workflow(WORKFLOWS / "reusable-backend-tests.yml")
    pytest_runs = "\n".join(
        step.get("run", "")
        for step in reusable["jobs"]["unit-tests"]["steps"]
        if isinstance(step, dict)
    )
    assert "--cov=app" in pytest_runs
    assert "--cov=alembic/versions" not in pytest_runs


def test_backend_duration_refresh_cannot_mask_a_failed_pytest_collection() -> None:
    reusable = _workflow(WORKFLOWS / "reusable-backend-tests.yml")
    duration_step = _step(
        reusable["jobs"]["unit-tests"], "Update historical test durations"
    )

    # A collection/import error may still produce an incomplete JUnit XML file.
    # Duration history is advisory and must run only after pytest succeeds so a
    # parser error cannot obscure the primary test failure.
    assert duration_step["if"] == "success() && hashFiles('pytest-report.xml') != ''"


def test_spectral_upload_is_optional_but_enforcement_is_not() -> None:
    job = _workflow(WORKFLOWS / "contract-validation.yml")["jobs"]["spectral-lint"]
    report = _step(job, "Run Spectral lint")
    upload = _step(job, "Upload SARIF to GitHub Code Scanning")
    enforce = _step(job, "Fail if errors found")

    assert report["continue-on-error"] is True
    assert upload["continue-on-error"] is True
    assert upload["if"] == "always()"
    assert "continue-on-error" not in enforce
    assert enforce["if"] == "always()"
    assert "--fail-severity error" in enforce["run"]
    assert job["steps"].index(upload) < job["steps"].index(enforce)


def test_visual_audit_reasserts_after_best_effort_evidence() -> None:
    job = _workflow(WORKFLOWS / "visual-audit.yml")["jobs"]["visual-audit"]
    audit = _step(job, "Run visual audit script")
    upload = _step(job, "Upload audit reports")
    reassert = _step(job, "Re-assert visual audit result")

    assert audit["id"] == "visual_audit"
    assert audit["continue-on-error"] is True
    assert job["steps"].index(audit) < job["steps"].index(upload)
    assert job["steps"].index(upload) < job["steps"].index(reassert)
    assert "steps.visual_audit.outcome == 'failure'" in reassert["if"]
    assert "exit 1" in reassert["run"]


def test_scheduled_workflows_reject_missing_required_inputs() -> None:
    quality = _workflow(WORKFLOWS / "quality-history.yml")["jobs"]["archive"]
    collect = _step(quality, "Collect latest successful CI quality manifest")["run"]
    for message in (
        "No successful main CI run is available",
        "has no downloadable quality-manifest",
        "quality-manifest.json is missing",
    ):
        start = collect.index(message)
        end = collect.index("exit 1", start)
        assert "exit 0" not in collect[start:end]

    weekly_workflow = _workflow(WORKFLOWS / "weekly-cleanup.yml")
    cleanup = weekly_workflow["jobs"]["cleanup"]
    assert weekly_workflow["concurrency"] == {
        "group": "weekly-cleanup",
        "cancel-in-progress": False,
    }
    missing = _step(cleanup, "Fail when required cleanup configuration is missing")
    assert "::error::" in missing["run"]
    assert "exit 1" in missing["run"]


def test_go_mutation_diagnostic_never_converts_tool_failure_to_success() -> None:
    job = _workflow(WORKFLOWS / "reusable-go-tests.yml")["jobs"]["mutation-diagnostic"]
    mutation = _step(job, "Run bounded Go mutation diagnostic")["run"]

    assert "set -euo pipefail" in mutation
    assert 'git fetch origin "$BASE_REF_NAME" --depth=1 || true' not in mutation
    assert (
        'CHANGED_PATHS="$(git diff --diff-filter=ACMRT --name-only '
        '"$BASE_REF"...HEAD)"' in mutation
    )
    assert 'git diff --name-only "$BASE_REF"...HEAD' not in mutation
    assert 'if [ ! -f "$target" ] || [ -L "$target" ]; then' in mutation
    assert "Mutation target is not a regular checked-out source file" in mutation
    assert "Unable to resolve mutation diagnostic base revision" in mutation
    assert "No changed Go source files found" in mutation
    assert 'local isolated_root="$MUTATION_ROOT/$safe_target/repository"' in mutation
    assert 'local workdir="$isolated_root/$SERVICE_DIRECTORY"' in mutation
    assert 'cp -a "$GITHUB_WORKSPACE/$SERVICE_DIRECTORY/." "$workdir/"' in mutation
    assert (
        "for dependency in services/pkg/logging services/pkg/spiffe gen/go; do"
        in mutation
    )
    assert 'local dependency_source="$GITHUB_WORKSPACE/$dependency"' in mutation
    assert 'local dependency_destination="$isolated_root/$dependency"' in mutation
    assert (
        'if [ ! -d "$dependency_source" ] || [ -L "$dependency_source" ]; then'
        in mutation
    )
    assert 'cp -a "$dependency_source/." "$dependency_destination/"' in mutation
    assert 'cd "$workdir"' in mutation
    assert "treating this known tool panic as advisory" not in mutation
    assert 'pipeline_status=("${PIPESTATUS[@]}")' in mutation
    assert "Unable to persist go-mutesting output" in mutation


def test_go_coverage_retry_is_bounded_and_remains_fail_closed() -> None:
    """A transient profile miss may be retried once without weakening the gate."""

    job = _workflow(WORKFLOWS / "reusable-go-tests.yml")["jobs"]["test"]
    coverage_step = _step(job, "Check coverage threshold")["run"]

    assert "set -euo pipefail" in coverage_step
    assert 'THRESHOLD="$COVERAGE_THRESHOLD"' in coverage_step
    assert 'grep -vE "\\.pb\\.go|_mock\\.go|mock_|/gen/go"' in coverage_step
    assert "go tool cover -func=coverage.out" in coverage_step
    assert "Coverage rows below 100%" in coverage_step
    assert "printing diagnostics and retrying once" in coverage_step
    retry_command = "go test -v -race -count=1 -coverprofile=coverage.out ./..."
    assert coverage_step.count(retry_command) == 1
    assert "bounded retry exhausted" in coverage_step
    # The comparison is captured explicitly so tool errors cannot be treated
    # as the valid "not below" result.
    assert 'is_below_threshold "$COVERAGE"' in coverage_step
    assert 'case "$comparison_status" in' in coverage_step
    assert "exit 1" in coverage_step
    # The retry replaces the profile and independently rechecks the same
    # threshold; no exclusion, `continue-on-error`, or unconditional success
    # path may be introduced.
    assert "coverage.out coverage.filtered.out" in coverage_step
    assert "continue-on-error" not in coverage_step
    assert "exit 0" not in coverage_step
    assert "COVERAGE_THRESHOLD=" not in coverage_step


def test_go_coverage_threshold_comparison_errors_fail_closed() -> None:
    """Malformed coverage arithmetic must fail, never look like a pass."""

    job = _workflow(WORKFLOWS / "reusable-go-tests.yml")["jobs"]["test"]
    coverage_step = _step(job, "Check coverage threshold")["run"]

    for invariant in (
        "validate_percentage()",
        "command -v bc >/dev/null 2>&1",
        'if ! [[ "$value" =~',
        'validate_percentage "$THRESHOLD" "threshold"',
        'comparison_result="$(',
        "printf '%s < %s\\n'",
        "comparison_status=$?",
        "retry_comparison_status=$?",
        'case "$comparison_status" in',
        'case "$retry_comparison_status" in',
        'echo "::error::Coverage threshold comparison failed."',
    ):
        assert invariant in coverage_step

    # A valid false result (status 1) means "not below"; all other non-zero
    # statuses are comparison/tool errors and must terminate the gate.
    assert "1)\n    ;;" in coverage_step
    assert "2)" in coverage_step
    assert 'echo "::error::Coverage threshold comparison failed."' in coverage_step
    assert "exit 1" in coverage_step


def test_mutation_scope_diff_failures_cannot_look_like_empty_changes() -> None:
    workflows = (
        _workflow(CI),
        _workflow(WORKFLOWS / "manual-mutation-evidence.yml"),
    )
    scope_scripts = [
        step["run"]
        for workflow in workflows
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name")
        in {
            "Detect changed Python source",
            "Resolve changed Python scope",
            "Resolve manual mutation comparison base",
        }
    ]

    assert len(scope_scripts) == 6
    for script in scope_scripts:
        assert "git diff --name-only" in script
        assert 'git diff --name-only "$COMPARE_BASE...HEAD" | grep' not in script
        assert "grep -E '^app/.*\\.py$'" in script


def test_k6_job_does_not_fake_connectivity_to_an_absent_target() -> None:
    job = _workflow(CI)["jobs"]["ws-stress-test"]
    scripts = "\n".join(step.get("run", "") for step in job["steps"])

    assert job["name"] == "WebSocket 10k Scenario Validation (advisory)"
    assert "k6 inspect" in scripts
    assert "k6 run" not in scripts
    assert not any(step.get("continue-on-error") for step in job["steps"])


def test_ci_success_only_allows_skips_for_explicit_event_guards() -> None:
    job = _workflow(CI)["jobs"]["ci-success"]
    check_step = _step(job, "Check all jobs passed")
    gate = check_step["run"]

    assert check_step["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "EVENT_REF": "${{ github.ref }}",
        "PRE_COMMIT_RESULT": "${{ needs.pre-commit-check.result }}",
        "PRE_COMMIT_SECURITY_RESULT": "${{ needs.pre-commit-security-and-types.result }}",
        "FRONTEND_TESTS_RESULT": "${{ needs.frontend-tests.result }}",
        "BACKEND_TESTS_RESULT": "${{ needs.backend-tests.result }}",
        "GO_TESTS_RESULT": "${{ needs.go-tests.result }}",
        "RUST_TESTS_RESULT": "${{ needs.rust-tests.result }}",
        "BACKEND_TYPE_CHECK_RESULT": "${{ needs.backend-type-check.result }}",
        "MUTATION_SCOPE_RESULT": "${{ needs.mutation-scope.result }}",
        "COVERAGE_RESULT": "${{ needs.coverage-policy-gate.result }}",
    }
    assert "required_results=(" in gate
    assert 'if [[ "$result" != "$expected_result" ]]' in gate
    assert 'if [[ "$job" == mutation-tests-* ]]; then' in gate
    assert 'if [[ "$job" == "coverage-policy-gate" ]]; then' in gate
    assert 'expected_result="$coverage_expected_result"' in gate
    assert '"coverage-policy-gate|$COVERAGE_RESULT"' in gate
    assert "mutation_expected_result=skipped" in gate
    assert '"$res" != "success" && "$res" != "skipped"' not in gate
    assert "stryker-preflight" in job["needs"]
    assert (
        'if [[ "$PRE_COMMIT_RESULT" == "success" && '
        '"$FRONTEND_TESTS_RESULT" == "success" && '
        '"$COVERAGE_RESULT" == "success" ]]; then' in gate
    )
    assert (
        'elif [[ "$PRE_COMMIT_RESULT" == "success" && '
        '"$FRONTEND_TESTS_RESULT" == "success" && '
        '"${{ needs.stryker-preflight.result }}" == "success" && '
        '"$COVERAGE_RESULT" != "success" ]]; then' in gate
    )
    assert (
        'assert_event_result "stryker-preflight" '
        '"${{ needs.stryker-preflight.result }}" "success"' in gate
    )
    for mutation_job in (
        "stryker-preflight",
        "stryker-aggregate",
        "stryker-evidence-roundtrip",
        "frontend-mutation-required-context",
    ):
        assert (
            f'assert_event_result "{mutation_job}" '
            f'"${{{{ needs.{mutation_job}.result }}}}" "success"' in gate
        )
        assert (
            f'assert_event_result "{mutation_job}" '
            f'"${{{{ needs.{mutation_job}.result }}}}" "skipped"' in gate
        )
    assert 'assert_event_result "codecov-upload"' in gate
    assert '"sbom-generate|${{ needs.sbom-generate.result }}"' in gate
    for advisory in (
        "e2e-tests-cross-browser",
        "chaos-tests",
        "db-migration-integrity",
    ):
        assert f'"{advisory}|${{{{ needs.{advisory}.result }}}}"' not in gate


def test_ci_success_allows_coverage_skip_only_after_producer_failure() -> None:
    """A dependency skip is expected only for a failed coverage producer.

    The aggregate coverage job is dependency-gated, so a backend/frontend/Go/
    Rust failure naturally makes it ``skipped``.  The finalizer must model that
    narrow, known state while rejecting a skipped gate when all producers are
    green (or when a producer was cancelled unexpectedly).
    """

    job = _workflow(CI)["jobs"]["ci-success"]
    gate = _step(job, "Check all jobs passed")["run"]

    assert "coverage_expected_result=success" in gate
    assert "for prerequisite in" in gate
    for prerequisite in (
        '"$BACKEND_TESTS_RESULT"',
        '"$FRONTEND_TESTS_RESULT"',
        '"$GO_TESTS_RESULT"',
        '"$RUST_TESTS_RESULT"',
    ):
        assert prerequisite in gate
    assert '"$RUST_TESTS_RESULT"; do' in gate
    assert (
        'if [[ "$prerequisite" == "failure" || "$prerequisite" == "skipped" ]]; then'
        in gate
    )
    assert "coverage_expected_result=skipped" in gate
    assert 'expected_result="$coverage_expected_result"' in gate
    assert '"coverage-policy-gate|$COVERAGE_RESULT"' in gate

    # The special case must not turn an arbitrary skipped result into success:
    # only the explicit producer states above may select ``skipped``.
    assert 'if [[ "$prerequisite" == "cancelled"' not in gate


def test_stryker_preflight_candidates_are_retry_safe_and_fail_closed() -> None:
    jobs = _workflow(CI)["jobs"]
    producer = jobs["stryker-preflight"]
    upload = _step(producer, "Upload immutable Stryker preflight")
    assert upload["with"]["name"] == (
        "frontend-mutation-preflight-${{ github.run_id }}-"
        "${{ github.run_attempt }}-${{ github.sha }}"
    )
    # GitHub permits rerunning failed jobs for up to 30 days.  The immutable
    # producer must outlive that window or a later partial retry cannot reuse
    # already-validated preflight evidence and fails before it can make
    # progress.
    assert upload["with"]["retention-days"] == 30

    for job_name in ("stryker-preflight", "stryker-shards", "stryker-aggregate"):
        checkout = _step(jobs[job_name], "Checkout")
        assert checkout["with"]["persist-credentials"] is False
        node_setup = _step(jobs[job_name], "Setup Node.js")
        assert node_setup["with"]["node-version"] == "24.15.0"

    producer_selector = _step(
        producer, "Select immutable same-run historical Stryker cost candidate"
    )
    assert producer_selector["env"] == {"GH_TOKEN": "${{ github.token }}"}
    for job_name in ("stryker-shards", "stryker-aggregate"):
        job = jobs[job_name]
        selector = _step(job, "Select immutable same-run Stryker preflight candidate")
        assert selector["id"] == "select_stryker_preflight"
        assert selector["env"] == {"GH_TOKEN": "${{ github.token }}"}
        assert "scripts/quality/select_same_run_artifact_cli.py" in selector["run"]
        assert '--artifact-prefix "frontend-mutation-preflight-"' in selector["run"]
        download = _step(job, "Download selected Stryker preflight candidate")
        assert download["with"] == {
            "artifact-ids": "${{ steps.select_stryker_preflight.outputs.artifact_id }}",
            "repository": "${{ github.repository }}",
            "run-id": "${{ github.run_id }}",
            "github-token": "${{ github.token }}",
            "path": (
                "frontend/reports/mutation/preflight-candidates/"
                "${{ steps.select_stryker_preflight.outputs.artifact_name }}"
            ),
        }
        assert "pattern" not in download["with"]

    aggregate_shards = _step(
        jobs["stryker-aggregate"], "Download all same-run Stryker shard candidates"
    )
    assert aggregate_shards["with"] == {
        "pattern": "frontend-mutation-shard-${{ github.run_id }}-*",
        "path": "frontend/reports/mutation/external",
        "merge-multiple": False,
    }
    assert "name" not in aggregate_shards["with"]

    roundtrip = jobs["stryker-evidence-roundtrip"]
    assert _step(roundtrip, "Checkout")["with"]["persist-credentials"] is False
    assert _step(roundtrip, "Setup Node.js")["with"]["node-version"] == "24.15.0"
    assert roundtrip["env"] == {
        "STRYKER_VALIDATED_CANDIDATE_ROOT": "reports/mutation/validated-candidates",
        "STRYKER_SOURCE_HEAD_SHA": "${{ github.event.pull_request.head.sha || github.sha }}",
        "STRYKER_BASE_SHA": "${{ github.event.pull_request.base.sha || github.sha }}",
        "STRYKER_BASE_REF": "${{ github.event.pull_request.base.ref || github.ref_name }}",
    }
    roundtrip_selector = _step(
        roundtrip, "Select immutable same-run validated Stryker evidence candidate"
    )
    assert roundtrip_selector["id"] == "select_stryker_validated"
    assert roundtrip_selector["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert (
        "scripts/quality/select_same_run_artifact_cli.py" in roundtrip_selector["run"]
    )
    roundtrip_download = _step(
        roundtrip, "Download selected immutable Stryker evidence candidate"
    )
    assert roundtrip_download["with"] == {
        "artifact-ids": "${{ steps.select_stryker_validated.outputs.artifact_id }}",
        "repository": "${{ github.repository }}",
        "run-id": "${{ github.run_id }}",
        "github-token": "${{ github.token }}",
        "path": (
            "frontend/reports/mutation/validated-candidates/"
            "${{ steps.select_stryker_validated.outputs.artifact_name }}"
        ),
    }
    assert "pattern" not in roundtrip_download["with"]


def test_download_artifact_uses_only_supported_fail_closed_inputs() -> None:
    """The v8 action has no ``if-no-artifact-found`` input.

    Missing-artifact handling belongs to an explicit selector or shell guard;
    passing an unknown action input merely emits a warning and silently weakens
    the transport contract.  Keep this invariant repository-wide so a new
    workflow cannot reintroduce the typo.
    """

    for workflow_path in sorted(WORKFLOWS.glob("*.*ml")):
        workflow = _workflow(workflow_path)
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if not isinstance(uses, str) or not uses.startswith(
                    "actions/download-artifact@"
                ):
                    continue
                with_values = step.get("with", {})
                assert "if-no-artifact-found" not in with_values, (
                    f"{workflow_path.name}:{job_name}:{step.get('name', '<unnamed>')}"
                )


def test_critical_pattern_downloads_have_explicit_payload_guards() -> None:
    """Multi-artifact cohorts remain globs but verify transport before use."""

    workflow = _workflow(CI)
    for job_name, download_name in (
        ("mutation-tests-universe", "Download same-run mutmut stats candidates"),
        ("stryker-aggregate", "Download all same-run Stryker shard candidates"),
    ):
        job = workflow["jobs"][job_name]
        download = _step(job, download_name)
        assert "pattern" in download["with"]
        start = job["steps"].index(download) + 1
        following_runs = "\n".join(
            step.get("run", "")
            for step in job["steps"][start:]
            if isinstance(step, dict)
        )
        assert "find " in following_runs or "test -d" in following_runs
        assert "-type d" in following_runs or "expected=" in following_runs


def test_ci_success_does_not_enqueue_a_finalizer_after_run_cancellation() -> None:
    """Superseded PR runs must release the workflow concurrency group promptly."""

    job = _workflow(CI)["jobs"]["ci-success"]
    assert job["if"] == "${{ always() && !cancelled() }}"


def test_sonar_optionality_is_explicit_and_isolated() -> None:
    path = WORKFLOWS / "sonar.yml"
    text = path.read_text(encoding="utf-8")
    job = _workflow(path)["jobs"]["sonarcloud"]
    scan = _step(job, "SonarScan")

    assert "Advisory external analysis" in text
    assert "not a protected" in text
    assert scan["continue-on-error"] is True


def test_literal_continue_on_error_cases_are_exhaustively_classified() -> None:
    expected_steps = {
        ("admin-smoke-monitoring.yml", "admin-smoke", "Run admin smoke script"),
        ("ci.yml", "docker-security-scan", "Run Trivy vulnerability scanner"),
        (
            "ci.yml",
            "docker-security-scan",
            "Retry Trivy vulnerability scanner after registry transient failure",
        ),
        (
            "ci.yml",
            "docker-security-scan",
            "Upload Trivy results to GitHub Security tab",
        ),
        ("contract-validation.yml", "spectral-lint", "Run Spectral lint"),
        (
            "contract-validation.yml",
            "spectral-lint",
            "Upload SARIF to GitHub Code Scanning",
        ),
        (
            "reusable-e2e-tests.yml",
            "e2e",
            "Upload E2E coverage artifact",
        ),
        (
            "reusable-e2e-tests.yml",
            "e2e",
            "Upload Playwright report",
        ),
        (
            "quality-promotion-check.yml",
            "stabilization-window",
            "Evaluate stabilization window",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy vulnerability scanner (filesystem)",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy configuration scanner (IaC)",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy revocation-store configuration scanner",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy filesystem scan results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy config scan results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy revocation-store results",
        ),
        ("sonar.yml", "sonarcloud", "SonarScan"),
        ("visual-audit.yml", "visual-audit", "Run visual audit script"),
        (
            "unauthenticated-routes-smoke.yml",
            "unauthed-smoke",
            "Run unauthenticated routes smoke script",
        ),
    }
    observed_steps: set[tuple[str, str, str]] = set()
    observed_jobs: set[tuple[str, str, str]] = set()

    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job_name, job in _workflow(path)["jobs"].items():
            job_policy = job.get("continue-on-error")
            if job_policy:
                observed_jobs.add((path.name, job_name, str(job_policy)))
            for step in job.get("steps", []):
                if step.get("continue-on-error") is True:
                    observed_steps.add((path.name, job_name, step["name"]))

    assert observed_steps == expected_steps
    assert observed_jobs == {
        ("reusable-e2e-tests.yml", "e2e", "${{ inputs.advisory }}"),
        ("reusable-go-tests.yml", "mutation-diagnostic", "True"),
    }


def test_all_static_external_workflow_images_are_digest_pinned() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _workflow(path)
        source = path.relative_to(ROOT).as_posix()

        for image in _image_values(workflow):
            _assert_pinned(image, source=source)

        for scalar in _scalars(workflow):
            for image in _docker_cli_images(scalar):
                _assert_pinned(image, source=source)
            if "docker pull" in scalar:
                for quoted in re.findall(r'["\']([^"\']+)["\']', scalar):
                    if _SCRIPT_IMAGE.fullmatch(quoted):
                        _assert_pinned(quoted, source=source)


def test_external_workflow_images_use_the_audited_digests() -> None:
    scalars = [
        scalar
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for scalar in _scalars(_workflow(path))
    ]
    combined = "\n".join(scalars)

    for tag, pinned in EXPECTED_EXTERNAL_IMAGES.items():
        assert pinned in combined, f"expected pinned workflow image {pinned}"
        assert not re.search(rf"{re.escape(tag)}(?!@sha256:)", combined)


def test_active_workflows_pin_linux_runner_version() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        assert "ubuntu-latest" not in text, (
            f"{path.relative_to(ROOT).as_posix()} must pin ubuntu-24.04"
        )


def test_deployment_workflows_cannot_report_mock_success() -> None:
    assert not (WORKFLOWS / "preview-env.yml").exists()

    path = WORKFLOWS / "deploy.yml"
    text = path.read_text(encoding="utf-8")
    workflow = _workflow(path)
    deploy = workflow["jobs"]["deploy"]
    steps = deploy["steps"]

    assert workflow["name"] == "Deploy (Helm / Kubernetes)"
    assert deploy["environment"]["url"] == "${{ vars.DEPLOYMENT_URL }}"
    assert "placeholder" not in text.lower()
    assert "mocking kubernetes" not in text.lower()
    assert "deployed successfully" not in text.lower()
    assert "example.com" not in text
    assert not re.search(r"(?m)^\s*#\s*(?:helm|kubectl)\b", text)
    assert not any(name.startswith("build-") for name in workflow["jobs"])
    resolve = workflow["jobs"]["resolve-images"]
    resolve_text = "\n".join(str(step.get("run", "")) for step in resolve["steps"])
    assert ".github/workflows/build-release-images.yml" in resolve_text
    assert "verify_release_image_manifest.py" in resolve_text
    assert (
        "release-image-provenance-$RELEASE_SHA-attempt-$BUILD_RUN_ATTEMPT"
        in resolve_text
    )

    validate = _step(deploy, "Validate deployment contract")["run"]
    for setting in (
        "OIDC_DEPLOY_ROLE_ARN",
        "AWS_REGION",
        "EKS_CLUSTER_NAME",
        "K8S_NAMESPACE",
        "HELM_RELEASE_NAME",
        "HELM_VALUES_FILE",
        "CONNECTIONS_SECRET_NAME",
        "APPLICATION_SECRETS_NAME",
        "DEPLOYMENT_URL",
        "GATEWAY_HEALTH_URL",
        "WS_HUB_HEALTH_URL",
        "BACKEND_HEALTH_URL",
        "FRONTEND_HEALTH_URL",
    ):
        assert setting in validate
    assert "Required deployment setting" in validate
    assert "^sha256:[0-9a-f]{64}$" in validate
    assert "must resolve inside the checked-out repository" in validate

    cluster = _step(deploy, "Configure and verify cluster access")["run"]
    assert "aws eks update-kubeconfig" in cluster
    assert "kubectl cluster-info" in cluster

    helm = _step(deploy, "Deploy Helm release atomically")["run"]
    assert "bash .github/scripts/deploy-helm.sh upgrade" in helm
    helm_script = (WORKFLOWS.parent / "scripts" / "deploy-helm.sh").read_text(
        encoding="utf-8"
    )
    assert "helm upgrade --install" in helm_script
    for flag in ("--atomic", "--wait", "--wait-for-jobs"):
        assert flag in helm_script

    assert not any(step.get("name") == "Deploy WS Hub image" for step in steps)

    capture = _step(deploy, "Capture rollback state")
    rollback = _step(deploy, "Roll back a deployment that failed verification")
    assert capture["id"] == "rollback_state"
    assert "helm list" in capture["run"]
    assert "ws_hub_image=" not in capture["run"]
    assert "failure()" in rollback["if"]
    assert "helm rollback" in rollback["run"]
    assert "helm uninstall" in rollback["run"]
    assert "PREVIOUS_WS_HUB_IMAGE" not in rollback["run"]
    assert "kubectl set image" not in rollback["run"]

    smoke = _step(deploy, "Post-deployment smoke test")
    assert smoke["env"] == {
        "GATEWAY_URL": "${{ vars.GATEWAY_HEALTH_URL }}",
        "WS_HUB_URL": "${{ vars.WS_HUB_HEALTH_URL }}",
        "BACKEND_URL": "${{ vars.BACKEND_HEALTH_URL }}",
        "FRONTEND_URL": "${{ vars.FRONTEND_HEALTH_URL }}",
    }
    kyverno = _step(deploy, "Verify Kyverno policy compliance (MOD-14-02)")
    kyverno_script = kyverno["run"]
    assert "validatingpolicies.policies.kyverno.io" in kyverno_script
    assert "clusterpolicies.kyverno.io" not in kyverno_script
    assert ".status.conditionStatus.ready == true" in kyverno_script
    assert 'index("Deny") != null' in kyverno_script
    assert 'index("Audit") != null' in kyverno_script
    assert "validationFailureAction" not in kyverno_script
    dora = _step(deploy, "Record DORA Lead Time for Changes")
    assert steps.index(smoke) < steps.index(kyverno) < steps.index(rollback)
    assert steps.index(rollback) < steps.index(dora)


def test_sbom_osv_reporting_does_not_hide_scanner_failures() -> None:
    job = _workflow(WORKFLOWS / "sbom.yml")["jobs"]["sbom-go"]
    scan = _step(job, "Scan Go modules for vulnerabilities + generate SBOM")
    validate = _step(job, "Validate OSV scanner result")

    assert scan["id"] == "osv_scan"
    assert "|| true" not in scan["run"]
    assert "scanner_status=$?" in scan["run"]
    assert "scanner_status=$scanner_status" in scan["run"]
    assert validate["if"] == "always()"
    assert validate["env"]["SCANNER_STATUS"] == (
        "${{ steps.osv_scan.outputs.scanner_status }}"
    )
    assert '"$SCANNER_STATUS" -gt 1' in validate["run"]
    assert "structurally valid SARIF" in validate["run"]
    assert '"$SCANNER_STATUS" -eq 1 && "$finding_count" -eq 0' in validate["run"]


def test_reusable_trivy_scans_upload_evidence_then_fail_closed() -> None:
    job = _workflow(WORKFLOWS / "reusable-security-audit.yml")["jobs"][
        "docker-security"
    ]
    filesystem = _step(job, "Run Trivy vulnerability scanner (filesystem)")
    configuration = _step(job, "Run Trivy configuration scanner (IaC)")
    revocation = _step(job, "Run Trivy revocation-store configuration scanner")
    reassert = _step(job, "Re-assert Trivy filesystem and configuration gates")

    for scan, scan_id in (
        (filesystem, "trivy_fs"),
        (configuration, "trivy_config"),
        (revocation, "trivy_revocation"),
    ):
        assert scan["id"] == scan_id
        assert scan["continue-on-error"] is True
        assert scan["with"]["exit-code"] == "1"
    assert reassert["if"] == "always()"
    assert reassert["env"] == {
        "FILESYSTEM_OUTCOME": "${{ steps.trivy_fs.outcome }}",
        "CONFIGURATION_OUTCOME": "${{ steps.trivy_config.outcome }}",
        "REVOCATION_OUTCOME": "${{ steps.trivy_revocation.outcome }}",
    }
    assert 'exit "$failed"' in reassert["run"]


def test_workflow_tool_installers_do_not_use_latest_selectors() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))
    )
    assert not re.search(r"\bgo install\s+\S+@(?:latest|main|master)\b", combined)
    assert "go.uber.org/nilaway/cmd/nilaway@v0.0.0-20260808063849-8649a03c818a" in (
        WORKFLOWS / "nilaway.yml"
    ).read_text(encoding="utf-8")
    assert "uv pip install atheris" not in combined


def test_dependency_review_does_not_upload_a_report_it_never_creates() -> None:
    text = (WORKFLOWS / "dependency-review.yml").read_text(encoding="utf-8")
    assert "dependency-review-report.json" not in text


def test_schemathesis_operation_shards_preserve_depth_and_fail_closed_aggregate() -> (
    None
):
    workflow = _workflow(CI)
    shard_job = workflow["jobs"]["schemathesis-api-tests-shard"]
    matrix = shard_job["strategy"]["matrix"]["shard"]

    # Every operation remains covered with the same 25 examples; only the
    # process fan-out changes so each TestClient/lifespan-heavy shard is
    # smaller.  Keep the matrix explicit so a missing logical shard cannot be
    # hidden behind a dynamic expression.
    assert matrix == list(range(8))
    assert shard_job["name"] == (
        "Schemathesis - API Schema Conformance / shard ${{ matrix.shard }}/8"
    )
    run = _step(shard_job, "Run Schemathesis conformance tests")
    assert run["env"] == {
        "DATABASE_URL": "sqlite+aiosqlite:///./test_schemathesis.db",
        "ENVIRONMENT": "testing",
        "REVOCATION_REDIS_URL": "redis://localhost:6380/0",
        "OTEL_SDK_DISABLED": "true",
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET": "1",
        "SCHEMATHESIS_MAX_EXAMPLES": "25",
        "SCHEMATHESIS_SHARD_COUNT": "8",
        "SCHEMATHESIS_SHARD_INDEX": "${{ matrix.shard }}",
    }

    aggregate = workflow["jobs"]["schemathesis-api-tests"]
    assert aggregate["if"] == "${{ always() && !cancelled() }}"
    assert aggregate["needs"] == "schemathesis-api-tests-shard"
    gate = _step(aggregate, "Require every Schemathesis shard to pass")
    assert gate["env"] == {
        "SHARD_RESULT": "${{ needs.schemathesis-api-tests-shard.result }}"
    }
    assert 'if [[ "$SHARD_RESULT" != "success" ]]' in gate["run"]
    assert 'echo "Schemathesis shard aggregate: $SHARD_RESULT"' in gate["run"]
    assert "exit 1" in gate["run"]
