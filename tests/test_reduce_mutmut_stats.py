from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.reduce_mutmut_stats import main, reduce_stats_payload


def _stats_payload() -> dict[str, object]:
    return {
        "tests_by_mangled_function_name": {
            "app.alpha.x_alpha": [
                "tests/test_alpha.py::test_slow",
                "tests/test_alpha.py::test_fast_z",
                "tests/test_alpha.py::test_fast_a",
            ],
            "app.beta.x_beta": ["tests/test_beta.py::test_beta"],
        },
        "duration_by_test": {
            "tests/test_alpha.py::test_slow": 9.0,
            "tests/test_alpha.py::test_fast_z": 0.25,
            "tests/test_alpha.py::test_fast_a": 0.25,
            "tests/test_beta.py::test_beta": 0.5,
            "tests/test_unmapped.py::test_unmapped": 100.0,
        },
        "stats_time": 109.75,
    }


def test_reducer_selects_a_deterministic_observed_subset() -> None:
    original = _stats_payload()

    reduced, audit = reduce_stats_payload(original, tests_per_function=1)

    assert reduced == {
        "tests_by_mangled_function_name": {
            "app.alpha.x_alpha": ["tests/test_alpha.py::test_fast_a"],
            "app.beta.x_beta": ["tests/test_beta.py::test_beta"],
        },
        "duration_by_test": {
            "tests/test_alpha.py::test_fast_a": 0.25,
            "tests/test_beta.py::test_beta": 0.5,
        },
        "stats_time": 109.75,
    }
    assert audit["schema_version"] == 1
    assert audit["selection_policy"] == "fastest-observed-tests-per-function"
    assert audit["tests_per_function"] == 1
    assert audit["function_count"] == 2
    assert audit["original_mapping_edges"] == 4
    assert audit["selected_mapping_edges"] == 2
    assert audit["original_test_count"] == 5
    assert audit["selected_test_count"] == 2
    assert audit["monotonic_subset"] is True
    assert audit["source_sha256"] != audit["reduced_sha256"]

    original_mapping = original["tests_by_mangled_function_name"]
    reduced_mapping = reduced["tests_by_mangled_function_name"]
    assert isinstance(original_mapping, dict)
    assert isinstance(reduced_mapping, dict)
    for function_name, selected_tests in reduced_mapping.items():
        assert set(selected_tests) <= set(original_mapping[function_name])
        assert selected_tests


def test_reducer_rejects_missing_or_empty_observed_test_mappings() -> None:
    payload = _stats_payload()
    mapping = payload["tests_by_mangled_function_name"]
    assert isinstance(mapping, dict)
    mapping["app.empty.x_empty"] = []

    with pytest.raises(ValueError, match="non-empty test list"):
        reduce_stats_payload(payload, tests_per_function=1)

    payload = _stats_payload()
    durations = payload["duration_by_test"]
    assert isinstance(durations, dict)
    del durations["tests/test_alpha.py::test_slow"]
    with pytest.raises(ValueError, match="missing duration"):
        reduce_stats_payload(payload, tests_per_function=1)


def test_reducer_cli_supports_an_atomic_in_place_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stats_path = tmp_path / "mutmut-stats.json"
    audit_path = tmp_path / "mutmut-stats-reduction.json"
    stats_path.write_text(json.dumps(_stats_payload()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reduce_mutmut_stats.py",
            "--input",
            str(stats_path),
            "--output",
            str(stats_path),
            "--audit-output",
            str(audit_path),
            "--tests-per-function",
            "1",
        ],
    )

    assert main() == 0
    reduced = json.loads(stats_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert set(reduced["duration_by_test"]) == {
        "tests/test_alpha.py::test_fast_a",
        "tests/test_beta.py::test_beta",
    }
    assert audit["selected_test_count"] == 2
    assert not list(tmp_path.glob("*.tmp"))
