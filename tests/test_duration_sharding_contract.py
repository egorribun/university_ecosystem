"""Fail-closed contracts for historical-duration pytest sharding."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from scripts.quality.update_test_durations import build_duration_payload
from tests import conftest as project_conftest


class _ShardConfig:
    def getoption(self, name: str) -> int:
        return {"--shard-id": 0, "--num-shards": 2}[name]


def test_duration_sharding_rejects_a_malformed_history_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "test-durations.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(project_conftest, "PROJECT_ROOT", tmp_path)
    items = [SimpleNamespace(fspath=tmp_path / "tests" / "test_example.py")]

    with pytest.raises(pytest.UsageError, match="historical test durations"):
        project_conftest.pytest_collection_modifyitems(_ShardConfig(), items)


def test_duration_sharding_rejects_duplicate_history_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "test-durations.json").write_text(
        '{"durations": {}, "durations": {}}', encoding="utf-8"
    )
    monkeypatch.setattr(project_conftest, "PROJECT_ROOT", tmp_path)
    items = [SimpleNamespace(fspath=tmp_path / "tests" / "test_example.py")]

    with pytest.raises(pytest.UsageError, match="duplicate key"):
        project_conftest.pytest_collection_modifyitems(_ShardConfig(), items)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"durations": []},
        {"durations": {"tests/test_example.py": True}},
        {"durations": {"tests/test_example.py": -1}},
        {"default_duration_seconds": "slow", "durations": {}},
    ],
)
def test_duration_sharding_rejects_invalid_history_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "test-durations.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(project_conftest, "PROJECT_ROOT", tmp_path)
    items = [SimpleNamespace(fspath=tmp_path / "tests" / "test_example.py")]

    with pytest.raises(pytest.UsageError, match="historical test durations"):
        project_conftest.pytest_collection_modifyitems(_ShardConfig(), items)


def test_duration_merge_omits_new_all_skipped_files_and_preserves_history(
    tmp_path: Path,
) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        """<testsuite>
          <testcase file="tests/test_new_skipped.py" time="0.001"><skipped /></testcase>
          <testcase file="tests/test_historical_skipped.py" time="0.001"><skipped /></testcase>
        </testsuite>""",
        encoding="utf-8",
    )

    payload = build_duration_payload(
        report,
        existing={
            "default_duration_seconds": 3.0,
            "durations": {
                "tests/test_historical_skipped.py": 8.5,
                "tests/test_not_in_report.py": 4.0,
            },
        },
    )

    assert payload["durations"] == {
        "tests/test_historical_skipped.py": 8.5,
        "tests/test_not_in_report.py": 4.0,
    }
    assert payload["default_duration_seconds"] == 3.0


def test_duration_merge_keeps_executed_and_mixed_file_estimates(
    tmp_path: Path,
) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        """<testsuite>
          <testcase file="tests/test_executed.py" time="2.5" />
          <testcase file="tests/test_mixed_new.py" time="4.0" />
          <testcase file="tests/test_mixed_new.py" time="0.001"><skipped /></testcase>
          <testcase file="tests/test_mixed_historical.py" time="1.0" />
          <testcase file="tests/test_mixed_historical.py" time="0.001"><skipped /></testcase>
        </testsuite>""",
        encoding="utf-8",
    )

    payload = build_duration_payload(
        report,
        existing={
            "default_duration_seconds": 3.0,
            "durations": {"tests/test_mixed_historical.py": 9.0},
        },
    )

    # A file with an executed case takes its measured total, so the skipped
    # case's bookkeeping time is included and the stale 9.0 s value is replaced.
    assert payload["durations"] == {
        "tests/test_executed.py": 2.5,
        "tests/test_mixed_historical.py": 1.001,
        "tests/test_mixed_new.py": 4.001,
    }
    assert payload["default_duration_seconds"] == 2.5


def test_duration_merge_replaces_stale_history_when_a_case_is_skipped(
    tmp_path: Path,
) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        """<testsuite>
          <testcase file="tests/test_verify_like.py" time="700.0" />
          <testcase file="tests/test_verify_like.py" time="0.002"><skipped /></testcase>
        </testsuite>""",
        encoding="utf-8",
    )

    payload = build_duration_payload(
        report,
        existing={"durations": {"tests/test_verify_like.py": 13.429}},
    )

    assert payload["durations"] == {"tests/test_verify_like.py": 700.002}


def test_planned_estimates_price_unknown_files_per_item() -> None:
    known = [SimpleNamespace(), SimpleNamespace()]
    unknown = [SimpleNamespace() for _ in range(5)]
    file_to_items = {
        "tests/test_known.py": known,  # 10 s over 2 items -> 5 s per item
        "tests/test_unknown.py": unknown,
    }

    estimates = dict(
        project_conftest._planned_file_durations(
            file_to_items,
            {"tests/test_known.py": 10.0},
        )
    )

    assert estimates == {
        "tests/test_known.py": 10.0,
        "tests/test_unknown.py": 25.0,
    }


def test_planned_estimates_fall_back_to_one_second_per_item_without_history() -> None:
    file_to_items = {"tests/test_unknown.py": [SimpleNamespace(), SimpleNamespace()]}

    estimates = dict(project_conftest._planned_file_durations(file_to_items, {}))

    assert estimates == {"tests/test_unknown.py": 2.0}


def test_xdist_auto_worker_count_uses_logical_cpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: 4, raising=False)

    assert (
        project_conftest.pytest_xdist_auto_num_workers(config=cast(pytest.Config, None))
        == 4
    )


def test_xdist_auto_worker_count_falls_back_to_affinity_then_cpu_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: None, raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: {0, 1}, raising=False)

    assert project_conftest._logical_cpu_budget() == 2

    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: None)

    assert project_conftest._logical_cpu_budget() == 1
