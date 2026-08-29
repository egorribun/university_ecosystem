"""Contract for retry-safe primary CI mutmut artifact transport."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict[str, Any]:
    loaded = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_primary_ci_mutmut_chain_selects_only_complete_retry_safe_candidates() -> None:
    jobs = _workflow()["jobs"]
    stats = jobs["mutation-tests-stats"]
    universe = jobs["mutation-tests-universe"]
    incremental = jobs["mutation-tests-incremental"]

    stats_sidecar = _step(stats, "Create retry-bound mutmut stats sidecar")
    assert "scripts/mutmut_retry_artifacts.py create-stats" in stats_sidecar["run"]
    stats_upload = _step(stats, "Upload mutmut stats shard")
    assert stats_upload["with"]["name"] == (
        "mutmut-stats-shard-${{ matrix.stats_shard }}-attempt-${{ github.run_attempt }}"
    )
    assert "mutmut-stats-artifact.json" in stats_upload["with"]["path"]
    assert stats_upload["with"]["retention-days"] == 30

    stats_download = _step(universe, "Download same-run mutmut stats candidates")
    assert stats_download["with"] == {
        "pattern": "mutmut-stats-shard-*-attempt-*",
        "path": "mutmut-stats-candidates",
        "merge-multiple": False,
        "if-no-artifact-found": "error",
    }
    stats_selection = _step(universe, "Select complete retry-safe mutmut stats cohort")
    assert "scripts/mutmut_retry_artifacts.py select-stats" in stats_selection["run"]
    assert "--candidate-root" in stats_selection["run"]
    assert "mutmut-stats-selection.json" in stats_selection["run"]
    assert "! -type d" in stats_selection["run"]
    assert "select_coverage_artifacts" not in stats_selection["run"]
    universe_create = _step(universe, "Create retry-scoped mutmut universe envelope")
    assert "scripts/mutmut_retry_artifacts.py create-universe" in universe_create["run"]
    universe_upload = _step(universe, "Upload central mutmut universe")
    assert universe_upload["with"]["retention-days"] == 30

    scope = _step(incremental, "Detect changed Python source")
    universe_download = _step(
        incremental, "Download same-run mutmut universe candidates"
    )
    assert universe_download["with"] == {
        "pattern": "mutmut-universe-${{ github.run_id }}-*",
        "path": "mutmut-universe-candidates",
        "merge-multiple": False,
        "if-no-artifact-found": "error",
    }
    universe_selection = _step(incremental, "Select retry-safe central mutmut universe")
    assert (
        "scripts/mutmut_retry_artifacts.py select-universe" in universe_selection["run"]
    )
    assert "--candidate-root" in universe_selection["run"]
    assert "! -type d" in universe_selection["run"]
    assert "selected_producer_attempt" in universe_selection["run"]
    assert incremental["steps"].index(scope) < incremental["steps"].index(
        universe_download
    )
    assert incremental["steps"].index(universe_download) < incremental["steps"].index(
        universe_selection
    )
