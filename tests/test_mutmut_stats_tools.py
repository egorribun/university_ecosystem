from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.merge_mutmut_stats import merge_stats


def _write_stats(
    path: Path, *, tests: dict[str, float], mapping: dict[str, list[str]]
) -> None:
    path.write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": mapping,
                "duration_by_test": tests,
                "stats_time": 1.5,
            }
        ),
        encoding="utf-8",
    )


def test_merge_mutmut_stats_unions_test_associations_and_durations(
    tmp_path: Path,
) -> None:
    first = tmp_path / "shard-0" / "mutmut-stats.json"
    second = tmp_path / "shard-1" / "mutmut-stats.json"
    first.parent.mkdir()
    second.parent.mkdir()
    _write_stats(
        first,
        tests={"tests/test_a.py::test_a": 0.25},
        mapping={"app.one.func": ["tests/test_a.py::test_a"]},
    )
    _write_stats(
        second,
        tests={"tests/test_b.py::test_b": 0.5},
        mapping={"app.one.func": ["tests/test_b.py::test_b"]},
    )

    merged = merge_stats([first, second])

    assert merged["duration_by_test"] == {
        "tests/test_a.py::test_a": 0.25,
        "tests/test_b.py::test_b": 0.5,
    }
    assert merged["tests_by_mangled_function_name"] == {
        "app.one.func": [
            "tests/test_a.py::test_a",
            "tests/test_b.py::test_b",
        ]
    }
    assert merged["stats_time"] == 3.0


def test_merge_mutmut_stats_rejects_overlapping_test_shards(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_stats(
        first,
        tests={"tests/test_shared.py::test_shared": 0.25},
        mapping={"app.one.func": ["tests/test_shared.py::test_shared"]},
    )
    _write_stats(
        second,
        tests={"tests/test_shared.py::test_shared": 0.25},
        mapping={"app.one.func": ["tests/test_shared.py::test_shared"]},
    )

    with pytest.raises(ValueError, match="appears in multiple stats shards"):
        merge_stats([first, second])
