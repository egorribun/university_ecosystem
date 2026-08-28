"""Fail-closed contracts for active GitHub Actions workflows."""

from __future__ import annotations

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
    assert '"$descriptor_count" -gt 128' in matrix_step["run"]
    assert "Mutation matrix capacity" in matrix_step["run"]
    assert (
        'if [ "${{ steps.mutation_scope.outputs.has_python }}" = "true" ]; then'
        in matrix_step["run"]
    )
    assert (
        'matrix_summary="Fully validated fixed plan assignments: 128"'
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
    assert "scheduler queue p50/p95" in matrix_step["run"]

    assert runners["strategy"]["max-parallel"] == 9
    assert stryker["strategy"]["max-parallel"] == 11
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
    download = _step(job, "Download Lighthouse results")
    require = _step(job, "Require Lighthouse results artifact")
    enforce = _step(job, "Enforce Lighthouse thresholds")

    assert download["continue-on-error"] is True
    assert "outcome != 'success'" in require["if"]
    assert "::error::" in require["run"]
    assert "exit 1" in require["run"]
    assert "outcome == 'success'" in enforce["if"]


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
    upload = _step(trivy, "Upload Trivy results to GitHub Security tab")
    reassert = _step(trivy, "Re-assert Trivy vulnerability gate")
    assert scan["with"]["exit-code"] == "1"
    assert scan["continue-on-error"] is True
    assert upload["continue-on-error"] is True
    assert upload["if"] == "always()"
    assert "steps.trivy_scan.outcome == 'failure'" in reassert["if"]
    assert "exit 1" in reassert["run"]

    heads = _step(jobs["alembic-migrations"], "Check single migration head (MOD-22-05)")
    assert "set -euo pipefail" in heads["run"]
    assert "uv run alembic heads" in heads["run"]
    assert "|| true" not in heads["run"]


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

    cleanup = _workflow(WORKFLOWS / "weekly-cleanup.yml")["jobs"]["cleanup"]
    missing = _step(cleanup, "Fail when required cleanup configuration is missing")
    assert "::error::" in missing["run"]
    assert "exit 1" in missing["run"]


def test_incremental_go_mutation_never_converts_tool_failure_to_success() -> None:
    job = _workflow(WORKFLOWS / "reusable-go-tests.yml")["jobs"]["test"]
    mutation = _step(job, "Run incremental mutation tests")["run"]

    assert "set -euo pipefail" in mutation
    assert 'git fetch origin "$BASE_REF_NAME" --depth=1 || true' not in mutation
    assert 'CHANGED_PATHS="$(git diff --name-only "$BASE_REF"...HEAD)"' in mutation
    assert "Unable to resolve mutation-test base revision" in mutation
    assert "no mutation-test source files were resolved" in mutation
    assert "treating this known tool panic as advisory" not in mutation
    assert 'pipeline_status=("${PIPESTATUS[@]}")' in mutation
    assert "Unable to persist go-mutesting output" in mutation


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
        in {"Detect changed Python source", "Resolve manual mutation comparison base"}
    ]

    assert len(scope_scripts) == 5
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
    gate = _step(job, "Check all jobs passed")["run"]

    assert "required_results=(" in gate
    assert 'if [[ "$result" != "success" ]]' in gate
    assert '"$res" != "success" && "$res" != "skipped"' not in gate
    assert "stryker-preflight" in job["needs"]
    assert 'assert_event_result "stryker-preflight"' in gate
    assert 'assert_event_result "stryker-aggregate"' in gate
    assert 'assert_event_result "codecov-upload"' in gate
    assert '"sbom-generate|${{ needs.sbom-generate.result }}"' in gate
    for advisory in (
        "e2e-tests-cross-browser",
        "chaos-tests",
        "db-migration-integrity",
    ):
        assert f'"{advisory}|${{{{ needs.{advisory}.result }}}}"' not in gate


def test_stryker_preflight_candidates_are_retry_safe_and_fail_closed() -> None:
    jobs = _workflow(CI)["jobs"]
    expected_pattern = (
        "frontend-mutation-preflight-${{ github.run_id }}-*-${{ github.sha }}"
    )
    expected_download = {
        "pattern": expected_pattern,
        "path": "frontend/reports/mutation/preflight-candidates",
        "merge-multiple": False,
        "if-no-artifact-found": "error",
    }
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

    for job_name in ("stryker-shards", "stryker-aggregate"):
        download = _step(
            jobs[job_name], "Download immutable same-run Stryker preflight candidates"
        )
        assert download["with"] == expected_download
        assert "name" not in download["with"]

    aggregate_shards = _step(
        jobs["stryker-aggregate"], "Download all same-run Stryker shard candidates"
    )
    assert aggregate_shards["with"] == {
        "pattern": "frontend-mutation-shard-${{ github.run_id }}-*",
        "path": "frontend/reports/mutation/external",
        "merge-multiple": False,
        "if-no-artifact-found": "error",
    }
    assert "name" not in aggregate_shards["with"]

    roundtrip = jobs["stryker-evidence-roundtrip"]
    assert _step(roundtrip, "Checkout")["with"]["persist-credentials"] is False
    assert _step(roundtrip, "Setup Node.js")["with"]["node-version"] == "24.15.0"
    assert roundtrip["env"] == {
        "STRYKER_VALIDATED_CANDIDATE_ROOT": "reports/mutation/validated-candidates"
    }
    roundtrip_download = _step(
        roundtrip, "Download immutable same-run validated Stryker evidence candidates"
    )
    assert roundtrip_download["with"] == {
        "pattern": "frontend-mutation-validated-${{ github.run_id }}-*",
        "path": "frontend/reports/mutation/validated-candidates",
        "merge-multiple": False,
        "if-no-artifact-found": "error",
    }
    assert "name" not in roundtrip_download["with"]


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
        ("ci.yml", "performance-gate", "Download Lighthouse results"),
        ("ci.yml", "docker-security-scan", "Run Trivy vulnerability scanner"),
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
            "Upload Trivy filesystem scan results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy config scan results",
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
        ("reusable-e2e-tests.yml", "e2e", "${{ inputs.advisory }}")
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
    reassert = _step(job, "Re-assert Trivy filesystem and configuration gates")

    for scan, scan_id in ((filesystem, "trivy_fs"), (configuration, "trivy_config")):
        assert scan["id"] == scan_id
        assert scan["continue-on-error"] is True
        assert scan["with"]["exit-code"] == "1"
    assert reassert["if"] == "always()"
    assert reassert["env"] == {
        "FILESYSTEM_OUTCOME": "${{ steps.trivy_fs.outcome }}",
        "CONFIGURATION_OUTCOME": "${{ steps.trivy_config.outcome }}",
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
