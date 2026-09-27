from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import mutmut_stats_shard


def test_stats_shard_uses_isolated_runner_protocol(tmp_path, monkeypatch) -> None:
    """3.8 collection consumes a process runner, not its raw pytest harness."""
    monkeypatch.chdir(tmp_path)
    config = SimpleNamespace(
        pytest_add_cli_args_test_selection=["tests/"], process_isolation="fork"
    )
    mapped_test = "tests/test_example.py::test_contract"

    class ProcessRunner:
        def collect_stats(self, tests):
            assert tests is None
            directory = Path("mutants")
            directory.mkdir()
            (directory / "mutmut-stats.json").write_text(
                json.dumps(
                    {
                        "duration_by_test": {mapped_test: 0.25},
                        "tests_by_mangled_function_name": {"example.fn": [mapped_test]},
                    }
                ),
                encoding="utf-8",
            )

    def get_runner(max_workers):
        assert max_workers == 1
        return ProcessRunner()

    cli = SimpleNamespace(
        config=lambda: config,
        get_mutant_runner=get_runner,
        setup_source_paths=lambda: None,
        run_stats_collection=lambda runner: runner.collect_stats(None),
    )
    monkeypatch.setattr(mutmut_stats_shard, "_load_mutmut_cli", lambda: cli)
    monkeypatch.setattr(
        mutmut_stats_shard, "prepare_reused_generation", lambda cli: None
    )
    output = mutmut_stats_shard.collect_stats_shard(
        shard_id=0, num_shards=1, max_children=1, reuse_generated_universe=True
    )
    actual = json.loads(output.read_text(encoding="utf-8"))
    assert actual["duration_by_test"] == {mapped_test: 0.25}
    assert actual["tests_by_mangled_function_name"] == {"example.fn": [mapped_test]}
    assert config.pytest_add_cli_args_test_selection == ["tests/"]


def test_stats_shard_preserves_upstream_runner_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    failure = RuntimeError("runner could not establish isolation")

    def get_runner(max_workers):
        raise failure

    cli = SimpleNamespace(
        config=lambda: SimpleNamespace(
            pytest_add_cli_args_test_selection=[], process_isolation="fork"
        ),
        get_mutant_runner=get_runner,
        setup_source_paths=lambda: None,
    )
    monkeypatch.setattr(mutmut_stats_shard, "_load_mutmut_cli", lambda: cli)
    monkeypatch.setattr(
        mutmut_stats_shard, "prepare_reused_generation", lambda cli: None
    )
    with pytest.raises(RuntimeError) as raised:
        mutmut_stats_shard.collect_stats_shard(
            shard_id=0, num_shards=1, max_children=1, reuse_generated_universe=True
        )
    assert raised.value is failure
    assert not Path("mutants/mutmut-stats.json").exists()


@pytest.mark.parametrize("isolation", ["forkserver", "unknown", None])
@pytest.mark.parametrize("reuse", [False, True])
def test_stats_rejects_unsupported_isolation_before_generation(
    tmp_path, monkeypatch, isolation, reuse
) -> None:
    monkeypatch.chdir(tmp_path)
    config = SimpleNamespace(process_isolation=isolation)
    cli = SimpleNamespace(config=lambda: config)
    monkeypatch.setattr(mutmut_stats_shard, "_load_mutmut_cli", lambda: cli)
    with pytest.raises(RuntimeError, match="requires fork process isolation"):
        mutmut_stats_shard.collect_stats_shard(
            shard_id=0,
            num_shards=1,
            max_children=1,
            reuse_generated_universe=reuse,
        )
    assert config.process_isolation is isolation
    assert list(tmp_path.iterdir()) == []


def test_prepare_rejects_missing_modern_isolation_before_copy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = SimpleNamespace(config=lambda: SimpleNamespace())
    with pytest.raises(RuntimeError, match="requires fork process isolation"):
        mutmut_stats_shard._generate_mutant_universe(cli, max_children=1)
    assert list(tmp_path.iterdir()) == []
