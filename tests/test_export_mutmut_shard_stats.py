from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import export_mutmut_shard_stats as shard_stats
from scripts.export_mutmut_shard_stats import (
    _collect_all_results,
    _collect_selected_results,
    build_full_stats,
    build_shard_stats,
    load_selected_mutants,
    prepare_exact_execution_plan,
    verify_exact_execution,
    verify_exact_execution_plan,
)

_STATUS_BY_EXIT_CODE = {
    None: "not checked",
    -11: "segfault",
    0: "survived",
    1: "killed",
    2: "check was interrupted by user",
    33: "no tests",
    34: "skipped",
    36: "timeout",
    37: "caught by type check",
}


class _MutationData:
    def __init__(self, exit_code_by_key: dict[str, int | None]) -> None:
        self.exit_code_by_key = exit_code_by_key


class _FakeMutmut:
    def __init__(
        self,
        selected: list[tuple[_MutationData, str, int | None]],
        unfiltered: list[tuple[_MutationData, str, int | None]],
    ) -> None:
        self.selected = selected
        self.unfiltered = unfiltered
        self.received_names: list[str] | None = None
        self.received_name_calls: list[list[str]] = []
        self.config_loaded = False
        self.Config = SimpleNamespace(ensure_loaded=self._ensure_config_loaded)
        self.status_by_exit_code = _STATUS_BY_EXIT_CODE

    def _ensure_config_loaded(self) -> None:
        self.config_loaded = True

    def collect_source_file_mutation_data(
        self, *, mutant_names: list[str]
    ) -> tuple[
        list[tuple[_MutationData, str, int | None]],
        list[tuple[_MutationData, str, int | None]],
    ]:
        self.received_names = mutant_names
        self.received_name_calls.append(mutant_names)
        if mutant_names:
            return self.selected, self.unfiltered
        return [*self.selected, *self.unfiltered], []


def test_build_shard_stats_counts_only_exactly_selected_mutants() -> None:
    first = _MutationData(
        {
            "app.first.killed__mutmut_1": 1,
            "app.first.not_selected__mutmut_1": None,
        }
    )
    second = _MutationData(
        {
            "app.second.type_checked__mutmut_1": 37,
            "app.second.survived__mutmut_1": 0,
            "app.second.not_selected__mutmut_1": 36,
        }
    )
    fake_mutmut = _FakeMutmut(
        [
            (first, "app.first.killed__mutmut_1", 1),
            (second, "app.second.type_checked__mutmut_1", 37),
            (second, "app.second.survived__mutmut_1", 0),
        ],
        [
            (first, "app.first.not_selected__mutmut_1", None),
            (second, "app.second.not_selected__mutmut_1", 36),
        ],
    )
    selected_names = [
        "app.first.killed__mutmut_1",
        "app.second.type_checked__mutmut_1",
        "app.second.survived__mutmut_1",
    ]

    selected_results, status_by_exit_code = _collect_selected_results(
        selected_names, fake_mutmut
    )
    assert fake_mutmut.config_loaded is True
    assert fake_mutmut.received_names == selected_names
    assert fake_mutmut.received_name_calls == [selected_names]

    stats = build_shard_stats(selected_names, selected_results, status_by_exit_code)

    assert stats == {
        "killed": 1,
        "survived": 1,
        "total": 3,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
        "caught_by_type_check": 1,
    }


def test_verify_exact_execution_requires_every_selected_mutant_to_finish() -> None:
    selected_names = [
        "app.first.killed__mutmut_1",
        "app.second.pending__mutmut_1",
    ]

    with pytest.raises(ValueError, match="selected mutants were not executed"):
        verify_exact_execution(
            selected_names,
            [
                ("app.first.killed__mutmut_1", 1),
                ("app.second.pending__mutmut_1", None),
            ],
        )


def test_verify_exact_execution_rejects_execution_outside_the_selected_shard() -> None:
    selected_names = ["app.first.killed__mutmut_1"]

    with pytest.raises(ValueError, match="executed unselected mutants"):
        verify_exact_execution(
            selected_names,
            [
                ("app.first.killed__mutmut_1", 1),
                ("app.second.outside_shard__mutmut_1", 0),
            ],
        )


def test_collect_all_results_reads_the_complete_mutation_metadata() -> None:
    first = _MutationData({"app.first.killed__mutmut_1": 1})
    second = _MutationData({"app.second.pending__mutmut_1": None})
    fake_mutmut = _FakeMutmut(
        [(first, "app.first.killed__mutmut_1", 1)],
        [(second, "app.second.pending__mutmut_1", None)],
    )

    assert _collect_all_results(fake_mutmut) == [
        ("app.first.killed__mutmut_1", 1),
        ("app.second.pending__mutmut_1", None),
    ]
    assert fake_mutmut.received_name_calls == [[]]


def test_execution_plan_proves_a_pristine_exact_shard_completed() -> None:
    selected_names = [
        "app.first.killed__mutmut_1",
        "app.second.type_checked__mutmut_1",
    ]
    plan = prepare_exact_execution_plan(
        selected_names,
        [
            ("app.first.killed__mutmut_1", None),
            ("app.second.type_checked__mutmut_1", None),
            ("app.third.unselected__mutmut_1", None),
        ],
    )

    selected_results, proof = verify_exact_execution_plan(
        selected_names,
        [
            ("app.first.killed__mutmut_1", 1),
            ("app.second.type_checked__mutmut_1", 37),
            ("app.third.unselected__mutmut_1", None),
        ],
        plan,
    )

    assert selected_results == [
        ("app.first.killed__mutmut_1", 1),
        ("app.second.type_checked__mutmut_1", 37),
    ]
    assert proof["schema_version"] == 1
    assert proof["selected_count"] == 2
    assert proof["universe_count"] == 3
    assert proof["completed_selected_count"] == 2
    assert proof["completed_unselected_count"] == 0
    assert proof["selected_manifest"] == "selected-mutants.json"
    assert proof["selected_results_manifest"] == "selected-results.json"


def test_write_exact_execution_evidence_records_sorted_ids_and_terminal_outcomes(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "mutmut-exact-evidence"
    shard_stats.write_exact_execution_evidence(
        evidence_dir,
        [
            "app.zeta.survived__mutmut_1",
            "app.alpha.killed__mutmut_1",
        ],
        [
            ("app.zeta.survived__mutmut_1", 0),
            ("app.alpha.killed__mutmut_1", 1),
        ],
        _STATUS_BY_EXIT_CODE,
    )

    selected_manifest = json.loads(
        (evidence_dir / "selected-mutants.json").read_text(encoding="utf-8")
    )
    results_manifest = json.loads(
        (evidence_dir / "selected-results.json").read_text(encoding="utf-8")
    )

    assert selected_manifest["selected_count"] == 2
    assert selected_manifest["selected_mutants"] == [
        "app.alpha.killed__mutmut_1",
        "app.zeta.survived__mutmut_1",
    ]
    assert results_manifest["selected_count"] == 2
    assert results_manifest["selected_results"] == [
        {
            "exit_code": 1,
            "mutant_name": "app.alpha.killed__mutmut_1",
            "status": "killed",
        },
        {
            "exit_code": 0,
            "mutant_name": "app.zeta.survived__mutmut_1",
            "status": "survived",
        },
    ]


def test_incomplete_execution_evidence_records_partial_outcomes_and_exit_codes(
    tmp_path: Path,
) -> None:
    selected_names = [
        "app.alpha.killed__mutmut_1",
        "app.beta.pending__mutmut_1",
    ]
    plan = prepare_exact_execution_plan(
        selected_names,
        [
            ("app.alpha.killed__mutmut_1", None),
            ("app.beta.pending__mutmut_1", None),
            ("app.unselected.pending__mutmut_1", None),
        ],
    )
    evidence_dir = tmp_path / "mutmut-exact-evidence"

    proof = shard_stats.write_incomplete_exact_execution_evidence(
        evidence_dir,
        selected_names,
        [
            ("app.alpha.killed__mutmut_1", 1),
            ("app.beta.pending__mutmut_1", None),
            ("app.unselected.pending__mutmut_1", None),
        ],
        _STATUS_BY_EXIT_CODE,
        plan,
        mutation_exit_code=124,
        tee_exit_code=0,
        failure_exit_code=124,
        failure_reason="mutmut timeout",
    )

    results_manifest = json.loads(
        (evidence_dir / "selected-results.json").read_text(encoding="utf-8")
    )

    assert results_manifest["execution_complete"] is False
    assert results_manifest["selected_results"] == [
        {
            "exit_code": 1,
            "mutant_name": "app.alpha.killed__mutmut_1",
            "status": "killed",
            "terminal": True,
        },
        {
            "exit_code": None,
            "mutant_name": "app.beta.pending__mutmut_1",
            "status": "not checked",
            "terminal": False,
        },
    ]
    assert proof["execution_complete"] is False
    assert proof["mutation_exit_code"] == 124
    assert proof["tee_exit_code"] == 0
    assert proof["failure_exit_code"] == 124
    assert proof["failure_reason"] == "mutmut timeout"
    assert proof["completed_selected_count"] == 1
    assert proof["incomplete_selected_count"] == 1
    assert proof["selected_results_manifest"] == "selected-results.json"


def test_incomplete_execution_evidence_records_pre_pipeline_failure(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "mutmut-exact-evidence"
    proof = shard_stats.write_incomplete_exact_execution_evidence(
        evidence_dir,
        ["app.alpha.pending__mutmut_1"],
        None,
        {},
        {},
        mutation_exit_code=None,
        tee_exit_code=None,
        failure_exit_code=1,
        failure_reason="mutation budget helper returned an unsafe timeout value",
    )

    results_manifest = json.loads(
        (evidence_dir / "selected-results.json").read_text(encoding="utf-8")
    )

    assert results_manifest["execution_complete"] is False
    assert results_manifest["selected_results"] == [
        {
            "exit_code": None,
            "mutant_name": "app.alpha.pending__mutmut_1",
            "status": "not checked",
            "terminal": False,
        }
    ]
    assert proof["failure_exit_code"] == 1
    assert proof["failure_reason"] == (
        "mutation budget helper returned an unsafe timeout value"
    )
    assert proof["mutation_exit_code"] is None
    assert proof["tee_exit_code"] is None
    assert proof["metadata_available"] is False
    assert proof["incomplete_selected_count"] == 1


def test_execution_plan_rejects_preexisting_mutation_results() -> None:
    with pytest.raises(ValueError, match="not pristine"):
        prepare_exact_execution_plan(
            ["app.first.killed__mutmut_1"],
            [
                ("app.first.killed__mutmut_1", None),
                ("app.second.stale__mutmut_1", 1),
            ],
        )


def test_execution_plan_rejects_a_changed_mutation_universe() -> None:
    selected_names = ["app.first.killed__mutmut_1"]
    plan = prepare_exact_execution_plan(
        selected_names,
        [
            ("app.first.killed__mutmut_1", None),
            ("app.second.unselected__mutmut_1", None),
        ],
    )

    with pytest.raises(ValueError, match="universe changed"):
        verify_exact_execution_plan(
            selected_names,
            [
                ("app.first.killed__mutmut_1", 1),
                ("app.third.changed__mutmut_1", None),
            ],
            plan,
        )


def test_build_shard_stats_preserves_selected_not_checked_status() -> None:
    stats = build_shard_stats(
        ["app.module.pending__mutmut_1"],
        [("app.module.pending__mutmut_1", None)],
        _STATUS_BY_EXIT_CODE,
    )

    assert stats["total"] == 1
    assert sum(value for key, value in stats.items() if key != "total") == 0


def test_build_full_stats_uses_the_complete_mutmut_universe() -> None:
    first = _MutationData({"app.first.killed__mutmut_1": 1})
    second = _MutationData({"app.second.type_checked__mutmut_1": 37})
    fake_mutmut = _FakeMutmut(
        [
            (first, "app.first.killed__mutmut_1", 1),
            (second, "app.second.type_checked__mutmut_1", 37),
        ],
        [],
    )

    full_results, status_by_exit_code = _collect_selected_results([], fake_mutmut)

    assert fake_mutmut.config_loaded is True
    assert fake_mutmut.received_names == []
    assert build_full_stats(full_results, status_by_exit_code) == {
        "killed": 1,
        "survived": 0,
        "total": 2,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
        "caught_by_type_check": 1,
    }


def test_build_full_stats_rejects_an_empty_mutation_universe() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        build_full_stats([], _STATUS_BY_EXIT_CODE)


def test_build_shard_stats_rejects_missing_selected_mutant() -> None:
    with pytest.raises(ValueError, match="missing selected mutants"):
        build_shard_stats(["app.module.missing__mutmut_1"], [], _STATUS_BY_EXIT_CODE)


def test_build_shard_stats_rejects_duplicate_selected_names() -> None:
    with pytest.raises(ValueError, match="duplicate mutant names"):
        build_shard_stats(
            ["app.module.duplicate__mutmut_1", "app.module.duplicate__mutmut_1"],
            [("app.module.duplicate__mutmut_1", 1)],
            _STATUS_BY_EXIT_CODE,
        )


def test_build_shard_stats_rejects_duplicate_selected_results() -> None:
    with pytest.raises(ValueError, match="appears more than once"):
        build_shard_stats(
            ["app.module.duplicate__mutmut_1"],
            [
                ("app.module.duplicate__mutmut_1", 1),
                ("app.module.duplicate__mutmut_1", 1),
            ],
            _STATUS_BY_EXIT_CODE,
        )


def test_load_selected_mutants_rejects_glob_patterns(tmp_path: Path) -> None:
    selected_file = tmp_path / "selected.txt"
    selected_file.write_text("app.module.*\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be exact"):
        load_selected_mutants(selected_file)


def test_build_shard_stats_rejects_glob_patterns() -> None:
    with pytest.raises(ValueError, match="must be exact"):
        build_shard_stats(
            ["app.module.*"],
            [("app.module.mutant__mutmut_1", 1)],
            _STATUS_BY_EXIT_CODE,
        )
