"""Fail-closed workflow contract for historical Stryker shard-cost evidence."""

from __future__ import annotations

from pathlib import Path

import yaml

CI_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    return next(
        step
        for step in job["steps"]  # type: ignore[index]
        if isinstance(step, dict) and step.get("name") == name
    )


def test_stryker_artifact_token_steps_precede_pr_code_in_all_four_jobs() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    for job_name, selected in (
        (
            "stryker-preflight",
            "Select immutable same-run historical Stryker cost candidate",
        ),
        ("stryker-shards", "Select immutable same-run Stryker preflight candidate"),
        ("stryker-aggregate", "Select immutable same-run Stryker preflight candidate"),
        (
            "stryker-evidence-roundtrip",
            "Select immutable same-run validated Stryker evidence candidate",
        ),
    ):
        steps = jobs[job_name]["steps"]
        selector = _step(jobs[job_name], selected)
        assert steps[0] is selector
        assert selector["uses"].startswith("actions/github-script@")
        assert "GH_TOKEN" not in selector.get("env", {})
        script = selector["with"]["script"]
        for identity in (
            "head_sha",
            "run_attempt",
            "workflow_run",
            "digest",
            "size_in_bytes",
        ):
            assert identity in script
        checkout_index = steps.index(_step(jobs[job_name], "Checkout"))
        npm_index = steps.index(_step(jobs[job_name], "Install frontend dependencies"))
        for index, step in enumerate(steps):
            if "github-token" in step.get("with", {}) or "API_TOKEN" in step.get(
                "env", {}
            ):
                assert index < checkout_index < npm_index
            assert "GH_TOKEN" not in step.get("env", {})


def test_stryker_artifacts_are_materialized_before_dependency_execution() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    for job_name, materializations in (
        (
            "stryker-preflight",
            ("Materialize selected historical Stryker cost without credentials",),
        ),
        (
            "stryker-shards",
            ("Materialize selected Stryker preflight without credentials",),
        ),
        (
            "stryker-aggregate",
            (
                "Materialize selected Stryker preflight without credentials",
                "Materialize same-run Stryker shards without credentials",
            ),
        ),
        (
            "stryker-evidence-roundtrip",
            ("Materialize selected Stryker evidence without credentials",),
        ),
    ):
        steps = jobs[job_name]["steps"]
        install_index = steps.index(
            _step(jobs[job_name], "Install frontend dependencies")
        )
        for name in materializations:
            materialize = _step(jobs[job_name], name)
            assert steps.index(materialize) < install_index
            script = materialize["run"]
            assert 'test ! -L "$candidate"' in script
            assert 'realpath -m -- "$dst"' in script
            assert 'test ! -L "$dst"' in script


def test_cross_run_snapshot_is_bound_to_pre_checkout_action_outputs() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    preflight = jobs["stryker-preflight"]
    steps = preflight["steps"]
    fetch = _step(preflight, "Fetch bounded cross-run Stryker timing snapshot")
    verify = _step(preflight, "Verify cross-run Stryker timing without a token")
    assert steps.index(fetch) < steps.index(_step(preflight, "Checkout"))
    assert "metadata_sha256" in fetch["with"]["script"]
    assert "cost_sha256" in fetch["with"]["script"]
    assert "preflight_sha256" in fetch["with"]["script"]
    for output in ("METADATA", "COST", "PREFLIGHT"):
        assert verify["env"][f"SNAPSHOT_{output}_SHA256"] == (
            "${{ steps.cross_run_snapshot.outputs." + output.lower() + "_sha256 }}"
        )
        assert f"--snapshot-{output.lower()}-sha256" in verify["run"]


def test_historical_stryker_cost_evidence_is_same_run_bound_and_optional() -> None:
    """A retry may optimize only with a prior verified artifact from this exact run/SHA."""

    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    preflight = jobs["stryker-preflight"]
    aggregate = jobs["stryker-aggregate"]

    max_parallel = jobs["stryker-shards"]["strategy"]["max-parallel"]
    assert 1 <= max_parallel <= 20
    assert max_parallel == 6
    assert "STRYKER_HISTORICAL_COSTS_ARTIFACT" not in preflight["env"]

    selector = _step(
        preflight, "Select immutable same-run historical Stryker cost candidate"
    )
    assert selector["id"] == "select_historical_stryker_cost"
    assert selector["uses"].startswith("actions/github-script@")
    assert selector["env"]["ARTIFACT_PREFIX"] == "frontend-mutation-historical-costs-"
    assert selector["env"]["ATTEMPT_POLICY"] == "earlier"
    assert selector["env"]["ALLOW_EMPTY"] == "true"
    selector_script = selector["with"]["script"]
    for invariant in (
        "getWorkflowRun",
        "listWorkflowRunArtifacts",
        "run.head_sha !== sourceSha",
        "item.workflow_run?.head_sha !== sourceSha",
        "item.digest",
        "item.size_in_bytes",
    ):
        assert invariant in selector_script

    download = _step(preflight, "Download selected historical Stryker cost candidate")
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["if"] == (
        "${{ steps.select_historical_stryker_cost.outputs.has_candidate == 'true' }}"
    )
    assert download["with"] == {
        "artifact-ids": "${{ steps.select_historical_stryker_cost.outputs.artifact_id }}",
        "repository": "${{ github.repository }}",
        "run-id": "${{ github.run_id }}",
        "github-token": "${{ github.token }}",
        "path": (
            "${{ runner.temp }}/stryker-same-run-cost/"
            "${{ steps.select_historical_stryker_cost.outputs.artifact_name }}"
        ),
        "digest-mismatch": "error",
    }
    assert "pattern" not in download["with"]

    historical_generation = _step(
        preflight,
        "Generate canonical immutable Stryker preflight with verified historical costs",
    )
    assert historical_generation["if"] == (
        "${{ steps.select_historical_stryker_cost.outputs.has_candidate == 'true' }}"
    )
    assert historical_generation["working-directory"] == "frontend"
    assert historical_generation["env"] == {
        "STRYKER_HISTORICAL_COSTS_ARTIFACT": (
            "${{ steps.select_historical_stryker_cost.outputs.artifact_name }}"
            "/HISTORICAL_COSTS.json"
        )
    }
    assert historical_generation["run"] == "npm run test:mutation"

    fallback_generation = _step(
        preflight, "Generate canonical immutable Stryker preflight"
    )
    assert fallback_generation["if"] == (
        "${{ steps.select_historical_stryker_cost.outputs.has_candidate != 'true' }}"
    )
    assert "env" not in fallback_generation
    assert fallback_generation["run"] == "npm run test:mutation"

    fetch = _step(preflight, "Fetch bounded cross-run Stryker timing snapshot")
    assert preflight["steps"].index(fetch) < preflight["steps"].index(
        _step(preflight, "Checkout")
    )
    assert fetch["uses"].startswith("actions/github-script@")
    assert fetch["if"] == fallback_generation["if"]
    assert fetch["env"] == {
        "API_TOKEN": "${{ github.token }}",
        "PR_BRANCH": "${{ github.event.pull_request.head.ref }}",
    }
    verify = _step(preflight, "Verify cross-run Stryker timing without a token")
    assert verify["if"] == (
        "${{ steps.cross_run_snapshot.outputs.has_candidate == 'true' }}"
    )
    assert "GH_TOKEN" not in verify.get("env", {})
    assert "API_TOKEN" not in verify.get("env", {})
    assert (
        "python3 -m scripts.quality.select_stryker_history_artifact_cli"
        in verify["run"]
    )
    assert "--offline-snapshot" in verify["run"]
    replan = _step(preflight, "Replan immutable Stryker preflight from vetted costs")
    assert (
        replan["if"] == "${{ steps.verify_cross_run.outputs.has_candidate == 'true' }}"
    )
    assert replan["env"] == {"STRYKER_PREFLIGHT_MODE": "replan"}
    assert replan["run"] == "npm run test:mutation"
    for generation_step in (historical_generation, fallback_generation, replan):
        assert "GH_TOKEN" not in generation_step.get("env", {})
        assert "API_TOKEN" not in generation_step.get("env", {})

    historical_env_steps = [
        step
        for job in (preflight, jobs["stryker-shards"], aggregate)
        for step in job["steps"]
        if isinstance(step, dict)
        and "STRYKER_HISTORICAL_COSTS_ARTIFACT" in step.get("env", {})
    ]
    assert historical_env_steps == [historical_generation]

    upload = _step(aggregate, "Upload verified historical Stryker cost model")
    assert upload["if"] == "${{ success() }}"
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"] == {
        "name": (
            "frontend-mutation-historical-costs-${{ github.run_id }}-"
            "${{ github.run_attempt }}-${{ github.sha }}"
        ),
        "path": "frontend/reports/mutation/historical-costs/HISTORICAL_COSTS.json",
        "if-no-files-found": "error",
        "overwrite": False,
        "retention-days": 30,
    }
    aggregate_steps = aggregate["steps"]
    assert aggregate_steps.index(
        _step(aggregate, "Aggregate and verify fresh frontend mutation evidence")
    ) < (aggregate_steps.index(upload))


def test_all_stryker_selectors_bind_rest_head_sha_to_pr_head_not_merge_checkout() -> (
    None
):
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    selectors = (
        (
            "stryker-preflight",
            "Select immutable same-run historical Stryker cost candidate",
        ),
        ("stryker-shards", "Select immutable same-run Stryker preflight candidate"),
        ("stryker-aggregate", "Select immutable same-run Stryker preflight candidate"),
        (
            "stryker-evidence-roundtrip",
            "Select immutable same-run validated Stryker evidence candidate",
        ),
    )
    for job_name, step_name in selectors:
        selector = _step(jobs[job_name], step_name)
        assert selector["env"]["SOURCE_SHA"] == (
            "${{ github.event.pull_request.head.sha }}"
        )
        assert selector["env"]["TESTED_SHA"] == "${{ github.sha }}"
        selector_script = selector["with"]["script"]
        assert "run.head_sha !== sourceSha" in selector_script
        assert "suffix !== testedSha" in selector_script


def test_all_stryker_jobs_persist_distinct_pr_source_and_base_identities() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    expected = {
        "STRYKER_SOURCE_HEAD_SHA": "${{ github.event.pull_request.head.sha || github.sha }}",
        "STRYKER_BASE_SHA": "${{ github.event.pull_request.base.sha || github.sha }}",
        "STRYKER_BASE_REF": "${{ github.event.pull_request.base.ref || github.ref_name }}",
    }
    for job_name in (
        "stryker-preflight",
        "stryker-shards",
        "stryker-aggregate",
        "stryker-evidence-roundtrip",
    ):
        for key, value in expected.items():
            assert jobs[job_name]["env"].get(key) == value


def test_all_ci_same_run_selectors_have_non_pr_head_sha_fallback() -> None:
    """Selectors shared by push and PR jobs must not pass an empty head SHA."""

    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    selectors = (
        ("performance-gate", "Select immutable same-run Lighthouse evidence candidate"),
        (
            "mutation-tests-incremental",
            "Select immutable same-run mutmut universe candidate",
        ),
    )
    for job_name, step_name in selectors:
        selector_script = _step(jobs[job_name], step_name)["run"]
        assert (
            '--run-head-sha "${{ github.event.pull_request.head.sha || github.sha }}"'
            in selector_script
        )


def test_singleton_downloads_use_server_selected_ids() -> None:
    """Singleton retry artifacts must not be fetched by a client-side glob."""

    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    for job_name, download_name, selector_id in (
        (
            "stryker-shards",
            "Download selected Stryker preflight candidate",
            "select_stryker_preflight",
        ),
        (
            "stryker-aggregate",
            "Download selected Stryker preflight candidate",
            "select_stryker_preflight",
        ),
        (
            "stryker-evidence-roundtrip",
            "Download selected immutable Stryker evidence candidate",
            "select_stryker_validated",
        ),
    ):
        job = jobs[job_name]
        download = _step(job, download_name)
        values = download["with"]
        assert values["artifact-ids"] == (
            f"${{{{ steps.{selector_id}.outputs.artifact_id }}}}"
        )
        assert values["repository"] == "${{ github.repository }}"
        assert values["run-id"] == "${{ github.run_id }}"
        assert values["github-token"] == "${{ github.token }}"
        assert (
            "${{ steps." + selector_id + ".outputs.artifact_name }}" in values["path"]
        )
        assert "pattern" not in values
