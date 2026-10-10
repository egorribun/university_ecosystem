"""Fail-closed contracts for historical-duration pytest sharding."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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

    assert payload["durations"] == {
        "tests/test_executed.py": 2.5,
        "tests/test_mixed_historical.py": 9.0,
        "tests/test_mixed_new.py": 4.0,
    }
    assert payload["default_duration_seconds"] == 2.5
