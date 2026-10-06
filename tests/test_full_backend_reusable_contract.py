from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
NIGHTLY = WORKFLOWS / "nightly-full-gate.yml"
MANUAL = WORKFLOWS / "manual-mutation-evidence.yml"
FULL_BACKEND = WORKFLOWS / "reusable-full-backend-mutation.yml"
HELM = WORKFLOWS / "reusable-helm-dependencies.yml"
BASELINE = ROOT / "tests" / "fixtures" / "full-backend-reusable-baseline.v1.yaml"
REQUIRED_CONTEXTS = {"CI Success", "Coverage & Quality Policy Gate"}


def _baseline() -> dict[str, object]:
    value = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert value["schema"] == "full-backend-reusable-baseline-v1"
    return value


def _digest(value: object) -> str:
    rendered = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return __import__("hashlib").sha256(rendered.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _on(workflow: dict[str, object]) -> dict[str, object]:
    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def _jobs(workflow: dict[str, object]) -> dict[str, dict[str, object]]:
    value = workflow.get("jobs")
    assert isinstance(value, dict)
    return value


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    value = job.get("steps")
    assert isinstance(value, list)
    return value


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    return next(step for step in _steps(job) if step.get("name") == name)


def _python_guard(step: dict[str, object]) -> str:
    run = step["run"]
    assert isinstance(run, str)
    match = re.fullmatch(r"python3 - <<'PY'\n(?P<program>.*)\nPY\n?", run, re.DOTALL)
    assert match is not None
    return match.group("program")


def _run_python_guard(
    program: str,
    environment: dict[str, str],
    *,
    omit_job_context: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str]:
    with tempfile.TemporaryDirectory(prefix="workflow-provenance-") as temp_dir:
        output_path = Path(temp_dir) / "github-output"
        output_path.write_text("", encoding="utf-8")
        safe_environment = {
            key: value
            for key, value in os.environ.items()
            if key.casefold() in {"path", "systemroot", "windir", "temp", "tmp"}
        }
        safe_environment.update(environment)
        safe_environment["GITHUB_OUTPUT"] = str(output_path)
        if omit_job_context:
            safe_environment.pop("JOB_CONTEXT_JSON", None)
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", program],
            check=False,
            capture_output=True,
            text=True,
            env=safe_environment,
        )
        return result, output_path.read_text(encoding="utf-8")


def _job_context(
    reusable_path: str,
    source_sha: str,
    *,
    repository: str = "egorribun/university_ecosystem",
) -> dict[str, object]:
    return {
        "workflow_ref": (f"{repository}/{reusable_path}@refs/heads/egorribun"),
        "workflow_sha": source_sha,
        "workflow_file_path": reusable_path,
        "status": "in_progress",
    }


def _base_environment(
    reusable_path: str,
    *,
    source_sha: str = "a" * 40,
    github_sha: str | None = None,
    repository: str = "egorribun/university_ecosystem",
) -> dict[str, str]:
    caller_path = ".github/workflows/manual-mutation-evidence.yml"
    return {
        "SOURCE_SHA": source_sha,
        "GITHUB_SHA_VALUE": source_sha if github_sha is None else github_sha,
        "GITHUB_REF_VALUE": "refs/heads/egorribun",
        "GITHUB_EVENT_NAME_VALUE": "workflow_dispatch",
        "GITHUB_REPOSITORY_VALUE": repository,
        "GITHUB_WORKFLOW_REF_VALUE": (
            f"{repository}/{caller_path}@refs/heads/egorribun"
        ),
        "GITHUB_WORKFLOW_SHA_VALUE": source_sha,
        "JOB_CONTEXT_JSON": json.dumps(
            _job_context(reusable_path, source_sha, repository=repository)
        ),
        "RUN_ID_VALUE": "777001",
        "RUN_ATTEMPT_VALUE": "2",
    }


def _run_provenance_guard(
    helm_artifact_name: str,
    *,
    source_sha: str = "a" * 40,
    github_sha: str | None = None,
    run_id: str = "777001",
    run_attempt: str = "2",
    job_context_json: str | None = None,
    omit_job_context: bool = False,
    repository: str = "egorribun/university_ecosystem",
) -> tuple[subprocess.CompletedProcess[str], str]:
    verify = _step(
        _jobs(_load(FULL_BACKEND))["verify-full-mutation-provenance"],
        "Validate caller, reusable source, and same-run Helm artifact",
    )
    environment = _base_environment(
        ".github/workflows/reusable-full-backend-mutation.yml",
        source_sha=source_sha,
        github_sha=github_sha,
        repository=repository,
    )
    environment["HELM_ARTIFACT_NAME"] = helm_artifact_name
    environment["RUN_ID_VALUE"] = run_id
    environment["RUN_ATTEMPT_VALUE"] = run_attempt
    if job_context_json is not None:
        environment["JOB_CONTEXT_JSON"] = job_context_json
    return _run_python_guard(
        _python_guard(verify), environment, omit_job_context=omit_job_context
    )


def _run_helm_provenance_guard(
    *,
    source_sha: str = "a" * 40,
    github_sha: str | None = None,
    job_context_json: str | None = None,
    omit_job_context: bool = False,
    repository: str = "egorribun/university_ecosystem",
) -> tuple[subprocess.CompletedProcess[str], str]:
    verify = _step(
        _jobs(_load(HELM))["produce"],
        "Verify Helm producer caller and source provenance",
    )
    environment = _base_environment(
        ".github/workflows/reusable-helm-dependencies.yml",
        source_sha=source_sha,
        github_sha=github_sha,
        repository=repository,
    )
    environment["GITHUB_EVENT_NAME_VALUE"] = "workflow_dispatch"
    if job_context_json is not None:
        environment["JOB_CONTEXT_JSON"] = job_context_json
    return _run_python_guard(
        _python_guard(verify), environment, omit_job_context=omit_job_context
    )


def _frontend_job_ids() -> tuple[str, ...]:
    return (
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
        "frontend-mutation-tests-full",
        "frontend-mutation-roundtrip",
    )


def _manual_frontend_job_ids() -> tuple[str, ...]:
    return (
        "manual-frontend-mutation-preflight",
        "manual-frontend-mutation-shards",
        "manual-frontend-mutation-aggregate",
        "manual-frontend-mutation-roundtrip",
    )


def test_full_backend_is_a_trusted_reusable_workflow_with_same_run_artifacts() -> None:
    workflow = _load(FULL_BACKEND)
    call = _on(workflow)["workflow_call"]
    assert set(_on(workflow)) == {"workflow_call"}
    assert set(call["inputs"]) == {"source_sha", "helm_artifact_name"}
    assert call["inputs"]["source_sha"]["required"] is True
    assert call["inputs"]["helm_artifact_name"]["required"] is True

    jobs = _jobs(workflow)
    assert set(jobs) == {
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
        "mutation-tests-full-aggregate",
    }
    verify = jobs["verify-full-mutation-provenance"]
    verify_script = _step(
        verify, "Validate caller, reusable source, and same-run Helm artifact"
    )["run"]
    verify_step = _step(
        verify, "Validate caller, reusable source, and same-run Helm artifact"
    )
    assert verify_step["env"]["JOB_CONTEXT_JSON"] == "${{ toJSON(job) }}"
    assert "${{ job.workflow_" not in verify_script
    assert 'json.loads(required_env("JOB_CONTEXT_JSON"))' in verify_script
    assert 'job_context.get("workflow_ref")' in verify_script
    assert 'job_context.get("workflow_sha")' in verify_script
    assert 'job_context.get("workflow_file_path")' in verify_script
    assert "nightly-full-gate.yml@refs/heads/main" in verify_script
    assert "manual-mutation-evidence.yml@refs/heads/egorribun" in verify_script
    assert "pull_request" not in verify_script
    assert 'if repository != "egorribun/university_ecosystem":' in verify_script
    assert 'expected_prefix = f"{helm_artifact_prefix}{run_id}-"' in verify_script
    assert "int(producer_attempt) > int(run_attempt)" in verify_script

    stats = jobs["mutation-tests-full-stats"]
    plan = jobs["mutation-tests-full-plan"]
    execute = jobs["mutation-tests-full"]
    aggregate = jobs["mutation-tests-full-aggregate"]
    assert stats["needs"] == "verify-full-mutation-provenance"
    assert plan["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
    ]
    assert execute["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-plan",
    ]
    assert aggregate["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full",
    ]
    assert stats["strategy"]["matrix"]["stats_shard"] == list(range(8))
    assert execute["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert execute["strategy"]["max-parallel"] == 8

    for job in (stats, plan, execute, aggregate):
        for step in _steps(job):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["ref"] == "${{ github.sha }}"

    stats_upload = _step(stats, "Upload full mutmut stats shard")["with"]["name"]
    stats_download = _step(plan, "Download full mutmut stats shards")["with"]["pattern"]
    execute_upload = _step(execute, "Upload full mutation shard evidence")["with"][
        "name"
    ]
    aggregate_download = _step(aggregate, "Download full mutation shard evidence")[
        "with"
    ]["pattern"]
    for name in (stats_upload, stats_download, execute_upload, aggregate_download):
        assert (
            "${{ needs.verify-full-mutation-provenance.outputs.artifact_namespace }}"
            in name
        )
        assert "${{ github.run_id }}-${{ github.run_attempt }}" in name
    assert "expected=8" in _step(plan, "Require all full mutmut stats shards")["run"]
    assert "seq 0 7" in _step(plan, "Require all full mutmut stats shards")["run"]
    assert (
        "expected=128"
        in _step(aggregate, "Require all full mutmut execution shards")["run"]
    )
    assert (
        "seq 1 128"
        in _step(aggregate, "Require all full mutmut execution shards")["run"]
    )
    aggregate_script = _step(aggregate, "Merge and gate full mutation evidence")["run"]
    assert "scripts/merge_mutmut_cicd_stats.py" in aggregate_script
    assert "--expected-shards 128" in aggregate_script
    assert "scripts/check_mutation_score.py --min-score 100" in aggregate_script
    assert "if-no-artifact-found" not in str(
        _step(aggregate, "Download full mutation shard evidence")["with"]
    )


def test_full_backend_guard_rejects_input_sha_that_differs_from_event_sha() -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1",
        source_sha="a" * 40,
        github_sha="b" * 40,
    )
    assert result.returncode != 0
    assert output == ""


def test_helm_guard_rejects_input_sha_that_differs_from_event_sha() -> None:
    result, output = _run_helm_provenance_guard(
        source_sha="a" * 40,
        github_sha="b" * 40,
    )
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_accepts_prior_helm_attempt_from_same_run() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777001-1")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert output == (
        "artifact_namespace=manual-full\n"
        "helm_artifact_prefix=manual-full-helm-dependencies-\n"
        "workflow_path=.github/workflows/manual-mutation-evidence.yml\n"
    )


def test_provenance_guard_rejects_coherent_fork_repository() -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-2",
        repository="forker/university_ecosystem",
    )
    assert result.returncode != 0
    assert output == ""
    assert "forker" not in result.stdout + result.stderr


def test_helm_provenance_guard_rejects_coherent_fork_repository() -> None:
    result, output = _run_helm_provenance_guard(
        repository="forker/university_ecosystem"
    )
    assert result.returncode != 0
    assert output == ""
    assert "forker" not in result.stdout + result.stderr


def test_provenance_guard_rejects_future_helm_attempt() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777001-3")
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_rejects_noncanonical_attempt_integer() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777001-0001")
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_rejects_helm_artifact_from_another_run() -> None:
    result, output = _run_provenance_guard("manual-full-helm-dependencies-777002-1")
    assert result.returncode != 0
    assert output == ""


def test_provenance_guard_rejects_helm_artifact_from_another_namespace() -> None:
    result, output = _run_provenance_guard("nightly-helm-dependencies-777001-1")
    assert result.returncode != 0
    assert output == ""


@pytest.mark.parametrize(
    "context_json",
    [
        "not-json",
        "[]",
        "{}",
        json.dumps(
            {
                "workflow_ref": 4,
                "workflow_sha": "a" * 40,
                "workflow_file_path": ".github/workflows/reusable-full-backend-mutation.yml",
            }
        ),
        json.dumps(
            {
                "workflow_ref": "x",
                "workflow_sha": "a" * 40,
                "workflow_file_path": ".github/workflows/reusable-full-backend-mutation.yml",
            }
        ),
    ],
)
def test_provenance_guard_rejects_missing_malformed_or_wrong_job_context(
    context_json: str,
) -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1", job_context_json=context_json
    )
    assert result.returncode != 0
    assert output == ""
    assert "workflow_ref" not in result.stderr
    assert "workflow_sha" not in result.stderr


def test_provenance_guard_rejects_absent_job_context_without_echoing_input() -> None:
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1", omit_job_context=True
    )
    assert result.returncode != 0
    assert output == ""
    assert "JOB_CONTEXT_JSON" not in result.stderr


def test_provenance_guard_does_not_emit_unneeded_job_context_fields() -> None:
    reusable_path = ".github/workflows/reusable-full-backend-mutation.yml"
    context = _job_context(reusable_path, "a" * 40)
    context["container"] = {"id": "DO_NOT_EMIT_CONTAINER_SENTINEL"}
    context["services"] = {"db": "DO_NOT_EMIT_SERVICE_SENTINEL"}
    result, output = _run_provenance_guard(
        "manual-full-helm-dependencies-777001-1",
        job_context_json=json.dumps(context),
    )
    assert result.returncode == 0, result.stderr
    assert "DO_NOT_EMIT" not in result.stdout + result.stderr + output


def test_helm_provenance_guard_uses_closed_job_context_and_exact_attempt() -> None:
    result, output = _run_helm_provenance_guard()
    assert result.returncode == 0, result.stderr
    assert output == (
        "artifact_name=manual-full-helm-dependencies-777001-2\n"
        "artifact_prefix=manual-full-helm-dependencies-\n"
        "workflow_path=.github/workflows/manual-mutation-evidence.yml\n"
    )
    context = _job_context(".github/workflows/reusable-helm-dependencies.yml", "a" * 40)
    context.pop("workflow_sha")
    rejected, no_output = _run_helm_provenance_guard(
        job_context_json=json.dumps(context)
    )
    assert rejected.returncode != 0
    assert no_output == ""


def test_mutation_shard_artifacts_stay_attempt_exact_and_fail_closed() -> None:
    jobs = _jobs(_load(FULL_BACKEND))
    stats = jobs["mutation-tests-full-stats"]
    plan = jobs["mutation-tests-full-plan"]
    execute = jobs["mutation-tests-full"]
    aggregate = jobs["mutation-tests-full-aggregate"]

    stats_upload = _step(stats, "Upload full mutmut stats shard")["with"]["name"]
    stats_download = _step(plan, "Download full mutmut stats shards")["with"]["pattern"]
    plan_upload = next(
        step["with"]["name"]
        for step in _steps(plan)
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    plan_download = next(
        step["with"]["name"]
        for step in _steps(execute)
        if step.get("uses", "").startswith("actions/download-artifact@")
        and "mutmut-plan" in step.get("with", {}).get("name", "")
    )
    shard_upload = _step(execute, "Upload full mutation shard evidence")["with"]["name"]
    shard_download = _step(aggregate, "Download full mutation shard evidence")["with"][
        "pattern"
    ]

    for artifact_name in (
        stats_upload,
        stats_download,
        plan_upload,
        plan_download,
        shard_upload,
        shard_download,
    ):
        assert "${{ github.run_id }}" in artifact_name
        assert "${{ github.run_attempt }}" in artifact_name
    assert "current-or-earlier" not in stats_download
    assert "current-or-earlier" not in plan_download
    assert "current-or-earlier" not in shard_download

    stats_gate = _step(plan, "Require all full mutmut stats shards")["run"]
    execution_gate = _step(aggregate, "Require all full mutmut execution shards")["run"]
    assert "expected=8" in stats_gate
    assert "seq 0 7" in stats_gate
    assert "expected=128" in execution_gate
    assert "seq 1 128" in execution_gate


def test_nightly_calls_full_backend_only_from_main_nightly_events() -> None:
    workflow = _load(NIGHTLY)
    baseline = _baseline()
    triggers = _on(workflow)
    assert set(triggers) == {"schedule", "repository_dispatch"}
    assert _digest(triggers) == baseline["nightly_trigger_sha256"]
    jobs = _jobs(workflow)
    assert "workflow_dispatch" not in triggers
    assert "mutation-tests-full-stats" not in jobs
    assert "mutation-tests-full-plan" not in jobs
    assert "mutation-tests-full-aggregate" not in jobs

    helm = jobs["nightly-helm-dependencies"]
    backend = jobs["mutation-tests-full"]
    assert (
        helm["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert helm["uses"] == "./.github/workflows/reusable-helm-dependencies.yml"
    assert (
        backend["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert backend["needs"] == "nightly-helm-dependencies"
    assert backend["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    assert backend["with"] == {
        "source_sha": "${{ github.sha }}",
        "helm_artifact_name": "${{ needs.nightly-helm-dependencies.outputs.artifact_name }}",
    }
    notify_needs = jobs["notify-failure"]["needs"]
    assert "mutation-tests-full" in notify_needs
    assert not {
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full-aggregate",
    }.intersection(notify_needs)
    expected_jobs = baseline["nightly_preserved_jobs"]
    for job_id, expected_digest in expected_jobs.items():
        assert job_id in jobs
        assert _digest(jobs[job_id]) == expected_digest


def test_manual_full_backend_is_opt_in_branch_bound_and_non_required() -> None:
    workflow = _load(MANUAL)
    baseline = _baseline()
    triggers = _on(workflow)
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["backend_scope"] == {
        "description": "Choose the default incremental backend evidence or full backend evidence.",
        "required": True,
        "type": "choice",
        "default": "incremental",
        "options": ["incremental", "full"],
    }
    assert inputs["mutation_base_sha"]["required"] is False

    jobs = _jobs(workflow)
    for job_id in ("manual-mutation-stats", "manual-mutation-tests"):
        assert jobs[job_id]["if"] == "${{ inputs.backend_scope == 'incremental' }}"
    guard = jobs["manual-full-backend-scope-guard"]
    assert guard["if"] == "${{ inputs.backend_scope == 'full' }}"
    guard_script = _step(
        guard, "Verify manual full scope is the trusted egorribun workflow source"
    )["run"]
    assert '"$GITHUB_REF_VALUE" == "refs/heads/egorribun"' in guard_script
    assert '"$GITHUB_EVENT_NAME_VALUE" == "workflow_dispatch"' in guard_script
    assert '[[ "$GITHUB_WORKFLOW_SHA_VALUE" == "$GITHUB_SHA_VALUE" ]]' in guard_script
    assert (
        '[[ "$GITHUB_REPOSITORY_VALUE" == "egorribun/university_ecosystem" ]]'
        in guard_script
    )
    assert (
        '[[ "$GITHUB_WORKFLOW_REF_VALUE" == "egorribun/university_ecosystem/.github/workflows/manual-mutation-evidence.yml@refs/heads/egorribun" ]]'
        in guard_script
    )
    assert "$GITHUB_REPOSITORY_VALUE/.github" not in guard_script

    helm = jobs["manual-full-helm-dependencies"]
    backend = jobs["manual-full-backend-mutation"]
    assert helm["needs"] == "manual-full-backend-scope-guard"
    assert helm["uses"] == "./.github/workflows/reusable-helm-dependencies.yml"
    assert backend["needs"] == [
        "manual-full-backend-scope-guard",
        "manual-full-helm-dependencies",
    ]
    assert backend["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    assert backend["with"] == {
        "source_sha": "${{ github.sha }}",
        "helm_artifact_name": "${{ needs.manual-full-helm-dependencies.outputs.artifact_name }}",
    }
    for job_id in (
        "manual-full-backend-scope-guard",
        "manual-full-helm-dependencies",
        "manual-full-backend-mutation",
    ):
        assert "(non-required)" in jobs[job_id]["name"]
        assert jobs[job_id]["name"] not in REQUIRED_CONTEXTS
    expected_jobs = baseline["manual_preserved_jobs"]
    for job_id in _manual_frontend_job_ids():
        assert _digest(jobs[job_id]) == expected_jobs[job_id]


def test_helm_dependency_reusable_has_fixed_callers_and_exact_run_attempt_artifact() -> (
    None
):
    workflow = _load(HELM)
    triggers = _on(workflow)
    assert set(triggers) == {"workflow_call"}
    jobs = _jobs(workflow)
    producer = jobs["produce"]
    verify = _step(producer, "Verify Helm producer caller and source provenance")
    script = verify["run"]
    assert verify["env"]["JOB_CONTEXT_JSON"] == "${{ toJSON(job) }}"
    assert "${{ job.workflow_" not in script
    assert 'json.loads(required_env("JOB_CONTEXT_JSON"))' in script
    assert 'job_context.get("workflow_ref")' in script
    assert 'job_context.get("workflow_sha")' in script
    assert 'job_context.get("workflow_file_path")' in script
    assert "nightly-full-gate.yml@refs/heads/main" in script
    assert 'if repository != "egorribun/university_ecosystem":' in script
    assert "manual-mutation-evidence.yml@refs/heads/egorribun" in script
    assert "pull_request" not in script
    upload = _step(producer, "Upload verified Helm dependency artifact")
    assert upload["with"]["name"] == "${{ steps.verify.outputs.artifact_name }}"
    artifact_script = _step(
        producer, "Verify Helm producer caller and source provenance"
    )["run"]
    assert (
        'artifact_name = f"{artifact_prefix}{run_id}-{run_attempt}"' in artifact_script
    )
    checkout = next(
        step
        for step in _steps(producer)
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"


def test_extraction_preserves_nightly_nonmutation_quality_lanes_and_manual_frontend() -> (
    None
):
    baseline = _baseline()
    nightly = _jobs(_load(NIGHTLY))
    expected_nightly = baseline["nightly_preserved_jobs"]
    for job_id, expected_digest in expected_nightly.items():
        assert job_id in nightly
        assert _digest(nightly[job_id]) == expected_digest

    manual = _jobs(_load(MANUAL))
    expected_manual = baseline["manual_preserved_jobs"]
    for job_id in ("manual-mutation-stats", "manual-mutation-tests"):
        actual = dict(manual[job_id])
        actual.pop("if")
        assert _digest(actual) == expected_manual[job_id]
    for job_id in _manual_frontend_job_ids():
        assert _digest(manual[job_id]) == expected_manual[job_id]


def test_full_backend_execution_steps_match_original_except_reusable_boundaries() -> (
    None
):
    baseline = _baseline()
    reusable = _jobs(_load(FULL_BACKEND))
    expected_jobs = baseline["full_mutation_steps"]
    for job_id, expected in expected_jobs.items():
        job = reusable[job_id]
        assert job["timeout-minutes"] == expected["timeout_minutes"]
        assert _digest(job.get("strategy")) == expected["strategy_sha256"]
        expected_names = expected["step_names"]
        steps_by_name = {step.get("name"): step for step in _steps(job)}
        assert set(expected_names) <= set(steps_by_name)
        pairs = sorted(
            (name, steps_by_name[name].get("run")) for name in expected_names
        )
        assert _digest(pairs) == expected["sha256"]


def test_reusable_helm_consumer_uses_same_run_verified_artifact_before_build() -> None:
    reusable = _jobs(_load(FULL_BACKEND))
    provenance = _step(
        reusable["verify-full-mutation-provenance"],
        "Validate caller, reusable source, and same-run Helm artifact",
    )["run"]
    assert 'expected_prefix = f"{helm_artifact_prefix}{run_id}-"' in provenance
    assert "int(producer_attempt) > int(run_attempt)" in provenance

    for job_id in ("mutation-tests-full-stats", "mutation-tests-full"):
        job = reusable[job_id]
        names = [step.get("name") for step in _steps(job)]
        selector = _step(job, "Select same-run Helm dependency artifact")["run"]
        assert "select_same_run_artifact_cli.py" in selector
        assert '"${{ github.run_id }}"' in selector
        assert '"${{ github.run_attempt }}"' in selector
        assert (
            '"${{ needs.verify-full-mutation-provenance.outputs.workflow_path }}"'
            in selector
        )
        assert (
            '"${{ needs.verify-full-mutation-provenance.outputs.helm_artifact_prefix }}"'
            in selector
        )
        assert "--attempt-policy current-or-earlier" in selector
        download = _step(job, "Download same-run Helm dependency artifact")
        assert (
            download["with"]["artifact-ids"]
            == "${{ steps.select_nightly_helm.outputs.artifact_id }}"
        )
        restore_index = names.index("Restore verified Helm dependency archives")
        build_index = names.index("Resolve Helm chart dependencies")
        assert (
            names.index("Download same-run Helm dependency artifact")
            < restore_index
            < build_index
        )
        restore = _step(job, "Restore verified Helm dependency archives")["run"]
        assert "helm_dependency_artifact.py restore" in restore
        assert "--producer-attempt-policy at-or-before" in restore
        assert '"$GITHUB_WORKSPACE" charts/university-ecosystem/charts' in restore
        helm = _step(job, "Resolve Helm chart dependencies")["run"]
        assert "--skip-refresh" in helm
        assert "helm dependency build" not in helm


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
