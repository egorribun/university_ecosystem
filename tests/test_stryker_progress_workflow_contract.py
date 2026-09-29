"""Observer-only O9 diagnostic must not enter canonical mutation evidence."""

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def test_fresh_shard_only_uploads_separate_information_after_attempt() -> None:
    job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["stryker-shards"]
    steps = job["steps"]
    prepare = next(
        step
        for step in steps
        if step.get("name") == "Prepare progress diagnostic export"
    )
    fresh = next(
        step for step in steps if step.get("name") == "Run fresh Stryker shard"
    )
    upload = next(
        step
        for step in steps
        if step.get("name") == "Upload current-attempt progress diagnostic"
    )
    canonical = next(
        step
        for step in steps
        if step.get("name") == "Upload current-attempt shard evidence"
    )
    cache = next(
        step
        for step in steps
        if step.get("name") == "Cache successful frontend mutation shard"
    )
    assert fresh["id"] == "run_fresh_stryker"
    assert (
        fresh["if"] == "${{ steps.restore_stryker_shard.outputs.cache-hit != 'true' }}"
    )
    assert prepare["id"] == "prepare_progress_export"
    assert prepare["if"] == fresh["if"]
    assert prepare["continue-on-error"] is True
    assert "mktemp -d" in prepare["run"]
    assert "$RUNNER_TEMP" in prepare["run"]
    assert steps.index(prepare) < steps.index(fresh)
    assert fresh["env"] == {
        "STRYKER_PROGRESS_ENABLED": "1",
        "STRYKER_PROGRESS_EXPORT_DIRECTORY": "${{ steps.prepare_progress_export.outputs.directory }}",
    }
    assert fresh["run"] == "npm run test:mutation"
    assert "STRYKER_PROGRESS_ENABLED" not in job["env"]
    assert "STRYKER_PROGRESS_ENABLED" not in next(
        step
        for step in steps
        if step.get("name") == "Validate immutable Stryker preflight before execution"
    ).get("env", {})
    assert steps.index(fresh) < steps.index(upload)
    assert steps.index(upload) < steps.index(cache)
    assert (
        upload["if"]
        == "${{ always() && steps.prepare_progress_export.outputs.directory != '' && steps.run_fresh_stryker.outputs.progress_diagnostic == 'published' && (steps.run_fresh_stryker.outcome == 'success' || steps.run_fresh_stryker.outcome == 'failure' || steps.run_fresh_stryker.outcome == 'cancelled') }}"
    )
    assert upload["uses"] == canonical["uses"]
    assert upload["with"] == {
        "name": "frontend-mutation-progress-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}-${{ matrix.shard-index }}",
        "path": "${{ steps.prepare_progress_export.outputs.directory }}/diagnostic.json",
        "if-no-files-found": "warn",
        "overwrite": False,
        "retention-days": 7,
    }
    assert upload["continue-on-error"] is True
    assert job["timeout-minutes"] == 270
    assert job["env"]["STRYKER_SHARD_TIMEOUT_MS"] == "15300000"
    assert cache["with"]["path"] == "frontend/reports/mutation/shards"
    assert (
        cache["if"] == "${{ steps.restore_stryker_shard.outputs.cache-hit != 'true' }}"
    )
    assert canonical["with"]["path"] == (
        "frontend/reports/mutation/shards/**/mutation.json\n"
        "frontend/reports/mutation/shards/**/SHARD_EVIDENCE.json\n"
    )
    assert "heartbeat_watchdog" not in fresh["run"]
