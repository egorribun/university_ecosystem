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


def test_quality_history_publishes_artifacts_without_repository_writes() -> None:
    workflow = _workflow(QUALITY_HISTORY)
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    archive = workflow["jobs"]["archive"]
    assert archive["permissions"] == {"actions": "read", "contents": "read"}
    steps = [step for step in archive["steps"] if isinstance(step, dict)]
    scripts = "\n".join(str(step.get("run", "")) for step in steps)
    text = QUALITY_HISTORY.read_text(encoding="utf-8")

    # No repository writes: no commit, push, branch or pull request.
    assert "git push" not in text
    assert "git commit" not in text
    assert "git switch -c" not in text
    assert "gh pr create" not in text
    assert "gh pr list" not in text
    assert "contents: write" not in text
    assert "pull-requests" not in text
    assert "automation/quality-history" not in text
    assert "docs/testing/quality-history" not in text
    assert "docs/testing/dashboard.md" not in scripts
    checkout = next(
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["persist-credentials"] is False
    # Secrets-free, injection-safe run blocks: expressions go through env only.
    assert "${{" not in scripts

    # Trusted source discovery and all manifest validation remain in place.
    assert 'artifact_name="quality-evidence-$head_sha-attempt-$run_attempt"' in scripts
    assert '--expected-commit-sha "$head_sha"' in scripts
    assert "sha256sum --check" in scripts
    assert "validate_quality_contract.py" in scripts
    assert "--expected-workflow-job coverage-policy-gate" in scripts
    assert "Workflow source is not the current immutable protected-main commit" in text

    # Prior history is validated before it is merged into the render input.
    assert (
        "gh run list --workflow quality-history.yml --branch main --status success"
        in scripts
    )
    assert ".commit_sha == $sha" in scripts
    assert "cmp --silent" in scripts

    # Deterministic render, job summary and 90-day artifact.
    assert "scripts/quality/generate_dashboard.py" in scripts
    assert '--history-dir "$publish_root/quality-history"' in scripts
    assert "--limit 30" in scripts
    assert (
        'cat "$RUNNER_TEMP/quality-publish/dashboard.md" >> "$GITHUB_STEP_SUMMARY"'
        in scripts
    )
    uploads = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert (
        upload["uses"]
        == "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    )
    assert (
        "uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2"
        in text
    )
    assert upload["with"]["retention-days"] == 90
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["name"].startswith(
        "quality-history-${{ steps.collect-manifest.outputs.head_sha }}"
    )
    assert "artifacts/quality/history" not in scripts


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
