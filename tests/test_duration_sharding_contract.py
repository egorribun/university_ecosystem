"""Fail-closed contracts for historical-duration pytest sharding."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
