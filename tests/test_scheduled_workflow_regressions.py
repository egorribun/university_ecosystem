from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from scripts.quality.generate_dashboard import main as generate_dashboard

ROOT = Path(__file__).resolve().parents[1]
QUALITY_HISTORY = ROOT / ".github" / "workflows" / "quality-history.yml"
NIGHTLY = ROOT / ".github" / "workflows" / "nightly-full-gate.yml"
FULL_BACKEND = ROOT / ".github" / "workflows" / "reusable-full-backend-mutation.yml"


def _workflow(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_quality_history_is_sha_addressed_tracked_and_idempotent() -> None:
    workflow = _workflow(QUALITY_HISTORY)
    archive = workflow["jobs"]["archive"]
    scripts = "\n".join(
        str(step.get("run", "")) for step in archive["steps"] if isinstance(step, dict)
    )

    assert 'history_path="docs/testing/quality-history/${head_sha}.json"' in scripts
    assert 'artifact_name="quality-evidence-$head_sha-attempt-$run_attempt"' in scripts
    assert '--expected-commit-sha "$head_sha"' in scripts
    assert "cmp --silent" in scripts
    assert 'echo "available=false" >> "$GITHUB_OUTPUT"' in scripts
    assert "${timestamp}-${head_sha}.json" not in scripts
    assert 'branch="automation/quality-history-${head_sha}"' in scripts
    assert "quality-history-$(date" not in scripts
    assert "gh pr list --state all" in scripts
    assert "git ls-remote --exit-code --heads" in scripts
    assert "artifacts/quality/history" not in scripts
    assert "git add docs/testing/quality-history docs/testing/dashboard.md" in scripts
    assert "git add -f" not in scripts


def test_nightly_full_mutation_uses_audited_monotonic_test_reduction() -> None:
    nightly = _workflow(NIGHTLY)
    caller = nightly["jobs"]["mutation-tests-full"]
    assert (
        caller["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert caller["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    assert caller["with"]["source_sha"] == "${{ github.sha }}"

    workflow = _workflow(FULL_BACKEND)
    plan_job = workflow["jobs"]["mutation-tests-full-plan"]
    job = workflow["jobs"]["mutation-tests-full"]
    plan_steps = plan_job["steps"]
    steps = job["steps"]
    reduction = next(
        step["run"]
        for step in plan_steps
        if step.get("name") == "Reduce full mutmut mapping to observed kill probes"
    )
    preflight = next(
        step["run"]
        for step in plan_steps
        if step.get("name") == "Plan and budget every exact full mutation shard"
    )
    run_script = next(
        step["run"]
        for step in steps
        if step.get("name") == "Plan and run exact full mutation shard"
    )
    assert "scripts/reduce_mutmut_stats.py" in reduction
    assert "--tests-per-function 2" in reduction
    assert "mutants/mutmut-stats-full.json" in reduction
    assert "mutants/mutmut-stats-reduction.json" in reduction
    assert plan_job["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
    ]
    assert job["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-plan",
    ]
    assert "nightly-helm-dependencies" not in job["needs"]
    assert "--output-directory mutants/mutmut-full-plan" in preflight
    assert "for shard in $(seq 1 128)" in preflight
    assert "scripts/mutmut_shard_budget.py" in preflight
    assert "--max-children 8" in preflight
    assert "--control-cycle-reserve-seconds 1" in preflight
    assert "--max-timeout-seconds 20970" in preflight
    assert "--metadata-startup-reserve-seconds 120" in preflight
    assert "plan-manifest.json" in preflight
    assert "cmp --silent" in run_script
    assert "scripts/plan_mutmut_shards.py" in run_script
    assert "--control-cycle-reserve-seconds 1" in run_script
    assert "--metadata-startup-reserve-seconds 120" in run_script
    assert "--max-timeout-seconds 20970" in run_script
    assert "--max-children 8" in run_script
    # The primary pass executes the stats-reduced exact shard against the
    # already validated generated universe. Full-map confirmation below must
    # use the complete mapping for each primary survivor.
    primary_run = (
        "uv run python scripts/run_mutmut_with_stats.py "
        '--reuse-generated-universe --max-children 8 "${MUTANT_NAMES[@]}"'
    )
    assert primary_run in run_script
    full_map_start = run_script.index('if [ "$survivor_count" -gt 0 ]; then')
    full_map_run = run_script[full_map_start:]
    assert "cp mutants/mutmut-stats-full.json mutants/mutmut-stats.json" in full_map_run
    assert 'for survivor in "${FULL_MAP_SURVIVORS[@]}"' in full_map_run
    assert (
        'uv run python scripts/run_mutmut_with_stats.py --max-children 2 "$survivor"'
        in full_map_run
    )
    assert "--reuse-generated-universe" not in full_map_run
    generation_selection = next(
        step["run"]
        for step in steps
        if step.get("name") == "Select retry-safe full mutmut generation base"
    )
    assert "scripts.mutmut_retry_artifacts select-universe" in generation_selection
    assert "--expected-mode generation" in generation_selection
    assert 'test "$SOURCE_REVISION" = "$COMMIT_SHA"' in generation_selection
    for binding in (
        '--source-revision "$SOURCE_REVISION"',
        '--commit-sha "$COMMIT_SHA"',
        '--run-id "$RUN_ID"',
        '--run-attempt "$RUN_ATTEMPT"',
        '--workflow "$WORKFLOW"',
        '--workflow-ref "$WORKFLOW_REF"',
        '--workflow-sha "$WORKFLOW_SHA"',
    ):
        assert binding in generation_selection
    assert "full-map-survivors.txt" in run_script
    assert '.status == "survived"' in run_script
    assert "--stats mutants/mutmut-stats-full.json" in run_script
    assert "--metadata-startup-reserve-seconds 120" in run_script
    assert "scripts/run_mutmut_with_stats.py --max-children 2" in run_script


def test_quality_dashboard_links_tracked_history_relative_to_its_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = tmp_path / "docs" / "testing" / "quality-history"
    history.mkdir(parents=True)
    commit_sha = "a" * 40
    (history / f"{commit_sha}.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-08-18T00:00:00Z",
                "commit_sha": commit_sha,
                "components": {},
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "quality-contract.json"
    contract.write_text(
        '{"policy": {}, "exclusions": [], "quarantines": []}\n',
        encoding="utf-8",
    )
    output = tmp_path / "docs" / "testing" / "dashboard.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_dashboard.py",
            "--history-dir",
            str(history),
            "--contract",
            str(contract),
            "--output",
            str(output),
        ],
    )

    assert generate_dashboard() == 0
    dashboard = output.read_text(encoding="utf-8")
    assert f"(quality-history/{commit_sha}.json)" in dashboard
    assert str(tmp_path).replace("\\", "/") not in dashboard


def test_quality_dashboard_limits_sha_named_history_by_evidence_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = tmp_path / "docs" / "testing" / "quality-history"
    history.mkdir(parents=True)
    snapshots = (
        ("f" * 40, "2026-08-01T00:00:00Z"),
        ("0" * 40, "2026-08-02T00:00:00Z"),
        ("a" * 40, "2026-08-03T00:00:00Z"),
    )
    for commit_sha, generated_at in snapshots:
        (history / f"{commit_sha}.json").write_text(
            json.dumps(
                {
                    "generated_at": generated_at,
                    "commit_sha": commit_sha,
                    "components": {},
                }
            ),
            encoding="utf-8",
        )
    contract = tmp_path / "quality-contract.json"
    contract.write_text(
        '{"policy": {}, "exclusions": [], "quarantines": []}\n',
        encoding="utf-8",
    )
    output = tmp_path / "docs" / "testing" / "dashboard.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_dashboard.py",
            "--history-dir",
            str(history),
            "--contract",
            str(contract),
            "--output",
            str(output),
            "--limit",
            "2",
        ],
    )

    assert generate_dashboard() == 0
    dashboard = output.read_text(encoding="utf-8")
    assert f"`{snapshots[0][0][:12]}`" not in dashboard
    assert f"`{snapshots[1][0][:12]}`" in dashboard
    assert f"`{snapshots[2][0][:12]}`" in dashboard
