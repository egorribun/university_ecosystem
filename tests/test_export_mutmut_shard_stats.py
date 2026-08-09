from __future__ import annotations

from pathlib import Path

import pytest

from scripts.export_mutmut_shard_stats import (
    _collect_selected_results,
    build_full_stats,
    build_shard_stats,
    load_selected_mutants,
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
        self.config_loaded = False
        self.status_by_exit_code = _STATUS_BY_EXIT_CODE

    def ensure_config_loaded(self) -> None:
        self.config_loaded = True

    def collect_source_file_mutation_data(
        self, *, mutant_names: list[str]
    ) -> tuple[
        list[tuple[_MutationData, str, int | None]],
        list[tuple[_MutationData, str, int | None]],
    ]:
        self.received_names = mutant_names
        return self.selected, self.unfiltered


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
