from __future__ import annotations

import gc
import json
import weakref
from types import SimpleNamespace

import pytest

import scripts.run_mutmut_with_stats as run_module
from scripts.mutmut_stats_shard import _stats_selection_args
from scripts.run_mutmut_with_stats import run_mutmut_from_stats


def test_mutation_worker_atfork_guard_skips_dead_otel_weakmethod(
    monkeypatch,
) -> None:
    """A dead OTel weak callback must not raise from a mutation fork."""

    registered: list[dict[str, object]] = []
    monkeypatch.setattr(
        run_module.os,
        "register_at_fork",
        lambda **kwargs: registered.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(run_module, "_ATFORK_GUARD_INSTALLED", False)
    monkeypatch.setattr(run_module, "_ATFORK_ORIGINAL", None)

    run_module.install_mutation_atfork_guard()

    class Target:
        def callback(self) -> str:
            return "alive"

    target = Target()
    weak_method = weakref.WeakMethod(target.callback)
    callback = lambda: weak_method()()  # noqa: E731 - mirrors the OTel callback
    run_module.os.register_at_fork(after_in_child=callback)

    guarded = registered[0]["after_in_child"]
    assert callable(guarded)
    assert guarded() == "alive"

    del target
    gc.collect()
    assert guarded() is None

    run_module.restore_mutation_atfork_guard()


def test_mutation_worker_atfork_guard_preserves_unrelated_callbacks() -> None:
    """Callbacks without weak targets and their failures remain untouched."""

    called: list[str] = []

    def callback() -> str:
        called.append("called")
        return "result"

    guarded = run_module._guard_atfork_callback(callback)
    assert guarded is callback
    assert guarded() == "result"
    assert called == ["called"]

    def failing_callback() -> None:
        raise TypeError("unrelated callback failure")

    guarded_failure = run_module._guard_atfork_callback(failing_callback)
    with pytest.raises(TypeError, match="unrelated callback failure"):
        guarded_failure()


def test_mutation_worker_installs_atfork_guard_before_running_mutmut(
    monkeypatch,
) -> None:
    """The guard must be active before mutmut can import/collect the app."""

    events: list[str] = []
    monkeypatch.setattr(
        run_module,
        "_parse_args",
        lambda: SimpleNamespace(
            mutant_names=("app.fn__mutmut_1",),
            max_children=2,
            reuse_generated_universe=True,
        ),
    )
    monkeypatch.setattr(
        run_module,
        "install_mutation_atfork_guard",
        lambda: events.append("guard"),
    )
    monkeypatch.setattr(
        run_module,
        "run_mutmut_from_stats",
        lambda **_: events.append("run"),
    )

    run_module.main()

    assert events == ["guard", "run"]


def test_mutation_worker_guard_covers_finite_otel_reader(monkeypatch) -> None:
    """Exercise the real SDK callback shape, not only a synthetic weak method."""

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )

    registered: list[dict[str, object]] = []
    monkeypatch.setattr(
        run_module.os,
        "register_at_fork",
        lambda **kwargs: registered.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(run_module, "_ATFORK_GUARD_INSTALLED", False)
    monkeypatch.setattr(run_module, "_ATFORK_ORIGINAL", None)

    run_module.install_mutation_atfork_guard()
    reader = PeriodicExportingMetricReader(
        ConsoleMetricExporter(), export_interval_millis=60_000
    )
    provider = MeterProvider(metric_readers=[reader])
    try:
        provider.shutdown()
        assert registered
        callback = registered[0]["after_in_child"]
        assert callable(callback)
        del reader, provider
        gc.collect()
        assert callback() is None
    finally:
        run_module.restore_mutation_atfork_guard()


class _FakeListAllTestsResult:
    def __init__(self, *, ids: set[str]) -> None:
        self.ids = ids


class _FakePytestRunner:
    def list_all_tests(self) -> str:
        return "unexpected pytest collection"

    def run_forced_fail(self) -> int:
        return 1


def test_single_full_stats_shard_preserves_the_normal_mutmut_config_fingerprint() -> (
    None
):
    """The full gate must load its stats instead of invalidating them immediately."""

    assert _stats_selection_args(shard_id=0, num_shards=1) == ()
    assert _stats_selection_args(shard_id=2, num_shards=4) == (
        "--shard-id=2",
        "--num-shards=4",
    )


def _write_complete_stats(tmp_path) -> None:
    (tmp_path / "mutants").mkdir()
    (tmp_path / "mutants/mutmut-stats.json").write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": {
                    "app.fn": ["tests/test_fn.py::test_fn"]
                },
                "duration_by_test": {"tests/test_fn.py::test_fn": 0.1},
                "stats_time": 0.1,
            }
        ),
        encoding="utf-8",
    )


def test_run_mutmut_from_stats_skips_the_second_in_process_pytest_collection(
    tmp_path, monkeypatch
) -> None:
    """The clean baseline must be the first pytest invocation in this process."""

    _write_complete_stats(tmp_path)
    monkeypatch.chdir(tmp_path)
    original_list_all_tests = _FakePytestRunner.list_all_tests
    original_run_forced_fail = _FakePytestRunner.run_forced_fail
    observed: dict[str, object] = {}

    def _run(mutant_names: tuple[str, ...], max_children: int) -> None:
        observed["mutant_names"] = mutant_names
        observed["max_children"] = max_children
        observed["stats_ids"] = _FakePytestRunner().list_all_tests().ids

    fake_cli = SimpleNamespace(
        PytestRunner=_FakePytestRunner,
        ListAllTestsResult=_FakeListAllTestsResult,
        collected_test_names=lambda: {"tests/test_fn.py::test_fn"},
        _run=_run,
    )

    run_mutmut_from_stats(
        mutant_names=("app.fn__mutmut_1",), max_children=2, mutmut_cli=fake_cli
    )

    assert observed == {
        "mutant_names": ("app.fn__mutmut_1",),
        "max_children": 2,
        "stats_ids": {"tests/test_fn.py::test_fn"},
    }
    assert _FakePytestRunner.list_all_tests is original_list_all_tests
    assert _FakePytestRunner.run_forced_fail is original_run_forced_fail


def test_run_mutmut_from_stats_scopes_forced_fail_to_selected_mutant_tests(
    tmp_path, monkeypatch
) -> None:
    """Forced-fail must validate the same exact test union as the shard."""

    _write_complete_stats(tmp_path)
    monkeypatch.chdir(tmp_path)
    observed: dict[str, object] = {}

    class _Runner:
        def list_all_tests(self) -> str:
            return "unexpected pytest collection"

        def run_tests(self, *, mutant_name: str | None, tests: object) -> int:
            observed["forced_fail_tests"] = set(tests)
            observed["forced_fail_mutant_name"] = mutant_name
            return 1

        def run_forced_fail(self) -> int:
            return self.run_tests(mutant_name=None, tests=())

    original_run_forced_fail = _Runner.run_forced_fail

    def _run(mutant_names: tuple[str, ...], max_children: int) -> None:
        observed["mutant_names"] = mutant_names
        observed["max_children"] = max_children
        _Runner().run_forced_fail()

    def tests_for_mutant_names(names: tuple[str, ...]) -> set[str]:
        observed["tests_for_mutant_names_argument"] = names
        return {
            "tests/test_alpha.py::test_alpha",
            "tests/test_beta.py::test_beta",
        }

    fake_cli = SimpleNamespace(
        PytestRunner=_Runner,
        ListAllTestsResult=_FakeListAllTestsResult,
        collected_test_names=lambda: {"tests/test_fn.py::test_fn"},
        tests_for_mutant_names=tests_for_mutant_names,
        _run=_run,
    )

    run_mutmut_from_stats(
        mutant_names=("app.alpha__mutmut_1", "app.beta__mutmut_2"),
        max_children=2,
        mutmut_cli=fake_cli,
    )

    assert observed == {
        "mutant_names": ("app.alpha__mutmut_1", "app.beta__mutmut_2"),
        "max_children": 2,
        "tests_for_mutant_names_argument": (
            "app.alpha__mutmut_1",
            "app.beta__mutmut_2",
        ),
        "forced_fail_tests": {
            "tests/test_alpha.py::test_alpha",
            "tests/test_beta.py::test_beta",
        },
        "forced_fail_mutant_name": None,
    }
    assert _Runner.run_forced_fail is original_run_forced_fail


def test_run_mutmut_from_stats_preserves_mutmuts_falsy_empty_selection(
    tmp_path, monkeypatch
) -> None:
    """An empty exact selection remains mutmut's configured full-universe case."""

    _write_complete_stats(tmp_path)
    monkeypatch.chdir(tmp_path)
    observed: dict[str, object] = {}

    class _Runner:
        def list_all_tests(self) -> str:
            return "unexpected pytest collection"

        def run_tests(self, *, mutant_name: str | None, tests: object) -> int:
            observed["forced_fail_tests"] = tests
            observed["forced_fail_mutant_name"] = mutant_name
            return 1

        def run_forced_fail(self) -> int:
            return self.run_tests(mutant_name=None, tests=("unexpected",))

    def tests_for_mutant_names(names: tuple[str, ...]) -> tuple[()]:
        observed["tests_for_mutant_names_argument"] = names
        return ()

    def _run(mutant_names: tuple[str, ...], max_children: int) -> None:
        observed["mutant_names"] = mutant_names
        observed["max_children"] = max_children
        _Runner().run_forced_fail()

    fake_cli = SimpleNamespace(
        PytestRunner=_Runner,
        ListAllTestsResult=_FakeListAllTestsResult,
        collected_test_names=lambda: {"tests/test_fn.py::test_fn"},
        tests_for_mutant_names=tests_for_mutant_names,
        _run=_run,
    )

    run_mutmut_from_stats(mutant_names=(), max_children=2, mutmut_cli=fake_cli)

    assert observed == {
        "mutant_names": (),
        "max_children": 2,
        "tests_for_mutant_names_argument": (),
        "forced_fail_tests": (),
        "forced_fail_mutant_name": None,
    }


def test_run_mutmut_from_stats_rejects_a_missing_stats_artifact(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match=r"mutants/mutmut-stats\.json"):
        run_mutmut_from_stats(
            mutant_names=(), max_children=2, mutmut_cli=SimpleNamespace()
        )


def test_run_mutmut_from_stats_reuses_validated_universe_and_restores_hooks_on_error(
    tmp_path, monkeypatch
) -> None:
    """Reuse must bypass generation, load hashes, and restore every hook on failure."""

    _write_complete_stats(tmp_path)
    monkeypatch.chdir(tmp_path)
    observed: dict[str, object] = {}
    loaded_stats = object()

    def validate(cli: object) -> None:
        observed["validated_cli"] = cli

    def load_stats(cli: object) -> object:
        observed["loaded_cli"] = cli
        return loaded_stats

    monkeypatch.setattr(run_module, "validate_universe_manifest", validate)
    monkeypatch.setattr(run_module, "load_reused_generation_stats", load_stats)

    class _Runner:
        def list_all_tests(self) -> str:
            return "unexpected pytest collection"

        def run_forced_fail(self) -> int:
            return 1

    def original_copy() -> None:
        observed["copied"] = True

    def original_copy_also() -> None:
        observed["copied_also"] = True

    def original_create(max_children: int) -> object:
        observed["generated_max_children"] = max_children
        return object()

    def _run(_mutant_names: tuple[str, ...], max_children: int) -> None:
        observed["reuse_copy_result"] = fake_cli.copy_src_dir()
        observed["reuse_copy_also_result"] = fake_cli.copy_also_copy_files()
        observed["reuse_stats"] = fake_cli.create_mutants(max_children)
        raise RuntimeError("synthetic mutation failure")

    fake_cli = SimpleNamespace(
        PytestRunner=_Runner,
        ListAllTestsResult=_FakeListAllTestsResult,
        collected_test_names=lambda: {"tests/test_fn.py::test_fn"},
        _run=_run,
        copy_src_dir=original_copy,
        copy_also_copy_files=original_copy_also,
        create_mutants=original_create,
    )

    with pytest.raises(RuntimeError, match="synthetic mutation failure"):
        run_mutmut_from_stats(
            mutant_names=("app.fn__mutmut_1",),
            max_children=3,
            mutmut_cli=fake_cli,
            reuse_generated_universe=True,
        )

    assert observed["validated_cli"] is fake_cli
    assert observed["loaded_cli"] is fake_cli
    assert observed["reuse_stats"] is loaded_stats
    assert observed["reuse_copy_result"] is None
    assert observed["reuse_copy_also_result"] is None
    assert "copied" not in observed
    assert "copied_also" not in observed
    assert "generated_max_children" not in observed
    assert fake_cli.copy_src_dir is original_copy
    assert fake_cli.copy_also_copy_files is original_copy_also
    assert fake_cli.create_mutants is original_create
