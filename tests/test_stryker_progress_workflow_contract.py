"""Observer-only O9 diagnostic must not enter canonical mutation evidence."""

from pathlib import Path

import yaml

NIGHTLY = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "nightly-full-gate.yml"
)


def test_nightly_shard_keeps_complete_canonical_evidence_separate() -> None:
    job = yaml.safe_load(NIGHTLY.read_text(encoding="utf-8"))["jobs"][
        "frontend-mutation-shards"
    ]
    steps = job["steps"]
    fresh = next(
        step for step in steps if step.get("name") == "Run fresh nightly Stryker shard"
    )
    canonical = next(
        step
        for step in steps
        if step.get("name") == "Upload current-attempt shard evidence"
    )
    cache = next(
        step
        for step in steps
        if step.get("name") == "Cache successful nightly frontend mutation shard"
    )
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert job["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert fresh.get("id") in (None, "run_fresh_stryker")
    assert (
        fresh["if"]
        == "${{ steps.restore_nightly_stryker_shard.outputs.cache-hit != 'true' }}"
    )
    assert "STRYKER_PROGRESS_ENABLED" not in job.get("env", {})
    assert fresh["run"] == "npm run test:mutation"
    assert job["timeout-minutes"] == 270
    assert job["env"]["STRYKER_SHARD_TIMEOUT_MS"] == "15300000"
    assert cache["with"]["path"] == "frontend/reports/mutation/shards"
    assert (
        cache["if"]
        == "${{ steps.restore_nightly_stryker_shard.outputs.cache-hit != 'true' }}"
    )
    assert canonical["with"]["path"] == (
        "frontend/reports/mutation/shards/**/mutation.json\n"
        "frontend/reports/mutation/shards/**/SHARD_EVIDENCE.json\n"
    )
    assert canonical["if"] == "${{ always() }}"
    assert "progress" not in canonical["with"]["path"].lower()
    assert "heartbeat_watchdog" not in fresh["run"]
