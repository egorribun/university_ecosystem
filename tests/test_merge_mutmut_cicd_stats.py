from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.merge_mutmut_cicd_stats import merge_stats


def _write_shard(
    root: Path,
    names: list[str],
    statuses: list[str],
    *,
    universe_names: list[str],
) -> Path:
    artifact = root / f"artifact-{len(list(root.glob('artifact-*')))}" / "mutants"
    evidence = artifact / "mutmut-exact-evidence"
    evidence.mkdir(parents=True)
    names = sorted(names)
    status_by_name = dict(zip(names, statuses, strict=True))
    status_to_field = {
        "killed": "killed",
        "survived": "survived",
        "caught by type check": "caught_by_type_check",
    }
    stats = {
        field: 0
        for field in (
            "killed",
            "survived",
            "total",
            "no_tests",
            "skipped",
            "suspicious",
            "timeout",
            "check_was_interrupted_by_user",
            "segfault",
            "caught_by_type_check",
        )
    }
    stats["total"] = len(names)
    records = []
    for index, name in enumerate(names, start=1):
        status = status_by_name[name]
        stats[status_to_field[status]] += 1
        records.append({"mutant_name": name, "exit_code": index, "status": status})

    def digest_names(values: list[str]) -> str:
        import hashlib

        return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()

    def digest_records(values: list[dict[str, object]]) -> str:
        import hashlib

        canonical = "\n".join(
            f"{item['mutant_name']}\t{item['exit_code']}\t{item['status']}"
            for item in values
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    selection_digest = digest_names(names)
    universe_digest = digest_names(universe_names)
    (artifact / "mutmut-cicd-stats.json").write_text(
        json.dumps(stats), encoding="utf-8"
    )
    (evidence / "selected-mutants.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selection_sha256": selection_digest,
                "selected_count": len(names),
                "selected_mutants": names,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "selected-results.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selection_sha256": selection_digest,
                "selected_count": len(names),
                "selected_results_sha256": digest_records(records),
                "selected_results": records,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "execution-proof.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selection_sha256": selection_digest,
                "selected_count": len(names),
                "universe_sha256": universe_digest,
                "universe_count": len(universe_names),
                "completed_selected_count": len(names),
                "completed_unselected_count": 0,
            }
        ),
        encoding="utf-8",
    )
    return artifact / "mutmut-cicd-stats.json"


def test_merge_stats_requires_complete_disjoint_universe(tmp_path: Path) -> None:
    universe = ["app.a__mutmut_1", "app.b__mutmut_1", "app.c__mutmut_1"]
    first = _write_shard(
        tmp_path,
        universe[:2],
        ["killed", "caught by type check"],
        universe_names=universe,
    )
    second = _write_shard(tmp_path, universe[2:], ["killed"], universe_names=universe)

    merged = merge_stats([first, second], expected_shards=2)

    assert merged["total"] == 3
    assert merged["killed"] == 2
    assert merged["caught_by_type_check"] == 1
    assert merged["survived"] == 0
    assert merged["universe_count"] == 3


def test_merge_stats_rejects_overlap(tmp_path: Path) -> None:
    universe = ["app.a__mutmut_1", "app.b__mutmut_1"]
    first = _write_shard(tmp_path, universe[:1], ["killed"], universe_names=universe)
    second = _write_shard(
        tmp_path, universe, ["killed", "killed"], universe_names=universe
    )

    with pytest.raises(ValueError, match="overlap"):
        merge_stats([first, second], expected_shards=2)


def test_merge_stats_rejects_missing_universe_member(tmp_path: Path) -> None:
    universe = ["app.a__mutmut_1", "app.b__mutmut_1", "app.c__mutmut_1"]
    first = _write_shard(tmp_path, universe[:1], ["killed"], universe_names=universe)
    second = _write_shard(
        tmp_path, universe[1:2], ["survived"], universe_names=universe
    )

    with pytest.raises(ValueError, match="complete universe"):
        merge_stats([first, second], expected_shards=2)


def test_merge_stats_rejects_incomplete_result_evidence(tmp_path: Path) -> None:
    universe = ["app.a__mutmut_1"]
    shard = _write_shard(tmp_path, universe, ["killed"], universe_names=universe)
    results_path = shard.parent / "mutmut-exact-evidence" / "selected-results.json"
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    payload["selected_results"][0]["status"] = "not checked"
    results_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        merge_stats([shard], expected_shards=1)
