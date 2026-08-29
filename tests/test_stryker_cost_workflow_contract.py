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


def test_historical_stryker_cost_evidence_is_same_run_bound_and_optional() -> None:
    """A retry may optimize only with a prior verified artifact from this exact run/SHA."""

    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    preflight = jobs["stryker-preflight"]
    aggregate = jobs["stryker-aggregate"]

    assert jobs["stryker-shards"]["strategy"]["max-parallel"] == 11
    assert "STRYKER_HISTORICAL_COSTS_ARTIFACT" not in preflight["env"]

    selector = _step(
        preflight, "Select immutable same-run historical Stryker cost candidate"
    )
    assert selector["id"] == "select_historical_stryker_cost"
    assert selector["shell"] == "bash"
    assert selector["env"] == {"GH_TOKEN": "${{ github.token }}"}
    selector_script = selector["run"]
    for invariant in (
        "set -euo pipefail",
        "scripts/quality/select_same_run_artifact_cli.py",
        '--artifact-prefix "frontend-mutation-historical-costs-"',
        '--artifact-suffix "${{ github.sha }}"',
        "--attempt-policy earlier",
        "--allow-empty",
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
            "frontend/reports/mutation/cost-candidates/"
            "${{ steps.select_historical_stryker_cost.outputs.artifact_name }}"
        ),
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
